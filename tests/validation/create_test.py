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
            self.assertEqual(str(cm.exception), message_vocab.SIGNED_TIME + " has invalid format")

    def test_wrong_length_raises_error(self):
        self.context.msg_output[message_vocab.SIGNED_TIME] = "202609111234567"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_signed_time(self.context)
            self.assertEqual(str(cm.exception), message_vocab.SIGNED_TIME + " has invalid format")


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
            self.assertEqual(str(cm.exception), "daysSupply must be a non-zero integer")

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
            self.assertEqual(str(cm.exception), f"{incorrect_field} has invalid format")

    def test_high_date_exceeds_limit(self):
        self.context.msg_output[message_vocab.DAYS_SUPPLY_LOW] = "20260911"
        self.context.msg_output[message_vocab.DAYS_SUPPLY_HIGH] = "20280911"

        with self.assertRaises(EpsValidationError) as cm:
            self.validator.check_repeat_dispense_window(self.context, self.handle_time)
            self.assertEqual(
                str(cm.exception),
                "daysSupplyValidHigh is more than "
                + str(constants.MAX_FUTURESUPPLYMONTHS)
                + " months beyond current day",
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
            self.assertEqual(str(cm.exception), "daysSupplyValidLow is after daysSupplyValidHigh")


class TestCheckPatientName(CreatePrescriptionValidatorTest):
    def test_adds_to_output_fields(self):
        self.validator.check_patient_name(self.context)

        self.assertIn(message_vocab.PREFIX, self.context.output_fields)
        self.assertIn(message_vocab.SUFFIX, self.context.output_fields)
        self.assertIn(message_vocab.GIVEN, self.context.output_fields)
        self.assertIn(message_vocab.FAMILY, self.context.output_fields)
