from decimal import Decimal
from unittest import TestCase

from parameterized import parameterized

from eps_spine_shared.common.dynamodb_common import (
    prescription_id_without_check_digit,
    replace_decimals,
)


class DynamoDbCommonTest(TestCase):
    """
    Tests relating to DynamoDbCommon.
    """

    def test_replace_decimals(self):
        """
        Test replacing values of Decimal type in object.
        """
        with_decimals = {"a": Decimal(1), "b": [Decimal(2)], "c": {"d": Decimal(3)}}

        expected = {"a": 1, "b": [2], "c": {"d": 3}}

        self.assertEqual(replace_decimals(with_decimals), expected)

    @parameterized.expand(
        [
            ("r1_with_check", "1A23FF-Z3F5D8-11F0BE", "1A23FF-Z3F5D8-11F0B"),
            (
                "r2_with_check",
                "297BDA4D-5D80-11F0-BB47-57D6E4EB747DO",
                "297BDA4D-5D80-11F0-BB47-57D6E4EB747D",
            ),
            ("r1_without_check", "1A23FF-Z3F5D8-11F0B", "1A23FF-Z3F5D8-11F0B"),
            (
                "r2_without_check",
                "297BDA4D-5D80-11F0-BB47-57D6E4EB747D",
                "297BDA4D-5D80-11F0-BB47-57D6E4EB747D",
            ),
        ]
    )
    def test_prescription_id_without_check_digit(self, _, with_check_digit, without_check_digit):
        """
        Test removing the check digit from R1 and R2 prescriptions IDs.
        """
        self.assertEqual(prescription_id_without_check_digit(with_check_digit), without_check_digit)
