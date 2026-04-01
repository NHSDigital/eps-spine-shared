from unittest import TestCase
from unittest.mock import Mock

from parameterized import parameterized

from eps_spine_shared.interactions.create_prescription import is_fetched_record


class IsFetchedRecordTest(TestCase):
    """
    Tests for the is_fetched_record function
    """

    @parameterized.expand(
        [
            (
                False,
                False,
                "Expected is_fetched_record to return False when context.fetchedRecord is False",
            ),
            (
                True,
                True,
                "Expected is_fetched_record to return True when context.fetchedRecord is True",
            ),
        ]
    )
    def test_is_fetched_record(self, fetched_record_value, expected_result, message):
        """
        Test that is_fetched_record returns the value of context.fetchedRecord
        """
        context = Mock()
        context.fetchedRecord = fetched_record_value

        result = is_fetched_record(context)

        self.assertEqual(result, expected_result, message)
