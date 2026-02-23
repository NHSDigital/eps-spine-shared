import uuid
import zlib

import simplejson

from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.logger import EpsLogger


class Notification:
    """
    Parent class for notifications
    """

    KEY_FIELDNAME = "key"
    PAYLOAD_FIELDNAME = "payload"
    EXCHANGE_FIELDNAME = "exchange"
    TOPIC_FIELDNAME = "topic"
    REPLAY_FIELDNAME = "potentialReplay"
    HL7 = "hl7"
    EB_XML = "ebXML"
    STATUS = "status"
    LOGGER = "log_reference"
    RELIABLE = "reliable"
    WDO_ID = "wdoID"
    SKIP_DELAY = "skipDelay"
    RETRY_PROFILE = "retryProfile"

    # Flag to retain internalID when notification is set as reliable
    RETAIN_INTERNAL_ID = "retainInternalId"

    # ASID to be used by any nomination process should it wish to generate messages
    NOMINATION_ASID = "990101234567"

    def __init__(self, replay_detected=False):
        """
        There are five basic parts of the notification message
        key - an ID for the notification
        payload - the body for the notification - will be defined in a child class
        exchange - the exchange name to which it should be published
        topic - the topic name to which it will be published
        potentialReplay - an indicator that the notification may have been prompted
        by a replayed message, may prompt the consuming application to take additional
        action during processing
        """
        self.key = None
        self.payload = None
        self.exchange = "NOTIFICATIONS"
        self.topic = "notification"
        self.potential_replay = replay_detected
        self.hl7 = {}
        self.ebxml = {}
        self.status = {}
        self.log_reference = None
        self.reliable = False
        self.retry_profile = None
        self.retain_internal_id = False

    def load_serialised_notification(self, serialised_notification):
        """
        Convert a string-based representation into a working object
        """
        notification = simplejson.loads(serialised_notification)
        self.create_from_dictionary(notification)

    def get_internal_id(self):
        """
        Used by standard work publisher
        """
        return self.key

    def serialise_to_json(self, compress=False):
        """
        Provide a string-based representation (using json) of the Notification
        """
        notification = self.return_dictionary()
        serialised_notification = simplejson.dumps(notification)
        if compress:
            return zlib.compress(serialised_notification)
        return serialised_notification

    def return_dictionary(self):
        """
        Convert the notification into a dictionary
        """
        notification = {}
        notification[self.KEY_FIELDNAME] = self.key
        notification[self.PAYLOAD_FIELDNAME] = self.payload
        notification[self.EXCHANGE_FIELDNAME] = self.exchange
        notification[self.TOPIC_FIELDNAME] = self.topic
        notification[self.REPLAY_FIELDNAME] = self.potential_replay
        notification[self.HL7] = self.hl7
        notification[self.EB_XML] = self.ebxml
        notification[self.STATUS] = self.status
        notification[self.LOGGER] = self.log_reference
        notification[self.RELIABLE] = self.reliable
        notification[self.RETRY_PROFILE] = self.retry_profile
        notification[self.RETAIN_INTERNAL_ID] = self.retain_internal_id
        return notification

    def create_from_dictionary(self, notification):
        """
        Write information from dictionary to object attributes
        """
        self.key = notification[self.KEY_FIELDNAME]
        self.payload = notification[self.PAYLOAD_FIELDNAME]
        self.exchange = notification[self.EXCHANGE_FIELDNAME]
        self.topic = notification[self.TOPIC_FIELDNAME]
        self.potential_replay = notification[self.REPLAY_FIELDNAME]
        self.hl7 = notification[self.HL7]
        self.ebxml = notification[self.EB_XML]
        self.status = notification[self.STATUS]
        self.log_reference = notification.get(self.LOGGER)
        self.reliable = notification.get(self.RELIABLE)
        self.retry_profile = notification.get(self.RETRY_PROFILE)
        self.retain_internal_id = notification.get(self.RETAIN_INTERNAL_ID)

    def set_key(self, key=None):
        """
        Use a UUID if no key is passed in
        """
        if key:
            self.key = key
        else:
            self.key = str(uuid.uuid4()).upper()

        return self.key

    def get_key(self):
        """
        Returns the Key
        """
        return self.key

    def set_payload(self, payload=None):
        """
        Set the payload
        """
        self.payload = payload

    @property
    def nhs_number(self):
        """
        Return the NHS Number that this notification is relating to if possible. Otherwise return None.
        """
        return self.payload.get("nhsNumber") or self.payload.get("Patient NHS Number")

    def write_log(self, log_object: EpsLogger):
        """
        Log the notification - this is used when there is a `logger` set - which should be the log reference to use
        when writing the log
        """
        if self.log_reference:
            log_object.write_log(self.log_reference, None, self.payload)

    @property
    def wdo_id(self):
        """
        property getter for payload WDO ID
        It's expected the notification is marked reliable if using this property.
        """
        return self.payload.get(self.WDO_ID, None)

    @wdo_id.setter
    def wdo_id(self, value):
        """
        property setter for payload WDO ID
        It's expected the notification is marked reliable if using this property.
        """
        if not self.reliable:
            raise EpsSystemError(
                EpsSystemError.DEVELOPMENT_FAILURE, "Notification is not flagged as reliable"
            )

        self.payload[self.WDO_ID] = value

    @property
    def skip_delay(self):
        """
        Property getter for skip_delay.
        """
        return self.payload.get(self.SKIP_DELAY, None)

    @skip_delay.setter
    def skip_delay(self, value):
        """
        Property setter for skip_delay.
        """
        self.payload[self.SKIP_DELAY] = value


class SubsequentCancellationResponse(Notification):
    """
    Notification to be used within the prescriptions service to allow
    the successful processing of one or more pending cancellation responses to
    trigger the subsequent cancellation response message.
    """

    CR_TOPIC = "prescriptions.SubsequentCancellationResponseNotification"
    PAYLOAD_NAME = "Pending Cancellation Object"

    def __init__(self, replay_detected=False):
        """
        The change may be re-applied, so generate a unique key
        """
        super().__init__(replay_detected)
        self.key = self.set_key()
        self.topic = self.CR_TOPIC

    def set_payload(self, cancellation_object):
        """
        Payload should comprise of:
        Context
        Pending Cancellation Object
        Cancellation Response Code
        """
        self.payload = {}
        self.payload["Context"] = self.topic
        self.payload[self.PAYLOAD_NAME] = cancellation_object
