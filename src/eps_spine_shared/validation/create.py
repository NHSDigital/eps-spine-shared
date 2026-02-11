from eps_spine_shared.errors import EpsValidationError
from eps_spine_shared.logger import EpsLogger
from eps_spine_shared.validation import message_vocab
from eps_spine_shared.validation.common import ValidationContext
from eps_spine_shared.validation.constants import REGEX_ALPHANUMERIC8, REGEX_ALPHANUMERIC12


class CreatePrescriptionValidator:
    """
    Validator for create prescription messages.
    """

    def __init__(self, log_object, internal_id):
        self.log_object = EpsLogger(log_object)
        self.internal_id = internal_id

    def check_prescriber_details(self, context: ValidationContext):
        """
        Validate prescriber details (not required beyond validation).
        """
        if not REGEX_ALPHANUMERIC8.match(context.msg_output[message_vocab.AGENT_PERSON]):
            self.log_object.write_log(
                "EPS0323a",
                None,
                dict(
                    {
                        "internalID": self.internal_id,
                        "prescribingGpCode": context.msg_output[message_vocab.AGENT_PERSON],
                    }
                ),
            )
            if not REGEX_ALPHANUMERIC12.match(context.msg_output[message_vocab.AGENT_PERSON]):
                raise EpsValidationError(message_vocab.AGENT_PERSON + " has invalid format")

        context.output_fields.add(message_vocab.AGENT_PERSON)

    def check_hcpl_org(self, context: ValidationContext):
        """
        This is an org only found in EPS2 prescriber details
        """
        if not REGEX_ALPHANUMERIC8.match(context.msg_output[message_vocab.HCPLORG]):
            raise EpsValidationError(message_vocab.HCPLORG + " has invalid format")
