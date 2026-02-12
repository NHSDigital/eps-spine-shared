import datetime
import sys
import traceback

from eps_spine_shared.common.prescription.statuses import LineItemStatus
from eps_spine_shared.errors import (
    EpsBusinessError,
    EpsSystemError,
    EpsValidationError,
    ErrorBase1634,
    ErrorBaseInstance,
)
from eps_spine_shared.logger import EpsLogger
from eps_spine_shared.nhsfundamentals.checksum_util import ChecksumUtil
from eps_spine_shared.nhsfundamentals.mim_rules import is_nhs_number_valid
from eps_spine_shared.nhsfundamentals.time_utilities import (
    StopWatch,
    TimeFormats,
    convert_international_time,
)
from eps_spine_shared.spinecore.schematron import SimpleReportSchematronApplier
from eps_spine_shared.validation import message_vocab
from eps_spine_shared.validation.constants import (
    MAX_LINEITEMS,
    MAX_PRESCRIPTIONREPEATS,
    NOT_DISPENSED,
    PERFORMER_TYPELIST,
    R1,
    REGEX_ALPHANUMERIC8,
    REGEX_GUID,
    REGEX_INTEGER12,
    REGEX_NUMERIC15,
    REGEX_PRESCRID,
    REGEX_PRESCRIDR1,
    REGEX_PRESCRIDR1_ALT,
    REGEX_ROLECODE,
    STATUS_ACUTE,
    STATUS_REPEAT,
    WITHDRAW_RSONLIST,
    WITHDRAW_TYPELIST,
)


class ValidationContext(object):
    """
    Used to hold context of a validation process
    """

    def __init__(self, msg_output=None):
        """
        Context of an individual validation run
        """
        # This dictionary will hold the outputs of the schematron once the schematron
        # validator has been applied to the xmlBody
        self.msg_output = {}
        if msg_output:
            self.msg_output = msg_output
        # Output fields should be set within the child class to determine what needs
        # to be copied back into the workerContext
        self.output_fields = set()


