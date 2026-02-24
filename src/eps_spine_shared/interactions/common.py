import base64
import datetime
import sys
import uuid
import zlib

from dateutil import relativedelta

from eps_spine_shared.common import indexes
from eps_spine_shared.common.dynamodb_client import EpsDataStoreError
from eps_spine_shared.common.dynamodb_common import prescription_id_without_check_digit
from eps_spine_shared.common.dynamodb_datastore import EpsDynamoDbDataStore
from eps_spine_shared.common.prescription import fields
from eps_spine_shared.common.prescription.repeat_dispense import RepeatDispenseRecord
from eps_spine_shared.common.prescription.repeat_prescribe import RepeatPrescribeRecord
from eps_spine_shared.common.prescription.single_prescribe import SinglePrescribeRecord
from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.logger import EpsLogger
from eps_spine_shared.nhsfundamentals.time_utilities import TimeFormats
from eps_spine_shared.spinecore.base_utilities import handle_encoding_oddities
from eps_spine_shared.spinecore.changelog import PrescriptionsChangeLogProcessor
from eps_spine_shared.spinecore.xml_utilities import apply_transform, serialise_xml, unzip_xml

CANCEL_INTERACTION = "PORX_IN050102UK32"
EXPECTED_DELETE_WAIT_TIME_MONTHS = 18
EXPECTED_NOMINATED_RELEASE_DELETE_WAIT_TIME_DAYS = 36
SERVICE = "urn:nhs:names:services:mm"
TEST_PRESCRIBING_SITES = ["Z99901", "Z99902"]

PRESCRIPTION_EXPIRY_PERIOD_MONTHS = 6
REPEAT_DISP_EXPIRY_PERIOD_MONTHS = 12
DATA_CLEANSE_PERIOD_MONTHS = 6
WD_ACTIVE_EXPIRY_PERIOD_DAYS = 180
EXPIRED_DELETE_PERIOD = 90
CANCELLED_DELETE_PERIOD = 180
CLAIMED_DELETE_PERIOD = 36
NOT_DISPENSED_DELETE_PERIOD = 30
NOMINATED_DOWNLOAD_LEAD_DAYS = 7
NOTIFICATION_DELAY_PERIOD = 180
PURGED_DELETE_PERIOD = 365


def check_for_replay(
    eps_record_id, eps_record_retrieved, message_id, context, log_object: EpsLogger, internal_id
):
    """
    Check a retrieved record for the existence of the message GUID within the change log
    """
    try:
        change_log = eps_record_retrieved["changeLog"]
    except Exception as e:  # noqa: BLE001
        log_object.write_log(
            "EPS0004",
            sys.exc_info(),
            dict({"internalID": internal_id, "epsRecordID": eps_record_id}),
        )
        raise EpsSystemError("systemFailure") from e

    if message_id in change_log:
        log_object.write_log(
            "EPS0005",
            None,
            dict(
                {
                    "internalID": internal_id,
                    "epsRecordID": eps_record_id,
                    "changeLog": str(change_log),
                }
            ),
        )
        context.replayedChangeLog = change_log[message_id]
        return True

    return False


def build_working_record(context, log_object: EpsLogger, internal_id):
    """
    An epsRecord object needs to be created from the record extracted from the
    store.  The record-type should have been extracted - and this will be used to
    determine which class of object to create.

    Note that Pending Cancellation placeholders will not have a recordType, so
    default this to 'Acute' to allow processing to continue.
    """
    recordType = (
        "Acute"
        if "recordType" not in context.recordToProcess
        else context.recordToProcess["recordType"]
    )
    if recordType == "Acute":
        context.epsRecord = SinglePrescribeRecord(log_object, internal_id)
    elif recordType == "RepeatPrescribe":
        context.epsRecord = RepeatPrescribeRecord(log_object, internal_id)
    elif recordType == "RepeatDispense":
        context.epsRecord = RepeatDispenseRecord(log_object, internal_id)
    else:
        log_object.write_log(
            "EPS0133", None, dict({"internalID": internal_id, "recordType": str(recordType)})
        )
        raise EpsSystemError("developmentFailure")

    context.epsRecord.create_record_from_store(context.recordToProcess["value"])


