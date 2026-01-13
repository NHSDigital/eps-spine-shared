from datetime import datetime


class TimeFormats:
    STANDARD_DATE_TIME_UTC_ZONE_FORMAT = "%Y%m%d%H%M%S+0000"
    STANDARD_DATE_TIME_FORMAT = "%Y%m%d%H%M%S"
    STANDARD_DATE_TIME_LENGTH = 14
    DATE_TIME_WITHOUT_SECONDS_FORMAT = "%Y%m%d%H%M"
    STANDARD_DATE_FORMAT = "%Y%m%d"
    STANDARD_DATE_FORMAT_YEAR_MONTH = "%Y%m"
    STANDARD_DATE_FORMAT_YEAR_ONLY = "%Y"
    HL7_DATETIME_FORMAT = "%Y%m%dT%H%M%S.%f"
    SPINE_DATETIME_MS_FORMAT = "%Y%m%d%H%M%S.%f"
    SPINE_DATE_FORMAT = "%Y%m%d"
    EBXML_FORMAT = "%Y-%m-%dT%H:%M:%S"
    SMSP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    EXTENDED_SMSP_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
    EXTENDED_SMSP_PLUS_Z_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


_TIMEFORMAT_LENGTH_MAP = {
    TimeFormats.STANDARD_DATE_TIME_LENGTH: TimeFormats.STANDARD_DATE_TIME_FORMAT,
    12: TimeFormats.DATE_TIME_WITHOUT_SECONDS_FORMAT,
    8: TimeFormats.STANDARD_DATE_FORMAT,
    6: TimeFormats.STANDARD_DATE_FORMAT_YEAR_MONTH,
    4: TimeFormats.STANDARD_DATE_FORMAT_YEAR_ONLY,
    22: TimeFormats.HL7_DATETIME_FORMAT,
    21: TimeFormats.SPINE_DATETIME_MS_FORMAT,
    20: TimeFormats.SMSP_FORMAT,
    23: TimeFormats.EXTENDED_SMSP_FORMAT,
    26: TimeFormats.EXTENDED_SMSP_FORMAT,
    24: TimeFormats.EXTENDED_SMSP_PLUS_Z_FORMAT,
    27: TimeFormats.EXTENDED_SMSP_PLUS_Z_FORMAT,
}


def _guess_common_datetime_format(time_string, raise_error_if_unknown=False):
    """
    Guess the date time format from the commonly used list

    Args:
        time_string (str):
            The datetime string to try determine the format of.
        raise_error_if_unknown (bool):
            Determines the action when the format cannot be determined.
            False (default) will return None, True will raise an error.
    """
    format = None
    if len(time_string) == 19:
        try:
            datetime.strptime(time_string, TimeFormats.EBXML_FORMAT)
            format = TimeFormats.EBXML_FORMAT
        except ValueError:
            format = TimeFormats.STANDARD_DATE_TIME_UTC_ZONE_FORMAT
    else:
        format = _TIMEFORMAT_LENGTH_MAP.get(len(time_string), None)

    if not format and raise_error_if_unknown:
        raise ValueError("Could not determine datetime format of '{}'".format(time_string))

    return format


def convert_spine_date(date_string, date_format=None):
    """
    Try to convert a Spine date using the passed format - if it fails - try the most
    appropriate
    """
    if date_format:
        try:
            dateObject = datetime.strptime(date_string, date_format)
            return dateObject
        except ValueError:
            pass

    date_format = _guess_common_datetime_format(date_string, raise_error_if_unknown=True)
    return datetime.strptime(date_string, date_format)


def time_now_as_string(date_format=TimeFormats.STANDARD_DATE_TIME_FORMAT):
    """
    Return the current date and time as a string in standard format
    """
    return now().strftime(date_format)


def now():
    """
    Utility to gets the current date and time.
    The intention is for this to be easier to replace when testing.
    :returns: a datetime representing the current date and time
    """
    return datetime.now()
