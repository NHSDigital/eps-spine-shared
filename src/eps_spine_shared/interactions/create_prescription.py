from datetime import datetime, timezone

from eps_spine_shared.common.dynamodb_client import EpsDataStoreError
from eps_spine_shared.common.dynamodb_common import prescription_id_without_check_digit
from eps_spine_shared.common.dynamodb_datastore import EpsDynamoDbDataStore
from eps_spine_shared.common.prescription.record import PrescriptionRecord
from eps_spine_shared.common.prescription.repeat_dispense import RepeatDispenseRecord
from eps_spine_shared.common.prescription.repeat_prescribe import RepeatPrescribeRecord
from eps_spine_shared.common.prescription.single_prescribe import SinglePrescribeRecord
from eps_spine_shared.common.prescription.types import PrescriptionTreatmentType
from eps_spine_shared.errors import (
    EpsBusinessError,
    EpsErrorBase,
    EpsSystemError,
    ErrorBase1634,
    ErrorBaseInstance,
)
from eps_spine_shared.interactions.common import (
    apply_all_cancellations,
    build_working_record,
    check_for_pending_cancellations,
    check_for_replay,
    prepare_document_for_store,
)
from eps_spine_shared.logger import EpsLogger
from eps_spine_shared.validation.common import check_mandatory_items
from eps_spine_shared.validation.create import run_validations

MANDATORY_ITEMS = [
    "agentOrganization",
    "agentRoleProfileCodeId",
    "hcplOrgCode",
    "prescribingGpCode",
    "nhsNumber",
    "prescriptionID",
    "prescriptionTime",
    "prescriptionTreatmentType",
    "signedTime",
    "birthTime",
    "agentSdsRole",
    "hl7EventID",
]

CANCELLATION_BODY_XSLT = "cancellationDocument_to_cancellationResponse.xsl"
CANCELLATION_SUCCESS_RESPONSE_TEXT = "Prescription/Item was cancelled"
CANCELLATION_SUCCESS_RESPONSE_CODE = "0001"
CANCEL_SUCCESS_RESPONSE_CODE_SYSTEM = "2.16.840.1.113883.2.1.3.2.4.17.19"
CANCELLATION_SUCCESS_STYLESHEET = "CancellationResponse_PORX_MT135201UK31.xsl"


def validate_wdo(context, log_object: EpsLogger, internal_id):
    """
    Validate the WDO using the local validator
    """
    try:
        check_mandatory_items(context, MANDATORY_ITEMS)
        run_validations(context, datetime.now(tz=timezone.utc), log_object, internal_id)
    except EpsBusinessError as e:
        if isinstance(e.error_code, dict) and e.error_code["errorCode"] == "5000":
            raise EpsBusinessError(
                ErrorBaseInstance(
                    ErrorBase1634.UNABLE_TO_PROCESS, e.error_code["supplementaryInformation"]
                )
            ) from e
        else:
            raise e

    log_object.write_log("EPS0138", None, {"internalID": internal_id})


def audit_prescription_id(prescription_id, log_object: EpsLogger, internal_id, interaction_id):
    """
    Log out the inbound prescriptionID - to help with tracing issue by prescriptionID
    """
    log_object.write_log(
        "EPS0095a",
        None,
        {
            "internalID": internal_id,
            "prescriptionID": prescription_id,
            "interactionID": interaction_id,
        },
    )


def check_for_duplicate(
    context,
    prescription_id,
    internal_id,
    log_object: EpsLogger,
    data_store_object: EpsDynamoDbDataStore,
):
    """
    Check prescription store for existence of prescription
    """
    eps_record_id = prescription_id_without_check_digit(prescription_id)

    try:
        is_present = data_store_object.is_record_present(internal_id, eps_record_id)
        if not is_present:
            log_object.write_log(
                "EPS0003", None, {"internalID": internal_id, "eps_record_id": eps_record_id}
            )
            return
    except EpsDataStoreError as e:
        log_object.write_log(
            "EPS0130",
            None,
            {"internalID": internal_id, "eps_record_id": eps_record_id, "reason": e.error_topic},
        )
        raise EpsSystemError(EpsSystemError.IMMEDIATE_REQUEUE) from e

    # Prescription present - may be a pending cancellation
    try:
        record_returned = data_store_object.return_record_for_process(internal_id, eps_record_id)
    except EpsDataStoreError as e:
        log_object.write_log(
            "EPS0130",
            None,
            {"internalID": internal_id, "eps_record_id": eps_record_id, "reason": e.error_topic},
        )
        raise EpsSystemError(EpsSystemError.IMMEDIATE_REQUEUE) from e

    check_for_late_upload_request(record_returned, log_object, internal_id)

    context.replayDetected = check_for_replay(
        eps_record_id, record_returned["value"], context.messageID, context
    )

    if context.replayDetected:
        return

    context.recordToProcess = record_returned
    if not check_existing_record_real(eps_record_id, context):
        log_object.write_log(
            "EPS0128a", None, {"internalID": internal_id, "prescriptionID": context.prescriptionID}
        )

        raise EpsSystemError(EpsSystemError.MESSAGE_FAILURE)


