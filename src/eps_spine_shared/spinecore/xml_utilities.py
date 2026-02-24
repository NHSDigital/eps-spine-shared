from xml.sax.saxutils import unescape

from lxml import etree


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
