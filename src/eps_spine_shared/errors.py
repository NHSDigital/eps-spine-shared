from enum import Enum

from botocore.exceptions import NoCredentialsError


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

    def __init__(self, errorTopic, *args):  # noqa: B042
        """
        errorTopic is the topic to be used when writing the WDO to the error exchange
        """
        super(EpsSystemError, self).__init__(*args)
        self.errorTopic = errorTopic


class EpsBusinessError(Exception):
    """
    Exception to be raised by a message worker if an expected error condition is hit,
    one that is expected to cause a HL7 error response with a set errorCode.
    To be caught in Spine application code and re-raised as SpineBusinessError.
    """

    def __init__(self, errorCode, suppInfo=None, messageId=None):  # noqa: B042
        super(EpsBusinessError, self).__init__()
        self.errorCode = errorCode
        self.supplementaryInformation = suppInfo
        self.messageId = messageId

    def __str__(self):
        if self.supplementaryInformation:
            return "{} {}".format(self.errorCode, self.supplementaryInformation)
        return str(self.errorCode)


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
