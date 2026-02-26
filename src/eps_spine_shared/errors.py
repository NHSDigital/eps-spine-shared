from enum import Enum

from botocore.exceptions import NoCredentialsError

# Try to import spine error classes. If successful, we are on spine and should use wrapper classes.
on_spine = False
try:
    # from spinecore.prescriptions.common.errors.errorbaseprescriptionsearch \
    #     import ErrorBasePrescSearch # pyright: ignore[reportMissingImports]
    from spinecore.common.aws.awscommon import (  # pyright: ignore[reportMissingImports]
        NoCredentialsErrorWithRetry,
    )
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

    on_spine = True
except ImportError:
    pass


if on_spine:

    class EpsNoCredentialsErrorWithRetry:
        """
        Wrapper for NoCredentialsErrorWithRetry
        """

        def __init__(self, *args):
            raise NoCredentialsErrorWithRetry(*args)

    class EpsSystemError:
        """
        Wrapper for SpineSystemError
        """

        def __init__(self, *args):
            raise SpineSystemError(*args)

    class EpsBusinessError:
        """
        Wrapper for SpineBusinessError
        """

        def __init__(self, *args):
            raise SpineBusinessError(*args)

    class EpsErrorBase:
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

    class EpsNoCredentialsErrorWithRetry(NoCredentialsError):
        """
        Extends NoCredentialsError to provide information about retry attempts.
        """

        fmt = "Unable to locate credentials after {attempts} attempts"

    class EpsSystemError(Exception):
        """
        Exception to be raised if an unexpected system error occurs.
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
        MISSING_ISSUE = 11
