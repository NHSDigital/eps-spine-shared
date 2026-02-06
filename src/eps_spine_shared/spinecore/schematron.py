from abc import ABCMeta, abstractmethod

from eps_spine_shared.errors import EpsBusinessError, ErrorBaseInstance, ErrorBaseRegistry
from eps_spine_shared.nhsfundamentals.time_utilities import date_today_as_string
from eps_spine_shared.spinecore.xml_utilities import apply_transform_catch_error, unescape_string

_FORWARDSLASH = "/"
_BACKSLASH = "\\"
_ESCAPED_BACKSLASH = "\\\\"
_TRIPLE_STAR = "***"
_ESCAPED_TRIPLE_STAR = "\\*\\*\\*"
_TRIPLE_PLUS = "+++"
_ESCAPED_TRIPLE_PLUS = "\\+\\+\\+"

_PIPE = "|"
_ESCAPED_PIPE = "\\-\\-\\-"

_FAULT = "fault"
_WARNING = "warning"
_BEGIN_BLOCK = "BEGIN-BLOCK"
_END_BLOCK = "END-BLOCK"
_BEGIN_LIST_ENTRY = "BEGIN-LIST-ENTRY"
_END_LIST_ENTRY = "END-LIST-ENTRY"
_FAULT_CONTEXT_START = "["


def schematron_escape(val):
    """
    Escape the input to the schematron process
    """
    if val is None:
        return None

    val = str(val)

    if val.isspace():
        return val

    # Escaping for our private tokenisation scheme
    val = val.replace(_BACKSLASH, _ESCAPED_BACKSLASH)
    val = val.replace(_TRIPLE_STAR, _ESCAPED_TRIPLE_STAR)
    val = val.replace(_TRIPLE_PLUS, _ESCAPED_TRIPLE_PLUS)
    val = val.replace(_PIPE, _ESCAPED_PIPE)
    return val


def schematron_unescape(val):
    """
    Unescape the input from the schematron process
    """
    if val is None:
        return None

    val = str(val)

    if val.isspace():
        return val

    # Unescaping for our private tokenisation scheme
    val = val.replace(_ESCAPED_PIPE, _PIPE)
    val = val.replace(_ESCAPED_TRIPLE_PLUS, _TRIPLE_PLUS)
    val = val.replace(_ESCAPED_TRIPLE_STAR, _TRIPLE_STAR)
    val = val.replace(_ESCAPED_BACKSLASH, _BACKSLASH)

    return val