def check_for_pending_cancellations(context):
    """
    Check for pending cancellations on the record, and bind them to context
    if they exist
    """
    pending_cancellations = context.epsRecord.return_pending_cancellations()
    if pending_cancellations:
        context.cancellationObjects = pending_cancellations


def prepare_document_for_store(
    context, doc_type, doc_ref_title, log_object: EpsLogger, internal_id, services_dict, deep_copy
):
    """
    For inbound messages to be stored in the datastore.
    The key for the object should be the internalID of the message.
    """
    if context.replayDetected:
        context.documentsToStore = None
        return

    if (
        hasattr(context, "prescriptionID") and context.prescriptionID
    ):  # noqa: SIM108 - More readable as is
        presc_id = context.prescriptionID
    else:
        presc_id = "NominatedReleaseRequest_" + internal_id

    document_ref = internal_id

    setattr(context, doc_ref_title, document_ref)

    documentToStore = {}
    documentToStore["key"] = document_ref
    documentToStore["value"] = extract_body_to_store(
        presc_id, doc_type, context, services_dict, deep_copy, log_object, internal_id
    )
    documentToStore["index"] = create_index_for_document(context, doc_ref_title, presc_id)
    documentToStore["vectorClock"] = None
    context.documentsToStore.append(documentToStore)
    context.documentReferences.append(document_ref)

    log_object.write_log(
        "EPS0125",
        None,
        {"internalID": internal_id, "type": doc_type, "key": document_ref, "vectorClock": "None"},
    )


def extract_body_to_store(
    prescription_id,
    doc_type,
    context,
    services_dict,
    deep_copy,
    log_object: EpsLogger,
    internal_id,
    base_document=None,
):
    """
    Extract the inbound message body and prepare as a document for the epsDocument
    store
    """
    try:
        if base_document is None:
            base_document = context.xmlBody

        deep_copy_transform = services_dict["Style Sheets"][deep_copy]
        compressed_document = zlib.compress(str(deep_copy_transform(base_document)))
        encoded_document = base64.b64encode(compressed_document)
        value = {}
        value["content"] = encoded_document
        value["content type"] = "xml"
        value["id"] = prescription_id
        value["type"] = doc_type
    except Exception as e:  # noqa: BLE001
        log_object.write_log(
            "EPS0014b", sys.exc_info(), {"internalID": internal_id, "type": doc_type}
        )
        raise EpsSystemError(EpsSystemError.MESSAGE_FAILURE) from e
    return value


def create_index_for_document(context, doc_ref_title, prescription_id):
    """
    Index required is prescriptionID should there be a need to search for document by prescription ID
    Other index is storeTimeByDocRefTitle - this allows for documents of a certain
    type to be queried by the range of the document age (e.g. searching for all
    Claim Notices which have been present for more than 48 hours)
    """
    store_time = context.handleTime.strftime(TimeFormats.STANDARD_DATE_TIME_FORMAT)

    default_delta = relativedelta(months=+EXPECTED_DELETE_WAIT_TIME_MONTHS)
    nominated_release_delta = relativedelta(days=+EXPECTED_NOMINATED_RELEASE_DELETE_WAIT_TIME_DAYS)
    delete_date_obj_delta = (
        nominated_release_delta
        if doc_ref_title == "NominatedReleaseRequestMsgRef"
        else default_delta
    )

    delete_date_obj = context.handleTime + delete_date_obj_delta
    delete_date = delete_date_obj.strftime(TimeFormats.STANDARD_DATE_FORMAT)

    index_dict = {}
    index_dict[indexes.INDEX_PRESCRIPTION_ID] = [prescription_id]
    index_dict[indexes.INDEX_STORE_TIME_DOC_REF_TITLE] = [doc_ref_title + "_" + store_time]
    index_dict[indexes.INDEX_DELETE_DATE] = [delete_date]

    return index_dict


