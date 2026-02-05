from enum import Enum

from botocore.exceptions import NoCredentialsError

# Try to import spine error classes. If successful, we are on spine and should use wrapper classes.
onSpine = False
try:
    # from spinecore.prescriptions.common.errors.errorbaseprescriptionsearch \
    #     import ErrorBasePrescSearch # pyright: ignore[reportMissingImports]
    from spinecore.common.errors import (  # pyright: ignore[reportMissingImports]
        SpineBusinessError,
        SpineSystemError,
    )

    # from spinecore.prescriptions.common.errors.errorbase1634 \
    #     import ErrorBase1634 # pyright: ignore[reportMissingImports]
    from spinecore.prescriptions.common.errors.errorbase1719 import (  # pyright: ignore[reportMissingImports]
        ErrorBase1719,
    )
    from spinecore.prescriptions.common.errors.errorbase1722 import (  # pyright: ignore[reportMissingImports]
        ErrorBase1722,
    )

    onSpine = True
except ImportError:
    pass


class EpsNoCredentialsErrorWithRetry(NoCredentialsError):
    """
    Extends NoCredentialsError to provide information about retry attempts.
    To be caught in Spine application code and re-raised as NoCredentialsErrorWithRetry.
    """

    fmt = "Unable to locate credentials after {attempts} attempts"


if onSpine:

    class EpsSystemError(SpineSystemError):
        """
        Wrapper for SpineSystemError
        """

        def __init__(self, *args):
            super(EpsSystemError, self).__init__(*args)

    class EpsBusinessError(SpineBusinessError):
        """
        Wrapper for SpineBusinessError
        """

        def __init__(self, *args):
            super(EpsBusinessError, self).__init__(*args)

    class EpsErrorBase(Enum):
        """
        Wrapper for ErrorBases
        """

        MISSING_ISSUE = ErrorBase1722.PRESCRIPTION_NOT_FOUND
        ITEM_NOT_FOUND = ErrorBase1722.ITEM_NOT_FOUND
        INVALID_LINE_STATE_TRANSITION = ErrorBase1722.INVALID_LINE_STATE_TRANSITION
        MAX_REPEAT_MISMATCH = ErrorBase1722.MAX_REPEAT_MISMATCH
        NOT_CANCELLED_EXPIRED = ErrorBase1719.NOT_CANCELLED_EXPIRED
        NOT_CANCELLED_CANCELLED = ErrorBase1719.NOT_CANCELLED_CANCELLED
        NOT_CANCELLED_NOT_DISPENSED = ErrorBase1719.NOT_CANCELLED_NOT_DISPENSED
        NOT_CANCELLED_DISPENSED = ErrorBase1719.NOT_CANCELLED_DISPENSED
        NOT_CANCELLED_WITH_DISPENSER = ErrorBase1719.NOT_CANCELLED_WITH_DISPENSER
        NOT_CANCELLED_WITH_DISPENSER_ACTIVE = ErrorBase1719.NOT_CANCELLED_WITH_DISPENSER_ACTIVE
        PRESCRIPTION_NOT_FOUND = ErrorBase1719.PRESCRIPTION_NOT_FOUND

else:

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
        MISSING_ISSUE = 11