class _AbstractSchematronApplier(object):
    """
    Class which uses schematron to validate an incoming request and extract a message dictionary from it
    """

    __metaclass__ = ABCMeta

    def __init__(self, schematron_xslt, internal_id, log_object):
        self._schematron_xslt = schematron_xslt
        self._internal_id = internal_id
        self._log_object = log_object

    def apply_schematron(self, request):
        """
        Applies the schematron_xslt to the given request, returning a dictionary of
        extracted message variables. Any faults found in the schematron output are
        raised as SchematronError instances
        """
        [output_dictionary, fault_list] = self.apply_schematron_returning_fault_list(request)
        if fault_list:
            raise EpsBusinessError(fault_list[0])

        return output_dictionary

    def apply_schematron_returning_fault_list(self, request):
        """
        Applies the schematron_xslt to the given request, returning a dictionary of
        extracted message variables
        """
        schematron_output = self._apply_xslt(request)
        return self._parse_schematron_output(schematron_output)

    def _apply_xslt(self, request):
        """
        Applies the schematron to the request to return validation output
        Returns:
            schematronOutput: the Schematron output
        """
        tree = apply_transform_catch_error(
            self._log_object, self._internal_id, self._schematron_xslt, request
        )
        return str(tree).splitlines()

    def _parse_schematron_output(self, schematron_output):
        """
        Parses the schematron output to create a dictionary with the reported values
        """
        output_dictionary = {}
        fault_list = []

        element_generator = self._element_generator(schematron_output)
        for element_list in element_generator:
            if element_list[0] == _FAULT:
                fault = element_list[1:]
                error_base_instance = self._make_error_base_instance(fault)
                self._log_object.write_log(
                    "PUP0027a",
                    None,
                    {
                        "internalID": self._internal_id,
                        "errorCode": error_base_instance.error_code,
                        "faultText": "|".join(fault),
                    },
                )
                fault_list.append(error_base_instance)
            elif element_list[0] == _WARNING:
                fault = element_list[1:]
                error_base_instance = self._make_error_base_instance(fault)
                self._log_object.write_log(
                    "PUP0027b",
                    None,
                    {"internalID": self._internal_id, "errorCode": error_base_instance.error_code},
                )
                # fault_list.append(error_base_instance)
            elif element_list[0] == _BEGIN_BLOCK:
                action = element_list[1]
                block_path = element_list[2]
                self._add_block(action, block_path, output_dictionary, element_generator)
            elif element_list[0] == _BEGIN_LIST_ENTRY:
                action = element_list[1]
                list_path = element_list[2]
                self._add_list_entry(action, list_path, output_dictionary, element_generator)
            else:
                action = element_list[0]
                path = element_list[1]
                value = element_list[2]
                self._add_entry(action, path, value, output_dictionary)

        return [output_dictionary, fault_list]

    def _make_error_base_instance(self, fault):
        """
        Construct an error base instance from the schematron fault
        """
        [error_base_field, error_context, supplementary_info] = self._parse_fault(fault)
        error_base_entry = ErrorBaseRegistry.get_error_field(error_base_field)
        if error_base_entry.allow_supplementary_info and supplementary_info:  # noqa: SIM108
            error_base_instance = ErrorBaseInstance(error_base_entry, *supplementary_info)
        else:
            error_base_instance = ErrorBaseInstance(error_base_entry)

        error_base_instance.error_context = error_context

        return error_base_instance

    @staticmethod
    def _parse_fault(fault):
        """
        Parses a fault list to return the errorBaseField, errorContext (if present)
        and supplementary information (if present)

        fault[0] is either 'ErrorBaseClass.ERROR_BASE_ENTRY'
                 or 'ErrorBaseClass.ERROR_BASE_ENTRY[errorContext]'
        fault[1:], if present, is the supplementary information
        """
        split = fault[0].split(_FAULT_CONTEXT_START)
        error_base_field = split[0]

        # Trim trailing ']'
        error_context = split[1][:-1] if len(split) > 1 else None

        supplementary_info = fault[1:] if len(fault) > 1 else None

        return [error_base_field, error_context, supplementary_info]

    @abstractmethod
    def _add_entry(self, action, path, value, output_dictionary):
        """
        Adds an entry to the output dictionary
        """
        pass

    @abstractmethod
    def _find_list(self, action, list_path, output_dictionary):
        """
        Finds the list for the given action and listPath. This implementation always creates
        a new list since each entry added to an action results in a new entry in the action's
        list. The implementation in SimpleReportSchematronApplier returns the existing list,
        if there is one.
        """
        pass

    def _add_list_entry(self, action, list_path, output_dictionary, element_generator):
        """
        Parses the schematron output for an entry to be added to an unordered list
        """
        list_entry_dictionary = self._parse_block(element_generator, _END_LIST_ENTRY)
        target_list = self._find_list(action, list_path, output_dictionary)
        target_list.append(list_entry_dictionary)

    @staticmethod
    def _create_list_path(base_list_path, list_entry_counter):
        """
        Appends the listEntryCounter to the baseListPath to create the path at which
        the new list item will be stored
        """
        return base_list_path + _FORWARDSLASH + str(list_entry_counter)

    def _add_block(self, action, block_path, output_dictionary, element_generator):
        """
        Parses the schematron output for a block entry (multiple lines to be grouped
        in a single extract - i.e. a structure)
        """
        block_dictionary = self._parse_block(element_generator, _END_BLOCK)
        self._add_entry(action, block_path, block_dictionary, output_dictionary)

    def _parse_block(self, element_generator, block_terminator):
        """
        Parses the schematron output for a block entry (multiple lines to be grouped
        in a single extract - i.e. a structure) terminated by the given terminator. Used
        for the construction of both block entries and list entries
        """
        block_ended = False
        block_dictionary = {}
        while not block_ended:
            element_list = next(element_generator)
            if element_list[0] == block_terminator:
                block_ended = True
            elif element_list[0] == _BEGIN_BLOCK:
                action = element_list[1]
                block_path = element_list[2]
                self._add_block(action, block_path, block_dictionary, element_generator)
            elif element_list[0] == _BEGIN_LIST_ENTRY:
                action = element_list[1]
                list_path = element_list[2]
                self._add_list_entry(action, list_path, block_dictionary, element_generator)
            else:
                path = element_list[0]
                value = unescape_string(element_list[1])
                self._add_to_dictionary(path, value, block_dictionary)
        return block_dictionary

    @staticmethod
    def _find_or_create_action_list(action, output_dictionary):
        """
        Finds the entry for the given action, creating it if it doesn't yet exist
        """
        if action not in output_dictionary:
            output_dictionary[action] = []

        return output_dictionary[action]

    def _add_to_dictionary(self, path, value, dictionary):
        """
        Adds the given value to the dictionary at the path specified. The path may contain
        forward-slashes, which are interpreted as sub-elements in the path to add entries
        to a dictionary within a dictionary
        """
        split_path = path.split(_FORWARDSLASH, 1)

        if len(split_path) > 1:
            if split_path[0] not in dictionary:
                dictionary[split_path[0]] = {}
            self._add_to_dictionary(split_path[1], value, dictionary[split_path[0]])
        else:
            dictionary[split_path[0]] = value

    @staticmethod
    def _element_generator(schematron_output):
        """
        Generator to allow iteration across the schematron output
        """
        reading_multiline_content = False
        content_close_token = None
        content_complete = False
        content = ""
        for line in schematron_output:
            if line.find("P1R1_SUBSTITUTE_DATE") > 0:
                # Handle the P1R1 nullFlavor="UNK" date formats
                line = line.replace("P1R1_SUBSTITUTE_DATE", date_today_as_string())  # noqa: PLW2901
            if reading_multiline_content:
                content = "{0}\n{1}".format(content, line)
                if content.endswith(content_close_token):
                    content_complete = True
                    reading_multiline_content = False
            elif line.startswith(_TRIPLE_STAR):
                line = line[3:]  # noqa: PLW2901 - Strip the leading ***
                element_list = line.split(_PIPE)
                content = element_list[-1]
                if content.endswith(_TRIPLE_STAR):
                    content_complete = True
                else:
                    reading_multiline_content = True
                    content_complete = False
                    content_close_token = _TRIPLE_STAR
            elif line.startswith(_TRIPLE_PLUS):
                line = line[3:]  # noqa: PLW2901 - Strip the leading +++
                element_list = line.split(
                    _PIPE,
                )
                content = element_list[-1]
                if content.endswith(_TRIPLE_PLUS):
                    content_complete = True
                else:
                    reading_multiline_content = True
                    content_complete = False
                    content_close_token = _TRIPLE_PLUS

            if content_complete:
                element_list[-1] = schematron_unescape(content[:-3])
                yield element_list
                content_complete = False


