import sys
from xml.sax.saxutils import unescape

from lxml import etree

from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.logger import EpsLogger


def apply_transform(transformer, xml_object, request_parameters=None):
    """
    Return an XML object following application of an xslt transform
    """
    if not request_parameters:
        request_parameters = {}

    return transformer(xml_object, **request_parameters)


def apply_transform_catch_error(
    log_object: EpsLogger, internal_id, transformer, xml_object, request_parameters=None
):
    """
    Raise an EpsSystemError if the transform hits any issues
    """
    try:
        return apply_transform(transformer, xml_object, request_parameters)
    except etree.XSLTApplyError as e:
        log_object.write_log(
            "PUP0197", sys.exc_info(), {"internalID": internal_id, "message": str(e)}
        )
        raise EpsSystemError(EpsSystemError.SYSTEM_FAILURE) from e


def unescape_string(sample_string):
    """
    Unescape sample strings
    """
    return unescape(sample_string)