def check_for_late_upload_request(existing_record, log_object: EpsLogger, internal_id):
    """
    It is possible for a cancellation to be received and then for an upload request to follow after over six months.
    In this case, the record having a next activity of purge results in an exception upon further processing.
    """
    record = PrescriptionRecord(log_object, internal_id)
    record.create_record_from_store(existing_record["value"])

    if record.is_next_activity_purge():
        prescription_id = record.return_prescription_id()
        log_object.write_log(
            "EPS0818", None, {"prescriptionID": prescription_id, "internalID": internal_id}
        )
        # Re-raise this as SpineBusinessError with equivalent errorCode from ErrorBase1722.
        raise EpsBusinessError(EpsErrorBase.EXISTS_WITH_NEXT_ACTIVITY_PURGE)


def check_existing_record_real(eps_record_id, context, log_object: EpsLogger, internal_id):
    """
    Presence of cancellation placeholder has already been confirmed, so now retrieve
    the pending cancellation for processing so that the new prescription may overwrite it.
    """
    vector_clock = context.recordToProcess["vectorClock"]
    log_object.write_log(
        "EPS0139",
        None,
        dict({"internalID": internal_id, "key": eps_record_id, "vectorClock": vector_clock}),
    )

    build_working_record(context, log_object, internal_id)

    isPrescription = context.epsRecord.check_real()
    if isPrescription:
        log_object.write_log(
            "EPS0128",
            None,
            dict({"internalID": internal_id, "prescriptionID": context.prescriptionID}),
        )
        # Re-raise this as SpineBusinessError with equivalent errorCode from ErrorBase1722.
        raise EpsBusinessError(EpsErrorBase.DUPLICATE_PRESRIPTION)

    # Pending Cancellation
    check_for_pending_cancellations(context)
    context.cancellationPlaceholderFound = True
    context.fetchedRecord = True
    return True


def create_initial_record(context, log_object: EpsLogger, internal_id):
    """
    Create a Prescriptions Record object, and set all initial values
    """

    if context.replayDetected:
        return

    treatment_type = context.prescriptionTreatmentType
    if treatment_type == PrescriptionTreatmentType.ACUTE_PRESCRIBING:
        record_object = SinglePrescribeRecord(log_object, internal_id)
    elif treatment_type == PrescriptionTreatmentType.REPEAT_PRESCRIBING:
        record_object = RepeatPrescribeRecord(log_object, internal_id)
    elif treatment_type == PrescriptionTreatmentType.REPEAT_DISPENSING:
        record_object = RepeatDispenseRecord(log_object, internal_id)
    else:
        log_object.write_log(
            "EPS0122", None, dict({"internalID": internal_id, "treatmentType": treatment_type})
        )
        raise EpsSystemError("messageFailure")

    record_object.create_initial_record(context)
    context.epsRecord = record_object
    context.epsRecord.set_initial_prescription_status(context.handleTime)

    if context.cancellationPlaceholderFound:
        apply_all_cancellations(context, True)


def prescriptions_workflow(
    context,
    log_object: EpsLogger,
    internal_id,
    prescription_id,
    interaction_id,
    doc_type,
    doc_ref_title,
    services_dict,
    deep_copy,
):
    """
    Workflow for creating a prescription
    """
    validate_wdo(context, log_object, internal_id)
    audit_prescription_id(prescription_id, log_object, internal_id, interaction_id)
    check_for_duplicate(prescription_id)
    prepare_document_for_store(
        context, doc_type, doc_ref_title, log_object, internal_id, services_dict, deep_copy
    )
    create_initial_record(context, log_object, internal_id)