def log_pending_cancellation_event(context, start_issue_number, log_object: EpsLogger, internal_id):
    """
    Generate a pending cancellation eventLog entry
    """
    if not hasattr(context, "responseParameters"):
        context.responseParameters = {}
        context.responseParameters["cancellationResponseText"] = "Subsequent cancellation"
        context.responseParameters["timeStampSent"] = datetime.datetime.now().strftime(
            TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        context.responseParameters["messageID"] = context.messageID

    context.responseDetails = {}
    context.responseDetails[PrescriptionsChangeLogProcessor.RSP_PARAMS] = context.responseParameters
    errorResponseStylesheet = "generateHL7MCCIDetectedIssue.xsl"
    cancellationBodyXSLT = "cancellationRequest_to_cancellationResponse.xsl"
    responseXSLT = [errorResponseStylesheet, cancellationBodyXSLT]
    context.responseDetails[PrescriptionsChangeLogProcessor.XSLT] = responseXSLT
    context.epsRecord.increment_scn()
    create_event_log(context, log_object, internal_id, start_issue_number)
    context.epsRecord.add_event_to_change_log(internal_id, context.eventLog)


def create_event_log(context, log_object: EpsLogger, internal_id, instance_id=None):
    """
    Create the change log for this event. Will be placed on change log in record
    under a key of the messageID
    """
    if context.replayDetected:
        return

    if not instance_id:
        if context.epsRecord:
            instance_id = context.epsRecord.return_current_instance()
        else:
            log_object.write_log("EPS0673", None, {"internalID": internal_id})
            instance_id = "NotAvailable"
    context.instanceID = instance_id

    if context.epsRecord:
        eventLog = PrescriptionsChangeLogProcessor.log_for_domain_update(context, internal_id)
        context.eventLog = eventLog


def handle_missing_cancellation_document(cancellation_obj, log_object: EpsLogger, internal_id):
    """
    In some cases there has been missing cancellation object references - in
    particular post migration.  Ignore generating a response in this case - but raise
    an error
    """
    reasons = cancellation_obj.get(fields.FIELD_REASONS)
    if not reasons:
        log_object.write_log("EPS0650", None, {"internalID": internal_id})
        return
    for reason in reasons:
        log_object.write_log("EPS0651", None, {"internalID": internal_id, "reason": str(reason)})


def return_cancellation_document(context, cancellation_document_key):
    """
    Use the cancellationDocumentKey to retrieve the cancelation document from the
    document store, then dencode and decompress the content and return the xmlPayload
    """
    zipped_encoded_doc = retrieve_eps_document_by_key(context, cancellation_document_key)

    return unzip_xml(zipped_encoded_doc)


def retrieve_eps_document_by_key(
    context,
    document_key,
    datastore_object: EpsDynamoDbDataStore,
    log_object: EpsLogger,
    internal_id,
):
    """
    Fetch from the document store and add to the context
    """
    log_object.write_log("EPS0144", None, {"internalID": internal_id, "documentKey": document_key})

    try:
        doc_object = datastore_object.return_document_for_process(internal_id, document_key)
    except EpsDataStoreError as e:
        log_object.write_log("EPS0142", None, {"internalID": internal_id, "reason": e.error_topic})
        raise EpsSystemError(EpsSystemError.SYSTEM_FAILURE) from e

    if str(context.prescriptionID) != str(doc_object["id"]):
        log_object.write_log(
            "EPS0143",
            None,
            {
                "internalID": internal_id,
                "msgPrescID": str(context.prescriptionID),
                "docPrescID": str(doc_object["id"]),
            },
        )
        raise EpsSystemError(EpsSystemError.MESSAGE_FAILURE)

    return doc_object["content"]


def generate_cancellation_payload(
    cancellation_doc,
    services_dict,
    cancellation_body_xslt,
    response_text,
    response_code,
    response_code_system,
    log_object: EpsLogger,
    internal_id,
):
    """
    There is an additional transformation required to prepare the cancellation
    response from the inbound cancellation request.

    There are two transformations: one to create the payload from the inbound request
    and then one to wrap the payload in a standard HL7 format, this method is just to
    create the payload.
    """
    stylesheets = services_dict["Style Sheets"]
    response_generator = stylesheets[cancellation_body_xslt]

    cancellation_msg = cancellation_doc

    success_text = '"' + response_text + '"'
    success_code = '"' + response_code + '"'
    success_code_system = '"' + response_code_system + '"'

    response_params = {}
    response_params["cancellationResponseText"] = success_text
    response_params["cancellationResponseCode"] = success_code
    response_params["cancellationResponseCodeSystem"] = success_code_system

    try:
        return apply_transform(response_generator, cancellation_msg, response_params)
    except SystemError as system_error:
        log_object.write_log("EPS0042", sys.exc_info(), dict({"internalID": internal_id}))
        raise EpsSystemError("developmentFailure") from system_error


def generate_complete_cancellation_message(
    hl7,
    core_body_xml,
    response_parameters,
    context,
    services_dict,
    cancellation_success_stylesheet,
    log_object: EpsLogger,
    internal_id,
):
    """
    This is the final stage of message generation and takes either a success or
    failure partial payload and puts it into an outbound message with valid
    response parameters.
    """
    final_generator = services_dict["Style Sheets"][cancellation_success_stylesheet]

    service_asid = services_dict["Service ASID"]
    response_guid = str(uuid.uuid4()).upper()

    response_parameters["messageID"] = '"' + response_guid + '"'
    response_parameters["refToEventID"] = '"' + context.messageID + '"'

    response_parameters["refToMessageID"] = '"' + context.messageID + '"'
    response_parameters["timeStampAck"] = '"' + context.timestampRcv + '"'
    response_parameters["timeStampSent"] = '"' + context.timestampPrc + '"'
    response_parameters["fromASID"] = '"' + context.toASID + '"'
    response_parameters["toASID"] = '"' + context.fromASID + '"'
    response_parameters["serviceASID"] = '"' + service_asid + '"'
    response_parameters["interactionID"] = '"' + hl7["interactionID"] + '"'

    try:
        final_xml = apply_transform(final_generator, core_body_xml, response_parameters)
    except SystemError as system_error:
        log_object.write_log("EPS0042", sys.exc_info(), {"internalID": internal_id})
        raise EpsSystemError("developmentFailure") from system_error

    message_body = serialise_xml(final_xml)

    response_obj = {}
    response_obj["responseXML"] = message_body
    response_obj["Response Parameters"] = response_parameters

    return response_obj


def apply_all_cancellations(
    context,
    log_object: EpsLogger,
    internal_id,
    was_pending=False,
    start_issue_number=None,
    send_subsequent_cancellation=True,
):
    """
    Apply all the cancellations on the context (these should normally be fetched from
    the record)
    """
    for cancellation_obj in context.cancellationObjects:
        [cancel_id, issues_updated] = context.epsRecord.apply_cancellation(
            cancellation_obj, start_issue_number
        )
        log_object.write_log(
            "EPS0266",
            None,
            {
                "internalID": internal_id,
                "prescriptionID": context.prescriptionID,
                "issuesUpdated": issues_updated,
                "cancellationID": cancel_id,
            },
        )

        if not is_death(cancellation_obj, log_object, internal_id):
            if was_pending and send_subsequent_cancellation:
                context.cancellationObjects.append(cancellation_obj)


def is_death(cancellation_obj, log_object: EpsLogger, internal_id):
    """
    Returns True if this is a Death Notification
    """
    reasons = cancellation_obj.get(fields.FIELD_REASONS)

    if not reasons:
        return False

    for reason in reasons:
        if str(handle_encoding_oddities(reason)).lower().find("notification of death") != -1:
            log_object.write_log(
                "EPS0652", None, {"internalID": internal_id, "reason": str(reason)}
            )
            return True

    return False


def prepare_record_for_store(
    context, log_object: EpsLogger, internal_id, fetched_record=False, key=None
):
    """
    Prepare the record to be stored:
    1 - Check there is a need to store (not replay)
    2 - Set the key
    3 - Add change log to record
    4 - Set the index (including calculation of nextActivity)
    5 - Set the value (from the epsRecord object)

    fetched_record indicates whether the recordToStore is based on one retrieved by
    this interactionWorker process.  If it is, there will be a vectorClock, which
    is required in order for the updateApplier to use as an optimistic 'lock'

    key if passed will be used as the key to be stored (otherwise generate from
    context.prescriptionID)
    """
    if context.replayDetected:
        context.recordToStore = None
        return

    context.recordToStore = {}

    if not key:
        presc_id = prescription_id_without_check_digit(context.prescriptionID)
        context.recordToStore["key"] = presc_id
    else:
        context.recordToStore["key"] = key

    index_dict = create_record_index(context, log_object, internal_id)
    context.recordToStore["index"] = index_dict
    context.epsRecord.add_index_to_record(index_dict)
    context.epsRecord.add_document_references(context.documentReferences)

    context.epsRecord.increment_scn()
    context.epsRecord.add_event_to_change_log(context.messageID, context.eventLog)

    context.recordToStore["value"] = context.epsRecord.return_record_to_be_stored()

    if fetched_record:
        context.recordToStore["vectorClock"] = context.recordToProcess["vectorClock"]
    else:
        context.recordToStore["vectorClock"] = None

    context.recordToStore["recordType"] = context.epsRecord.record_type

    log_object.write_log(
        "EPS0125",
        None,
        {
            "internalID": internal_id,
            "type": "prescriptionRecord",
            "key": context.recordToStore["key"],
            "vectorClock": "None",
        },
    )


def create_record_index(context, log_object: EpsLogger, internal_id):
    """
    Create the index values to be used when storing the epsRecord.
    There may be separate index terms for each individual instance
    (but only unique index terms for the prescription should be returned).
    """
    indexMaker = indexes.EpsIndexFactory(
        log_object, internal_id, TEST_PRESCRIBING_SITES, get_nad_references()
    )
    return indexMaker.build_indexes(context)


def get_nad_references():
    """
    Create a reference dictionary of information
    for use during next activity date calculation
    """
    return {
        "prescriptionExpiryPeriod": relativedelta(months=+PRESCRIPTION_EXPIRY_PERIOD_MONTHS),
        "repeatDispenseExpiryPeriod": relativedelta(months=+REPEAT_DISP_EXPIRY_PERIOD_MONTHS),
        "dataCleansePeriod": relativedelta(months=+DATA_CLEANSE_PERIOD_MONTHS),
        "withDispenserActiveExpiryPeriod": relativedelta(days=+WD_ACTIVE_EXPIRY_PERIOD_DAYS),
        "expiredDeletePeriod": relativedelta(days=+EXPIRED_DELETE_PERIOD),
        "cancelledDeletePeriod": relativedelta(days=+CANCELLED_DELETE_PERIOD),
        "claimedDeletePeriod": relativedelta(days=+CLAIMED_DELETE_PERIOD),
        "notDispensedDeletePeriod": relativedelta(days=+NOT_DISPENSED_DELETE_PERIOD),
        "nominatedDownloadDateLeadTime": relativedelta(days=+NOMINATED_DOWNLOAD_LEAD_DAYS),
        "notificationDelayPeriod": relativedelta(days=+NOTIFICATION_DELAY_PERIOD),
        "purgedDeletePeriod": relativedelta(days=+PURGED_DELETE_PERIOD),
    }
