import base64
import sys
import zlib
from xml.sax.saxutils import unescape

from lxml import etree

from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.logger import EpsLogger


def apply_transform(transformer, xml_obj, request_params=None):
    """
    Return an XML object following application of an xslt transform
    """
    if not request_params:
        request_params = {}

    return transformer(xml_obj, **request_params)


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


def object_xml(serialised_xml, recover=None, huge_tree=False):
    """
    Reverse the serialisation process in serialise_xml
    """
    if serialised_xml is None:
        raise ValueError("serialisedXML was None")
    if recover:
        xml_security_rules = etree.XMLParser(
            load_dtd=False, resolve_entities=False, recover=recover, huge_tree=huge_tree
        )
    else:
        xml_security_rules = etree.XMLParser(
            load_dtd=False, resolve_entities=False, huge_tree=huge_tree
        )
    return etree.XML(serialised_xml, xml_security_rules)


def unzip_xml(squashedXML):
    """
    Given the serialised output from zipXML - return the XML root node object
    """
    return object_xml(zlib.decompress(base64.b64decode(squashedXML)))


def serialise_xml(xml, xml_declaration=True):
    """
    Given a root xml node, serialise the body to a string
    """
    return etree.tostring(xml, encoding="UTF-8", xml_declaration=xml_declaration)
