from typing import Dict


class MockLogObject(object):
    """
    Mock log object
    """

    def __init__(self, severity_threshold="INFO"):
        self.__expectations = set([])
        self._called_references = []
        self._log_records = []
        self._severity_threshold = severity_threshold
        self.logged_messages = []

    def write_log(
        self,
        log_reference="UTI9999",
        error_list=None,
        log_row_dict=None,
        severity_threshold_override=None,
        process_name=None,
    ):
        """
        Dummy write log just keeps a list of the logReferences
        """
        log_row_dict = dict(log_row_dict) if log_row_dict else {}
        self.logged_messages.append((log_reference, log_row_dict))
        log_record = {
            "logReference": log_reference,
            "errorList": error_list,
            "logRowDict": log_row_dict,
            "severityThresholdOverried": severity_threshold_override,
            "processName": process_name,
        }
        self._log_records.append(log_record)

        self._called_references.append(log_reference)

        if log_reference in self.__expectations:
            self.__expectations.remove(log_reference)

    def was_logged(self, log_reference):
        """
        Was a particular log reference logged?
        """
        return log_reference in self._called_references

    def was_value_logged(self, log_reference, key, expected_value):
        """
        Was a particular log key supplied as expected
        """
        for log_record in self.log_records:
            if log_record["logReference"] == log_reference:
                # Deliberately done like this so that if there are multiple logReferences that are the same with
                # different value.
                match = expected_value == log_record["logRowDict"][key]
                if match:
                    return True
        return False

    def was_value_not_logged(self, log_reference, key, expected_value):
        """
        Was a particular log key not supplied as expected
        """
        for log_record in self.log_records:
            if log_record["logReference"] == log_reference:
                # Deliberately done like this so that if there are multiple logReferences that are the same with
                # different value.
                match = expected_value == log_record["logRowDict"][key]
                if match:
                    return False
        return True

    def logged_value_occurrences(self, log_reference, key, expected_value):
        """
        Return the number of occurrences of a particular key and value
        """
        occurrences = 0
        for log_record in self.log_records:
            if log_record["logReference"] == log_reference:
                # Deliberately done like this so that if there are multiple logReferences that are the same with
                # different value.
                match = expected_value == log_record["logRowDict"][key]
                if match:
                    occurrences += 1
        return occurrences

    def was_multiple_value_logged(self, log_reference: str, key_values: Dict):
        """
        Was a particular log key supplied as expected with the expected values
        """
        for log_record in self.log_records:
            found_count = 0
            if log_record["logReference"] == log_reference:
                for key in key_values:
                    if log_record["logRowDict"][key] == key_values[key]:
                        found_count += 1
                if found_count == len(key_values):
                    return True
        return False

    def get_logged_value(self, log_reference, key):
        """
        Get logged value for given reference and key
        """
        for log_record in self.log_records:
            if log_record["logReference"] == log_reference:
                return log_record["logRowDict"][key]

    def get_log_occurrences(self, log_reference):
        """
        Gets a list of the args that were passed each time a specified message was logged
        """
        return [args for reference, args in self.logged_messages if reference == log_reference]

    def log_occurrence_count(self, log_reference):
        """
        Returns the number of times a logReference was logged.
        """
        return len(self.get_log_occurrences(log_reference))

    def add_expected_reference(self, expected_reference):
        """
        set the expected reference
        """
        self.__expectations.add(expected_reference)

    def expectations_satisfied(self):
        """
        has the expected log line been written
        """
        return len(self.__expectations) == 0

    def clear_expectations(self):
        """
        clear expectations
        """
        self.__expectations = set([])

    def clear(self):
        """
        Clear everything
        """
        self.__expectations = set([])
        self._called_references = []
        self._log_records = []
        self.logged_messages = []

    @property
    def called_references(self):
        """
        The called references
        """
        return self._called_references

    @called_references.setter
    def called_references(self, new_called_references):
        """
        Setter
        """
        self._called_references = new_called_references

    @property
    def log_records(self):
        """
        The logRecords
        """
        return self._log_records

    @property
    def severity_threshold(self):
        """
        The severity threshold (ref logging.py _SEVERITY_INPUT_MAP)
        """
        return self._severity_threshold
