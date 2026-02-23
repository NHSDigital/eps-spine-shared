from datetime import datetime

from eps_spine_shared.interactions.metadata import EBXMLMetadata, HL7Metadata, StatusMetadata
from eps_spine_shared.nhsfundamentals.time_utilities import TimeFormats

NOT_DEFINED = "NOT_DEFINED"


class CreatePrescriptionWDO:
    """
    WDO from the context of the event processor
    """

    KEY_EBXML = "ebXML"
    KEY_HL7 = "hl7"
    KEY_STATUS = "status"
    LPT_DATETIME_FORMAT = TimeFormats.STANDARD_DATE_TIME_FORMAT

    def __init__(self):
        self.ebXML = None
        self.hl7 = None
        self.status = None

    def getPartyKeys(self):
        """
        Return the To and From PartyKeys from the ebXML wrapper
        """
        return [self.ebXML[EBXMLMetadata.KEY_FROMPARTY], self.ebXML[EBXMLMetadata.KEY_TOPARTY]]

    def getMessageIDs(self):
        """
        Return the HL7 MessageID, ebxml Conversation ID and the HL7 Response GUID
        """
        _eventID = self.hl7.get(HL7Metadata.KEY_EVENTID, None)
        return [
            self.hl7[HL7Metadata.KEY_MESSAGEID],
            self.ebXML[EBXMLMetadata.KEY_CONVID],
            self.status[StatusMetadata.KEY_RSPGUID],
            _eventID,
        ]

    def getRelatedInternalIDs(self):
        """
        Return any related internalIDs (IDs of messages which may have prompted the
        creation of this WDO
        """
        return self.status[StatusMetadata.KEY_RELATEDIDS]

    def getTimestamps(self):
        """
        Return the receipt and process timestamps for the work
        """
        return [
            self.status[StatusMetadata.KEY_RCVTIME],
            self.status[StatusMetadata.KEY_PROCESSTIME],
        ]

    def setProcessing(self, processStartTime=None):
        """
        Indicate that processing has started (up the process attempts count and set the
        process time)
        """
        self.status[StatusMetadata.KEY_PROCESSATTEMPTS] += 1
        if not processStartTime:
            processStartTime = datetime.now()
        processStartTimeString = processStartTime.strftime(self.LPT_DATETIME_FORMAT)
        if not self.status[StatusMetadata.KEY_PROCESSTIME]:
            self.status[StatusMetadata.KEY_PROCESSTIME] = processStartTimeString
