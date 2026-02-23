class StatusMetadata(object):
    """
    Mappings for the status dictionary within a WDO
    """

    KEY_PROCESSATTEMPTS = "processAttempts"
    KEY_PROCESSTIME = "lastProcessTime"
    KEY_RCVTIME = "timestampRcv"
    KEY_RELATEDIDS = "relatedInternalIDs"
    KEY_RSPGUID = "responseGUID"
    KEY_OUTBOUNDINTERACTION = "outboundInteractionID"


class HL7Metadata(object):
    """
    Mappings for the HL7 dictionary within a WDO
    """

    KEY_EVENTID = "eventID"
    KEY_FROMASID = "fromASID"
    KEY_MESSAGEID = "messageID"


class EBXMLMetadata(object):
    """
    Mappings for the ebXML dictionary within a WDO
    """

    KEY_CONVID = "conversationID"
    KEY_TOPARTY = "toPartyID"
    KEY_FROMPARTY = "fromPartyID"
    KEY_MSGID = "messageID"
    KEY_SERVICE = "ebXMLService"
