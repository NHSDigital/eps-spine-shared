from datetime import datetime
from unittest import mock
from unittest.case import TestCase

from parameterized.parameterized import parameterized

from eps_spine_shared.nhsfundamentals.time_utilities import (
    TimeFormats,
    convert_spine_date,
    guess_common_datetime_format,
    time_now_as_string,
)


class TimeUtilitiesTests(TestCase):
    """
    Time Utility Testing
    """

    @parameterized.expand(
        [
            ("gmt_end", "2021-03-28 01:59:59", "20210328015959"),
            ("bst_start", "2021-03-28 02:00:00", "20210328020000"),
            ("bst_end", "2021-10-31 01:59:59", "20211031015959"),
            ("gmt_start", "2021-10-31 02:00:00", "20211031020000"),
        ]
    )
    def testtime_now_as_string(self, _, utcNow, expected):
        """
        Check time_now_as_string returns standard spine format by default matching UTC time.
        """
        with mock.patch("eps_spine_shared.nhsfundamentals.time_utilities.now") as mockNow:
            mockNow.return_value = datetime.strptime(utcNow, "%Y-%m-%d %H:%M:%S")
            result = time_now_as_string()
            self.assertEqual(expected, result)

    @parameterized.expand(
        [
            ("length_4", "2022", TimeFormats.STANDARD_DATE_FORMAT_YEAR_ONLY),
            ("length_6", "202201", TimeFormats.STANDARD_DATE_FORMAT_YEAR_MONTH),
            ("length_8", "20220113", TimeFormats.STANDARD_DATE_FORMAT),
            ("length_12", "202201131234", TimeFormats.DATE_TIME_WITHOUT_SECONDS_FORMAT),
            ("length_14", "20220113123456", TimeFormats.STANDARD_DATE_TIME_FORMAT),
            ("length_19_EBXML", "2022-01-13T12:34:56", TimeFormats.EBXML_FORMAT),
            (
                "length_19_OTHER",
                "20220113123456+0000",
                TimeFormats.STANDARD_DATE_TIME_UTC_ZONE_FORMAT,
            ),
            ("length_20", "2022-01-13T12:34:56Z", TimeFormats.SMSP_FORMAT),
            ("length_21", "20220113123456.123456", TimeFormats.SPINE_DATETIME_MS_FORMAT),
            ("length_22", "20220113T123456.123456", TimeFormats.HL7_DATETIME_FORMAT),
            ("length_23", "2022-01-13T12:34:56.123456", TimeFormats.EXTENDED_SMSP_FORMAT),
            ("length_24", "2022-01-13T12:34:56.123456Z", TimeFormats.EXTENDED_SMSP_PLUS_Z_FORMAT),
            ("other", "202", None),
        ]
    )
    def testGuessCommonDateTimeFormat_Default(self, _, timeString, expected):
        """
        Check time format determined from date time string using default settings
        """
        result = guess_common_datetime_format(timeString)
        self.assertEqual(expected, result)

    def testGuessCommonDateTimeFormat_NoneIfUnknown(self):
        """
        Check time format determined from date time string specifying to return none if could not be determined
        """
        result = guess_common_datetime_format("202", False)
        self.assertIsNone(result)

    def testGuessCommonDateTimeFormat_ErrorIfUnknown_FormatUnknown(self):
        """
        Check time format determined from date time string with an unknown format, with raise error true
        """
        with self.assertRaises(ValueError):
            _ = guess_common_datetime_format("202", True)

    def testGuessCommonDateTimeFormat_ErrorIfUnknown_FormatKnown(self):
        """
        Check time format determined from date time string with a known format, with raise error true
        """
        result = guess_common_datetime_format("2020", True)
        self.assertEqual(TimeFormats.STANDARD_DATE_FORMAT_YEAR_ONLY, result)


class DateFormatTest(TestCase):
    """
    There is a safety method called convert_spine_date which will convert a date string if
    there is doubt over the actual format being used
    """

    def _formatTester(self, dateFormat, withFormat=False):
        """
        Test the format of a date
        """
        _now = datetime.now()
        _nowAsString = _now.strftime(dateFormat)
        if withFormat:
            _newNow = convert_spine_date(_nowAsString, dateFormat)
        else:
            _newNow = convert_spine_date(_nowAsString)

        if _newNow > _now:
            return _newNow - _now
        return _now - _newNow

    def testEbxml(self):
        """
        TimeFormats.EBXML_FORMAT
        """
        delta = self._formatTester(TimeFormats.EBXML_FORMAT)
        self.assertLessEqual(delta.seconds, 1)

    def testStandardUTC(self):
        """
        STANDARD_DATE_TIME_UTC_ZONE_FORMAT = '%Y%m%d%H%M%S+0000'
        STANDARD_DATE_TIME_FORMAT = '%Y%m%d%H%M%S'
        STANDARD_DATE_FORMAT = '%Y%m%d'
        HL7_DATETIME_FORMAT = '%Y%m%dT%H%M%S.%f'
        SPINE_DATETIME_MS_FORMAT = '%Y%m%d%H%M%S.%f'
        SPINE_DATE_FORMAT = '%Y%m%d'
        DAY_MONTH_YEAR_FORMAT = '%d%m%Y'
        DAY_MONTH_TWO_DIGIT_YEAR_FORMAT = '%d%m%y'
        DAY_MONTH_YEAR_WITH_SLASHES_FORMAT = '%d/%m/%Y'
        TWO_DIGIT_YEAR_AND_WEEK_FORMAT = '%y%W'
        """
        delta = self._formatTester(TimeFormats.STANDARD_DATE_TIME_UTC_ZONE_FORMAT)
        self.assertLessEqual(delta.seconds, 1)

    def testStandardDT(self):
        """
        The value of STANDARD_DATE_TIME_FORMAT = '%Y%m%d%H%M%S'
        """
        delta = self._formatTester(TimeFormats.STANDARD_DATE_TIME_FORMAT)
        self.assertLessEqual(delta.seconds, 1)

    def testStandardDTMS(self):
        """
        The value of SPINE_DATETIME_MS_FORMAT = '%Y%m%d%H%M%S.%f'
        """
        delta = self._formatTester(TimeFormats.SPINE_DATETIME_MS_FORMAT)
        self.assertLessEqual(delta.seconds, 1)

    def testStandardHL7(self):
        """
        The value of HL7_DATETIME_FORMAT = '%Y%m%dT%H%M%S.%f'
        """
        delta = self._formatTester(TimeFormats.HL7_DATETIME_FORMAT)
        self.assertLessEqual(delta.seconds, 1)

    def testStandardDate(self):
        """
        The value of SPINE_DATE_FORMAT = '%Y%m%d'
        """
        delta = self._formatTester(TimeFormats.SPINE_DATE_FORMAT)
        self.assertLessEqual(delta.days, 1)

    def testStandardDT_withFormat(self):
        """
        The value of STANDARD_DATE_TIME_FORMAT = '%Y%m%d%H%M%S'
        """
        delta = self._formatTester(TimeFormats.STANDARD_DATE_TIME_FORMAT, True)
        self.assertLessEqual(delta.seconds, 1)
