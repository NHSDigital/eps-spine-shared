import unittest

from eps_spine_shared.errors import EpsValidationError
from eps_spine_shared.validation import message_vocab
from eps_spine_shared.validation.common import ValidationContext
from eps_spine_shared.validation.create import CreatePrescriptionValidator
from tests.mock_logger import MockLogObject


class CreatePrescriptionValidatorTest(unittest.TestCase):
    def setUp(self):
        self.log_object = MockLogObject()
        self.internal_id = "test-internal-id"
        self.validator = CreatePrescriptionValidator(self.log_object, self.internal_id)
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
