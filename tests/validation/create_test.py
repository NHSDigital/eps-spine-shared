import unittest
from datetime import datetime
from unittest.mock import MagicMock

from parameterized import parameterized

from eps_spine_shared.errors import EpsValidationError
from eps_spine_shared.logger import EpsLogger
from eps_spine_shared.validation import constants, message_vocab
from eps_spine_shared.validation.common import ValidationContext
from eps_spine_shared.validation.create import CreatePrescriptionValidator
from tests.mock_logger import MockLogObject


class CreatePrescriptionValidatorTest(unittest.TestCase):
    def setUp(self):
        self.log_object = EpsLogger(MockLogObject())
        interaction_worker = MagicMock()
        interaction_worker.log_object = self.log_object

        self.validator = CreatePrescriptionValidator(interaction_worker)
        self.internal_id = "test-internal-id"
        self.validator.internal_id = self.internal_id

        self.context = ValidationContext()


class TestCheckHcplOrg(CreatePrescriptionValidatorTest):
    def test_valid_hcpl_org(self):
        self.context.msg_output[message_vocab.HCPLORG] = "ORG12345"
        self.validator.check_hcpl_org(self.context)

    def test_invalid_format_raises_error(self):
        self.context.msg_output[message_vocab.HCPLORG] = "ORG@1234"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_hcpl_org(self.context)

        self.assertEqual(str(cm.exception), message_vocab.HCPLORG + " has invalid format")


class TestCheckSignedTime(CreatePrescriptionValidatorTest):
    def test_valid_signed_time(self):
        self.context.msg_output[message_vocab.SIGNED_TIME] = "20260911123456"
        self.validator.check_signed_time(self.context)

        self.assertIn(message_vocab.SIGNED_TIME, self.context.output_fields)

    @parameterized.expand(
        [
            ("+0100"),
            ("-0000"),
            ("+0000"),
        ]
    )
    def test_valid_international_signed_time(self, date_suffix):
        self.context.msg_output[message_vocab.SIGNED_TIME] = "20260911123456" + date_suffix
        self.validator.check_signed_time(self.context)

        self.assertIn(message_vocab.SIGNED_TIME, self.context.output_fields)

    def test_invalid_international_signed_time_raises_error(self):
        self.context.msg_output[message_vocab.SIGNED_TIME] = "20260911123456+0200"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_signed_time(self.context)

        self.assertEqual(
            str(cm.exception),
            message_vocab.SIGNED_TIME
            + " is not a valid time or in the valid format; expected format %Y%m%d%H%M%S",
        )

    def test_wrong_length_raises_error(self):
        self.context.msg_output[message_vocab.SIGNED_TIME] = "202609111234567"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_signed_time(self.context)

        self.assertEqual(
            str(cm.exception),
            message_vocab.SIGNED_TIME
            + " is not a valid time or in the valid format; expected format %Y%m%d%H%M%S",
        )


class TestCheckDaysSupply(CreatePrescriptionValidatorTest):
    def test_none(self):
        self.context.msg_output[message_vocab.DAYS_SUPPLY] = None
        self.validator.check_days_supply(self.context)

        self.assertIn(message_vocab.DAYS_SUPPLY, self.context.output_fields)

    def test_non_integer(self):
        self.context.msg_output[message_vocab.DAYS_SUPPLY] = "one"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_days_supply(self.context)

        self.assertEqual(str(cm.exception), "daysSupply is not an integer")

    def test_negative_integer(self):
        self.context.msg_output[message_vocab.DAYS_SUPPLY] = "-5"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_days_supply(self.context)

        self.assertEqual(str(cm.exception), "daysSupply is not an integer")

    def test_exceeds_max(self):
        self.context.msg_output[message_vocab.DAYS_SUPPLY] = str(constants.MAX_DAYSSUPPLY + 1)

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_days_supply(self.context)

        self.assertEqual(
            str(cm.exception), "daysSupply cannot exceed " + str(constants.MAX_DAYSSUPPLY)
        )