class PrescriptionsValidator:
    """
    General validation class for prescription service
    """

    def __init__(self, interaction_worker):
        """
        Setup matching functions to be used within prescriptions, as well as common
        variables to be matched against
        """
        self.log_object: EpsLogger = interaction_worker.log_object
        self.compiled_style_sheets = interaction_worker.services_dict["Style Sheets"]
        self.json_schemas = interaction_worker.services_dict["JSON Schemas"]
        self.internal_id = None
        self.validation_output_dict = {}
        self.sync_timer = StopWatch()
        self.xml_body = None

        self.mandatory_extracted_items = interaction_worker.mandatory_extracted_items
        self.interaction_id = interaction_worker.interaction_id
        self.validator_sheet1 = interaction_worker.stage_1_validator
        self.validator_sheet2 = interaction_worker.stage_2_validator
        self.checksum_util = ChecksumUtil(self.log_object)

        # InternalID and xmlBody are unique to each run, and are re-set each time
        # the validate method is called
        self.xml_body = None
        self.internal_id = None

    # Investigate change in ordering of this function JIRA SPII-24327
    def validate(self, xml_body, internal_id, worker_context):
        """
        Run the actual validation, and return with:
        [success, expected, errorCode]

        The output_fields are added as the workflow progresses - and the attributes in the
        output fields are transferred to the context object (of the message worker)
        """
        validation_context = ValidationContext()
        self.xml_body = xml_body
        self.internal_id = internal_id

        if self.validator_sheet1:
            self.schematron_validate(self.validator_sheet1, validation_context)
        if self.validator_sheet2:
            self.schematron_validate(self.validator_sheet2, validation_context)
        self.output_validate(validation_context, worker_context.handle_time)
        self.commit_output_fields_to_context(validation_context, worker_context)

    def commit_output_fields_to_context(
        self, validation_context: ValidationContext, worker_context
    ):
        """
        Add all output_fields to the context
        """
        for field in validation_context.output_fields:
            if not hasattr(worker_context, field):
                self.log_object.write_log(
                    "EPS0324", None, dict({"internalID": self.internal_id, "attributeName": field})
                )
                raise EpsSystemError(EpsSystemError.DEVELOPMENT_FAILURE)
            setattr(worker_context, field, validation_context.msg_output.get(field))

    def schematron_validate(self, validator_sheet, validation_context: ValidationContext = None):
        """
        Parse message through schematron xsl to validate and extract
        - validate basic message structure (issues returned as faults - the fault should
        be a json object, that will transfer to a dictionary)
        - It is mandatory for the fault dictionary to contain an errorCode that is mapped
        into the errorBase for the service
        - extract values required (issues returned as reports in form report|key|value)
        """

        if not validator_sheet:
            self.log_object.write_log("MWS0038a", None, dict({"internalID": self.internal_id}))
            raise EpsSystemError(EpsSystemError.DEVELOPMENT_FAILURE)

        update_validate = self.compiled_style_sheets[validator_sheet]
        schematron_applier = SimpleReportSchematronApplier(
            update_validate, self.internal_id, self.log_object
        )

        try:
            schematron_output = schematron_applier.apply_schematron(self.xml_body)
            validation_context.msg_output.update(schematron_output)
        except EpsBusinessError:
            self.log_object.write_log(
                "MWS0038",
                None,
                dict({"internalID": self.internal_id, "schematron": validator_sheet}),
            )
            raise

        self.log_object.write_log(
            "MWS0040", None, dict({"internalID": self.internal_id, "schematron": validator_sheet})
        )

    def output_validate(self, validation_context: ValidationContext = None, handle_time=None):
        """
        All validation failures (of the message format itself) have an error code
        of 5000.  However, to help clarify they should be supported by supplementary
        information (this is sparsely provided in Spine I - and so information has been
        re-written for Spine II)
        """
        try:
            self.check_mandatory_items(validation_context)
            self.run_validations(validation_context, handle_time)
            self.log_object.write_log("EPS0001", None, {"internalID": self.internal_id})
        except EpsValidationError as e:
            supp_info = e.supp_info
            error_detail = ErrorBaseInstance(ErrorBase1634.UNABLE_TO_PROCESS, supp_info)
            _lastLogLine = traceback.format_tb(sys.exc_info()[2])
            self.log_object.write_log(
                "EPS0002",
                None,
                {
                    "internalID": self.internal_id,
                    "interactionID": self.interaction_id,
                    "errorDetails": supp_info,
                    "lastLogLine": _lastLogLine,
                },
            )
            raise EpsBusinessError(error_detail) from e

    def check_mandatory_items(self, context: ValidationContext):
        """
        Check for mandatory keys in the schematron output
        """
        for mandatory_key in self.mandatory_extracted_items:
            if mandatory_key not in context.msg_output:
                raise EpsValidationError("Mandatory field " + mandatory_key + " missing")

    def run_validations(self, validation_context: ValidationContext, handle_time):
        """
        Select which individual validation functions to apply
        """
        pass

    def _check_receiver_org(self, context: ValidationContext):
        """
        Check the receiver organization
        """
        if not REGEX_ALPHANUMERIC8.match(context.msg_output[message_vocab.RECEIVERORG]):
            raise EpsValidationError(message_vocab.RECEIVERORG + " has invalid format")
        context.output_fields.add(message_vocab.RECEIVERORG)

    def _set_receiver_org(self, context: ValidationContext):
        """
        Set the receiver organization from the agentOrganisation
        """
        context.msg_output[message_vocab.RECEIVERORG] = context.msg_output[message_vocab.AGENTORG]

    def _check_unattended_request(self, context: ValidationContext):
        """
        Check for unattended request
        """
        if not context.msg_output[message_vocab.UNATTENDEDREQUEST]:
            return False
        if context.msg_output[message_vocab.UNATTENDEDREQUEST] == "true":
            return True
        return False

    def _check_organisation_and_roles(self, context: ValidationContext):
        """
        Check the organisation and role information is of the correct format
        Requires:
            agent_organization
            agent_role_profile_code_id
            agent_sds_role
        """
        if not REGEX_ALPHANUMERIC8.match(context.msg_output[message_vocab.AGENTORG]):
            raise EpsValidationError(message_vocab.AGENTORG + " has invalid format")
        if not REGEX_NUMERIC15.match(context.msg_output[message_vocab.ROLEPROFILE]):
            self.log_object.write_log(
                "EPS0323b",
                None,
                {
                    "internalID": self.internal_id,
                    "agent_sds_role_profile_id": context.msg_output[message_vocab.ROLEPROFILE],
                },
            )
            # MB: Relax validation in Live as pert of go-live work
            # raise EpsValidationError(message_vocab.ROLEPROFILE + ' has invalid format')

        if context.msg_output[message_vocab.ROLE] == "NotProvided":
            self.log_object.write_log("EPS0330", None, dict({"internalID": self.internal_id}))
        elif not REGEX_ROLECODE.match(context.msg_output[message_vocab.ROLE]):
            self.log_object.write_log(
                "EPS0323",
                None,
                dict(
                    {
                        "internalID": self.internal_id,
                        "agent_sds_role": context.msg_output[message_vocab.ROLE],
                    }
                ),
            )

        context.output_fields.add(message_vocab.AGENTORG)
        context.output_fields.add(message_vocab.ROLEPROFILE)
        context.output_fields.add(message_vocab.ROLE)

    def _check_role_profile(self, context: ValidationContext):
        """
        Check the organisation and role information is of the correct format
        Requires:
            agentRoleProfilecodeId
            agentSdsRole
        """
        if not REGEX_NUMERIC15.match(context.msg_output[message_vocab.ROLEPROFILE]):
            self.log_object.write_log(
                "EPS0323b",
                None,
                {
                    "internalID": self.internal_id,
                    "agentSdsRoleProfileId": context.msg_output[message_vocab.ROLEPROFILE],
                },
            )
            # MB: Relax validation in Live as pert of go-live work
            # raise EpsValidationError(message_vocab.ROLEPROFILE + ' has invalid format')

    def _set_component_count(self, context: ValidationContext):
        """
        Check that the component count is a non-zero integer
        """
        try:
            if int(context.msg_output[message_vocab.COMPONENTCOUNT]) <= 0:
                raise ValueError
        except ValueError as value_error:
            raise EpsValidationError(
                message_vocab.COMPONENTCOUNT + " has invalid format"
            ) from value_error
        context.output_fields.add(message_vocab.COMPONENTCOUNT)

    def _check_hl7_event_id(self, context: ValidationContext):
        """
        Check a HL7 ID is in a valid UUID format
        Requires:
            hl7EventID
        """
        if not REGEX_GUID.match(context.msg_output[message_vocab.HL7EVENTID]):
            raise EpsValidationError(message_vocab.HL7EVENTID + " has invalid format")
        context.output_fields.add(message_vocab.HL7EVENTID)

    def _check_nhs_number(self, context: ValidationContext):
        """
        Check an nhs number is of a valid format
        Requires:
            nhsNumber
        """
        if is_nhs_number_valid(context.msg_output[message_vocab.PATIENTID]):
            context.output_fields.add(message_vocab.PATIENTID)
        else:
            supp_info = message_vocab.PATIENTID + " is not valid"
            raise EpsValidationError(supp_info)

    def _check_attribute_present(self, context: ValidationContext, attributeName):
        """
        Check that the attribute name is present in the message output and add to field
        """
        if attributeName in context.msg_output:
            context.output_fields.add(attributeName)
        else:
            raise EpsSystemError(EpsSystemError.DEVELOPMENT_FAILURE)

    def _check_prescription_id(self, context: ValidationContext):
        """
        Check the format of a prescription ID and that it has the correct checksum
        """
        if not REGEX_PRESCRID.match(context.msg_output[message_vocab.PRESCID]):
            raise EpsValidationError(message_vocab.PRESCID + " has invalid format")

        valid = self.checksum_util.check_checksum(
            context.msg_output[message_vocab.PRESCID], self.internal_id
        )
        if not valid:
            raise EpsValidationError(message_vocab.PRESCID + " has invalid checksum")

        context.output_fields.add(message_vocab.PRESCID)

    def _check_prescription_id_dispense_side(self, context: ValidationContext):
        """
        On release need to determine target version - is it R1 or R2 - before validating
        the prescription ID
        """
        context.msg_output[message_vocab.PRESCID] = context.msg_output[message_vocab.TARGET_PRESCID]
        context.msg_output[message_vocab.TARGET_PRESCVR] = context.msg_output[
            message_vocab.TARGET_PRESCVR
        ]
        if context.msg_output.get(message_vocab.TARGET_PRESCVR, R1) == R1:
            self._check_r1_prescription_id(context)
        else:
            self._check_prescription_id(context)

        context.output_fields.add(message_vocab.PRESCID)
        context.output_fields.add(message_vocab.TARGET_PRESCVR)

    def _check_prescription_id_dispense_rebuild(self, context: ValidationContext):
        """
        On dispense_rebuild need to determine target version - is it R1 or R2 - before validating
        the prescription ID. This is the Root ID in the prescription rebuild case
        """

        context.msg_output[message_vocab.PRESCID] = context.msg_output[
            message_vocab.ROOT_TARGET_PRESCID
        ]
        context.msg_output[message_vocab.TARGET_PRESCVR] = context.msg_output[
            message_vocab.ROOT_TARGET_PRESCVR
        ]

        if context.msg_output.get(message_vocab.TARGET_PRESCVR, R1) == R1:
            self._check_r1_prescription_id(context)
        else:
            self._check_prescription_id(context)

        context.output_fields.add(message_vocab.PRESCID)
        context.output_fields.add(message_vocab.TARGET_PRESCVR)

    def _add_checksum(self, prescriptionID):
        """
        Generate and add the checksum to a 36 character R1 Prescription ID

        To use the calculate_checksum function (requires 37 character PrrescriptionID),
        we must first add a dummy check digit
        """
        prscID = prescriptionID + "_"

        checkValue = self.checksum_util.calculate_checksum(prscID)

        return str(prescriptionID + checkValue)

    def _check_current_instance(self, context: ValidationContext):
        """
        Confirm that the current instance is an integer (or can be written as an
        integer)
        """
        try:
            if int(context.msg_output[message_vocab.CURRINSTANCE]) <= 0:
                raise ValueError
        except ValueError as value_error:
            raise EpsValidationError(
                message_vocab.CURRINSTANCE + " has invalid format"
            ) from value_error
        context.output_fields.add(message_vocab.CURRINSTANCE)

    def _set_instance_number(self, context: ValidationContext):
        """
        Check for the presence of an instance number in the inbound message.
        As this is optional for Acute messages, default to '1' if not provided.

        Note that a repeat dispense message without an instance reference is invalid, but
        this will be caught in the state transition check if the default instance does not
        have the correct status.
        """
        if context.msg_output.get(message_vocab.REPEATLOW):
            context.msg_output[message_vocab.CURRINSTANCE] = context.msg_output[
                message_vocab.REPEATLOW
            ]
        else:
            context.msg_output[message_vocab.CURRINSTANCE] = 1
        context.output_fields.add(message_vocab.CURRINSTANCE)

    def _set_target_instance_number(self, context: ValidationContext):
        """
        Check for the presence of a target instance number in the inbound message.
        As this is optional for Acute messages, default to '1' if not provided.

        Note that a repeat dispense message without an instance reference is invalid, but
        this will be caught in the state transition check if the default instance does not
        have the correct status.
        """

        if context.msg_output.get(message_vocab.TARGET_INSTANCE):
            context.output_fields.add(message_vocab.TARGET_INSTANCE)

    def _set_prescription_status(self, context: ValidationContext):
        """
        Set the prescription status from msg_output to context
        """
        if context.msg_output.get(message_vocab.PRESCSTATUS):
            context.output_fields.add(message_vocab.PRESCSTATUS)

    def _check_non_dispensing_reasons(self, context: ValidationContext):
        """
        Set the non dispensing reason code msg_output to context
        """
        if context.msg_output.get(message_vocab.NONDISPENSINGREASON):
            non_dispensing_reason_code = str(
                context.msg_output.get(message_vocab.NONDISPENSINGREASON)
            )
            self.log_object.write_log(
                "EPS0079",
                None,
                dict(
                    {
                        "internalID": self.internal_id,
                        "interactionID": self.interaction_id,
                        "reasonCodeCategory": NOT_DISPENSED,
                        "reasonCode": non_dispensing_reason_code,
                        "reasonText": None,
                        "target": "Prescription",
                    }
                ),
            )
        dn_prefix = "dnLineItem"
        for line_number in range(1, int(context.msg_output[message_vocab.LINEITEMS_TOTAL]) + 1):
            line_item_ndr = dn_prefix + str(line_number) + message_vocab.NONDISPENSINGREASON
            if context.msg_output.get(line_item_ndr):
                non_dispensing_reason_code = str(context.msg_output.get(line_item_ndr))
                self.log_object.write_log(
                    "EPS0079",
                    None,
                    dict(
                        {
                            "internalID": self.internal_id,
                            "interactionID": self.interaction_id,
                            "reasonCodeCategory": NOT_DISPENSED,
                            "reasonCode": non_dispensing_reason_code,
                            "reasonText": None,
                            "target": "LineItem",
                        }
                    ),
                )

    def _prescription_id_consistency(
        self, specific_context: ValidationContext, full_context: ValidationContext
    ):
        """
        Checks that the prescription_id in the specific_context matches that of the
        root (full) context
        """
        context_presc_id = specific_context.msg_output.get(message_vocab.TARGET_PRESCID)
        root_presc_id = full_context.msg_output.get(message_vocab.ROOT_TARGET_PRESCID)
        if context_presc_id != root_presc_id:
            supp_info = "Mismatch between root Prescription ID "
            supp_info += str(root_presc_id)
            supp_info += " and Dispense Notification component Prescription ID "
            supp_info += str(context_presc_id)
            raise EpsValidationError(supp_info)

    def _dispensing_org_consistency(
        self, specific_context: ValidationContext, full_context: ValidationContext
    ):
        """
        Checks that the dispensingOrg is consistent between dispense notification
        components

        First pass will set the rootDispensingOrg, subsequent runs will compare
        """
        context_dispensing_org = specific_context.msg_output.get(message_vocab.DISPENSERORG)
        root_dispensing_org = full_context.msg_output.get(message_vocab.DISPENSERORG, None)
        if not root_dispensing_org:
            full_context.msg_output[message_vocab.DISPENSERORG] = context_dispensing_org
            full_context.output_fields.add(message_vocab.DISPENSERORG)
            return
        if context_dispensing_org != root_dispensing_org:
            supp_info = "Mismatch of dispensingOrg between dispense notification components"
            raise EpsValidationError(supp_info)

    def _nhs_number_consistency(
        self, specific_context: ValidationContext, full_context: ValidationContext
    ):
        """
        Checks that the nhsNumber is consistent between dispense notification components

        First pass will set the rootPatientID, subsequent runs will compare
        """
        context_patient_id = specific_context.msg_output.get(message_vocab.PATIENTID)
        root_patient_id = full_context.msg_output.get(message_vocab.PATIENTID, None)
        if not root_patient_id:
            full_context.msg_output[message_vocab.PATIENTID] = context_patient_id
            full_context.output_fields.add(message_vocab.PATIENTID)
            full_context.msg_output[message_vocab.PATIENTID] = context_patient_id
            return
        if context_patient_id != root_patient_id:
            supp_info = "Mismatch between nhsNumbers provided: "
            supp_info += str(context_patient_id)
            supp_info += " and "
            supp_info += str(root_patient_id)
            raise EpsValidationError(supp_info)

    def _line_item_count_consistency(
        self, specific_context: ValidationContext, full_context: ValidationContext
    ):
        """
        Checks that the total line item count is consistent between dispense notification
        components

        First pass will set the rootTotalLineItems, subsequent runs will compare
        """
        context_total_line_items = specific_context.msg_output.get(message_vocab.LINEITEMS_TOTAL)
        root_total_line_items = full_context.msg_output.get(message_vocab.LINEITEMS_TOTAL, None)
        if not root_total_line_items:
            full_context.msg_output[message_vocab.LINEITEMS_TOTAL] = context_total_line_items
            return
        if context_total_line_items != root_total_line_items:
            supp_info = "Mismatch of lineItem count between dispense notification components"
            raise EpsValidationError(supp_info)

    def _line_item_ref_consistency(
        self, specific_context: ValidationContext, full_context: ValidationContext
    ):
        """
        Checks that the line items match the between the  dispense notification components

        First pass will set the rootLineItemRefs, subsequent runs will compare to this list
        """
        root_line_item_refs = full_context.msg_output.get(message_vocab.LINEITEM_REFS, None)
        context_total_line_items = specific_context.msg_output.get(message_vocab.LINEITEMS_TOTAL)

        context_line_refs = []

        for i in range(1, int(context_total_line_items) + 1):
            line_ref = "lineItem" + str(i) + "Ref"
            context_line_refs.append(specific_context.msg_output.get(line_ref))

        if not root_line_item_refs:
            full_context.msg_output[message_vocab.LINEITEM_REFS] = context_line_refs
            return

        for line_item in context_line_refs:
            if line_item not in root_line_item_refs:
                supp_info = "Unexpected Line Item reference "
                supp_info += str(line_item)
                supp_info += " found in Dispense Notification component"
                raise EpsValidationError(supp_info)

    def _set_repeat_dispense_instances(self, context: ValidationContext):
        """
        Set the repeat high and low values for prescription if present
        """
        context.msg_output[message_vocab.REPEATLOW] = context.msg_output.get(
            message_vocab.REPEATLOW
        )
        context.output_fields.add(message_vocab.REPEATLOW)
        context.msg_output[message_vocab.REPEATHIGH] = context.msg_output.get(
            message_vocab.REPEATHIGH
        )
        context.output_fields.add(message_vocab.REPEATHIGH)

    def _check_replacement_of_target(self, context: ValidationContext):
        """
        Check that the optional replacementOf target is a valid GUID and add it to the
        output fields
        """
        if message_vocab.REPLACE_GUID not in context.msg_output:
            context.msg_output[message_vocab.REPLACE_GUID] = None
        elif not REGEX_GUID.match(context.msg_output[message_vocab.REPLACE_GUID]):
            supp_info = message_vocab.REPLACE_GUID + " ID is not a valid GUID format"
            raise EpsValidationError(supp_info)
        context.output_fields.add(message_vocab.REPLACE_GUID)

    def _check_withdraw_target(self, context: ValidationContext):
        """
        Check that the optional target dispense notification to withdraw is a valid GUID
        and add it to the output fields
        """
        if message_vocab.WITHDRAW_GUID not in context.msg_output:
            context.msg_output[message_vocab.WITHDRAW_GUID] = None
        elif not REGEX_GUID.match(context.msg_output[message_vocab.WITHDRAW_GUID]):
            supp_info = message_vocab.WITHDRAW_GUID + " ID is not a valid GUID format"
            raise EpsValidationError(supp_info)
        context.output_fields.add(message_vocab.WITHDRAW_GUID)

    def _check_withdraw_type(self, context: ValidationContext):
        """
        Check that the mandatory withdraw type is provided and valid and add it
        to the output fields
        """
        if context.msg_output[message_vocab.WITHDRAW_TYPE] not in WITHDRAW_TYPELIST:
            supp_info = message_vocab.WITHDRAW_TYPE + " is not of expected type"
            raise EpsValidationError(supp_info)
        context.output_fields.add(message_vocab.WITHDRAW_TYPE)

    def _check_withdraw_reason(self, context: ValidationContext):
        """
        Check that the mandatory withdraw reason is provided and valid and add it
        to the output fields
        """
        if context.msg_output[message_vocab.WITHDRAW_RSON] not in WITHDRAW_RSONLIST:
            supp_info = message_vocab.WITHDRAW_RSON + " is not of expected type"
            raise EpsValidationError(supp_info)
        context.output_fields.add(message_vocab.WITHDRAW_RSON)

    def _check_r1_prescription_id(self, context: ValidationContext):
        """
        Check the format of an R1 prescription ID and that it has the correct checksum

        Due to ambiguity in MIM3.1.07, some systems send the R1 Prescription ID without
        the check digit as a 36 character UUID. In this case, a checksum will be created.
        """

        presc_id = context.msg_output[message_vocab.PRESCID]

        if REGEX_PRESCRIDR1.match(presc_id):
            valid = self.checksum_util.check_checksum(presc_id, self.internal_id)
            if not valid:
                raise EpsValidationError(message_vocab.PRESCID + " has invalid checksum")
        elif REGEX_PRESCRIDR1_ALT.match(presc_id):
            self.log_object.write_log(
                "EPS0450", None, {"internalID": self.internal_id, "prescID": presc_id}
            )
            full_presc_id = self._add_checksum(context.msg_output[message_vocab.PRESCID])
            context.msg_output[message_vocab.PRESCID] = full_presc_id
        else:
            raise EpsValidationError(message_vocab.PRESCID + " has invalid format")

        context.output_fields.add(message_vocab.PRESCID)

    def _check_standard_date_time(self, context: ValidationContext, attribute_name):
        """
        Check for a valid time
        """
        try:
            if len(context.msg_output[attribute_name]) != 14:
                if len(context.msg_output[attribute_name]) != 19:
                    raise ValueError("Wrong String Length")
                parsed_time = self._convert_international_time(context.msg_output[attribute_name])
                context.msg_output[attribute_name] = parsed_time
            datetime.datetime.strptime(
                context.msg_output[attribute_name], TimeFormats.STANDARD_DATE_TIME_FORMAT
            )
        except ValueError as value_error:
            supp_info = attribute_name + " is not a valid time or in the "
            supp_info += "valid format; expected format " + TimeFormats.STANDARD_DATE_TIME_FORMAT
            raise EpsValidationError(supp_info) from value_error

        context.output_fields.add(attribute_name)

    def _convert_international_time(self, international_time):
        """
        Use the shared function to convert BST to GMT
        """
        return convert_international_time(international_time, self.log_object, self.internal_id)

    def _check_standard_date(self, context: ValidationContext, attribute_name):
        """
        Check for a valid time
        """
        try:
            if len(context.msg_output[attribute_name]) != 8:
                raise ValueError("Wrong String Length")
            datetime.datetime.strptime(
                context.msg_output[attribute_name], TimeFormats.STANDARD_DATE_FORMAT
            )
        except ValueError as value_error:
            supp_info = attribute_name + " is not a valid time or in the "
            supp_info += "valid format; expected format " + TimeFormats.STANDARD_DATE_FORMAT
            raise EpsValidationError(supp_info) from value_error

        context.output_fields.add(attribute_name)

    def _check_repeat_dispense_instances(self, context: ValidationContext):
        """
        Repeat dispense instances is an integer range found within repeat dispense
        prescriptions to articulate the number of instances.  Low must be 1!
        """
        if not (
            context.msg_output.get(message_vocab.REPEATLOW)
            and context.msg_output.get(message_vocab.REPEATHIGH)
        ):
            if context.msg_output[message_vocab.TREATMENTTYPE] == STATUS_ACUTE:
                return
            supp_info = message_vocab.REPEATHIGH + " and " + message_vocab.REPEATLOW
            supp_info += " values must both be provided if not Acute prescription"
            raise EpsValidationError(supp_info)

        if not REGEX_INTEGER12.match(context.msg_output[message_vocab.REPEATHIGH]):
            supp_info = message_vocab.REPEATHIGH + " is not an integer"
            raise EpsValidationError(supp_info)
        if not REGEX_INTEGER12.match(context.msg_output[message_vocab.REPEATLOW]):
            supp_info = message_vocab.REPEATLOW + " is not an integer"
            raise EpsValidationError(supp_info)

        context.msg_output[message_vocab.REPEATLOW] = int(
            context.msg_output[message_vocab.REPEATLOW]
        )
        context.msg_output[message_vocab.REPEATHIGH] = int(
            context.msg_output[message_vocab.REPEATHIGH]
        )
        if context.msg_output[message_vocab.REPEATLOW] != 1:
            supp_info = message_vocab.REPEATLOW + " must be 1"
            raise EpsValidationError(supp_info)
        if context.msg_output[message_vocab.REPEATHIGH] > MAX_PRESCRIPTIONREPEATS:
            supp_info = message_vocab.REPEATHIGH + " must not be over configured "
            supp_info += "maximum of " + str(MAX_PRESCRIPTIONREPEATS)
            raise EpsValidationError(supp_info)
        if (
            context.msg_output[message_vocab.REPEATHIGH]
            < context.msg_output[message_vocab.REPEATLOW]
        ):
            supp_info = message_vocab.REPEATLOW + " is greater than " + message_vocab.REPEATHIGH
            raise EpsValidationError(supp_info)
        if (
            context.msg_output[message_vocab.REPEATHIGH] != 1
            and context.msg_output[message_vocab.TREATMENTTYPE] == STATUS_REPEAT
        ):
            self.log_object.write_log(
                "EPS0509",
                None,
                {
                    "internalID": self.internal_id,
                    "target": "Prescription",
                    "maxRepeats": context.msg_output[message_vocab.REPEATHIGH],
                },
            )

        context.output_fields.add(message_vocab.REPEATLOW)
        context.output_fields.add(message_vocab.REPEATHIGH)

    def _check_birth_date(self, context: ValidationContext, handle_time):
        """
        Birth date must be a valid date, and must not be in the future
        """
        self._check_standard_date(context, message_vocab.BIRTHTIME)
        now_as_string = handle_time.strftime(TimeFormats.STANDARD_DATE_TIME_FORMAT)
        if context.msg_output[message_vocab.BIRTHTIME] > now_as_string:
            supp_info = message_vocab.BIRTHTIME + " is in the future"
            raise EpsValidationError(supp_info)

    def _check_nominated_performer(self, context: ValidationContext):
        """
        If there is nominated performer (i.e. pharmacy) information - then the format
        needs to be validated
        """
        if context.msg_output.get(message_vocab.NOMPERFORMER) and context.msg_output.get(
            message_vocab.NOMPERFORMER_TYPE
        ):
            if not REGEX_ALPHANUMERIC8.match(context.msg_output.get(message_vocab.NOMPERFORMER)):
                raise EpsValidationError("nominatedPerformer has invalid format")
            if context.msg_output.get(message_vocab.NOMPERFORMER_TYPE) not in PERFORMER_TYPELIST:
                raise EpsValidationError("nominatedPerformer has invalid type")

        if context.msg_output.get(message_vocab.NOMPERFORMER) == "":
            raise EpsValidationError("nominatedPerformer is present but empty")

        context.output_fields.add(message_vocab.NOMPERFORMER)
        context.output_fields.add(message_vocab.NOMPERFORMER_TYPE)

    def _check_dispenser_code(self, context: ValidationContext):
        """
        Check the dispenser code that has been passed in the release request
        """
        dispenser_code = context.msg_output[message_vocab.DISPENSER]
        if not REGEX_ALPHANUMERIC8.match(dispenser_code):
            self.log_object.write_log(
                "EPS0332", None, {"internalID": self.internal_id, "dispenserCode": dispenser_code}
            )
            if not REGEX_INTEGER12.match(dispenser_code):
                self.log_object.write_log(
                    "EPS0323c",
                    None,
                    {
                        "internalID": self.internal_id,
                        "dispenserCode": context.msg_output[message_vocab.DISPENSER],
                    },
                )
                # MB: Relax validation in Live as pert of go-live work
                # raise EpsValidationError(message_vocab.DISPENSER + ' has invalid format')

        context.output_fields.add(message_vocab.DISPENSER)
        context.output_fields.add(message_vocab.AGENT_PERSON)

    def _check_claim_id(self, context: ValidationContext):
        """
        Check that a GUID has been passed as claim ID
        """
        if not REGEX_GUID.match(context.msg_output[message_vocab.CLAIMID]):
            raise EpsValidationError(message_vocab.CLAIMID + " is not a valid GUID format")
        context.output_fields.add(message_vocab.CLAIMID)

    def _check_claim_time(self, context: ValidationContext, handle_time):
        """
        Claim time must be a valid date / time, not in the future (tolerance of one day
        is granted to allow for server timing issues)
        """
        if len(context.msg_output[message_vocab.CLAIM_TIME]) != 14:
            if len(context.msg_output[message_vocab.CLAIM_TIME]) == 19:
                parsed_time = self._convert_international_time(
                    context.msg_output[message_vocab.CLAIM_TIME]
                )
                context.msg_output[message_vocab.CLAIM_TIME] = parsed_time
            else:
                supp_info = "claimTime is not a valid time or in the valid format; "
                supp_info += "expected format " + TimeFormats.STANDARD_DATE_TIME_FORMAT
                raise EpsValidationError(supp_info)

        dc_time = datetime.datetime.strptime(
            context.msg_output[message_vocab.CLAIM_TIME], TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        if dc_time > (handle_time + datetime.timedelta(days=1)):
            raise EpsValidationError("claimTime is more than one day in the future")

        context.msg_output[message_vocab.CLAIM_DATE] = dc_time.strftime(
            TimeFormats.STANDARD_DATE_FORMAT
        )
        context.output_fields.add(message_vocab.CLAIM_DATE)

    def _check_dispense_time(self, context: ValidationContext, handle_time):
        """
        Dispense time must be a valid date/time, not in the future (tolerance of one day
        is granted to allow for server timing issues)
        """
        self._check_standard_date_time(context, message_vocab.DISPENSEN_TIME)
        dn_time = datetime.datetime.strptime(
            context.msg_output[message_vocab.DISPENSEN_TIME], TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        if dn_time > (handle_time + datetime.timedelta(days=1)):
            raise EpsValidationError(
                message_vocab.DISPENSEN_TIME + " is more than one day in the future"
            )

        # There is some name confusion here - the code uses dispenseTime, but Schematron
        # outputs a dispenseNotifictaionTime
        context.msg_output[message_vocab.DISPENSE_TIME] = context.msg_output[
            message_vocab.DISPENSEN_TIME
        ]
        context.msg_output[message_vocab.DISPENSE_DATE] = dn_time.strftime(
            TimeFormats.STANDARD_DATE_FORMAT
        )
        context.output_fields.add(message_vocab.DISPENSE_TIME)
        context.output_fields.add(message_vocab.DISPENSE_DATE)

    def _check_dispense_withdraw_time(self, context: ValidationContext, handle_time):
        """
        Dispense time must be a valid date/time, not in the future (tolerance of one day
        is granted to allow for server timing issues)
        """

        self._check_standard_date_time(context, message_vocab.DISPENSEW_TIME)

        dw_time = datetime.datetime.strptime(
            context.msg_output[message_vocab.DISPENSEW_TIME], TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        if dw_time > (handle_time + datetime.timedelta(days=1)):
            raise EpsValidationError(
                message_vocab.DISPENSEW_TIME + " is more than one day in the future"
            )

        # There is some name confusion here - the code uses dispenseTime, but Schematron
        # outputs a dispenseWithdrawlTime
        context.msg_output[message_vocab.DISPENSE_TIME] = context.msg_output[
            message_vocab.DISPENSEW_TIME
        ]
        context.msg_output[message_vocab.DISPENSE_DATE] = dw_time.strftime(
            TimeFormats.STANDARD_DATE_FORMAT
        )
        context.output_fields.add(message_vocab.DISPENSE_TIME)
        context.output_fields.add(message_vocab.DISPENSE_DATE)

    def _check_dispense_withdraw_id(self, context: ValidationContext):
        """
        Confirm that the Dispense Withdraw ID is a valid GUID
        """
        if not REGEX_GUID.match(context.msg_output[message_vocab.DISPENSEW_ID]):
            raise EpsValidationError(message_vocab.DISPENSEW_ID + " is not a valid GUID format")
        context.output_fields.add(message_vocab.DISPENSEW_ID)

    def _check_dispense_notification_id(self, context: ValidationContext):
        """
        Confirm that the Dispense Notification ID is a valid GUID
        """
        if not REGEX_GUID.match(context.msg_output[message_vocab.DISPENSEN_ID]):
            raise EpsValidationError(message_vocab.DISPENSEN_ID + " is not a valid GUID format")
        context.output_fields.add(message_vocab.DISPENSEN_ID)

    def _check_line_items_dispense_side(self, context: ValidationContext, claim=False):
        """
        Check for each of the Line Items that:
        1) the Status, Reference and ID have been provided
        2) the (lineItem) Status and Prescription Status are a valid combination
        3) the Reference and ID are both valid GUIDs
        """
        context.msg_output[message_vocab.LINEITEMS] = []
        [_prefix, _id] = self._select_tags(claim)

        for line_number in range(1, int(context.msg_output[message_vocab.LINEITEMS_TOTAL]) + 1):
            line_item = self._build_line_dict(context, line_number, claim)
            status_combo_check = self.validate_line_prescription_status(
                context.msg_output[message_vocab.PRESCSTATUS],
                line_item[message_vocab.LINEITEM_DT_STATUS],
            )

            if not status_combo_check:
                supp_info = "Invalid state combination for line item " + str(line_number)
            elif not REGEX_GUID.match(line_item[message_vocab.LINEITEM_DT_ID]):
                supp_info = "lineItem" + str(line_number) + "ID is not a valid GUID format"
            elif not REGEX_GUID.match(line_item[_id]):
                supp_info = _prefix + str(line_number) + "ID is not a valid GUID format"
            else:
                context.msg_output[message_vocab.LINEITEMS].append(line_item)
                continue
            raise EpsValidationError(supp_info)

        context.output_fields.add(message_vocab.LINEITEMS)

    def _build_line_dict(self, context: ValidationContext, line_number, claim):
        """
        Build the dictionary of information from an individual line
        """
        line_item = {}
        [prefix, id] = self._select_tags(claim)
        try:
            line_item[message_vocab.LINEITEM_DT_ID] = context.msg_output[
                message_vocab.LINEITEM_PX + str(line_number) + message_vocab.LINEITEM_SX_REF
            ]
            line_item[message_vocab.LINEITEM_DT_STATUS] = context.msg_output[
                message_vocab.LINEITEM_PX + str(line_number) + message_vocab.LINEITEM_SX_STATUS
            ]
            line_item[id] = context.msg_output[
                prefix + str(line_number) + message_vocab.LINEITEM_SX_ID
            ]
        except KeyError as key_error:
            print(sys.exc_info())
            raise EpsValidationError(
                "Missing information from line item " + str(line_number)
            ) from key_error

        max_repeat_ref = prefix + str(line_number) + message_vocab.LINEITEM_SX_REPEATHIGH
        current_inst_ref = prefix + str(line_number) + message_vocab.LINEITEM_SX_REPEATLOW
        if max_repeat_ref in context.msg_output:
            line_item[message_vocab.LINEITEM_DT_MAXREPEATS] = context.msg_output[max_repeat_ref]
        else:
            line_item[message_vocab.LINEITEM_DT_MAXREPEATS] = context.msg_output[
                message_vocab.REPEATHIGH
            ]
        if current_inst_ref in context.msg_output:
            line_item[message_vocab.LINEITEM_DT_CURRINSTANCE] = context.msg_output[current_inst_ref]
        else:
            line_item[message_vocab.LINEITEM_DT_CURRINSTANCE] = context.msg_output[
                message_vocab.REPEATLOW
            ]

        return line_item

    def _select_tags(self, claim):
        """
        Return the _prefix and _id tags to be used if it is a claim, otherwise return
        for dispense notification
        """
        if claim:
            return [message_vocab.LINEITEM_PX_CLAIM, message_vocab.LINEITEM_DT_CLAIMID]

        return [message_vocab.LINEITEM_PX_DN, message_vocab.LINEITEM_DT_DNID]

    def validate_line_prescription_status(self, prescription_status, line_item_status):
        """
        Compare lineItem status with the prescription status and confirm that the
        combination is valid
        """
        if line_item_status in LineItemStatus.VALID_STATES[prescription_status]:
            return True

        self.log_object.write_log(
            "EPS0259",
            None,
            dict(
                {
                    "internalID": self.internal_id,
                    "lineItemStatus": line_item_status,
                    "prescriptionStatus": prescription_status,
                }
            ),
        )
        return False

    def validate_line_items(self, context: ValidationContext):
        """
        Validating line items - there are up to 32 line items

        Each line item has a GUID (ID)
        Each line item may have a repeatLow and a repeatHigh (not one but not the other)
        Result needs to be places onto lineItems dictionary

        Fields may be presented as empty when fields are not present - so these need to be
        treated correctly as not present
        - To manage this, delete any keys from the dictionary if the result is None or ''
        """
        maxRepeatHigh = 1
        context.msg_output[message_vocab.LINEITEMS] = []

        for line_number in range(MAX_LINEITEMS):

            line_item = line_number + 1
            line_dict = {}

            line_item_id = message_vocab.LINEITEM_PX + str(line_item) + message_vocab.LINEITEM_SX_ID
            if context.msg_output.get(line_item_id):
                line_dict[message_vocab.LINEITEM_DT_ORDER] = line_item
                line_dict[message_vocab.LINEITEM_DT_ID] = context.msg_output[line_item_id]
                line_dict[message_vocab.LINEITEM_DT_STATUS] = "0007"
            else:
                break

            line_item_repeat_high = (
                message_vocab.LINEITEM_PX + str(line_item) + message_vocab.LINEITEM_SX_REPEATHIGH
            )
            line_item_repeat_low = (
                message_vocab.LINEITEM_PX + str(line_item) + message_vocab.LINEITEM_SX_REPEATLOW
            )
            if context.msg_output.get(line_item_repeat_high):
                line_dict[message_vocab.LINEITEM_DT_MAXREPEATS] = context.msg_output[
                    line_item_repeat_high
                ]
            if context.msg_output.get(line_item_repeat_low):
                line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE] = context.msg_output[
                    line_item_repeat_low
                ]

            maxRepeatHigh = self.validateLineItem(context, line_item, line_dict, maxRepeatHigh)
            context.msg_output[message_vocab.LINEITEMS].append(line_dict)

        if len(context.msg_output[message_vocab.LINEITEMS]) < 1:
            supp_info = "No valid line items found"
            raise EpsValidationError(supp_info)

        maxLineItem = message_vocab.LINEITEM_PX
        maxLineItem += str(MAX_LINEITEMS + 1)
        maxLineItem += message_vocab.LINEITEM_SX_ID
        if maxLineItem in context.msg_output:
            supp_info = "lineItems over expected max count of " + str(MAX_LINEITEMS)
            raise EpsValidationError(supp_info)

        if (
            message_vocab.REPEATHIGH in context.msg_output
            and maxRepeatHigh < context.msg_output[message_vocab.REPEATHIGH]
        ):
            supp_info = "Prescription repeat count must not be greater than all "
            supp_info += "Line Item repeat counts"
            raise EpsValidationError(supp_info)

        context.output_fields.add(message_vocab.LINEITEMS)

    def validate_line_item(self, context: ValidationContext, line_item, line_dict, max_repeat_high):
        """
        Ensure that the GUID is valid
        Check for an appropriate combination of maxRepeats and currentInstance
        Check for an appropriate value of maxRepeats
        Check for an appropriate value for currentInstance
        """
        if not REGEX_GUID.match(line_dict[message_vocab.LINEITEM_DT_ID]):
            supp_info = line_dict[message_vocab.LINEITEM_DT_ID]
            supp_info += " is not a valid GUID format"
            raise EpsValidationError(supp_info)

        if (
            message_vocab.LINEITEM_DT_MAXREPEATS not in line_dict
            and message_vocab.LINEITEM_DT_CURRINSTANCE not in line_dict
            and context.msg_output[message_vocab.TREATMENTTYPE] == STATUS_ACUTE
        ):
            return max_repeat_high

        self._check_for_invalid_line_item_repeat_combinations(context, line_dict, line_item)

        if not REGEX_INTEGER12.match(line_dict[message_vocab.LINEITEM_DT_MAXREPEATS]):
            supp_info = "repeat.High for line item "
            supp_info += str(line_item) + " is not an integer"
            raise EpsValidationError(supp_info)

        repeat_high = int(line_dict[message_vocab.LINEITEM_DT_MAXREPEATS])
        if repeat_high < 1:
            supp_info = "repeat.High for line item "
            supp_info += str(line_item) + " must be greater than zero"
            raise EpsValidationError(supp_info)
        if repeat_high > int(context.msg_output[message_vocab.REPEATHIGH]):
            supp_info = "repeat.High of " + str(repeat_high)
            supp_info += " for line item " + str(line_item)
            supp_info += " must not be greater than " + message_vocab.REPEATHIGH
            supp_info += " of " + str(context.msg_output[message_vocab.REPEATHIGH])
            raise EpsValidationError(supp_info)
        if repeat_high != 1 and context.msg_output[message_vocab.TREATMENTTYPE] == STATUS_REPEAT:
            self.log_object.write_log(
                "EPS0509",
                None,
                {
                    "internalID": self.internal_id,
                    "target": str(line_item),
                    "maxRepeats": repeat_high,
                },
            )
        if not REGEX_INTEGER12.match(line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE]):
            supp_info = "repeat.Low for line item " + str(line_item)
            supp_info += " is not an integer"
            raise EpsValidationError(supp_info)
        repeat_low = int(line_dict[message_vocab.LINEITEM_DT_CURRINSTANCE])
        if repeat_low != 1:
            supp_info = "repeat.Low for line item " + str(line_item) + " is not set to 1"
            raise EpsValidationError(supp_info)

        max_repeat_high = max(max_repeat_high, repeat_high)
        return max_repeat_high

    def _check_for_invalid_line_item_repeat_combinations(
        self, context: ValidationContext, line_dict, line_item
    ):
        """
        If not an acute prescription - check the combination of repeat and instance
        informaiton is valid
        """
        if (
            message_vocab.LINEITEM_DT_MAXREPEATS not in line_dict
            and message_vocab.LINEITEM_DT_CURRINSTANCE not in line_dict
        ):
            supp_info = "repeat.High and repeat.Low values must both be "
            supp_info += "provided for lineItem " + str(line_item) + " "
            supp_info += "if not acute prescription"
            raise EpsValidationError(supp_info)
        elif message_vocab.LINEITEM_DT_MAXREPEATS not in line_dict:
            supp_info = "repeat.Low provided but not repeat.High for line item "
            supp_info += str(line_item)
            raise EpsValidationError(supp_info)
        elif message_vocab.LINEITEM_DT_CURRINSTANCE not in line_dict:
            supp_info = "repeat.High provided but not repeat.Low for line item "
            supp_info += str(line_item)
            raise EpsValidationError(supp_info)
        elif not context.msg_output.get(message_vocab.REPEATHIGH):
            supp_info = "Line item " + str(line_item)
            supp_info += " repeat value provided for non-repeat prescription"
            raise EpsValidationError(supp_info)