class MultiActionSchematronApplier(_AbstractSchematronApplier):
    """
    A schematron applier which supports multiple report actions (instead of just 'report and 'fault').
    The output dictionary is keyed by action, with each action having a list of extracts. This enables
    multiple reports for the same action and path key to be present.
    """

    def __init__(self, schematron_xslt, supported_actions, internal_id, log_object):
        super(MultiActionSchematronApplier, self).__init__(schematron_xslt, internal_id, log_object)
        self._supported_actions = supported_actions

    def _add_entry(self, action, path, value, output_dictionary):
        """
        Adds an entry to the output dictionary
        """
        if action in self._supported_actions:
            action_dictionary = {}
            self._add_to_dictionary(path, value, action_dictionary)
            action_list = self._find_or_create_action_list(action, output_dictionary)
            action_list.append(action_dictionary)
        elif action != "":
            self._log_object.write_log(
                "PUP0051", None, dict({"internalID": self._internalID, "element": action})
            )

    def _find_list(self, action, list_path, output_dictionary):
        """
        Finds the list for the given action and listPath. This implementation always creates
        a new list since each entry added to an action results in a new entry in the action's
        list. The implementation in SimpleReportSchematronApplier returns the existing list,
        if there is one.
        """
        target_list = []
        self._add_entry(action, list_path, target_list, output_dictionary)
        return target_list


class SimpleReportSchematronApplier(_AbstractSchematronApplier):
    """
    Class which produces an output dictionary containing the extract from Schematron
    without the entries being contained in lists keyed on action. i.e. instead of
    {'report':[{'key1':'value1'}, {'key2':'value2'}]} it will produce
    {'key1':'value1', 'key2':'value2'}
    """

    def _add_entry(self, action, path, value, output_dictionary):
        """
        Adds an entry to the output dictionary
        """
        if action == "report":
            self._add_to_dictionary(path, value, output_dictionary)
        elif action != "":
            self._log_object.write_log(
                "PUP0051", None, dict({"internalID": self._internal_id, "element": action})
            )

    def _find_list(self, action, list_path, output_dictionary):
        """
        Finds the list for the given action and listPath. If not found, a new list is created.
        """
        target_list = self._find_entry(action, list_path, output_dictionary)
        if not target_list:
            target_list = []
            self._add_entry(action, list_path, target_list, output_dictionary)

        return target_list

    def _find_entry(self, action, path, output_dictionary):
        """
        Finds the existing entry at a given path within an action
        """
        if action != "report":
            return None

        return self._find_within_dictionary(path, output_dictionary)

    def _find_within_dictionary(self, path, dictionary):
        """
        Finds the entry at the given path within the dictionary. Forward slashes in the
        path are interpreted as sub-elements within the path to look in a dictionary
        within the parent dictionary
        """
        split_path = path.split(_FORWARDSLASH, 1)

        if len(split_path) > 1:
            if split_path[0] not in dictionary:
                return None
            self._find_within_dictionary(split_path[1], dictionary[split_path[0]])
        else:
            return dictionary.get(split_path[0])