class TestCheckRepeatDispenseWindow(CreatePrescriptionValidatorTest):
    def setUp(self):
        super().setUp()
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.handle_time = datetime(2026, 9, 11, 12, 34, 56)

    def test_non_repeat(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE
        self.validator.check_repeat_dispense_window(self.context, self.handle_time)

        self.assertEqual(self.context.msg_output[message_vocab.DAYS_SUPPLY_LOW], "20260911")
        self.assertEqual(self.context.msg_output[message_vocab.DAYS_SUPPLY_HIGH], "20270911")

        self.assertIn(message_vocab.DAYS_SUPPLY_LOW, self.context.output_fields)
        self.assertIn(message_vocab.DAYS_SUPPLY_HIGH, self.context.output_fields)

    def test_missing_low_and_high(self):
        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_window(self.context, self.handle_time)

        self.assertEqual(
            str(cm.exception),
            "daysSupply effective time not provided but prescription treatment type is repeat",
        )

    @parameterized.expand(
        [
            ("20260911", "202709111", "daysSupplyValidHigh"),
            ("202609111", "20270911", "daysSupplyValidLow"),
        ]
    )
    def test_invalid_dates(self, low_date, high_date, incorrect_field):
        self.context.msg_output[message_vocab.DAYS_SUPPLY_LOW] = low_date
        self.context.msg_output[message_vocab.DAYS_SUPPLY_HIGH] = high_date

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_window(self.context, self.handle_time)

        self.assertEqual(
            str(cm.exception),
            f"{incorrect_field} is not a valid time or in the valid format; expected format %Y%m%d",
        )

    def test_high_date_exceeds_limit(self):
        self.context.msg_output[message_vocab.DAYS_SUPPLY_LOW] = "20260911"
        self.context.msg_output[message_vocab.DAYS_SUPPLY_HIGH] = "20280911"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_window(self.context, self.handle_time)

        self.assertEqual(
            str(cm.exception),
            f"daysSupplyValidHigh is more than {str(constants.MAX_FUTURESUPPLYMONTHS)} months beyond current day",
        )

    def test_high_date_in_the_past(self):
        self.context.msg_output[message_vocab.DAYS_SUPPLY_LOW] = "20260911"
        self.context.msg_output[message_vocab.DAYS_SUPPLY_HIGH] = "20260910"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_window(self.context, self.handle_time)

        self.assertEqual(str(cm.exception), "daysSupplyValidHigh is in the past")

    def test_low_after_high(self):
        self.context.msg_output[message_vocab.DAYS_SUPPLY_LOW] = "20260912"
        self.context.msg_output[message_vocab.DAYS_SUPPLY_HIGH] = "20260911"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_window(self.context, self.handle_time)

        self.assertEqual(str(cm.exception), "daysSupplyValid low is after daysSupplyValidHigh")


class TestCheckPrescriberDetails(CreatePrescriptionValidatorTest):
    def test_8_char_alphanumeric(self):
        self.context.msg_output[message_vocab.AGENT_PERSON] = "ABCD1234"
        self.validator.check_prescriber_details(self.context)

        self.assertIn(message_vocab.AGENT_PERSON, self.context.output_fields)
        self.assertFalse(self.validator.log_object.logger.was_logged("EPS0323a"))

    def test_12_char_alphanumeric(self):
        self.context.msg_output[message_vocab.AGENT_PERSON] = "ABCD12345678"
        self.validator.check_prescriber_details(self.context)

        self.assertIn(message_vocab.AGENT_PERSON, self.context.output_fields)
        self.assertTrue(self.validator.log_object.logger.was_logged("EPS0323a"))

    def test_too_long_raises_error(self):
        self.context.msg_output[message_vocab.AGENT_PERSON] = "ABCD123456789"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_prescriber_details(self.context)

        self.assertEqual(str(cm.exception), message_vocab.AGENT_PERSON + " has invalid format")
        self.assertTrue(
            self.validator.log_object.logger.was_multiple_value_logged(
                "EPS0323a", {"internalID": self.internal_id, "prescribingGpCode": "ABCD123456789"}
            )
        )

    def test_special_chars_raises_error(self):
        self.context.msg_output[message_vocab.AGENT_PERSON] = "ABC@1234"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_prescriber_details(self.context)

        self.assertEqual(str(cm.exception), message_vocab.AGENT_PERSON + " has invalid format")

    def test_adds_to_output_fields(self):
        self.context.msg_output[message_vocab.AGENT_PERSON] = "ABCD1234"
        self.validator.check_prescriber_details(self.context)

        self.assertIn(message_vocab.AGENT_PERSON, self.context.output_fields)


class TestCheckPatientName(CreatePrescriptionValidatorTest):
    def test_adds_to_output_fields(self):
        self.validator.check_patient_name(self.context)

        self.assertIn(message_vocab.PREFIX, self.context.output_fields)
        self.assertIn(message_vocab.SUFFIX, self.context.output_fields)
        self.assertIn(message_vocab.GIVEN, self.context.output_fields)
        self.assertIn(message_vocab.FAMILY, self.context.output_fields)


class TestCheckPrescriptionTreatmentType(CreatePrescriptionValidatorTest):
    def test_unrecognised_treatment_type_raises_error(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = "9999"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_prescription_treatment_type(self.context)

        self.assertEqual(str(cm.exception), "prescriptionTreatmentType is not of expected type")


class TestCheckPrescriptionType(CreatePrescriptionValidatorTest):
    def test_unrecognised_prescription_type(self):
        self.context.msg_output[message_vocab.PRESCTYPE] = "9999"
        self.validator.check_prescription_type(self.context)

        self.assertEqual(self.context.msg_output[message_vocab.PRESCTYPE], "NotProvided")
        self.assertIn(message_vocab.PRESCTYPE, self.context.output_fields)


class TestCheckRepeatDispenseInstances(CreatePrescriptionValidatorTest):
    def setUp(self):
        super().setUp()
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP

    def test_acute_prescription_without_repeat_values(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE
        self.context.msg_output[message_vocab.REPEATLOW] = None
        self.context.msg_output[message_vocab.REPEATHIGH] = None

        self.validator.check_repeat_dispense_instances(self.context)

        self.assertNotIn(message_vocab.REPEATLOW, self.context.output_fields)
        self.assertNotIn(message_vocab.REPEATHIGH, self.context.output_fields)

    def test_non_acute_without_repeat_values_raises_error(self):
        self.context.msg_output[message_vocab.REPEATLOW] = None
        self.context.msg_output[message_vocab.REPEATHIGH] = None

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_instances(self.context)

        self.assertIn("must both be provided", str(cm.exception))

    @parameterized.expand(
        [
            ("1", "abc", message_vocab.REPEATHIGH),
            ("abc", "1", message_vocab.REPEATLOW),
        ]
    )
    def test_repeat_high_or_low_not_integer_raises_error(
        self, low_value, high_value, incorrect_field
    ):
        self.context.msg_output[message_vocab.REPEATLOW] = low_value
        self.context.msg_output[message_vocab.REPEATHIGH] = high_value

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_instances(self.context)

        self.assertEqual(str(cm.exception), incorrect_field + " is not an integer")

    def test_repeat_low_not_one_raises_error(self):
        self.context.msg_output[message_vocab.REPEATLOW] = "2"
        self.context.msg_output[message_vocab.REPEATHIGH] = "6"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_instances(self.context)

        self.assertEqual(str(cm.exception), message_vocab.REPEATLOW + " must be 1")

    def test_repeat_high_exceeds_max_raises_error(self):
        self.context.msg_output[message_vocab.REPEATLOW] = "1"
        self.context.msg_output[message_vocab.REPEATHIGH] = str(
            constants.MAX_PRESCRIPTIONREPEATS + 1
        )

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_instances(self.context)

        self.assertIn("must not be over configured maximum", str(cm.exception))

    def test_repeat_low_greater_than_high_raises_error(self):
        self.context.msg_output[message_vocab.REPEATLOW] = "1"
        self.context.msg_output[message_vocab.REPEATHIGH] = "0"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_instances(self.context)

        self.assertIn("is greater than", str(cm.exception))

    def test_repeat_prescription_with_multiple_instances_logs_warning(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT
        self.context.msg_output[message_vocab.REPEATLOW] = "1"
        self.context.msg_output[message_vocab.REPEATHIGH] = "6"

        self.validator.check_repeat_dispense_instances(self.context)

        self.assertTrue(self.validator.log_object.logger.was_logged("EPS0509"))
        self.assertIn(message_vocab.REPEATLOW, self.context.output_fields)
        self.assertIn(message_vocab.REPEATHIGH, self.context.output_fields)

    def test_valid_repeat_dispense_instances(self):
        self.context.msg_output[message_vocab.REPEATLOW] = "1"
        self.context.msg_output[message_vocab.REPEATHIGH] = "6"

        self.validator.check_repeat_dispense_instances(self.context)

        self.assertIn(message_vocab.REPEATLOW, self.context.output_fields)
        self.assertIn(message_vocab.REPEATHIGH, self.context.output_fields)


class TestCheckBirthDate(CreatePrescriptionValidatorTest):
    def setUp(self):
        super().setUp()
        self.handle_time = datetime(2026, 9, 11, 12, 34, 56)

    def test_valid_birth_date(self):
        self.context.msg_output[message_vocab.BIRTHTIME] = "20000101"
        self.validator.check_birth_date(self.context, self.handle_time)

        self.assertIn(message_vocab.BIRTHTIME, self.context.output_fields)

    def test_birth_date_in_future_raises_error(self):
        self.context.msg_output[message_vocab.BIRTHTIME] = "20260912"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_birth_date(self.context, self.handle_time)

        self.assertEqual(str(cm.exception), message_vocab.BIRTHTIME + " is in the future")

    def test_invalid_birth_date_format_raises_error(self):
        self.context.msg_output[message_vocab.BIRTHTIME] = "2000010112"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_birth_date(self.context, self.handle_time)

        self.assertEqual(
            str(cm.exception),
            message_vocab.BIRTHTIME
            + " is not a valid time or in the valid format; expected format %Y%m%d",
        )


class TestValidateLineItems(CreatePrescriptionValidatorTest):
    def setUp(self):
        super().setUp()
        self.line_item_1_id = "12345678-1234-1234-1234-123456789012"
        self.context.msg_output[message_vocab.LINEITEM_PX + "1" + message_vocab.LINEITEM_SX_ID] = (
            self.line_item_1_id
        )

    def test_no_line_items_raises_error(self):
        del self.context.msg_output[message_vocab.LINEITEM_PX + "1" + message_vocab.LINEITEM_SX_ID]
        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_items(self.context)

        self.assertEqual(str(cm.exception), "No valid line items found")

    def test_single_valid_line_item(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE

        self.validator.validate_line_items(self.context)

        self.assertEqual(len(self.context.msg_output[message_vocab.LINEITEMS]), 1)
        self.assertEqual(
            self.context.msg_output[message_vocab.LINEITEMS][0][message_vocab.LINEITEM_SX_ID],
            self.line_item_1_id,
        )
        self.assertIn(message_vocab.LINEITEMS, self.context.output_fields)

    def test_multiple_valid_line_items(self):
        self.context.msg_output[message_vocab.LINEITEM_PX + "2" + message_vocab.LINEITEM_SX_ID] = (
            "12345678-1234-1234-1234-123456789013"
        )
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE

        self.validator.validate_line_items(self.context)

        self.assertEqual(len(self.context.msg_output[message_vocab.LINEITEMS]), 2)
        self.assertIn(message_vocab.LINEITEMS, self.context.output_fields)

    def test_exceeds_max_line_items_raises_error(self):
        for i in range(1, constants.MAX_LINEITEMS + 2):
            self.context.msg_output[
                message_vocab.LINEITEM_PX + str(i) + message_vocab.LINEITEM_SX_ID
            ] = f"12345678-1234-1234-1234-1234567890{i:02d}"
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_items(self.context)

        self.assertIn("over expected max count", str(cm.exception))

    def test_line_item_with_repeat_values(self):
        self.context.msg_output[
            message_vocab.LINEITEM_PX + "1" + message_vocab.LINEITEM_SX_REPEATHIGH
        ] = "6"
        self.context.msg_output[
            message_vocab.LINEITEM_PX + "1" + message_vocab.LINEITEM_SX_REPEATLOW
        ] = "1"
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.context.msg_output[message_vocab.REPEATHIGH] = 6

        self.validator.validate_line_items(self.context)

        line_items = self.context.msg_output[message_vocab.LINEITEMS]
        self.assertEqual(len(line_items), 1)
        self.assertEqual(line_items[0][message_vocab.LINEITEM_DT_MAXREPEATS], "6")
        self.assertEqual(line_items[0][message_vocab.LINEITEM_DT_CURRINSTANCE], "1")

    def test_prescription_repeat_less_than_line_item_repeat_raises_error(self):
        self.context.msg_output[
            message_vocab.LINEITEM_PX + "1" + message_vocab.LINEITEM_SX_REPEATHIGH
        ] = "6"
        self.context.msg_output[
            message_vocab.LINEITEM_PX + "1" + message_vocab.LINEITEM_SX_REPEATLOW
        ] = "1"
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.context.msg_output[message_vocab.REPEATHIGH] = 3

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_items(self.context)

        self.assertIn("must not be greater than prescriptionRepeatHigh", str(cm.exception))


class TestValidateLineItem(CreatePrescriptionValidatorTest):
    def setUp(self):
        super().setUp()
        self.line_item_id = "12345678-1234-1234-1234-123456789012"
        self.line_item = 1
        self.line_dict = {}
        self.context = ValidationContext()

    def test_invalid_line_item_id(self):
        self.line_dict[message_vocab.LINEITEM_DT_ID] = "invalid-line-item-id"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_item(self.context, self.line_item, self.line_dict, 1)

        self.assertEqual(str(cm.exception), "invalid-line-item-id is not a valid GUID format")

    def test_missing_items_from_line_dict(self):
        self.line_dict[message_vocab.LINEITEM_DT_ID] = self.line_item_id
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE

        max_repeats = self.validator.validate_line_item(
            self.context, self.line_item, self.line_dict, 1
        )

        self.assertEqual(max_repeats, 1)

    def test_repeat_high_not_integer(self):
        self.validator.check_for_invalid_line_item_repeat_combinations = MagicMock()

        self.line_dict[message_vocab.LINEITEM_DT_ID] = self.line_item_id
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "abc"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_item(self.context, self.line_item, self.line_dict, 1)

        self.assertEqual(str(cm.exception), "repeat.High for line item 1 is not an integer")

    def test_repeat_high_less_than_one(self):
        self.validator.check_for_invalid_line_item_repeat_combinations = MagicMock()

        self.line_dict[message_vocab.LINEITEM_DT_ID] = self.line_item_id
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "0"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_item(self.context, self.line_item, self.line_dict, 1)

        self.assertEqual(str(cm.exception), "repeat.High for line item 1 must be greater than zero")

    def test_repeat_high_exceeds_prescription_repeat_high(self):
        self.validator.check_for_invalid_line_item_repeat_combinations = MagicMock()

        self.line_dict[message_vocab.LINEITEM_DT_ID] = self.line_item_id
        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "6"

        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.context.msg_output[message_vocab.REPEATHIGH] = "3"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_item(self.context, self.line_item, self.line_dict, 1)

        self.assertEqual(
            str(cm.exception),
            "repeat.High of 6 for line item 1 must not be greater than "
            "prescriptionRepeatHigh of 3",
        )

    def test_repeat_high_not_1_when_treatment_type_is_repeat(self):
        self.validator.check_for_invalid_line_item_repeat_combinations = MagicMock()

        self.line_dict[message_vocab.LINEITEM_DT_ID] = self.line_item_id
        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "3"
        self.line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE] = "1"

        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT
        self.context.msg_output[message_vocab.REPEATHIGH] = "3"

        self.validator.validate_line_item(self.context, self.line_item, self.line_dict, 1)

        self.assertTrue(self.validator.log_object.logger.was_logged("EPS0509"))

    def test_repeat_low_not_integer(self):
        self.validator.check_for_invalid_line_item_repeat_combinations = MagicMock()

        self.line_dict[message_vocab.LINEITEM_DT_ID] = self.line_item_id
        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "3"
        self.line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE] = "abc"

        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE
        self.context.msg_output[message_vocab.REPEATHIGH] = "3"
        self.context.msg_output[message_vocab.REPEATLOW] = "1"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_item(self.context, self.line_item, self.line_dict, 1)

        self.assertEqual(str(cm.exception), "repeat.Low for line item 1 is not an integer")

    def test_repeat_low_not_1(self):
        self.validator.check_for_invalid_line_item_repeat_combinations = MagicMock()

        self.line_dict[message_vocab.LINEITEM_DT_ID] = self.line_item_id
        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "3"
        self.line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE] = "2"

        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE
        self.context.msg_output[message_vocab.REPEATHIGH] = "3"
        self.context.msg_output[message_vocab.REPEATLOW] = "1"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.validate_line_item(self.context, self.line_item, self.line_dict, 1)

        self.assertEqual(str(cm.exception), "repeat.Low for line item 1 is not set to 1")


class TestCheckForInvalidLineItemRepeatCombinations(CreatePrescriptionValidatorTest):
    def setUp(self):
        super().setUp()
        self.line_item = 1
        self.line_dict = {message_vocab.LINEITEM_DT_ID: "12345678-1234-1234-1234-123456789012"}

    def test_repeat_dispense_without_repeat_values_raises_error(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_for_invalid_line_item_repeat_combinations(
                self.context, self.line_dict, self.line_item
            )

        self.assertEqual(
            str(cm.exception),
            "repeat.High and repeat.Low values must both be provided for lineItem 1 if not acute prescription",
        )

    def test_acute_prescription_with_repeat_values_raises_error(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_ACUTE
        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "6"
        self.line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE] = "1"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_for_invalid_line_item_repeat_combinations(
                self.context, self.line_dict, self.line_item
            )

        self.assertEqual(
            str(cm.exception), "Line item 1 repeat value provided for non-repeat prescription"
        )

    def test_repeat_dispense_with_only_repeat_high_raises_error(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "6"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_for_invalid_line_item_repeat_combinations(
                self.context, self.line_dict, self.line_item
            )

        self.assertEqual(
            str(cm.exception), "repeat.High provided but not repeat.Low for line item 1"
        )

    def test_repeat_dispense_with_only_repeat_low_raises_error(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE] = "1"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_for_invalid_line_item_repeat_combinations(
                self.context, self.line_dict, self.line_item
            )

        self.assertEqual(
            str(cm.exception), "repeat.Low provided but not repeat.High for line item 1"
        )

    def test_repeat_dispense_with_valid_repeat_values(self):
        self.context.msg_output[message_vocab.TREATMENTTYPE] = constants.STATUS_REPEAT_DISP
        self.context.msg_output[message_vocab.REPEATHIGH] = "6"

        self.line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = "6"
        self.line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE] = "1"

        self.validator.check_for_invalid_line_item_repeat_combinations(
            self.context, self.line_dict, self.line_item
        )
