from eps_spine_shared.interactions.wdo import CreatePrescriptionWDO
from eps_spine_shared.validation.create import CreatePrescriptionValidator


class CreatePrescriptionContext:
    """
    Context object to be used by the create prescription process
    """

    def __init__(self):
        """
        Only standard prescriptions context variables required
        """
        self.local_validator: CreatePrescriptionValidator = None
        self.schematron_escaped_xml_body = None

    def set_working_copy_wdo(self, wdo: CreatePrescriptionWDO):
        """
        Create a copy of the WDO on the context
        """
        self.internal_id = wdo.getInternalID()
        self.message_id, self.conversation_id, self.response_guid, self.event_id = (
            wdo.getMessageIDs()
        )
        self.from_party_key, self.to_party_key = wdo.getPartyKeys()
        self.related_internal_ids = wdo.getRelatedInternalIDs()

        self.warning_list = []

        wdo.setProcessing()
        self.timestamp_rcv, self.timestamp_prc = wdo.getTimestamps()

        self.http_method = wdo.getHttpMethod()
        self.encoded_jwt = wdo.getJwt()
        self.request_url = wdo.getRequestUrl()

        self._setBody(wdo)
        self.wdo = wdo

    def _setBody(self, wdo: CreatePrescriptionWDO):
        """
        Set the request body on the object
        """
        if wdo.isExternalPrescriptionSearch() or wdo.isInternalJsonMessage():
            self.xml_body = None
        else:
            self.xml_body, self.schematron_escaped_xml_body = wdo.readRequestAsXML()
