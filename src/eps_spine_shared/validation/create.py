from dateutil.relativedelta import relativedelta

from eps_spine_shared.common.prescription.fields import DEFAULT_DAYSSUPPLY
from eps_spine_shared.errors import EpsValidationError
from eps_spine_shared.nhsfundamentals.time_utilities import TimeFormats
from eps_spine_shared.validation import constants, message_vocab
from eps_spine_shared.validation.common import PrescriptionsValidator, ValidationContext


class CreatePrescriptionValidator(PrescriptionsValidator):
    """
    Validator for create prescription messages.
    """

    def __init__(self, interaction_worker):
        super().__init__(interaction_worker)
        self.internal_id = None

    def check_hcpl_org(self, context: ValidationContext):
        """
        This is an org only found in EPS2 prescriber details
        """
        if not constants.REGEX_ALPHANUMERIC8.match(context.msg_output[message_vocab.HCPLORG]):
            raise EpsValidationError(message_vocab.HCPLORG + " has invalid format")

    def check_signed_time(self, context: ValidationContext):
        """
        Signed time must be a valid date/time
        """
        self._check_standard_date_time(context, message_vocab.SIGNED_TIME)

    def check_days_supply(self, context: ValidationContext):
        """
        daysSupply is how many days each prescription instance should cover - supports
        the calculation of nominated download dates
        """
        if not context.msg_output.get(message_vocab.DAYS_SUPPLY):
            context.msg_output[message_vocab.DAYS_SUPPLY] = DEFAULT_DAYSSUPPLY
        else:
            if not constants.REGEX_INTEGER12.match(context.msg_output[message_vocab.DAYS_SUPPLY]):
                raise EpsValidationError("daysSupply is not an integer")
            days_supply = int(context.msg_output[message_vocab.DAYS_SUPPLY])
            if days_supply < 0:
                raise EpsValidationError("daysSupply must be a non-zero integer")
            if days_supply > constants.MAX_DAYSSUPPLY:
                raise EpsValidationError(
                    "daysSupply cannot exceed " + str(constants.MAX_DAYSSUPPLY)
                )
            # This will need to be an integer when used in the interaction worker
            context.msg_output[message_vocab.DAYS_SUPPLY] = days_supply

        context.output_fields.add(message_vocab.DAYS_SUPPLY)

    def check_repeat_dispense_window(self, context: ValidationContext, handle_time):
        """
        The overall time to cover the dispense of all repeated instances

        Return immediately if not a repeat dispense, or if a repeat dispense and values
        are missing
        """
        context.output_fields.add(message_vocab.DAYS_SUPPLY_LOW)
        context.output_fields.add(message_vocab.DAYS_SUPPLY_HIGH)

        max_supply_date = handle_time + relativedelta(months=+constants.MAX_FUTURESUPPLYMONTHS)
        max_supply_date_string = max_supply_date.strftime(TimeFormats.STANDARD_DATE_FORMAT)

        if not context.msg_output[message_vocab.TREATMENTTYPE] == constants.STATUS_REPEAT_DISP:
            context.msg_output[message_vocab.DAYS_SUPPLY_LOW] = handle_time.strftime(
                TimeFormats.STANDARD_DATE_FORMAT
            )
            context.msg_output[message_vocab.DAYS_SUPPLY_HIGH] = max_supply_date_string
            return

        if not (
            context.msg_output.get(message_vocab.DAYS_SUPPLY_LOW)
            and context.msg_output.get(message_vocab.DAYS_SUPPLY_HIGH)
        ):
            supp_info = "daysSupply effective time not provided but "
            supp_info += "prescription treatment type is repeat"
            raise EpsValidationError(supp_info)

        self._check_standard_date(context, message_vocab.DAYS_SUPPLY_HIGH)
        self._check_standard_date(context, message_vocab.DAYS_SUPPLY_LOW)

        if context.msg_output[message_vocab.DAYS_SUPPLY_HIGH] > max_supply_date_string:
            supp_info = "daysSupplyValidHigh is more than "
            supp_info += str(constants.MAX_FUTURESUPPLYMONTHS) + " months beyond current day"
            raise EpsValidationError(supp_info)
        if context.msg_output[message_vocab.DAYS_SUPPLY_HIGH] < handle_time.strftime(
            TimeFormats.STANDARD_DATE_FORMAT
        ):
            raise EpsValidationError("daysSupplyValidHigh is in the past")
        if (
            context.msg_output[message_vocab.DAYS_SUPPLY_LOW]
            > context.msg_output[message_vocab.DAYS_SUPPLY_HIGH]
        ):
            raise EpsValidationError("daysSupplyValid low is after daysSupplyValidHigh")

    def check_prescriber_details(self, context: ValidationContext):
        """
        Validate prescriber details (not required beyond validation).
        """
        if not constants.REGEX_ALPHANUMERIC8.match(context.msg_output[message_vocab.AGENT_PERSON]):
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
            if not constants.REGEX_ALPHANUMERIC12.match(
                context.msg_output[message_vocab.AGENT_PERSON]
            ):
                raise EpsValidationError(message_vocab.AGENT_PERSON + " has invalid format")

        context.output_fields.add(message_vocab.AGENT_PERSON)

    def check_patient_name(self, context: ValidationContext):
        """
        Adds patient name to the context output_fields
        """
        context.output_fields.add(message_vocab.PREFIX)
        context.output_fields.add(message_vocab.SUFFIX)
        context.output_fields.add(message_vocab.GIVEN)
        context.output_fields.add(message_vocab.FAMILY)

    def check_prescription_treatment_type(self, context: ValidationContext):
        """
        Validate treatment type
        """
        if context.msg_output[message_vocab.TREATMENTTYPE] not in constants.TREATMENT_TYPELIST:
            supp_info = message_vocab.TREATMENTTYPE + " is not of expected type"
            raise EpsValidationError(supp_info)
        context.output_fields.add(message_vocab.TREATMENTTYPE)
