import abc
import importlib
from enum import Enum
from http import HTTPStatus as httplib

from botocore.exceptions import NoCredentialsError

from eps_spine_shared.spinecore.base_utilities import handle_encoding_oddities

CODESYSTEM_1634 = "2.16.840.1.113883.2.1.3.2.4.16.34"


class EpsNoCredentialsErrorWithRetry(NoCredentialsError):
    """
    Extends NoCredentialsError to provide information about retry attempts.
    To be caught in Spine application code and re-raised as NoCredentialsErrorWithRetry.
    """

    fmt = "Unable to locate credentials after {attempts} attempts"


class EpsSystemError(Exception):
    """
    Exception to be raised if an unexpected system error occurs.
    To be caught in Spine application code and re-raised as SpineSystemError.
    """

    MESSAGE_FAILURE = "messageFailure"
    DEVELOPMENT_FAILURE = "developmentFailure"
    SYSTEM_FAILURE = "systemFailure"
    IMMEDIATE_REQUEUE = "immediateRequeue"
    RETRY_EXPIRED = "retryExpired"
    PUBLISHER_HANDLES_REQUEUE = "publisherHandlesRequeue"
    UNRELIABLE_MESSAGE = "unreliableMessage"

    def __init__(self, error_topic, *args):  # noqa: B042
        """
        error_topic is the topic to be used when writing the WDO to the error exchange
        """
        super(EpsSystemError, self).__init__(*args)
        self.error_topic = error_topic


class EpsBusinessError(Exception):
    """
    Exception to be raised by a message worker if an expected error condition is hit,
    one that is expected to cause a HL7 error response with a set errorCode.
    To be caught in Spine application code and re-raised as SpineBusinessError.
    """

    def __init__(self, error_code, supp_info=None, message_id=None):  # noqa: B042
        super(EpsBusinessError, self).__init__()
        self.error_code = error_code
        self.supplementary_information = supp_info
        self.message_id = message_id

    def __str__(self):
        if self.supplementary_information:
            return "{} {}".format(self.error_code, self.supplementary_information)
        return str(self.error_code)


class EpsErrorBase(Enum):
    """
    To be used in Spine application code to remap to ErrorBases.
    """

    INVALID_LINE_STATE_TRANSITION = 1
    ITEM_NOT_FOUND = 2
    MAX_REPEAT_MISMATCH = 3
    NOT_CANCELLED_EXPIRED = 4
    NOT_CANCELLED_CANCELLED = 5
    NOT_CANCELLED_NOT_DISPENSED = 6
    NOT_CANCELLED_DISPENSED = 7
    NOT_CANCELLED_WITH_DISPENSER = 8
    NOT_CANCELLED_WITH_DISPENSER_ACTIVE = 9
    PRESCRIPTION_NOT_FOUND = 10
    EXISTS_WITH_NEXT_ACTIVITY_PURGE = 11
    DUPLICATE_PRESRIPTION = 12


class EpsValidationError(Exception):
    """
    Exception to be raised by validation functions.
    Must be passed supplementary information to be appended to error response text.
    """

    def __init__(self, supplementary_info):
        """
        Add supplementary information
        """
        super(EpsValidationError, self).__init__(supplementary_info)
        self.supp_info = supplementary_info


class ErrorBaseInstance(object):
    """
    Allow an instance of an error_base_entry object to be created.  This is required should
    there be a need to add supplementary information (which cannot be stored in the static
    class)
    """

    WARNING = "WG"
    ERROR = "ER"

    def __init__(self, error_base_entry, *supplementary_information):
        self.error_base_entry = error_base_entry
        self.supplementary_information = supplementary_information
        self.errorContext = None

    @property
    def error_code(self):
        """
        Error code
        """
        return self.error_base_entry.error_code

    @property
    def error_level(self):
        """
        Error level
        """
        return self.error_base_entry.error_level

    @property
    def error_type(self):
        """
        Error type
        """
        return self.error_base_entry.error_type

    @property
    def code_system(self):
        """
        Error code system
        """
        return self.error_base_entry.code_system

    @property
    def status_code(self):
        """
        HTTP error code
        """
        return self.error_base_entry.status_code

    @property
    def type(self):
        """
        HTTP error code
        """
        return self.error_base_entry.type

    @property
    def description(self):
        """
        Description
        """
        if self.error_base_entry.allow_supplementary_info and self.supplementary_information:
            try:
                return self.error_base_entry.description.format(*self.supplementary_information)
            except UnicodeEncodeError:
                decoded_information = []
                for item in self.supplementary_information:
                    decoded_information.append(handle_encoding_oddities(item))
                return self.error_base_entry.description.format(*decoded_information)
        else:
            return self.error_base_entry.description

    @property
    def ebxml_error_code(self):
        """
        ebXml error code
        """
        return self.error_base_entry.ebxml_error_code

    @property
    def soap_value(self):
        """
        SOAP value
        """
        return self.error_base_entry.soap_value

    @property
    def p1r1_error_code(self):
        """
        P1R1 error code
        """
        if hasattr(self.error_base_entry, "p1r1_error_code"):
            return self.error_base_entry.p1r1_error_code
        return None

    @property
    def ack_type_code(self):
        """
        Ack type code
        """
        if hasattr(self.error_base_entry, "ack_type_code"):
            return self.error_base_entry.ack_type_code
        return None

    @property
    def parent(self):
        """
        Parent error
        """
        return self.error_base_entry.parent

    def __str__(self):
        return self.description

    def eq_error_base_entry(self, other):
        """
        errorBaseEntry is a singleton, do object level comparison to determine if an identical errorBaseEntry.
        Cannot use the errorCode as SUPP info has the same code
        """
        if isinstance(other, AbstractErrorBaseEntry):
            return (
                self.error_code == other.error_code
                and self.error_base_entry.allow_supplementary_info == other.allow_supplementary_info
            )
        elif isinstance(other, ErrorBaseInstance):
            return (
                self.error_code == other.error_code
                and self.error_base_entry.allow_supplementary_info
                == other.error_base_entry.allow_supplementary_info
            )
        return False


class ErrorBaseRegistry(object):
    """
    Registry of all error bases
    """

    _ERROR_MODULE_LOOKUP = {}

    @classmethod
    def register_error_base(cls, errorbase):
        """
        Register an error base
        """
        cls._ERROR_MODULE_LOOKUP[errorbase.__name__] = errorbase.__module__

    @classmethod
    def get_error_field(cls, class_field):
        """
        Return a reference to a static field given a module and qualified field name
        """
        [class_name, field_name] = class_field.split(".")

        module_name = cls._ERROR_MODULE_LOOKUP[class_name]
        module = importlib.import_module(module_name)

        clazz = getattr(module, class_name)
        return getattr(clazz, field_name)


class AbstractErrorBaseEntry(object):
    """
    Abstract base class for all error base entries
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, code_system, error_code, description, allow_supplementary_info, error_level):
        self.code_system = code_system
        self.error_code = error_code
        self.description = description
        self.allow_supplementary_info = allow_supplementary_info
        self.error_level = error_level

    @property
    @abc.abstractmethod
    def error_type(self):
        """
        Error type
        """
        pass

    @property
    def status_code(self):
        """
        Error type
        """
        return httplib.OK

    def __str__(self):
        return self.description

    def __eq__(self, other):
        return self.error_code == getattr(other, "error_code", None)


class AbstractHL7ErrorBaseEntry(AbstractErrorBaseEntry):
    """
    Abstract base class for all HL7 error base entries
    """

    __metaclass__ = abc.ABCMeta

    ERROR_TYPE = "HL7"

    # refactor to condense input arguments. JIRA SPII-24325

    def __init__(
        self,
        code_system,
        error_code,
        description,
        allow_supplementary_info,
        error_level,
        parent,
        ack_type_code,
        p1r1_error_code,
    ):
        super(AbstractHL7ErrorBaseEntry, self).__init__(
            code_system, error_code, description, allow_supplementary_info, error_level
        )
        self.parent = parent
        self.ack_type_code = ack_type_code
        self.p1r1_error_code = p1r1_error_code

    @property
    def error_type(self):
        """
        Error type
        """
        return AbstractHL7ErrorBaseEntry.ERROR_TYPE

    def eq_error_base_entry(self, other):
        """
        Allows comparison of either a ErrorBaseInstance or ErrorBaseEntry (type depends in if there is SUPP info)
        """
        if isinstance(other, ErrorBaseInstance):
            return (
                other.error_base_entry.error_code == self.error_code
                and other.error_base_entry.allow_supplementary_info == self.allow_supplementary_info
            )
        return (
            other.error_code == self.error_code
            and other.allow_supplementary_info == self.allow_supplementary_info
        )


class AbstractAckDetailErrorBaseEntry(AbstractHL7ErrorBaseEntry):
    """
    Abstract base class for all acknowledgement detail error base entries
    """

    __metaclass__ = abc.ABCMeta

    ERROR_TYPE = "ACKNOWLEDGEMENT_DETAIL"

    def __init__(
        self,
        code_system,
        error_code,
        description,
        allow_supplementary_info,
        error_level,
        parent=None,
        ack_type_code=None,
        p1r1_error_code="0",
    ):
        super(AbstractAckDetailErrorBaseEntry, self).__init__(
            code_system,
            error_code,
            description,
            allow_supplementary_info,
            error_level,
            parent,
            ack_type_code,
            p1r1_error_code,
        )

    @property
    def error_type(self):
        """
        Error type
        """
        return AbstractAckDetailErrorBaseEntry.ERROR_TYPE


class _ErrorBase1634Entry(AbstractAckDetailErrorBaseEntry):
    """
    Error base 2.16.840.1.113883.2.1.3.2.4.16.34 entry
    """

    def __init__(self, error_code, description, allow_supplementary_info=False, error_level="ER"):
        super(_ErrorBase1634Entry, self).__init__(
            CODESYSTEM_1634, error_code, description, allow_supplementary_info, error_level
        )


class ErrorBase1634(object):
    """
    Error base 2.16.840.1.113883.2.1.3.2.4.16.34 registry
    """

    PRESCRIPTION_CANCELLED = _ErrorBase1634Entry("0001", "Prescription has been cancelled")
    PRESCRIPTION_EXPIRED = _ErrorBase1634Entry("0002", "Prescription has expired")
    PRESCRIPTION_NOT_FOUND = _ErrorBase1634Entry(
        "0003", "Prescription can not be found. Contact prescriber"
    )
    PRESCRIPTION_WITH_ANOTHER = _ErrorBase1634Entry(
        "0004", "Prescription is with another dispenser"
    )
    PRESCRIPTION_DISPENSED = _ErrorBase1634Entry(
        "0005", "Prescription has been dispensed/not dispensed"
    )
    NO_MORE_NOMINATED = _ErrorBase1634Entry(
        "0006", "No more nominated prescriptions available", error_level="AE"
    )
    NOMINATED_DISABLED = _ErrorBase1634Entry(
        "0007", "Nominated download functionality disabled in SPINE"
    )
    UNABLE_TO_PROCESS = _ErrorBase1634Entry(
        "5000", "Unable to process message. Information missing or invalid - {0}", True
    )


class AbstractErrorBaseEntry(object):
    """
    Abstract base class for all error base entries
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, code_system, error_code, description, allow_supplementary_info, error_level):
        self.code_system = code_system
        self.error_code = error_code
        self.description = description
        self.allow_supplementary_info = allow_supplementary_info
        self.error_level = error_level

    @property
    @abc.abstractmethod
    def error_type(self):
        """
        Error type
        """
        pass

    @property
    def status_code(self):
        """
        Error type
        """
        return httplib.OK

    def __str__(self):
        return self.description

    def __eq__(self, other):
        return self.error_code == getattr(other, "error_code", None)
