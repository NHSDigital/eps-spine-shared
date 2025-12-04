# flake8: noqa: E501
import datetime
import sys
from copy import copy

from dateutil.relativedelta import relativedelta

from eps_spine_shared.common import indexes
from eps_spine_shared.errors import (
    EpsBusinessError,
    EpsErrorBase,
    EpsSystemError,
)
from eps_spine_shared.nhsfundamentals.timeutilities import TimeFormats
from eps_spine_shared.spinecore.baseutilities import handleEncodingOddities, quoted
from eps_spine_shared.spinecore.changelog import PrescriptionsChangeLogProcessor


class PrescriptionStatus(object):
    """
    Prescription states and related information
    """

    AWAITING_RELEASE_READY = "0000"
    TO_BE_DISPENSED = "0001"
    WITH_DISPENSER = "0002"
    WITH_DISPENSER_ACTIVE = "0003"
    EXPIRED = "0004"
    CANCELLED = "0005"
    DISPENSED = "0006"
    NOT_DISPENSED = "0007"
    CLAIMED = "0008"
    NO_CLAIMED = "0009"
    REPEAT_DISPENSE_FUTURE_INSTANCE = "9000"
    FUTURE_DATED_PRESCRIPTION = "9001"
    PENDING_CANCELLATION = "9005"

    PRESCRIPTION_DISPLAY_LOOKUP = {}
    PRESCRIPTION_DISPLAY_LOOKUP[AWAITING_RELEASE_READY] = "Awaiting Release Ready"
    PRESCRIPTION_DISPLAY_LOOKUP[TO_BE_DISPENSED] = "To Be Dispensed"
    PRESCRIPTION_DISPLAY_LOOKUP[WITH_DISPENSER] = "With Dispenser"
    PRESCRIPTION_DISPLAY_LOOKUP[WITH_DISPENSER_ACTIVE] = "With Dispenser - Active"
    PRESCRIPTION_DISPLAY_LOOKUP[EXPIRED] = "Expired"
    PRESCRIPTION_DISPLAY_LOOKUP[CANCELLED] = "Cancelled"
    PRESCRIPTION_DISPLAY_LOOKUP[DISPENSED] = "Dispensed"
    PRESCRIPTION_DISPLAY_LOOKUP[NOT_DISPENSED] = "Not Dispensed"
    PRESCRIPTION_DISPLAY_LOOKUP[CLAIMED] = "Claimed"
    PRESCRIPTION_DISPLAY_LOOKUP[NO_CLAIMED] = "No-Claimed"
    PRESCRIPTION_DISPLAY_LOOKUP[REPEAT_DISPENSE_FUTURE_INSTANCE] = "Repeat Dispense future instance"
    PRESCRIPTION_DISPLAY_LOOKUP[FUTURE_DATED_PRESCRIPTION] = "Prescription future instance"
    PRESCRIPTION_DISPLAY_LOOKUP[PENDING_CANCELLATION] = "Cancelled future instance"

    CANCELLABLE_STATES = [
        AWAITING_RELEASE_READY,
        TO_BE_DISPENSED,
        REPEAT_DISPENSE_FUTURE_INSTANCE,
        FUTURE_DATED_PRESCRIPTION,
    ]

    WITH_DISPENSER_STATES = [WITH_DISPENSER, WITH_DISPENSER_ACTIVE]

    ACTIVE_STATES = [AWAITING_RELEASE_READY, TO_BE_DISPENSED, WITH_DISPENSER, WITH_DISPENSER_ACTIVE]

    FUTURE_STATES = [FUTURE_DATED_PRESCRIPTION, REPEAT_DISPENSE_FUTURE_INSTANCE]

    COMPLETED_STATES = [EXPIRED, CANCELLED, DISPENSED, NOT_DISPENSED, CLAIMED, NO_CLAIMED]

    NOT_COMPLETED_STATES = [
        AWAITING_RELEASE_READY,
        TO_BE_DISPENSED,
        WITH_DISPENSER,
        WITH_DISPENSER_ACTIVE,
        FUTURE_DATED_PRESCRIPTION,
        REPEAT_DISPENSE_FUTURE_INSTANCE,
    ]

    INCLUDE_PERFORMER_STATES = [
        WITH_DISPENSER,
        WITH_DISPENSER_ACTIVE,
        DISPENSED,
        NOT_DISPENSED,
        CLAIMED,
        NO_CLAIMED,
    ]

    EXPIRY_IMMUTABLE_STATES = [EXPIRED, CANCELLED, DISPENSED, NOT_DISPENSED, CLAIMED, NO_CLAIMED]

    UNACTIONED_STATES = [
        AWAITING_RELEASE_READY,
        TO_BE_DISPENSED,
        WITH_DISPENSER,
        REPEAT_DISPENSE_FUTURE_INSTANCE,
        PENDING_CANCELLATION,
    ]

    ALL_VALID_STATES = [
        AWAITING_RELEASE_READY,
        TO_BE_DISPENSED,
        WITH_DISPENSER,
        WITH_DISPENSER_ACTIVE,
        EXPIRED,
        CANCELLED,
        DISPENSED,
        NOT_DISPENSED,
        CLAIMED,
        NO_CLAIMED,
        REPEAT_DISPENSE_FUTURE_INSTANCE,
        FUTURE_DATED_PRESCRIPTION,
        PENDING_CANCELLATION,
    ]

    EXPIRY_LOOKUP = {}
    EXPIRY_LOOKUP[AWAITING_RELEASE_READY] = EXPIRED
    EXPIRY_LOOKUP[TO_BE_DISPENSED] = EXPIRED
    EXPIRY_LOOKUP[WITH_DISPENSER] = EXPIRED
    EXPIRY_LOOKUP[WITH_DISPENSER_ACTIVE] = DISPENSED
    EXPIRY_LOOKUP[REPEAT_DISPENSE_FUTURE_INSTANCE] = EXPIRED
    EXPIRY_LOOKUP[FUTURE_DATED_PRESCRIPTION] = EXPIRED
    EXPIRY_LOOKUP[PENDING_CANCELLATION] = EXPIRED


class LineItemStatus(object):
    """
    Prescription line item states and related information
    """

    FULLY_DISPENSED = "0001"
    NOT_DISPENSED = "0002"
    PARTIAL_DISPENSED = "0003"
    NOT_DISPENSED_OWING = "0004"
    CANCELLED = "0005"
    EXPIRED = "0006"
    TO_BE_DISPENSED = "0007"
    WITH_DISPENSER = "0008"

    ITEM_CANCELLABLE_STATES = [TO_BE_DISPENSED]
    ITEM_WITH_DISPENSER_STATES = [WITH_DISPENSER, PARTIAL_DISPENSED]

    ACTIVE_STATES = [TO_BE_DISPENSED, WITH_DISPENSER, PARTIAL_DISPENSED, NOT_DISPENSED_OWING]

    INCLUDE_PERFORMER_STATES = [
        WITH_DISPENSER,
        PARTIAL_DISPENSED,
        FULLY_DISPENSED,
        NOT_DISPENSED,
        NOT_DISPENSED_OWING,
    ]

    ITEM_DISPLAY_LOOKUP = {}
    ITEM_DISPLAY_LOOKUP[FULLY_DISPENSED] = "Item fully dispensed"
    ITEM_DISPLAY_LOOKUP[NOT_DISPENSED] = "Item not dispensed"
    ITEM_DISPLAY_LOOKUP[PARTIAL_DISPENSED] = "Item dispensed - partial"
    ITEM_DISPLAY_LOOKUP[NOT_DISPENSED_OWING] = "Item not dispensed owing"
    ITEM_DISPLAY_LOOKUP[EXPIRED] = "Expired"
    ITEM_DISPLAY_LOOKUP[CANCELLED] = "Item Cancelled"
    ITEM_DISPLAY_LOOKUP[TO_BE_DISPENSED] = "To Be Dispensed"
    ITEM_DISPLAY_LOOKUP[WITH_DISPENSER] = "Item with dispenser"

    VALID_STATES = {}
    VALID_STATES[PrescriptionStatus.AWAITING_RELEASE_READY] = [CANCELLED, EXPIRED, TO_BE_DISPENSED]
    VALID_STATES[PrescriptionStatus.TO_BE_DISPENSED] = [CANCELLED, EXPIRED, TO_BE_DISPENSED]
    VALID_STATES[PrescriptionStatus.WITH_DISPENSER] = [CANCELLED, EXPIRED, WITH_DISPENSER]
    VALID_STATES[PrescriptionStatus.WITH_DISPENSER_ACTIVE] = [
        FULLY_DISPENSED,
        NOT_DISPENSED,
        PARTIAL_DISPENSED,
        NOT_DISPENSED_OWING,
        CANCELLED,
        EXPIRED,
        WITH_DISPENSER,
    ]
    VALID_STATES[PrescriptionStatus.EXPIRED] = [CANCELLED, EXPIRED]
    VALID_STATES[PrescriptionStatus.CANCELLED] = [CANCELLED, EXPIRED]
    VALID_STATES[PrescriptionStatus.DISPENSED] = [
        FULLY_DISPENSED,
        NOT_DISPENSED,
        CANCELLED,
        EXPIRED,
    ]
    VALID_STATES[PrescriptionStatus.NOT_DISPENSED] = [NOT_DISPENSED, CANCELLED, EXPIRED]
    VALID_STATES[PrescriptionStatus.CLAIMED] = [FULLY_DISPENSED, NOT_DISPENSED, CANCELLED, EXPIRED]
    VALID_STATES[PrescriptionStatus.NO_CLAIMED] = [
        FULLY_DISPENSED,
        NOT_DISPENSED,
        CANCELLED,
        EXPIRED,
    ]
    VALID_STATES[PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE] = [
        CANCELLED,
        EXPIRED,
        TO_BE_DISPENSED,
    ]
    VALID_STATES[PrescriptionStatus.FUTURE_DATED_PRESCRIPTION] = [
        CANCELLED,
        EXPIRED,
        TO_BE_DISPENSED,
    ]

    EXPIRY_IMMUTABLE_STATES = [FULLY_DISPENSED, NOT_DISPENSED, EXPIRED, CANCELLED]

    EXPIRY_LOOKUP = {}
    EXPIRY_LOOKUP[TO_BE_DISPENSED] = "0006"
    EXPIRY_LOOKUP[PARTIAL_DISPENSED] = "0001"
    EXPIRY_LOOKUP[NOT_DISPENSED_OWING] = "0002"
    EXPIRY_LOOKUP[WITH_DISPENSER] = "0006"


class PrescriptionTreatmentType(object):
    """
    Constants for prescription treatment type.
    """

    ACUTE_PRESCRIBING = "0001"  # "one-off" prescriptions
    REPEAT_PRESCRIBING = "0002"  # may be re-issued by prescribing site
    REPEAT_DISPENSING = "0003"  # may be automatically reissued by Spine

    prescriptionTreatmentTypes = {
        ACUTE_PRESCRIBING: "Acute Prescription",
        REPEAT_PRESCRIBING: "Repeat Prescribing",
        REPEAT_DISPENSING: "Repeat Dispensing",
    }


class PrescriptionTypes(object):
    """
    Constants for prescription type.
    """

    # Translate prescription type codes to their text value
    prescriptionTypeCodes = {
        "0001": "GENERAL PRACTITIONER PRESCRIBING",
        "0002": "INTENTIONALLY LEFT BLANK",
        "0003": "NURSE PRACTITIONER PRESCRIBING",
        "0004": "HOSPITAL PRESCRIBING",
        "0006": "DENTAL PRESCRIBING",
        "0007": "SUPPLEMENTARY PRESCRIBER PRESCRIBING",
        "0009": "GENERAL PRACTITIONER PRESCRIBING: PRIVATE",
        "0012": "EXTENDED FORUMULARY PRESCRIBER",
        "0101": "PRIMARY CARE PRESCRIBER - MEDICAL PRESCRIBER",
        "0102": "GENERAL PRACTITIONER PRESCRIBING - TRAINEE DOCTOR/GP REGISTRAR",
        "0103": "GENERAL PRACTITIONER PRESCRIBING - DEPUTISING SERVICES",
        "0104": "PRIMARY CARE PRESCRIBER - NURSE INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0105": "PRIMARY CARE PRESCRIBER - COMMUNITY PRACTITIONER NURSE PRESCRIBER",
        "0106": "GENERAL PRACTITIONER PRESCRIBING - PCT EMPLOYED NURSE INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0107": "GENERAL PRACTITIONER PRESCRIBING - PCT EMPLOYED COMMUNITY PRACTITIONER NURSE PRESCRIBER",
        "0108": "PRIMARY CARE PRESCRIBER - PHARMACIST INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0109": "GENERAL PRACTITIONER PRESCRIBING - PCT EMPLOYED PHARMACIST PRESCRIBER",
        "0113": "PRIMARY CARE PRESCRIBER - OPTOMETRIST INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0114": "PRIMARY CARE PRESCRIBER - PODIATRIST/CHIROPODIST INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0116": "PRIMARY CARE PRESCRIBER - RADIOGRAPHER INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0117": "PRIMARY CARE PRESCRIBER - PHYSIOTHERAPIST INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0119": "GENERAL PRACTITIONER PRESCRIBING - PCT EMPLOYED PODIATRIST/CHIROPODIST",
        "0120": "GENERAL PRACTITIONER PRESCRIBING - PCT EMPLOYED OPTOMETRIST",
        "0121": "GENERAL PRACTITIONER PRESCRIBING - PCT EMPLOYED RADIOGRAPHER",
        "0122": "GENERAL PRACTITIONER PRESCRIBING - PCT EMPLOYED PHYSIOTHERAPIST",
        "0123": "PRIMARY CARE PRESCRIBER - HOSPITAL PRESCRIBER",
        "0124": "PRIMARY CARE PRESCRIBER - DIETICIAN SUPPLEMENTARY PRESCRIBER",
        "0125": "PRIMARY CARE PRESCRIBER - PARAMEDIC INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0304": "NURSE PRACTITIONER - PRACTICE EMPLOYED NURSE INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0305": "NURSE PRACTITIONER - PRACTICE EMPLOYED COMMUNITY PRACTITIONER NURSE PRESCRIBER",
        "0306": "NURSE PRACTITIONER - PRACTICE EMPLOYED NURSE INDEPENDENT/SUPPLEMENTARY PRESCRIBER",
        "0307": "NURSE PRACTITIONER - PRACTICE EMPLOYED COMMUNITY PRACTITIONER NURSE PRESCRIBER",
        "0406": "HOSPITAL PRESCRIBING - HOSPITAL PRESCRIBER",
        "0607": "DENTAL PRESCRIBING - DENTIST",
        "0708": "SUPPLEMENTARY PRESCRIBING - PRACTICE EMPLOYED PHARMACIST",
        "0709": "SUPPLEMENTARY PRESCRIBING - PCT EMPLOYED PHARMACIST",
        "0713": "SUPPLEMENTARY PRESCRIBING - PRACTICE EMPLOYED OPTOMETRIST",
        "0714": "SUPPLEMENTARY PRESCRIBING - PRACTICE EMPLOYED PODIATRIST/CHIROPODIST",
        "0716": "SUPPLEMENTARY PRESCRIBING - PRACTICE EMPLOYED RADIOGRAPHER",
        "0717": "SUPPLEMENTARY PRESCRIBING - PRACTICE EMPLOYED PHYSIOTHERAPIST",
        "0718": "SUPPLEMENTARY PRESCRIBING - PCT EMPLOYED OPTOMETRIST",
        "0719": "SUPPLEMENTARY PRESCRIBING - PCT EMPLOYED PODIATRIST/CHIROPODIST",
        "0721": "SUPPLEMENTARY PRESCRIBING - PCT EMPLOYED RADIOGRAPHER",
        "0722": "SUPPLEMENTARY PRESCRIBING - PCT EMPLOYED PHYSIOTHERAPIST",
        "0901": "PRIVATE PRESCRIBING - GP",
        "0904": "PRIVATE PRESCRIBING - NURSE PRESCRIBING",
        "0908": "PRIVATE PRESCRIBING - PHARMACIST PRESCRIBING",
        "0913": "PRIVATE PRESCRIBING - OPTOMETRIST",
        "0914": "PRIVATE PRESCRIBING - PODIATRIST/CHIROPODIST",
        "0915": "PRIVATE PRESCRIBING - PHYSIOTHERAPIST",
        "0916": "PRIVATE PRESCRIBING - RADIOGRAPHER",
        "1004": "Outpatient Community Prescriber - Nurse Independent Supplementary prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1005": "Outpatient Community Prescriber - Community Practitioner Nurse prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1008": "Outpatient Community Prescriber - Pharmacist Independent Supplementary prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1013": "Outpatient Community Prescriber - Optometrist Independent Supplementary prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1014": "Outpatient Community Prescriber - Podiatrist Chiropodist Independent Supplementary prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1016": "Outpatient Community Prescriber - Radiographer Independent Supplementary prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1017": "Outpatient Community Prescriber - Physiotherapist Independent Supplementary prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1024": "Outpatient Community Prescriber - Dietician Supplementary prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1025": "Outpatient Community Prescriber - Paramedic Independent Supplementary prescriber - FP10SS (HP) Hospital outpatient prescriptions dispensed in a community pharmacy",
        "1104": "Outpatient Hospital Pharmacy Prescriber - Nurse Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1105": "Outpatient Hospital Pharmacy Prescriber - Community Practitioner Nurse prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1108": "Outpatient Hospital Pharmacy Prescriber - Pharmacist Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1113": "Outpatient Hospital Pharmacy Prescriber - Optometrist Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1114": "Outpatient Hospital Pharmacy Prescriber - Podiatrist Chiropodist Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1116": "Outpatient Hospital Pharmacy Prescriber - Radiographer Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1117": "Outpatient Hospital Pharmacy Prescriber - Physiotherapist Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1124": "Outpatient Hospital Pharmacy Prescriber - Dietician Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1125": "Outpatient Hospital Pharmacy Prescriber - Paramedic Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed in their own hospital pharmacy",
        "1204": "Outpatient Homecare Prescriber - Nurse Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1205": "Outpatient Homecare Prescriber - Community Practitioner Nurse prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1208": "Outpatient Homecare Prescriber - Pharmacist Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1213": "Outpatient Homecare Prescriber - Optometrist Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1214": "Outpatient Homecare Prescriber - Podiatrist Chiropodist Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1216": "Outpatient Homecare Prescriber - Radiographer Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1217": "Outpatient Homecare Prescriber - Physiotherapist Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1224": "Outpatient Homecare Prescriber - Dietician Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1225": "Outpatient Homecare Prescriber - Paramedic Independent Supplementary prescriber - NON- FP10 Hospital outpatient prescriptions dispensed by Homecare",
        "1001": "Outpatient Community Prescriber - Medical Prescriber",
        "1101": "Outpatient Pharmacy Prescriber - Medical Prescriber",
        "1201": "Outpatient Homecare Prescriber - Medical Prescriber",
        # WELSH CODES
        "0201": "Primary Care Prescriber - Medical Prescriber (Wales)",
        "0204": "Primary Care Prescriber - Nurse Independent/Supplementary prescriber (Wales)",
        "0205": "Primary Care Prescriber - Community Practitioner Nurse prescriber (Wales)",
        "0208": "Primary Care Prescriber - Pharmacist Independent/Supplementary prescriber (Wales)",
        "0213": "Primary Care Prescriber - Optometrist Independent/Supplementary prescriber (Wales)",
        "0214": "Primary Care Prescriber - Podiatrist/Chiropodist Independent/Supplementary prescriber (Wales)",
        "0216": "Primary Care Prescriber - Radiographer Independent/Supplementary prescriber (Wales)",
        "0217": "Primary Care Prescriber - Physiotherapist Independent/Supplementary prescriber (Wales)",
        "0224": "Primary Care Prescriber - Dietician Supplementary prescriber (Wales)",
        "0225": "Primary Care Prescriber - Paramedic Independent/Supplementary prescriber (Wales)",
        "2001": "Outpatient Community Prescriber - Medical Prescriber (Wales)",
        "2004": "Outpatient Community Prescriber - Nurse Independent/Supplementary prescriber (Wales)",
        "2005": "Outpatient Community Prescriber - Community Practitioner Nurse prescriber (Wales)",
        "2008": "Outpatient Community Prescriber - Pharmacist Independent/Supplementary prescriber (Wales)",
        "2013": "Outpatient Community Prescriber - Optometrist Independent/Supplementary prescriber (Wales)",
        "2014": "Outpatient Community Prescriber - Podiatrist/Chiropodist Independent/Supplementary (Wales)",
        "2016": "Outpatient Community Prescriber - Radiographer Independent/Supplementary prescriber (Wales)",
        "2017": "Outpatient Community Prescriber - Physiotherapist Independent/Supplementary prescriber (Wales)",
        "2024": "Outpatient Community Prescriber - Dietician Supplementary prescriber (Wales)",
        "2025": "Outpatient Community Prescriber - Paramedic Independent/Supplementary prescriber (Wales)",
        "0707": "Dental Prescribing - Dentist (Wales)",
        # ISLE OF MANN CODES
        "0501": "Primary Care Prescriber - Medical Prescriber (IOM)",
        "0504": "Primary Care Prescriber - Nurse Independent/Supplementary prescriber (IOM)",
        "0505": "Primary Care Prescriber - Community Practitioner Nurse prescriber (IOM)",
        "0508": "Primary Care Prescriber - Pharmacist Independent/Supplementary prescriber (IOM)",
        "0513": "Primary Care Prescriber - Optometrist Independent/Supplementary prescriber (IOM)",
        "0514": "Primary Care Prescriber - Podiatrist/Chiropodist Independent/Supplementary prescriber (IOM)",
        "0516": "Primary Care Prescriber - Radiographer Independent/Supplementary prescriber (IOM)",
        "0517": "Primary Care Prescriber - Physiotherapist Independent/Supplementary prescriber (IOM)",
        "0524": "Primary Care Prescriber - Dietician Supplementary prescriber (IOM)",
        "0525": "Primary Care Prescriber - Paramedic Independent/Supplementary prescriber (IOM)",
        "5001": "Outpatient Community Prescriber - Medical Prescriber (IOM)",
        "5004": "Outpatient Community Prescriber - Nurse Independent/Supplementary prescriber (IOM)",
        "5005": "Outpatient Community Prescriber - Community Practitioner Nurse prescriber (IOM)",
        "5008": "Outpatient Community Prescriber - Pharmacist Independent/Supplementary prescriber (IOM)",
        "5013": "Outpatient Community Prescriber - Optometrist Independent/Supplementary prescriber (IOM)",
        "5014": "Outpatient Community Prescriber - Podiatrist/Chiropodist Independent/Supplementary (IOM)",
        "5016": "Outpatient Community Prescriber - Radiographer Independent/Supplementary prescriber (IOM)",
        "5017": "Outpatient Community Prescriber - Physiotherapist Independent/Supplementary prescriber (IOM)",
        "5024": "Outpatient Community Prescriber - Dietician Supplementary prescriber (IOM)",
        "5025": "Outpatient Community Prescriber - Paramedic Independent/Supplementary prescriber (IOM)",
    }


class PrescriptionLineItem(object):
    """
    Wrapper class to simplify interacting with line item sections of a prescription record.
    """

    def __init__(self, line_item_dict):
        """
        Constructor.

        :type line_item_dict: dict
        """
        self._line_item_dict = line_item_dict

    @property
    def id(self):
        """
        The line item's ID.

        :rtype: str
        """
        return self._line_item_dict[PrescriptionRecord.FIELD_ID]

    @property
    def status(self):
        """
        The status of this line item.

        :rtype: str
        """
        return self._line_item_dict[PrescriptionRecord.FIELD_STATUS]

    @property
    def previous_status(self):
        """
        The previous status of this line item.

        :rtype: str
        """
        return self._line_item_dict[PrescriptionRecord.FIELD_PREVIOUS_STATUS]

    @property
    def order(self):
        """
        The order of this line item.

        :rtype: int
        """
        return self._line_item_dict[PrescriptionRecord.FIELD_ORDER]

    @property
    def max_repeats(self):
        """
        The maximum number of repeats for this line item.

        :rtype: int
        """
        return int(self._line_item_dict[PrescriptionRecord.FIELD_MAX_REPEATS])

    def is_active(self):
        """
        Test whether this line item is active.

        :rtype: bool
        """
        return self.status in LineItemStatus.ACTIVE_STATES

    def update_status(self, new_status):
        """
        Set the line item status, and remember the previous status.

        :type new_status: str
        """
        self._line_item_dict[PrescriptionRecord.FIELD_PREVIOUS_STATUS] = self._line_item_dict[
            PrescriptionRecord.FIELD_STATUS
        ]
        self._line_item_dict[PrescriptionRecord.FIELD_STATUS] = new_status

    def expire(self, parent_prescription):
        """
        Expire this line item.

        :type parent_prescription: PrescriptionRecord
        """
        currentStatus = self.status
        if currentStatus not in LineItemStatus.EXPIRY_IMMUTABLE_STATES:
            newStatus = LineItemStatus.EXPIRY_LOOKUP[currentStatus]
            self.update_status(newStatus)
            parent_prescription.logObject.writeLog(
                "EPS0072b",
                None,
                {
                    "internalID": parent_prescription.internalID,
                    "lineItemChanged": self.id,
                    "previousStatus": currentStatus,
                    "newStatus": newStatus,
                },
            )


class PrescriptionClaim(object):
    """
    Wrapper class to simplify interacting with an issue claim portion of a prescription record.
    """

    def __init__(self, claim_dict):
        """
        Constructor.

        :type claim_dict: dict
        """
        self._claim_dict = claim_dict

    @property
    def received_date_str(self):
        """
        The date the claim was received.

        :rtype: str
        """
        return self._claim_dict[PrescriptionRecord.FIELD_CLAIM_RECEIVED_DATE]

    @received_date_str.setter
    def received_date_str(self, value):
        """
        The date the claim was received.

        :type value: str
        """
        self._claim_dict[PrescriptionRecord.FIELD_CLAIM_RECEIVED_DATE] = value

    def get_dict(self):
        """
        returns claim_dict
        """
        return self._claim_dict


class PrescriptionIssue(object):
    """
    Wrapper class to simplify interacting with an issue (instance) portion of a prescription record.

    Note: the correct domain terminology is "issue", however there are legacy references
    to "instance" in the code and database records.
    """

    def __init__(self, issue_dict):
        """
        Constructor.

        :type issue_dict: dict
        """
        self._issue_dict = issue_dict

    @property
    def number(self):
        """
        The number of this issue.

        :rtype: int
        """
        # Note: the number is stored as a string, so we need to convert
        number = int(self._issue_dict[PrescriptionRecord.FIELD_INSTANCE_NUMBER])
        return number

    @property
    def status(self):
        """
        The status code of the issue

        :rtype: str
        """
        return self._issue_dict[PrescriptionRecord.FIELD_PRESCRIPTION_STATUS]

    @status.setter
    def status(self, new_status):
        """
        The status code of the issue

        NOTE: this does not update the previous status - use update_status() to do that
        PAB - should we be using update_status() in places we are using this?
        :type new_status: str
        """
        self._issue_dict[PrescriptionRecord.FIELD_PRESCRIPTION_STATUS] = new_status

    @property
    def completion_date_str(self):
        """
        The issue completion date as a YYYYMMDD string, if available.

        :rtype: str or None
        """
        completion_date_str = self._issue_dict[PrescriptionRecord.FIELD_COMPLETION_DATE]
        if not completion_date_str:
            return None
        return completion_date_str

    def expire(self, expired_at_time, parent_prescription):
        """
        Update the issue and all its line items to be expired.

        :type expired_at_time: datetime.datetime
        :type parent_prescription: PrescriptionRecord
        """

        currentStatus = self.status

        # update the issue status, if appropriate
        if currentStatus not in PrescriptionStatus.EXPIRY_IMMUTABLE_STATES:
            newStatus = PrescriptionStatus.EXPIRY_LOOKUP[currentStatus]
            self.update_status(newStatus, parent_prescription)

            if currentStatus in PrescriptionStatus.UNACTIONED_STATES:
                parent_prescription.logObject.writeLog(
                    "EPS0616",
                    None,
                    {
                        "internalID": parent_prescription.internalID,
                        "previousStatus": currentStatus,
                        "releaseVersion": parent_prescription.getReleaseVersion(),
                        "prescriptionID": str(parent_prescription.returnPrescriptionID()),
                    },
                )

        # make sure all the line items are expired as well
        for lineItem in self.line_items:
            lineItem.expire(parent_prescription)

        parent_prescription.logObject.writeLog(
            "EPS0403",
            None,
            {
                "internalID": parent_prescription.internalID,
            },
        )

        # PAB: this will update the completion time of issues that are
        # already in EXPIRY_IMMUTABLE_STATES (ie. already completed) - is
        # this correct, or should this be guarded in the above if statement?
        self.mark_completed(expired_at_time, parent_prescription)

    def mark_completed(self, completion_datetime, parent_prescription):
        """
        Update the completion date of this issue.

        :type completion_datetime: datetime.datetime
        :type parent_prescription: PrescriptionRecord
        """
        current_completion_date_str = self.completion_date_str

        new_completion_date_str = completion_datetime.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        self._issue_dict[PrescriptionRecord.FIELD_COMPLETION_DATE] = new_completion_date_str

        parent_prescription.logAttributeChange(
            PrescriptionRecord.FIELD_COMPLETION_DATE,
            (current_completion_date_str or ""),
            new_completion_date_str,
            None,
        )

    @property
    def expiry_date_str(self):
        """
        The issue expiry date as a YYYYMMDD string.

        :rtype: str
        """
        return self._issue_dict[PrescriptionRecord.FIELD_EXPIRY_DATE]

    @property
    def line_items(self):
        """
        The line items for this issue.

        :rtype: list(PrescriptionLineItem)
        """
        line_item_dicts = self._issue_dict[PrescriptionRecord.FIELD_LINE_ITEMS]
        # wrap the dicts to add convenience methods
        line_items = [PrescriptionLineItem(d) for d in line_item_dicts]
        return line_items

    @property
    def claim(self):
        """
        The claim information for this issue.

        :rtype: PrescriptionClaim
        """
        claim_dict = self._issue_dict[PrescriptionRecord.FIELD_CLAIM]
        return PrescriptionClaim(claim_dict)

    def update_status(self, new_status, parent_prescription):
        """
        Update the issue status, and record the previous status.

        :type new_status: str
        """
        currentStatus = self.status
        self._issue_dict[PrescriptionRecord.FIELD_PREVIOUS_STATUS] = currentStatus
        self._issue_dict[PrescriptionRecord.FIELD_PRESCRIPTION_STATUS] = new_status
        parent_prescription.logAttributeChange(
            PrescriptionRecord.FIELD_PRESCRIPTION_STATUS, currentStatus, new_status, None
        )

    @property
    def dispensing_organization(self):
        """
        Dispensing organization for this issue.

        :rtype: str
        """
        dispense_dict = self._issue_dict[PrescriptionRecord.FIELD_DISPENSE]
        return dispense_dict[PrescriptionRecord.FIELD_DISPENSING_ORGANIZATION]

    @property
    def last_dispense_date(self):
        """
        Dispensing date for this issue.

        :rtype: str
        """
        dispense_dict = self._issue_dict[PrescriptionRecord.FIELD_DISPENSE]
        return dispense_dict[PrescriptionRecord.FIELD_LAST_DISPENSE_DATE]

    @property
    def last_dispense_notification_msg_ref(self):
        """
        Last Dispense Notification MsgRef for this issue.

        :rtype: str
        """
        dispense_dict = self._issue_dict[PrescriptionRecord.FIELD_DISPENSE]
        return dispense_dict[PrescriptionRecord.FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF]

    def clear_dispensing_organisation(self):
        """
        Clear the dispensing organisation from this instance.
        """
        dispense_dict = self._issue_dict[PrescriptionRecord.FIELD_DISPENSE]
        dispense_dict[PrescriptionRecord.FIELD_DISPENSING_ORGANIZATION] = None

    @property
    def dispense_window_low_date(self):
        """
        Dispense window low date

        :rtype: datetime or None
        """
        low_date_str = self._issue_dict.get(PrescriptionRecord.FIELD_DISPENSE_WINDOW_LOW_DATE)
        if not low_date_str:
            return None
        return datetime.datetime.strptime(low_date_str, TimeFormats.STANDARD_DATE_FORMAT)

    def has_active_line_item(self):
        """
        See if this instance has any active line items.

        :rtype: bool
        """
        return any(lineItem.is_active() for lineItem in self.line_items)

    def get_line_item_by_id(self, line_item_id):
        """
        Get a particular line item by its ID.

        Raises a KeyError if no item can be found.

        :type line_item_id: str
        :rtype: PrescriptionLineItem
        """
        for lineItem in self.line_items:
            if lineItem.id == line_item_id:
                return lineItem

        raise KeyError("Could not find line item '%s'" % line_item_id)

    @property
    def release_date(self):
        """
        The releaseDate for this issue, if one is specified

        :rtype: str
        """
        release_date = self._issue_dict.get(PrescriptionRecord.FIELD_RELEASE_DATE)
        return str(release_date)

    @property
    def next_activity(self):
        """
        The next activity for this issue, if one is specified.

        Note: some migrated prescriptions may not have a next activity specified,
        although this should hopefully be rectified. If so, we may be able to tighten
        up the return type.

        :rtype: str or None
        """
        next_activity_dict = self._issue_dict[PrescriptionRecord.FIELD_NEXT_ACTIVITY]
        return next_activity_dict.get(PrescriptionRecord.FIELD_ACTIVITY, None)

    @property
    def next_activity_date_str(self):
        """
        The next activity date for this issue, if one is specified.

        :rtype: str or None
        """
        next_activity_dict = self._issue_dict[PrescriptionRecord.FIELD_NEXT_ACTIVITY]
        return next_activity_dict.get(PrescriptionRecord.FIELD_DATE, None)

    @property
    def cancellations(self):
        """
        The cancellations for this issue.

        :rtype: list()
        """
        return self._issue_dict[PrescriptionRecord.FIELD_CANCELLATIONS]

    def get_line_item_cancellations(self, line_item_id):
        """
        Get the cancellations for a particular line item.

        :type line_item_id: str
        :rtype: list()
        """
        return [
            c
            for c in self.cancellations
            if c[PrescriptionRecord.FIELD_CANCEL_LINE_ITEM_REF] == line_item_id
        ]

    def get_line_item_first_cancellation_time(self, line_item_id):
        """
        Get the time of the first cancellation targetting a particular line item.

        :type line_item_id: str
        :rtype: str or None
        """
        cancellations = self.get_line_item_cancellations(line_item_id)
        cancellation_times = [c[PrescriptionRecord.FIELD_CANCELLATION_TIME] for c in cancellations]

        if cancellations:
            return min(cancellation_times, key=lambda x: int(x))
        return None

    @property
    def release_request_msg_ref(self):
        """
        The release request message reference for this issue.

        :rtype: str
        """
        return self._issue_dict[PrescriptionRecord.FIELD_RELEASE_REQUEST_MGS_REF]


class PrescriptionRecord(object):
    """
    Base class for all Prescriptions record objects

    A record object should be created by the validator used by a particular interaction
    The validator can then update the attributes of this object.

    The object should then support creating a new record, or existing an updated record
    using the attributes which have been bound to it
    """

    FIELD_AGENT_ORGANIZATION = "agentOrganization"
    FIELD_BATCH_ID = "batchID"
    FIELD_BATCH_NUMBER = "batchNumber"
    FIELD_BIRTH_TIME = "birthTime"
    FIELD_PREFIX = "prefix"
    FIELD_SUFFIX = "suffix"
    FIELD_GIVEN = "given"
    FIELD_FAMILY = "family"
    FIELD_CANCEL_LINE_ITEM_REF = "cancelLineItemRef"
    FIELD_CANCELLATION_ID = "cancellationID"
    FIELD_CANCELLATION_MSG_REF = "cancellationMsgRef"
    FIELD_CANCELLATION_TARGET = "cancellationTarget"
    FIELD_CANCELLATION_TIME = "cancellationTime"
    FIELD_CANCELLATIONS = "cancellations"
    FIELD_CHANGE_LOG = "changeLog"
    FIELD_CLAIM = "claim"
    FIELD_CLAIM_GUID = "claimGUID"
    FIELD_CLAIM_REBUILD = "claimRebuild"
    FIELD_CLAIM_RECEIVED_DATE = "claimReceivedDate"
    FIELD_CLAIM_SENT_DATE = "claimSentDate"
    FIELD_CLAIM_STATUS = "claimStatus"
    FIELD_CLAIMED_DISPLAY_NAME = "claimed"
    FIELD_COMPLETION_DATE = "completionDate"
    FIELD_CURRENT_INSTANCE = "currentInstance"
    FIELD_DAYS_SUPPLY = "daysSupply"
    FIELD_DAYS_SUPPLY_HIGH = "daysSupplyValidHigh"
    FIELD_DAYS_SUPPLY_LOW = "daysSupplyValidLow"
    FIELD_DISPENSE = "dispense"
    FIELD_DISPENSE_DATE = "dispenseDate"
    FIELD_DISPENSE_TIME = "dispenseTime"
    FIELD_DISPENSE_CLAIM_MSG_REF = "dispenseClaimMsgRef"
    FIELD_DISPENSE_HISTORY = "dispenseHistory"
    FIELD_DISPENSE_WINDOW_HIGH_DATE = "dispenseWindowHighDate"
    FIELD_DISPENSE_WINDOW_LOW_DATE = "dispenseWindowLowDate"
    FIELD_DISPENSING_ORGANIZATION = "dispensingOrganization"
    FIELD_EXPIRY_DATE = "expiryDate"
    FIELD_EXPIRY_PERIOD = "expiryPeriod"
    FIELD_FORMATTED_EXPIRY_DATE = "formattedExpiryDate"
    FIELD_HANDLE_TIME = "handleTime"
    FIELD_HIGHER_AGE_LIMIT = "higherAgeLimit"
    FIELD_HISTORIC_CLAIM_GUIDS = "historicClaimGUIDs"
    FIELD_HISTORIC_CLAIMS = "historicClaims"
    FIELD_HISTORIC_DISPENSE_CLAIM_MSG_REF = "historicDispenseClaimMsgRef"
    FIELD_HL7 = "hl7"
    FIELD_ID = "ID"
    FIELD_INDEXES = "indexes"
    FIELD_INSTANCES = "instances"
    FIELD_INSTANCE_NUMBER = "instanceNumber"
    FIELD_ISSUE = "issue"
    FIELD_LAST_DISPENSE_DATE = "lastDispenseDate"
    FIELD_LAST_DISPENSE_NOTIFICATION_GUID = "lastDispenseNotificationGuid"
    FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF = "lastDispenseNotificationMsgRef"
    FIELD_LAST_DISPENSE_STATUS = "lastDispenseStatus"
    FIELD_LOWER_AGE_LIMIT = "lowerAgeLimit"
    FIELD_LINE_ITEMS = "lineItems"
    FIELD_MAX_REPEATS = "maxRepeats"
    FIELD_NEXT_ACTIVITY = "nextActivity"
    FIELD_NHS_NUMBER = "nhsNumber"
    FIELD_NOMINATION = "nomination"
    FIELD_NOMINATED = "nominated"
    FIELD_NOMINATED_DOWNLOAD_DATE = "nominatedDownloadDate"
    FIELD_NOMINATED_PERFORMER = "nominatedPerformer"
    FIELD_NOMINATED_PERFORMER_TYPE = "nominatedPerformerType"
    FIELD_NOMINATION_HISTORY = "nominationHistory"
    FIELD_ORDER = "order"
    FIELD_PATIENT = "patient"
    FIELD_PENDING_CANCELLATIONS = "pendingCancellations"
    FIELD_PRESCRIBING_ORG = "prescribingOrganization"
    FIELD_PRESCRIBING_SITE_TEST_STATUS = "prescribingSiteTestStatus"
    FIELD_PRESCRIPTION = "prescription"
    FIELD_PRESCRIPTION_ID = "prescriptionID"
    FIELD_PRESCRIPTION_MSG_REF = "prescriptionMsgRef"
    FIELD_PRESCRIPTION_PRESENT = "prescriptionPresent"
    FIELD_PRESCRIPTION_REPEAT_HIGH = "prescriptionRepeatHigh"
    FIELD_PRESCRIPTION_STATUS = "prescriptionStatus"
    FIELD_PRESCRIPTION_TIME = "prescriptionTime"
    FIELD_PRESCRIPTION_DATE = "prescriptionDate"
    # NOTE: be aware of the two similar named fields here:
    # - treatment type describes whether the prescription is acute, repeat prescribe or
    #   repeat dispense
    # - prescription type seems to indicate where the prescription is from, eg. GP, nurse
    #   hospital, dental, etc. - see MIM 4.2 for details (vocabulary "PrescriptionType")
    # Confusingly, they both accept similar values, ie. numeric codes of the form "000X",
    # so take care when examining prescription records!
    FIELD_PRESCRIPTION_TREATMENT_TYPE = "prescriptionTreatmentType"
    FIELD_PRESCRIPTION_TYPE = "prescriptionType"
    FIELD_PREVIOUS_STATUS = "previousStatus"
    FIELD_REASONS = "Reasons"
    FIELD_RELEASE = "release"
    FIELD_RELEASE_DATE = "releaseDate"
    FIELD_RELEASE_REQUEST_MGS_REF = "releaseRequestMsgRef"
    FIELD_RELEASE_DISPENSER_DETAILS = "releaseDispenserDetails"
    FIELD_RELEASE_VERSION = "releaseVersion"
    FIELD_SCN = "SCN"
    FIELD_SIGNED_TIME = "signedTime"
    FIELD_STATUS = "status"
    FIELD_UNSUCCESSFUL_CANCELLATIONS = "unsuccessfulCancellations"
    FIELD_ACTIVITY = "activity"
    FIELD_DATE = "date"
    FIELD_CAPITAL_D_DATE = "Date"
    FIELD_TIMESTAMP = "Timestamp"

    FIELD_PRESCRIPTION_STATUS_DISPLAY_NAME = "prescriptionStatusDisplayName"
    FIELD_PRESCRIPTION_CURRENT_INSTANCE = "prescriptionCurrentInstance"
    FIELD_PRESCRIPTION_MAX_REPEATS = "prescriptionMaxRepeats"
    FIELD_PREVIOUS_ISSUE_DATE = "priorPreviousIssueDate"

    TREATMENT_TYPE_ACUTE = "0001"
    TREATMENT_TYPE_REPEAT_PRESCRIBE = "0002"
    TREATMENT_TYPE_REPEAT_DISPENSE = "0003"

    DEFAULT_DAYSSUPPLY = 28

    PATIENT_DETAILS = [
        FIELD_NHS_NUMBER,
        FIELD_BIRTH_TIME,
        FIELD_LOWER_AGE_LIMIT,
        FIELD_HIGHER_AGE_LIMIT,
        FIELD_PREFIX,
        FIELD_SUFFIX,
        FIELD_GIVEN,
        FIELD_FAMILY,
    ]

    PRESCRIPTION_DETAILS = [
        FIELD_PRESCRIPTION_ID,
        FIELD_PRESCRIPTION_MSG_REF,
        FIELD_PRESCRIPTION_TREATMENT_TYPE,
        FIELD_PRESCRIPTION_TYPE,
        FIELD_PRESCRIPTION_TIME,
        FIELD_PRESCRIBING_ORG,
        FIELD_SIGNED_TIME,
        FIELD_DAYS_SUPPLY,
        FIELD_MAX_REPEATS,
        FIELD_PENDING_CANCELLATIONS,
        FIELD_UNSUCCESSFUL_CANCELLATIONS,
        FIELD_CURRENT_INSTANCE,
        FIELD_PRESCRIPTION_PRESENT,
        FIELD_HL7,
        FIELD_SCN,
    ]

    NOMINATION_DETAILS = [
        FIELD_NOMINATED,
        FIELD_NOMINATED_PERFORMER,
        FIELD_NOMINATED_PERFORMER_TYPE,
        FIELD_NOMINATION_HISTORY,
    ]

    INSTANCE_DETAILS = [
        FIELD_NEXT_ACTIVITY,
        FIELD_INSTANCE_NUMBER,
        FIELD_DISPENSE_WINDOW_LOW_DATE,
        FIELD_DISPENSE_WINDOW_HIGH_DATE,
        FIELD_PREVIOUS_ISSUE_DATE,
        FIELD_COMPLETION_DATE,
        FIELD_NOMINATED_DOWNLOAD_DATE,
        FIELD_RELEASE_DATE,
        FIELD_RELEASE_REQUEST_MGS_REF,
        FIELD_EXPIRY_DATE,
        FIELD_DISPENSE_HISTORY,
        FIELD_PRESCRIPTION_STATUS,
        FIELD_PREVIOUS_STATUS,
        FIELD_LAST_DISPENSE_STATUS,
    ]

    DISPENSE_DETAILS = [
        FIELD_DISPENSING_ORGANIZATION,
        FIELD_LAST_DISPENSE_NOTIFICATION_GUID,
        FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF,
        FIELD_LAST_DISPENSE_DATE,
    ]

    LINE_ITEM_DETAILS = [
        FIELD_STATUS,
        FIELD_ID,
        FIELD_PREVIOUS_STATUS,
        FIELD_ORDER,
        FIELD_MAX_REPEATS,
    ]

    CLAIM_DETAILS = [
        FIELD_CLAIM_GUID,
        FIELD_BATCH_ID,
        FIELD_BATCH_NUMBER,
        FIELD_DISPENSE_CLAIM_MSG_REF,
        FIELD_HISTORIC_DISPENSE_CLAIM_MSG_REF,
        FIELD_CLAIM_RECEIVED_DATE,
        FIELD_CLAIM_STATUS,
        FIELD_CLAIM_REBUILD,
        FIELD_HISTORIC_CLAIM_GUIDS,
    ]

    INSTANCE_CANCELLATION_DETAILS = [
        FIELD_CANCELLATION_ID,
        FIELD_AGENT_ORGANIZATION,
        FIELD_CANCELLATION_TARGET,
        FIELD_CANCELLATION_TIME,
        FIELD_CANCELLATION_MSG_REF,
        FIELD_CANCEL_LINE_ITEM_REF,
        FIELD_REASONS,
        FIELD_CANCELLATION_MSG_REF,
    ]

    R1_PRESCRIPTIONID_LENGTHS = [36, 37]
    R2_PRESCRIPTIONID_LENGTHS = [19, 20]

    R1_VERSION = "R1"
    R2_VERSION = "R2"

    NOMINATED_DOWNLOAD_LEAD_DAYS = 7

    _YOUNG_AGE_EXEMPTION = 16
    _OLD_AGE_EXEMPTION = 60

    NEXTACTIVITY_EXPIRE = "expire"
    NEXTACTIVITY_CREATENOCLAIM = "createNoClaim"
    NEXTACTIVITY_DELETE = "delete"
    NEXTACTIVITY_PURGE = "purge"
    NEXTACTIVITY_READY = "ready"
    ACTIVITY_NOMINATED_DOWNLOAD = "nominated-download"
    BATCH_STATUS_AVAILABLE = "Available"
    BATCH_STATUS_ALL = "All"
    BATCH_STATUS_CURRENT = "Current"
    ADMIN_ACTION_RESET_NAD = "resetNAD"
    SPECIAL_DISPENSE_RESET = "specialDispenseReset"
    SPECIAL_RESET_CURRENT_INSTANCE = "specialCurrentInstanceReset"
    SPECIAL_APPLY_PENDING_CANCELLATIONS = "specialApplyPendingCancellations"

    UPDATE_DETAIL_TEXT = {
        NEXTACTIVITY_EXPIRE: "Batch update for Prescription Expiry",
        NEXTACTIVITY_CREATENOCLAIM: "Batch create no claim",
        NEXTACTIVITY_DELETE: "Batch prescription deletion",
        NEXTACTIVITY_READY: "Batch make prescription available for download",
        ACTIVITY_NOMINATED_DOWNLOAD: "Batch make prescription available for nominated download",
        ADMIN_ACTION_RESET_NAD: "Administrative reset of Next Activity Date",
        SPECIAL_DISPENSE_RESET: "Administrative hard-reset return to Spine",
        SPECIAL_RESET_CURRENT_INSTANCE: "Administrative reset current issue number",
        SPECIAL_APPLY_PENDING_CANCELLATIONS: "Administrative apply all pending cancellations",
        NEXTACTIVITY_PURGE: "Batch prescription purge",
    }

    ACTIVITY_LOOKUP = {}
    ACTIVITY_LOOKUP[NEXTACTIVITY_EXPIRE] = NEXTACTIVITY_EXPIRE
    ACTIVITY_LOOKUP[NEXTACTIVITY_CREATENOCLAIM] = NEXTACTIVITY_CREATENOCLAIM
    ACTIVITY_LOOKUP[NEXTACTIVITY_DELETE] = NEXTACTIVITY_DELETE
    ACTIVITY_LOOKUP[NEXTACTIVITY_PURGE] = NEXTACTIVITY_PURGE
    ACTIVITY_LOOKUP[ACTIVITY_NOMINATED_DOWNLOAD] = NEXTACTIVITY_READY
    ACTIVITY_LOOKUP[ADMIN_ACTION_RESET_NAD] = ADMIN_ACTION_RESET_NAD
    ACTIVITY_LOOKUP[SPECIAL_DISPENSE_RESET] = SPECIAL_DISPENSE_RESET
    ACTIVITY_LOOKUP[SPECIAL_RESET_CURRENT_INSTANCE] = SPECIAL_RESET_CURRENT_INSTANCE
    ACTIVITY_LOOKUP[SPECIAL_APPLY_PENDING_CANCELLATIONS] = SPECIAL_APPLY_PENDING_CANCELLATIONS

    USER_IMPACTING_ACTIVITY = [NEXTACTIVITY_READY]

    FIELDS_DOCUMENTS = "documents"
    FIELDS_SCN = PrescriptionsChangeLogProcessor.RECORD_SCN_REF

    SCN_MAX = 512
    # Limit beyond which we should stop updating the change log as almost certainly in an
    # uncontrolled loop - and updating the change log may lead to the record being of an
    # unbounded size

    def __init__(self, log_object, internal_id):
        """
        The basic attributes of an epsRecord
        """
        self.logObject = log_object
        self.internalID = internal_id
        self.nad_generator = NextActivityGenerator(log_object, internal_id)
        self.pending_instance_change = None
        self.prescription_record = None
        self.pre_change_issue_status_dict = {}
        self.pre_change_current_issue = None

    def create_initial_record(self, context, prescription=True):
        """
        Take the context of a worker object - which should contain validated output, and
        use to build an initial prescription object

        The prescription boolean is used to indicate that the creation has been caused
        by receipt of an actual prescription.  The creation may be triggered on receipt
        of a cancellation (prior to a prescription) in which case this should be set to
        False.
        """

        self.name_map_on_create(context)

        self.prescription_record = {}
        self.prescription_record[self.FIELDS_DOCUMENTS] = []
        self.prescription_record[self.FIELD_PRESCRIPTION] = self.create_prescription_snippet(
            context
        )
        self.prescription_record[self.FIELD_PRESCRIPTION][
            self.FIELD_PRESCRIPTION_PRESENT
        ] = prescription
        self.prescription_record[self.FIELD_PATIENT] = self.create_patient_snippet(context)
        self.prescription_record[self.FIELD_NOMINATION] = self.create_nomination_snippet(context)
        line_items = self.create_line_items(context)
        self.prescription_record[self.FIELD_INSTANCES] = self.create_instances(context, line_items)

    def return_prechange_issue_status_dict(self):
        """
        Returns a dictionary of the initial statuses by issue number.
        """
        return self.pre_change_issue_status_dict

    def return_prechange_current_issue(self):
        """
        Returns the current issue as it was prior to this change
        """
        return self.pre_change_current_issue

    def return_changed_issue_list(
        self,
        pre_change_issue_list,
        post_change_issue_list,
        max_repeats=None,
        changed_issues_list=None,
    ):
        """
        Iterate through the prescription issues comparing the pre and post change status dict
        for each issue number, checking for differences. If a difference is found, add the
        issue number as a string to the returned changed_issues_list.

        Accept an initial changed_issues_list as this may need to include other issues, e.g. in the pending cancellation
        case, an issue can be changed by adding a pending cancellation, even though the statuses don't change.
        """

        if not changed_issues_list:
            changed_issues_list = []

        if not max_repeats:
            max_repeats = self.maxRepeats
        for i in range(1, int(max_repeats) + 1):
            issue_ref = self.generate_status_dict_issue_reference(i)
            # The get will handle missing issues from the change log
            if pre_change_issue_list.get(issue_ref, {}) == post_change_issue_list.get(
                issue_ref, {}
            ):
                continue
            changed_issues_list.append(str(i))

        return changed_issues_list

    def generate_status_dict_issue_reference(self, issue_number):
        """
        Create the status dict issue reference. Moved into a separate function as it is used
        in a couple of places.
        """
        return self.FIELD_ISSUE + str(issue_number)

    def create_issue_current_status_dict(self):
        """
        Cycle through all of the issues in the prescription and add the current prescription
        status and the status of each line item (by order not ID) to a dictionary keyed on issue number
        """
        status_dict = {}
        prescription_issues = self.prescription_record[self.FIELD_INSTANCES]
        for issue in prescription_issues:
            issue_dict = {}
            issue_dict[self.FIELD_PRESCRIPTION] = str(
                prescription_issues[issue][self.FIELD_PRESCRIPTION_STATUS]
            )
            issue_dict[self.FIELD_LINE_ITEMS] = {}
            for line_item in prescription_issues[issue][self.FIELD_LINE_ITEMS]:
                line_order = line_item[self.FIELD_ORDER]
                line_status = line_item[self.FIELD_STATUS]
                issue_dict[self.FIELD_LINE_ITEMS][str(line_order)] = str(line_status)
            status_dict[self.generate_status_dict_issue_reference(issue)] = issue_dict
        return status_dict

    def add_event_to_change_log(self, message_id, event_log):
        """
        Add the event_log to the change log under the key of message_id. If the changeLog does
        not exist it will be created.

        Prescriptions change logs will not be be pruned and will grow unbounded.
        """
        # Set the SCN on the change log to be the same as on the record
        event_log[PrescriptionsChangeLogProcessor.SCN] = self.get_scn()
        length_before = len(self.prescription_record.get(self.FIELD_CHANGE_LOG, []))
        try:
            PrescriptionsChangeLogProcessor.updateChangeLog(
                self.prescription_record, event_log, message_id, self.SCN_MAX
            )
        except Exception as e:  # noqa: BLE001
            self.logObject.writeLog(
                "EPS0336",
                sys.exc_info(),
                {"internalID": self.internalID, "prescriptionID": self.id, "error": str(e)},
            )
            raise EpsSystemError(EpsSystemError.SYSTEM_FAILURE) from e
        length_after = len(self.prescription_record.get(self.FIELD_CHANGE_LOG, []))
        if length_after != length_before + 1:
            self.logObject.writeLog(
                "EPS0672",
                None,
                {
                    "internalID": self.internalID,
                    "lengthBefore": str(length_before),
                    "lengthAfter": str(length_after),
                },
            )

    def add_index_to_record(self, index_dict):
        """
        Replace the existing index information with a new set of index information
        """
        self.prescription_record[self.FIELD_INDEXES] = index_dict

    def increment_scn(self):
        """
        Check for an SCN on the record, if one does not already exist, add it.
        If it does exist, increment it - but throw a system error if this exceed a
        maximum to prevent a prescription ending up in an uncontrolled loop - SPII-14250.
        """
        if self.FIELDS_SCN not in self.prescription_record:
            self.prescription_record[self.FIELDS_SCN] = PrescriptionsChangeLogProcessor.INITIAL_SCN
        else:
            self.prescription_record[self.FIELDS_SCN] += 1

    def get_scn(self):
        """
        Check for an SCN on the record, if one does not already exist, create it.
        If it already exists, return it.
        """
        if self.FIELDS_SCN not in self.prescription_record:
            self.prescription_record[self.FIELDS_SCN] = PrescriptionsChangeLogProcessor.INITIAL_SCN

        return self.prescription_record[self.FIELDS_SCN]

    def add_document_references(self, document_refs):
        """
        Adds a document reference to the high-level document list.
        """
        if self.FIELDS_DOCUMENTS not in self.prescription_record:
            self.prescription_record[self.FIELDS_DOCUMENTS] = []

        for document in document_refs:
            self.prescription_record[self.FIELDS_DOCUMENTS].append(document)

    def return_record_to_be_stored(self):
        """
        Return a copy of the record in a storable format (i.e. note that this is not json
        encoded here - it will be encoded as it is placed onto the WDO)
        """
        return self.prescription_record

    def return_next_activity_nad_bin(self):
        """
        Return the nextActivityNAD_bin index of the prescription record
        """
        if self.FIELD_INDEXES in self.prescription_record:
            if indexes.INDEX_NEXTACTIVITY in self.prescription_record[self.FIELD_INDEXES]:
                return self.prescription_record[self.FIELD_INDEXES][indexes.INDEX_NEXTACTIVITY]
            if indexes.INDEX_NEXTACTIVITY.lower() in self.prescription_record[self.FIELD_INDEXES]:
                return self.prescription_record[self.FIELD_INDEXES][
                    indexes.INDEX_NEXTACTIVITY.lower()
                ]
        return None

    def create_record_from_store(self, record):
        """
        Convert the stored format into a self.prescription_record
        """
        self.prescription_record = record
        self.pre_change_issue_status_dict = self.create_issue_current_status_dict()
        self.pre_change_current_issue = self.prescription_record.get(
            self.FIELD_PRESCRIPTION, {}
        ).get(self.FIELD_CURRENT_INSTANCE)

    def name_map_on_create(self, context):
        """
        Map any additional names from the original context (e.g. if the property here is
        named differently at the point of extract from the message such as with
        agentOrganization)
        """

        context.prescribingOrganization = context.agentOrganization
        if hasattr(context, self.FIELD_PRESCRIPTION_REPEAT_HIGH):
            context.maxRepeats = context.prescriptionRepeatHigh
        if hasattr(context, self.FIELD_DAYS_SUPPLY_LOW):
            context.dispenseWindowLowDate = context.daysSupplyValidLow
        if hasattr(context, self.FIELD_DAYS_SUPPLY_HIGH):
            context.dispenseWindowHighDate = context.daysSupplyValidHigh

    def create_instances(self, context, line_items):
        """
        Create all prescription instances
        """
        instance_snippet = self.set_all_snippet_details(
            PrescriptionRecord.INSTANCE_DETAILS, context
        )
        instance_snippet[self.FIELD_LINE_ITEMS] = line_items
        instance_snippet[self.FIELD_INSTANCE_NUMBER] = "1"
        instance_snippet[self.FIELD_DISPENSE] = self.set_all_snippet_details(
            PrescriptionRecord.DISPENSE_DETAILS, context
        )
        instance_snippet[self.FIELD_CLAIM] = self.set_all_snippet_details(
            PrescriptionRecord.CLAIM_DETAILS, context
        )
        instance_snippet[self.FIELD_CANCELLATIONS] = []
        instance_snippet[self.FIELD_DISPENSE_HISTORY] = {}
        instance_snippet[self.FIELD_NEXT_ACTIVITY] = {}
        instance_snippet[self.FIELD_NEXT_ACTIVITY][self.FIELD_ACTIVITY] = None
        instance_snippet[self.FIELD_NEXT_ACTIVITY][self.FIELD_DATE] = None

        return {"1": instance_snippet}

    def create_prescription_snippet(self, context):
        """
        Create the prescription snippet from the prescription details
        """
        presc_details = self.set_all_snippet_details(
            PrescriptionRecord.PRESCRIPTION_DETAILS, context
        )
        presc_details[self.FIELD_CURRENT_INSTANCE] = str(1)
        return presc_details

    def create_patient_snippet(self, context):
        """
        Create the patient snippet from the patient details
        """
        return self.set_all_snippet_details(PrescriptionRecord.PATIENT_DETAILS, context)

    def create_nomination_snippet(self, context):
        """
        Create the nomination snippet from the nomination details
        """
        nomination_snippet = self.set_all_snippet_details(
            PrescriptionRecord.NOMINATION_DETAILS, context
        )
        if hasattr(context, self.FIELD_NOMINATED_PERFORMER):
            if context.nominatedPerformer:
                nomination_snippet[self.FIELD_NOMINATED] = True
        if not nomination_snippet[self.FIELD_NOMINATION_HISTORY]:
            nomination_snippet[self.FIELD_NOMINATION_HISTORY] = []
        return nomination_snippet

    def set_all_snippet_details(self, details_list, context):
        """
        Default any missing value to False
        """
        snippet = {}
        for item_detail in details_list:
            if hasattr(context, item_detail):
                value = getattr(context, item_detail)
            elif isinstance(context, dict) and item_detail in context:
                value = context[item_detail]
            else:
                snippet[item_detail] = False
                continue

            if isinstance(value, datetime.datetime):
                value = value.strftime(TimeFormats.STANDARD_DATE_TIME_FORMAT)
            snippet[item_detail] = value
        return snippet

    def create_line_items(self, context):
        """
        Create individual line items
        """

        complete_line_items = []

        for line_item in context.lineItems:
            line_item_snippet = self.set_all_snippet_details(
                PrescriptionRecord.LINE_ITEM_DETAILS, line_item
            )
            complete_line_items.append(line_item_snippet)

        return complete_line_items

    def _get_prescription_instance_data(self, instance_number, raise_exception_on_missing=True):
        """
        Internal method to support record access
        """
        prescription_instance_data = self.prescription_record[self.FIELD_INSTANCES].get(
            instance_number
        )
        if not prescription_instance_data:
            if raise_exception_on_missing:
                self._handle_missing_issue(instance_number)
            else:
                return {}
        return prescription_instance_data

    def get_prescription_instance_data(self, instance_number, raise_exception_on_missing=True):
        """
        Public method to support record access
        """
        return self._get_prescription_instance_data(instance_number, raise_exception_on_missing)

    @property
    def future_issues_available(self):
        """
        Return boolean to indicate if future issues are available or not. Always False for
        Acute and Repeat Prescribe
        """
        return False

    def get_issue(self, issue_number):
        """
        Get a particular issue of this prescription.

        :type issue_number: int
        :rtype: PrescriptionIssue
        """
        # explicitly check that we are receiving an int, as legacy code used strs
        if not isinstance(issue_number, int):
            raise TypeError("Issue number must be an int")

        issue_number_str = str(issue_number)
        issue_data = self.prescription_record[self.FIELD_INSTANCES].get(issue_number_str)

        if not issue_data:
            self._handle_missing_issue(issue_number)

        issue = PrescriptionIssue(issue_data)
        return issue

    def _handle_missing_issue(self, issue_number):
        """
        Missing instances are a data migration specific issue, and will throw
        a prescription not found error after after being logged
        """
        self.logObject.writeLog(
            "EPS0073c",
            None,
            {"internalID": self.internalID, "prescriptionID": self.id, "issue": issue_number},
        )
        # Re-raise this as SpineBusinessError with equivalent errorCode from ErrorBase1722.
        raise EpsBusinessError(EpsErrorBase.PRESCRIPTION_NOT_FOUND)

    @property
    def id(self):
        """
        The prescription's ID.

        :rtype: str
        """
        return self.prescription_record[self.FIELD_PRESCRIPTION][self.FIELD_PRESCRIPTION_ID]

    @property
    def issue_numbers(self):
        """
        Sorted list of issue numbers.

        Note: migrated prescriptions may have missing issues (before the current one)
        so do not be surprised if the list returned here is not the complete range.

        :rtype: list(int)
        """
        # we have to convert instance numbers to ints, as they're stored as strings
        issue_numbers = [int(i) for i in list(self.prescription_record["instances"].keys())]
        return sorted(issue_numbers)

    def get_issue_numbers_in_range(self, lowest=None, highest=None):
        """
        Sorted list of issue numbers in the specified range (inclusive).

        If either lowest or highest threshold is set to None then it will be ignored.

        :type lowest: int or None
        :type highest: int or None
        :rtype: list(int)
        """
        candidate_numbers = self.issue_numbers

        if lowest is not None:
            candidate_numbers = [i for i in candidate_numbers if i >= lowest]

        if highest is not None:
            candidate_numbers = [i for i in candidate_numbers if i <= highest]

        return candidate_numbers

    def get_issues_in_range(self, lowest=None, highest=None):
        """
        Sorted list of issues in the specified range (inclusive).

        If either lowest or highest threshold is set to None then it will be ignored.

        :type lowest: int or None
        :type highest: int or None
        :rtype: list(PrescriptionIssue)
        """
        issues = [self.get_issue(i) for i in self.get_issue_numbers_in_range(lowest, highest)]
        return issues

    def getIssuesFromCurrentUpwards(self):
        """
        Sorted list of issues, starting at the current one.

        :rtype: list(PrescriptionIssue)
        """
        return self.get_issues_in_range(self.currentIssueNumber, None)

    @property
    def missingIssueNumbers(self):
        """
        Sorted list of numbers of instances missing from the prescription.

        :rtype: list(int)
        """
        expectedIssueNumbers = range(1, self.maxRepeats + 1)
        actual_issue_numbers = self.issue_numbers
        missingIssueNumbers = set(expectedIssueNumbers) - set(actual_issue_numbers)

        return sorted(list(missingIssueNumbers))

    @property
    def issues(self):
        """
        List of issues, ordered by issue number.

        :rtype: list(PrescriptionIssue)
        """
        issues = [self.get_issue(i) for i in self.issue_numbers]
        return issues

    @property
    def _currentInstanceData(self):
        """
        Internal property to support record access
        """
        return self._get_prescription_instance_data(str(self.currentIssueNumber))

    @property
    def currentIssueNumber(self):
        """
        The current issue number of this prescription.

        :rtype: int
        """
        currentIssueNumberStr = self.prescription_record[self.FIELD_PRESCRIPTION].get(
            self.FIELD_CURRENT_INSTANCE
        )
        if not currentIssueNumberStr:
            self._handle_missing_issue(self.FIELD_CURRENT_INSTANCE)
        return int(currentIssueNumberStr)

    @currentIssueNumber.setter
    def currentIssueNumber(self, value):
        """
        The current issue number of this prescription.

        :type value: int
        """
        # explicitly check that we are receiving an int, as legacy code used strs
        if not isinstance(value, int):
            raise TypeError("Issue number must be an int")

        currentIssueNumberStr = str(value)
        self.prescription_record[self.FIELD_PRESCRIPTION][
            self.FIELD_CURRENT_INSTANCE
        ] = currentIssueNumberStr

    @property
    def currentIssue(self):
        """
        The current issue of this prescription.

        :rtype: PrescriptionIssue
        """
        return self.get_issue(self.currentIssueNumber)

    @property
    def _currentInstanceStatus(self):
        """
        Internal property to support record access

        ..  deprecated::
            use "currentIssue.status" instead
        """
        return self._currentInstanceData[self.FIELD_PRESCRIPTION_STATUS]

    @property
    def _pendingCancellations(self):
        """
        Internal property to support record access
        """
        return self.prescription_record[self.FIELD_PRESCRIPTION][self.FIELD_PENDING_CANCELLATIONS]

    @property
    def _pendingCancellationFlag(self):
        """
        Internal property to support record access
        """
        obj = self.prescription_record.get(self.FIELD_PRESCRIPTION, {}).get(
            self.FIELD_PENDING_CANCELLATIONS
        )
        if not obj:
            return False
        if isinstance(obj, list) and obj:
            return True
        return False

    @_pendingCancellations.setter
    def _pendingCancellations(self, value):
        """
        Internal property to support record access
        """
        self.prescription_record[self.FIELD_PRESCRIPTION][self.FIELD_PENDING_CANCELLATIONS] = value

    @property
    def _nhsNumber(self):
        """
        Internal property to support record access
        """
        return self.prescription_record[self.FIELD_PATIENT][self.FIELD_NHS_NUMBER]

    @property
    def _prescriptionTime(self):
        """
        Internal property to support record access

        ..  deprecated::
            use "time" instead (which returns a datetime instead of a str)
            PAB - but note - this field may contain just a date str, not a datetime?!
        :rtype: str
        """
        return self.prescription_record[self.FIELD_PRESCRIPTION][self.FIELD_PRESCRIPTION_TIME]

    @property
    def time(self):
        """
        The datetime of the prescription.

        PAB - what does this time actually signify? It needs better naming

        :rtype: datetime.datetime
        """
        prescriptionTimeStr = self.prescription_record[self.FIELD_PRESCRIPTION][
            self.FIELD_PRESCRIPTION_TIME
        ]
        prescriptionTime = datetime.datetime.strptime(
            prescriptionTimeStr, TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        return prescriptionTime

    @property
    def _releaseVersion(self):
        """
        Internal property to support record access
        """
        _prescriptionID = str(self.returnPrescriptionID())
        _idLength = len(_prescriptionID)
        if _idLength in self.R1_PRESCRIPTIONID_LENGTHS:
            return self.R1_VERSION
        if _idLength in self.R2_PRESCRIPTIONID_LENGTHS:
            return self.R2_VERSION

    def getReleaseVersion(self):
        """
        Return the prescription release version (R1 or R2)
        """
        return self._releaseVersion

    def addReleaseAndStatus(self, indexPrefix, isString=True):
        """
        returns a list containing the indexprefix concatenated with all applicable release
        versions and Prescription Statuses
        """
        _releaseVersion = self._releaseVersion
        _statusList = self.returnPrescriptionStatusSet()
        returnSet = []
        for eachStatus in _statusList:
            if not isString:
                for eachIndex in indexPrefix:
                    _newValue = eachIndex + "|" + _releaseVersion + "|" + eachStatus
                    returnSet.append(_newValue)
            else:
                _newValue = indexPrefix + "|" + _releaseVersion + "|" + eachStatus
                returnSet.append(_newValue)

        return returnSet

    def updateNominatedPerformer(self, context):
        """
        Update the "nominated performer" field and log the change.
        """
        nomination = self.prescription_record[self.FIELD_NOMINATION]
        self.logAttributeChange(
            self.FIELD_NOMINATED_PERFORMER,
            nomination[self.FIELD_NOMINATED_PERFORMER],
            context.nominatedPerformer,
            context.fieldsToUpdate,
        )
        nomination[self.FIELD_NOMINATED_PERFORMER] = context.nominatedPerformer

    def returnPrescSiteStatusIndex(self):
        """
        Return the prescribingOrganization and the prescription status
        """
        _prescSite = self.prescription_record[self.FIELD_PRESCRIPTION][self.FIELD_PRESCRIBING_ORG]
        _prescStatus = self.returnPrescriptionStatusSet()
        return [True, _prescSite, _prescStatus]

    def returnNomPharmStatusIndex(self):
        """
        Return the Nominated Pharmacy and the prescription status
        """
        nomPharm = self.returnNomPharm()
        if not nomPharm:
            return [None, None]
        prescStatus = self.returnPrescriptionStatusSet()
        return [nomPharm, prescStatus]

    def returnNomPharm(self):
        """
        Return the Nominated Pharmacy
        """
        return self.prescription_record.get(self.FIELD_NOMINATION, {}).get(
            self.FIELD_NOMINATED_PERFORMER
        )

    def returnDispSiteOrNomPharm(self, instance):
        """
        Returns the Dispensing Site if available, otherwise, returns the Nominated Pharmacy
        or None if neither exist
        """
        _dispSite = instance.get(self.FIELD_DISPENSE, {}).get(self.FIELD_DISPENSING_ORGANIZATION)
        if not _dispSite:
            _dispSite = self.returnNomPharm()
        return _dispSite

    def returnDispSiteStatusIndex(self):
        """
        Return the dispensingOrganization and the prescription status.
        If nominated but not yet downloaded, return NomPharm instead of dispensingOrg
        """
        dispensingSiteStatuses = set()
        for instanceKey in self.prescription_record[self.FIELD_INSTANCES]:
            instance = self._get_prescription_instance_data(instanceKey)
            _dispSite = self.returnDispSiteOrNomPharm(instance)
            if not _dispSite:
                continue
            _prescStatus = instance[self.FIELD_PRESCRIPTION_STATUS]
            dispensingSiteStatuses.add(_dispSite + "_" + _prescStatus)

        return [True, dispensingSiteStatuses]

    def returnNhsNumberPrescriberDispenserDateIndex(self):
        """
        Return the NHS Number Prescribing organization dispensingOrganization and the prescription date
        """
        nhsNumber = self.returnNHSNumber()
        prescriber = self.returnPrescribingOrganisation()
        indexStart = nhsNumber + "|" + prescriber + "|"
        prescriptionTime = self.returnPrescriptionTime()
        nhsNumberPrescDispDates = set()
        for instanceKey in self.prescription_record[self.FIELD_INSTANCES]:
            instance = self._get_prescription_instance_data(instanceKey)
            _dispSite = self.returnDispSiteOrNomPharm(instance)
            if not _dispSite:
                continue
            nhsNumberPrescDispDates.add(indexStart + _dispSite + "|" + prescriptionTime)

        return [True, nhsNumberPrescDispDates]

    def returnPrescriberDispenserDateIndex(self):
        """
        Return the Prescribing organization dispensingOrganization and the prescription date
        """
        prescriber = self.returnPrescribingOrganisation()
        indexStart = prescriber + "|"
        prescriptionTime = self.returnPrescriptionTime()
        prescDispDates = set()
        for instanceKey in self.prescription_record[self.FIELD_INSTANCES]:
            instance = self._get_prescription_instance_data(instanceKey)
            _dispSite = self.returnDispSiteOrNomPharm(instance)
            if not _dispSite:
                continue
            prescDispDates.add(indexStart + _dispSite + "|" + prescriptionTime)

        return [True, prescDispDates]

    def returnDispenserDateIndex(self):
        """
        Return the dispensingOrganization and the prescription date
        """
        indexStart = ""
        prescriptionTime = self.returnPrescriptionTime()
        prescDispDates = set()
        for instanceKey in self.prescription_record[self.FIELD_INSTANCES]:
            instance = self._get_prescription_instance_data(instanceKey)
            _dispSite = self.returnDispSiteOrNomPharm(instance)
            if not _dispSite:
                continue
            prescDispDates.add(indexStart + _dispSite + "|" + prescriptionTime)

        return [True, prescDispDates]

    def returnNhsNumberDispenserDateIndex(self):
        """
        Return the NHS Number dispensingOrganization and the prescription date
        """
        nhsNumber = self.returnNHSNumber()
        indexStart = nhsNumber + "|"
        prescriptionTime = self.returnPrescriptionTime()
        nhsNumberDispDates = set()
        for instanceKey in self.prescription_record[self.FIELD_INSTANCES]:
            instance = self._get_prescription_instance_data(instanceKey)
            _dispSite = self.returnDispSiteOrNomPharm(instance)
            if not _dispSite:
                continue
            nhsNumberDispDates.add(indexStart + _dispSite + "|" + prescriptionTime)

        return [True, nhsNumberDispDates]

    def returnNominatedPerformer(self):
        """
        Return the nominated performer (called when determining routing key extension)
        """
        nomPerformer = None
        _nomination = self.prescription_record.get(self.FIELD_NOMINATION)
        if _nomination:
            nomPerformer = _nomination.get(self.FIELD_NOMINATED_PERFORMER)
        return nomPerformer

    def returnNominatedPerformerType(self):
        """
        Return the nominated performer type
        """
        nomPerformerType = None
        _nomination = self.prescription_record.get(self.FIELD_NOMINATION)
        if _nomination:
            nomPerformerType = _nomination.get(self.FIELD_NOMINATED_PERFORMER_TYPE)
        return nomPerformerType

    def returnPrescriptionStatusSet(self):
        """
        For single instance prescription - the prescription status is always the current
        status of the first (and only) instance
        """
        statusSet = set()
        for instanceKey in self.prescription_record[self.FIELD_INSTANCES]:
            instance = self._get_prescription_instance_data(instanceKey)
            statusSet.add(instance[self.FIELD_PRESCRIPTION_STATUS])
        return list(statusSet)

    def returnNHSNumber(self):
        """
        Return the NHS Number
        """
        return self._nhsNumber

    def returnPrescriptionTime(self):
        """
        Return the Prescription Time
        """
        return self._prescriptionTime

    def returnPrescriptionID(self):
        """
        Return the Prescription ID
        """
        return self.prescription_record[self.FIELD_PRESCRIPTION][self.FIELD_PRESCRIPTION_ID]

    def returnPendingCancellationsFlag(self):
        """
        Return the pending cancellations flag
        """
        _prescription = self.prescription_record[self.FIELD_PRESCRIPTION]
        _maxRepeats = _prescription.get(self.FIELD_MAX_REPEATS)

        if not _maxRepeats:
            _maxRepeats = 1

        for prescriptionIssue in range(1, int(_maxRepeats) + 1):
            _prescriptionIssue = self.prescription_record[self.FIELD_INSTANCES].get(
                str(prescriptionIssue)
            )
            # handle missing issues
            if not _prescriptionIssue:
                continue
            issueSpecificCancellations = {}
            _appliedCancellationsForIssue = _prescriptionIssue.get(self.FIELD_CANCELLATIONS, [])
            _cancellationStatusStringPrefix = ""
            self._createCancellationSummaryDict(
                _appliedCancellationsForIssue,
                issueSpecificCancellations,
                _cancellationStatusStringPrefix,
            )
            if str(_prescriptionIssue[self.FIELD_INSTANCE_NUMBER]) == str(
                _prescription[self.FIELD_CURRENT_INSTANCE]
            ):
                _pendingCancellations = _prescription[self.FIELD_PENDING_CANCELLATIONS]
                _cancellationStatusStringPrefix = "Pending: "
                self._createCancellationSummaryDict(
                    _pendingCancellations,
                    issueSpecificCancellations,
                    _cancellationStatusStringPrefix,
                )
                for _, val in issueSpecificCancellations.items():
                    if val.get(self.FIELD_REASONS, "")[:7] == "Pending":
                        return True

        return False

    def _createCancellationSummaryDict(
        self, recordedCancellations, issueCancellationDict, cancellationStatus
    ):
        """
        Process a list of cancellations, creating a dictionary of cancellation reason text
        and applied SCN for each prescription and issue.

        cancellationStatus is used to seed the reasons in the pending scenario.
        """

        if not recordedCancellations:
            return

        for _cancellation in recordedCancellations:
            _subsequentReason = False
            _cancellationReasons = str(cancellationStatus)

            _cancellationID = _cancellation.get(self.FIELD_CANCELLATION_ID, [])
            _scn = PrescriptionsChangeLogProcessor.getSCN(
                self.prescription_record["changeLog"].get(_cancellationID, {})
            )
            for _cancellationReason in _cancellation.get(self.FIELD_REASONS, []):
                _cancellationText = _cancellationReason.split(":")[1].strip()
                if _subsequentReason:
                    _cancellationReasons += "; "
                _subsequentReason = True
                _cancellationReasons += str(handleEncodingOddities(_cancellationText))

            if _cancellation.get(self.FIELD_CANCELLATION_TARGET) == "Prescription":  # noqa: SIM108
                _cancellationTarget = self.FIELD_PRESCRIPTION
            else:
                _cancellationTarget = _cancellation.get(self.FIELD_CANCEL_LINE_ITEM_REF)

            if (
                issueCancellationDict.get(_cancellationTarget, {}).get(self.FIELD_ID)
                == _cancellationID
            ):
                # Cancellation has already been added and this is pending as multiple cancellations are not possible
                return

            issueCancellationDict[_cancellationTarget] = {
                self.FIELD_SCN: _scn,
                self.FIELD_REASONS: _cancellationReasons,
                self.FIELD_ID: _cancellationID,
            }

    def returnCurrentInstance(self):
        """
        Return the current instance

        ..  deprecated::
            use "currentIssueNumber" instead (which returns int instead of string)
        """
        return str(self.currentIssueNumber)

    def returnPrescriptionStatus(self, instanceNumber, raiseExceptionOnMissing=True):
        """
        For single instance prescription - the prescription status is always the current
        status of the first (and only) instance
        """
        return self._get_prescription_instance_data(
            str(instanceNumber), raiseExceptionOnMissing
        ).get(self.FIELD_PRESCRIPTION_STATUS)

    def returnPreviousPrescriptionStatus(self, instanceNumber, raiseExceptionOnMissing=True):
        """
        For single instance prescription - the previous prescription status is always the
        previous status of the first (and only) instance
        """
        return self._get_prescription_instance_data(
            str(instanceNumber), raiseExceptionOnMissing
        ).get(self.FIELD_PREVIOUS_STATUS)

    def returnLineItemByRef(self, instanceNumber, lineItemRef):
        """
        Return the line item from the instance that matches the reference provided
        """
        for lineItem in self._get_prescription_instance_data(instanceNumber)[self.FIELD_LINE_ITEMS]:
            if lineItem[self.FIELD_ID] == lineItemRef:
                return lineItem
        return None

    def returnPrescribingOrganisation(self):
        """
        Return the prescribing organisation from the record
        """
        return self.prescription_record[self.FIELD_PRESCRIPTION][self.FIELD_PRESCRIBING_ORG]

    def returnLastDnGuid(self, instanceNumber):
        """
        Return references to the last dispense notification messages
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        try:
            dispnMsgGuid = instance[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_NOTIFICATION_GUID]
            return dispnMsgGuid
        except KeyError:
            return None

    def returnLastDcGuid(self, instanceNumber):
        """
        Return references to the last dispense notification messages
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        try:
            claimMsgGuid = instance[self.FIELD_CLAIM][self.FIELD_CLAIM_GUID]
            return claimMsgGuid
        except KeyError:
            return None

    def returnDocumentReferencesForClaim(self, instanceNumber):
        """
        Return references to prescription, dispense notification and claim messages
        """
        prescMsgRef = self.prescription_record[self.FIELD_PRESCRIPTION][
            self.FIELD_PRESCRIPTION_MSG_REF
        ]
        instance = self._get_prescription_instance_data(instanceNumber)
        dispnMsgRef = instance[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF]
        claimMsgRef = instance[self.FIELD_CLAIM][self.FIELD_DISPENSE_CLAIM_MSG_REF]
        return [prescMsgRef, dispnMsgRef, claimMsgRef]

    def returnClaimDate(self, instanceNumber):
        """
        Returns the claim date recorded for an instance
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        claimRcvDate = instance[self.FIELD_CLAIM][self.FIELD_CLAIM_RECEIVED_DATE]
        return claimRcvDate

    def checkReal(self):
        """
        Check that the prescription object is real (as opposed to an empty one created
        by a pendingCancellation)

        If the prescriptionPresent flag is not there - act as if True
        """
        try:
            return self.prescription_record[self.FIELD_PRESCRIPTION][
                self.FIELD_PRESCRIPTION_PRESENT
            ]
        except KeyError:
            return True

    def checkReturnedRecordIsReal(self, returnedRecord):
        """
        Check that the returnedRecord is real (as opposed to an empty one created
        by a pendingCancellation). Look for a valid prescriptionTreatmentType
        """
        if returnedRecord[self.FIELD_PRESCRIPTION][self.FIELD_PRESCRIPTION_TREATMENT_TYPE]:
            return True

        return False

    def _getDispenseListToCheck(self, prescriptionStatus):
        """
        Consistency check fields
        """
        if prescriptionStatus == PrescriptionStatus.WITH_DISPENSER:
            checkList = [self.FIELD_DISPENSING_ORGANIZATION]
        elif prescriptionStatus == PrescriptionStatus.WITH_DISPENSER_ACTIVE:
            checkList = [self.FIELD_DISPENSING_ORGANIZATION, self.FIELD_LAST_DISPENSE_DATE]
        elif prescriptionStatus in [PrescriptionStatus.DISPENSED, PrescriptionStatus.CLAIMED]:
            checkList = [self.FIELD_LAST_DISPENSE_DATE]
        else:
            checkList = []

        return checkList

    def _getInstanceListToCheck(self, prescriptionStatus):
        """
        Consistency check fields
        """
        if prescriptionStatus == PrescriptionStatus.EXPIRED:
            checkList = [self.FIELD_COMPLETION_DATE, self.FIELD_EXPIRY_DATE]
        elif prescriptionStatus in [PrescriptionStatus.CANCELLED, PrescriptionStatus.NOT_DISPENSED]:
            checkList = [self.FIELD_COMPLETION_DATE]
        elif prescriptionStatus in [
            PrescriptionStatus.AWAITING_RELEASE_READY,
            PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE,
        ]:
            checkList = [self.FIELD_DISPENSE_WINDOW_LOW_DATE, self.FIELD_NOMINATED_DOWNLOAD_DATE]
        else:
            checkList = []

        return checkList

    def _getPrescriptionListToCheck(self, prescriptionStatus):
        """
        Consistency check fields
        """
        if prescriptionStatus in [
            PrescriptionStatus.AWAITING_RELEASE_READY,
            PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE,
        ]:
            checkList = [self.FIELD_PRESCRIPTION_TIME]
        else:
            checkList = [self.FIELD_PRESCRIPTION_TREATMENT_TYPE, self.FIELD_PRESCRIPTION_TIME]

        return checkList

    def _getClaimListToCheck(self, prescriptionStatus):
        """
        Consistency check fields
        """
        return (
            [self.FIELD_CLAIM_RECEIVED_DATE]
            if prescriptionStatus == PrescriptionStatus.CLAIMED
            else []
        )

    def _getNominateListToCheck(self):
        """
        Consistency check fields
        """
        pTType = self.prescription_record[self.FIELD_PRESCRIPTION][
            self.FIELD_PRESCRIPTION_TREATMENT_TYPE
        ]
        return (
            [self.FIELD_NOMINATED_PERFORMER]
            if pTType == self.TREATMENT_TYPE_REPEAT_DISPENSE
            else []
        )

    def checkRecordConsistency(self, context):
        """
        Check each line item to ensure consistency with the prescription status for
        this instance - the epsAdminUpdate can only impact a single instance

        *** Should be called targetInstance not currentInstance ***

        Check for the prescription status for that instance that required data exists
        Check a nominatedPerformer is set for repeat prescriptions (although this may
        not be required as a check due to DPR rules)
        """

        testFailures = []

        instanceDict = self._get_prescription_instance_data(context.currentInstance)

        for lineItemDict in instanceDict[self.FIELD_LINE_ITEMS]:
            valid = self.validateLinePrescriptionStatus(
                instanceDict[self.FIELD_PRESCRIPTION_STATUS], lineItemDict[self.FIELD_STATUS]
            )
            if not valid:
                testFailures.append("lineItemStatus check for " + lineItemDict[self.FIELD_ID])

        prescriptionStatus = instanceDict[self.FIELD_PRESCRIPTION_STATUS]

        prescription = self.prescription_record[self.FIELD_PRESCRIPTION]
        prescriptionList = self._getPrescriptionListToCheck(prescriptionStatus)
        self.individualConsistencyChecks(prescriptionList, prescription, testFailures)

        instanceList = self._getInstanceListToCheck(prescriptionStatus)
        self.individualConsistencyChecks(instanceList, instanceDict, testFailures)

        nomination = self.prescription_record[self.FIELD_NOMINATION]
        nominateList = self._getNominateListToCheck()
        self.individualConsistencyChecks(nominateList, nomination, testFailures, False)

        dispenseList = self._getDispenseListToCheck(prescriptionStatus)
        self.individualConsistencyChecks(
            dispenseList, instanceDict[self.FIELD_DISPENSE], testFailures
        )

        claimList = self._getClaimListToCheck(prescriptionStatus)
        self.individualConsistencyChecks(claimList, instanceDict[self.FIELD_CLAIM], testFailures)

        if not testFailures:
            return [True, None]

        for failureReason in testFailures:
            self.logObject.writeLog(
                "EPS0073",
                None,
                {
                    "internalID": self.internalID,
                    "failureReason": failureReason,
                },
            )

        return [False, "Record consistency check failure"]

    def individualConsistencyChecks(self, listOfChecks, recordPart, testFailures, failOnNone=True):
        """
        Loop through field names in a list to confirm there is a value on the recordPart
        for each field
        """
        for reqField in listOfChecks:
            if reqField not in recordPart:
                testFailures.append("Mandatory item " + reqField + " missing")
            if not recordPart[reqField]:
                if failOnNone:
                    testFailures.append("Mandatory item " + reqField + " set to None")
                    return
                self.logObject.writeLog(
                    "EPS0073b", None, {"internalID": self.internalID, "mandatoryItem": reqField}
                )

    def determineIfFinalIssue(self, _issueNumber):
        """
        Check if the issue is the final one, this may be because the current issue is
        already at MaxRepeats, or becuase subsequent issues are missing
        """
        if _issueNumber == self.maxRepeats:
            return True

        for i in range(int(_issueNumber) + 1, int(self.maxRepeats + 1)):
            issue_data = self._get_prescription_instance_data(str(i), False)
            if issue_data.get(self.FIELD_PRESCRIPTION_STATUS):
                return False
        return True

    def returnNextActivityIndex(self, testSites, nadReference, context):
        """
        Iterate through all prescription instances, determining the Next Activity and Date
        for each, and then set the lowest to the record.
        Ignore a next activity of delete for all but the last instance
        In the case of a tie-break, set the priority based on user impact (making a
        prescription instance 'ready' for download takes precedence over deleting or
        expiring an instance)
        """
        earliestActivityDate = "99991231"
        deleteDate = "99991231"

        earliestActivity = None

        for instanceKey in self.prescription_record[self.FIELD_INSTANCES]:
            instanceDict = self._get_prescription_instance_data(instanceKey, False)
            if not instanceDict.get(self.FIELD_PRESCRIPTION_STATUS):
                continue

            issue = PrescriptionIssue(instanceDict)
            nadStatus = self.setNadStatus(testSites, context, str(issue.number))
            [nextActivity, nextActivityDate, expiryDate] = self.nad_generator.nextActivityDate(
                nadStatus, nadReference
            )

            if self.FIELD_NEXT_ACTIVITY not in instanceDict:
                instanceDict[self.FIELD_NEXT_ACTIVITY] = {}

            instanceDict[self.FIELD_NEXT_ACTIVITY][self.FIELD_ACTIVITY] = nextActivity
            instanceDict[self.FIELD_NEXT_ACTIVITY][self.FIELD_DATE] = nextActivityDate

            if isinstance(expiryDate, datetime.datetime):
                expiryDate = expiryDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)

            instanceDict[self.FIELD_EXPIRY_DATE] = expiryDate

            _issueIsFinal = self.determineIfFinalIssue(issue.number)

            if not self._includeNextActivityForInstance(
                nextActivity, issue.number, self.currentIssueNumber, self.maxRepeats, _issueIsFinal
            ):
                continue

            # treat deletion separately to next activities
            if nextActivity == self.NEXTACTIVITY_DELETE:
                deleteDate = nextActivityDate
                continue

            # Note: string comparison of dates in YYYYMMDD format
            if nextActivityDate < earliestActivityDate:
                earliestActivityDate = nextActivityDate
                earliestActivity = nextActivity

            # Note: string comparison of dates in YYYYMMDD format
            if nextActivityDate <= earliestActivityDate:
                for activity in self.USER_IMPACTING_ACTIVITY:
                    if nextActivity == activity or earliestActivity == activity:
                        earliestActivity = activity
                        break

        if earliestActivity:
            return [earliestActivity, earliestActivityDate]

        return [self.NEXTACTIVITY_DELETE, deleteDate]

    def _includeNextActivityForInstance(
        self, nextActivity, issueNumber, currentIssueNumber, maxRepeats, issueIsFinal=None
    ):
        """
        Check whether the nextActivity should be included for the issue as a position
        within the prescription repeat issues.
         - The final issue (issueNumber == maxRepeats) supports everything
         - The previous issue(s) (issueNumber < currentInstance) support createNoClaim
         - The current issue supports everything other than delete and purge
         - Future issues support nothing

        Note: we shouldn't really need to pass in the currentIssueNumber and maxRepeats
        parameters as these are available from self. However, the unit tests are
        currently written to expect these to be passed in.

        Also note that due to missing prescription issues from Spine1, we need to be extra
        cautious and cannot just assume that later issues are present.

        :type nextActivity: str
        :type issueNumber: int
        :type currentIssueNumber: int
        :type maxRepeats: int
        :rtype: bool
        """

        issueIsCurrent = issueNumber == currentIssueNumber
        if not issueIsFinal:
            issueIsFinal = issueNumber == maxRepeats
        issueIsBeforeCurrent = issueNumber < currentIssueNumber
        allRemainingIssuesMissing = (issueNumber < currentIssueNumber) and (issueIsFinal)

        # default for future issue
        permittedActivities = []

        if (issueIsCurrent and issueIsFinal) or allRemainingIssuesMissing:
            # final issue
            permittedActivities = [
                self.NEXTACTIVITY_EXPIRE,
                self.NEXTACTIVITY_CREATENOCLAIM,
                self.NEXTACTIVITY_READY,
                self.NEXTACTIVITY_DELETE,
                self.NEXTACTIVITY_PURGE,
            ]

        elif issueIsBeforeCurrent:
            # previous issue
            permittedActivities = [self.NEXTACTIVITY_CREATENOCLAIM]

        elif issueIsCurrent:
            # current issue
            permittedActivities = [
                self.NEXTACTIVITY_EXPIRE,
                self.NEXTACTIVITY_READY,
                self.NEXTACTIVITY_CREATENOCLAIM,
            ]

        return nextActivity in permittedActivities

    def setNadStatus(self, testPrescribingSites, context, instanceNumberStr):
        """
        Create the status fields that are required for the Next Activity Index calculation

        *** Shortcut taken converting time to date for prescriptionTime - relies on
        relationship between standardDate format and standardDateTimeFormat staying
        consistent ***
        """
        _prescDetails = self.prescription_record[self.FIELD_PRESCRIPTION]
        _instDetails = self._get_prescription_instance_data(instanceNumberStr, False)

        nadStatus = {}
        nadStatus[self.FIELD_PRESCRIPTION_TREATMENT_TYPE] = _prescDetails[
            self.FIELD_PRESCRIPTION_TREATMENT_TYPE
        ]
        nadStatus[self.FIELD_PRESCRIPTION_DATE] = _prescDetails[self.FIELD_PRESCRIPTION_TIME][:8]
        nadStatus[self.FIELD_RELEASE_VERSION] = self._releaseVersion

        if _prescDetails[self.FIELD_PRESCRIBING_ORG] in testPrescribingSites:
            nadStatus[self.FIELD_PRESCRIBING_SITE_TEST_STATUS] = True
        else:
            nadStatus[self.FIELD_PRESCRIBING_SITE_TEST_STATUS] = False

        nadStatus[self.FIELD_DISPENSE_WINDOW_HIGH_DATE] = _instDetails[
            self.FIELD_DISPENSE_WINDOW_HIGH_DATE
        ]
        nadStatus[self.FIELD_DISPENSE_WINDOW_LOW_DATE] = _instDetails[
            self.FIELD_DISPENSE_WINDOW_LOW_DATE
        ]
        nadStatus[self.FIELD_NOMINATED_DOWNLOAD_DATE] = _instDetails[
            self.FIELD_NOMINATED_DOWNLOAD_DATE
        ]
        nadStatus[self.FIELD_LAST_DISPENSE_DATE] = _instDetails[self.FIELD_DISPENSE][
            self.FIELD_LAST_DISPENSE_DATE
        ]
        nadStatus[self.FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF] = _instDetails[
            self.FIELD_DISPENSE
        ][self.FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF]
        nadStatus[self.FIELD_COMPLETION_DATE] = _instDetails[self.FIELD_COMPLETION_DATE]
        nadStatus[self.FIELD_CLAIM_SENT_DATE] = _instDetails[self.FIELD_CLAIM][
            self.FIELD_CLAIM_RECEIVED_DATE
        ]
        nadStatus[self.FIELD_HANDLE_TIME] = context.handleTime
        nadStatus[self.FIELD_PRESCRIPTION_STATUS] = self.returnPrescriptionStatus(instanceNumberStr)
        nadStatus[self.FIELD_INSTANCE_NUMBER] = instanceNumberStr

        return nadStatus

    def rollForwardInstance(self):
        """
        If the currentInstance is changed, it is first stored as a pending_instance_change
        - so that the update can be applied at the end of the process
        """
        if self.pending_instance_change is not None:
            self.currentIssueNumber = int(self.pending_instance_change)

    def compareLineItemsForDispense(self, passedLineItems, validStatusChanges, instanceNumber):
        """
        Compare the line items provided on a dispense message with the previous (stored)
        state on the record to determine if this is a valid dispense notification for
        each line items.

        passedLineItems will be a list of lineItem dictionaries - with each lineItem
        having and:
        self.FIELD_ID - to match to an ID on the record
        'DN_ID' - a GUID for the dispense notification for that specific line item (this
        will actually be ignored)
        self.FIELD_STATUS - A changed status following the dispense of which this is a
        notification
        self.FIELD_MAX_REPEATS - to match the maxRepeats of the original record
        self.FIELD_CURRENT_INSTANCE - to match the instanceNumber of the current record

        Note that as per SPII-6085, we should permit a Repeat Prescribe message without a
        repeat number.
        """
        treatmentType = self.prescription_record[self.FIELD_PRESCRIPTION][
            self.FIELD_PRESCRIPTION_TREATMENT_TYPE
        ]
        instance = self._get_prescription_instance_data(instanceNumber)

        storedLineItems = instance[self.FIELD_LINE_ITEMS]
        [storedIDs, passedIDs] = [set(), set()]
        for lineItem in storedLineItems:
            storedIDs.add(str(lineItem[self.FIELD_ID]))
        for lineItem in passedLineItems:
            passedIDs.add(str(lineItem[self.FIELD_ID]))
        if storedIDs != passedIDs:
            self.logObject.writeLog(
                "EPS0146",
                None,
                {
                    "internalID": self.internalID,
                    "storedIDs": str(storedIDs),
                    "passedIDs": str(passedIDs),
                },
            )
            # Re-raise this as SpineBusinessError with equivalent errorCode from ErrorBase1722.
            raise EpsBusinessError(EpsErrorBase.ITEM_NOT_FOUND)

        for lineItem in passedLineItems:
            _stored_lineItem = self._returnMatchingLineItem(storedLineItems, lineItem)
            if not _stored_lineItem:
                continue

            previousStatus = _stored_lineItem[self.FIELD_STATUS]
            newStatus = lineItem[self.FIELD_STATUS]
            if [previousStatus, newStatus] not in validStatusChanges:
                self.logObject.writeLog(
                    "EPS0148",
                    None,
                    {
                        "internalID": self.internalID,
                        "lineItemID": lineItem[self.FIELD_ID],
                        "previousStatus": previousStatus,
                        "newStatus": newStatus,
                    },
                )
                # Re-raise this as SpineBusinessError with equivalent errorCode from ErrorBase1722.
                raise EpsBusinessError(EpsErrorBase.INVALID_LINE_STATE_TRANSITION)

            if treatmentType == self.TREATMENT_TYPE_ACUTE:
                continue

            if lineItem[self.FIELD_MAX_REPEATS] != _stored_lineItem[self.FIELD_MAX_REPEATS]:
                if treatmentType == self.TREATMENT_TYPE_REPEAT_PRESCRIBE:
                    self.logObject.writeLog(
                        "EPS0147b",
                        None,
                        {
                            "internalID": self.internalID,
                            "providedRepeatCount": (lineItem[self.FIELD_MAX_REPEATS]),
                            "storedRepeatCount": str(_stored_lineItem[self.FIELD_MAX_REPEATS]),
                            "lineItemID": lineItem[self.FIELD_ID],
                        },
                    )
                    continue

                # SPII-14044 - permit the maxRepeats for line items to be equal to the
                # prescription maxRepeats as is normal when the line item expires sooner
                # than the prescription.
                if lineItem.get(self.FIELD_MAX_REPEATS) is None or self.maxRepeats is None:
                    self.logObject.writeLog(
                        "EPS0147d",
                        None,
                        {
                            "internalID": self.internalID,
                            "providedRepeatCount": lineItem.get(self.FIELD_MAX_REPEATS),
                            "storedRepeatCount": (
                                self.maxRepeats if self.maxRepeats is None else str(self.maxRepeats)
                            ),
                            "lineItemID": lineItem.get(self.FIELD_ID),
                        },
                    )
                    # Re-raise this as SpineBusinessError with equivalent errorCode from ErrorBase1722.
                    raise EpsBusinessError(EpsErrorBase.MAX_REPEAT_MISMATCH)

                if int(lineItem[self.FIELD_MAX_REPEATS]) == int(self.maxRepeats):
                    self.logObject.writeLog(
                        "EPS0147c",
                        None,
                        {
                            "internalID": self.internalID,
                            "providedRepeatCount": (lineItem[self.FIELD_MAX_REPEATS]),
                            "storedRepeatCount": str(_stored_lineItem[self.FIELD_MAX_REPEATS]),
                            "lineItemID": lineItem[self.FIELD_ID],
                        },
                    )
                    continue

                self.logObject.writeLog(
                    "EPS0147",
                    None,
                    {
                        "internalID": self.internalID,
                        "providedRepeatCount": (lineItem[self.FIELD_MAX_REPEATS]),
                        "storedRepeatCount": str(_stored_lineItem[self.FIELD_MAX_REPEATS]),
                        "lineItemID": lineItem[self.FIELD_ID],
                    },
                )
                # Re-raise this as SpineBusinessError with equivalent errorCode from ErrorBase1722.
                raise EpsBusinessError(EpsErrorBase.MAX_REPEAT_MISMATCH)

    def _returnMatchingLineItem(self, storedLineItems, lineItem):
        """
        Match on line item ID
        """
        for _stored_lineItem in storedLineItems:
            if _stored_lineItem[self.FIELD_ID] == lineItem[self.FIELD_ID]:
                return _stored_lineItem
        return None

    def returnDetailsForRelease(self):
        """
        Need to return the status and expiryDate of the current instance - which can then
        be used in validity checks for release request messages
        """
        currentIssue = self.currentIssue
        details = [
            currentIssue.status,
            currentIssue.expiry_date_str,
            self.returnNominatedPerformer(),
        ]
        return details

    def returnDetailsForDispense(self):
        """
        For dispense messages the following details are required:
        - Instance status
        - NHS Number
        - Dispensing Organisation
        - Max repeats (if repeat type, otherwise return None)
        """
        currentIssue = self.currentIssue
        maxRepeats = str(self.prescriptionRecord[self.FIELD_PRESCRIPTION][self.FIELD_MAX_REPEATS])
        details = [
            str(currentIssue.number),
            currentIssue.status,
            self._nhsNumber,
            currentIssue.dispensing_organization,
            maxRepeats,
        ]
        return details

    def returnLastDispenseStatus(self, instanceNumber):
        """
        Return the lastDispenseStatus for the requested instance
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        lastDispenseStatus = instance[self.FIELD_LAST_DISPENSE_STATUS]
        return lastDispenseStatus

    def returnLastDispenseDate(self, instanceNumber):
        """
        Return the lastDispenseDate for the requested instance
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        lastDispenseDate = instance[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_DATE]
        return lastDispenseDate

    def returnDetailsForClaim(self, instanceNumberStr):
        """
        For claim messages the following details are required:
        - Instance status
        - NHS Number
        - Dispensing Organisation
        - Max repeats (if repeat type, otherwise return None)
        """
        issueNumber = int(instanceNumberStr)
        issue = self.get_issue(issueNumber)
        maxRepeats = str(self.prescriptionRecord[self.FIELD_PRESCRIPTION][self.FIELD_MAX_REPEATS])
        details = [
            issue.claim,
            issue.status,
            self._nhsNumber,
            issue.dispensingOrganization,
            maxRepeats,
        ]
        return details

    def returnLastDispMsgRef(self, instanceNumberStr):
        """
        returns the last dispense Msg Ref for the issue
        """
        issueNumber = int(instanceNumberStr)
        issue = self.get_issue(issueNumber)
        return issue.lastDispenseNotificationMsgRef

    def returnDetailsForDispenseProposalReturn(self):
        """
        For DPR changes currentInstance, instanceStatus and dispensingOrg required
        """
        dispensingOrg = self._currentInstanceData[self.FIELD_DISPENSE][
            self.FIELD_DISPENSING_ORGANIZATION
        ]
        return (self.currentIssueNumber, self._currentInstanceStatus, dispensingOrg)

    def updateForRelease(self, context):
        """
        Update a prescription to indicate valid release request:
        prescription instance to be changed to with-dispenser
        add dispense section onto the instance - with dispensingOrganization
        update status of individual line items
        """
        self.updateInstanceStatus(self._currentInstanceData, PrescriptionStatus.WITH_DISPENSER)
        self._currentInstanceData[self.FIELD_DISPENSE][
            self.FIELD_DISPENSING_ORGANIZATION
        ] = context.agentOrganization
        _releaseDate = context.handleTime.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        self._currentInstanceData[self.FIELD_RELEASE_DATE] = _releaseDate

        self.updateLineItemStatus(
            self._currentInstanceData, LineItemStatus.TO_BE_DISPENSED, LineItemStatus.WITH_DISPENSER
        )
        self.setExemptionDates()

    def updateForDispense(
        self, context, daysSupply, nomDownLeadDays, nomDownloadDateEnabled, maintainInstance=False
    ):
        """
        Update a prescription to indicate valid dispense notification:
        prescription instance to be changed to reflect passed-in status
        update status of individual line items to reflect passed-in status

        """
        if context.isAmendment:  # noqa: SIM108 - More readable as is
            _instance = self._get_prescription_instance_data(context.targetInstance)
        else:
            _instance = self._currentInstanceData

        _instance[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_DATE] = context.dispenseDate
        _instance[self.FIELD_LAST_DISPENSE_STATUS] = context.prescriptionStatus

        if hasattr(context, "agentOrganization"):
            if context.agentOrganization:
                _instance[self.FIELD_DISPENSE][
                    self.FIELD_DISPENSING_ORGANIZATION
                ] = context.agentOrganization

        if context.prescriptionStatus in PrescriptionStatus.COMPLETED_STATES:
            _instance[self.FIELD_COMPLETION_DATE] = context.dispenseDate
            self.setNextInstancePriorIssueDate(context)
            self.releaseNextInstance(context, daysSupply, nomDownLeadDays, nomDownloadDateEnabled)
        self.updateLineItemStatusFromDispense(_instance, context.lineItems)

        if maintainInstance:
            return

        self.updateInstanceStatus(_instance, context.prescriptionStatus)

    def updateForRebuild(
        self, context, daysSupply, nomDownLeadDays, dispenseDict, nomDownloadDateEnabled
    ):
        """
        Complete the actions required to update the prescription instance with the changes
        made in the interaction worker
        """

        _instance = self._get_prescription_instance_data(context.targetInstance)
        _instance[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_DATE] = dispenseDict[
            self.FIELD_DISPENSE_DATE
        ]
        _instance[self.FIELD_LAST_DISPENSE_STATUS] = dispenseDict[self.FIELD_PRESCRIPTION_STATUS]
        if dispenseDict[self.FIELD_PRESCRIPTION_STATUS] in PrescriptionStatus.COMPLETED_STATES:
            _instance[self.FIELD_COMPLETION_DATE] = dispenseDict[self.FIELD_DISPENSE_DATE]
            self.setNextInstancePriorIssueDate(context, context.targetInstance)
            self.releaseNextInstance(
                context, daysSupply, nomDownLeadDays, nomDownloadDateEnabled, context.targetInstance
            )
        self.updateLineItemStatusFromDispense(_instance, dispenseDict[self.FIELD_LINE_ITEMS])
        self.updateInstanceStatus(_instance, dispenseDict[self.FIELD_PRESCRIPTION_STATUS])

    def updateForClaim(self, context, instanceNumber):
        """
        Update a prescription to indicate valid dispense claim received:
        prescription instance to be changed to reflect passed-in status
        Do not update status of individual line items
        Add Claim details to record
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        self.updateInstanceStatus(instance, PrescriptionStatus.CLAIMED)
        instance[self.FIELD_CLAIM][self.FIELD_CLAIM_RECEIVED_DATE] = context.claimDate
        instance[self.FIELD_CLAIM][self.FIELD_CLAIM_STATUS] = self.FIELD_CLAIMED_DISPLAY_NAME
        instance[self.FIELD_CLAIM][self.FIELD_CLAIM_REBUILD] = False
        instance[self.FIELD_CLAIM][self.FIELD_CLAIM_GUID] = context.dispenseClaimID

    def updateForClaimAmend(self, context, instanceNumber):
        """
        Modification of updateForClaim for use when the claim is an amendment.
        - Do not change the claimReceivedDate from the original value
        - Change claimRebuild to True
        Update a prescription to indicate valid dispense claim received:
        prescription instance to be changed to reflect passed-in status
        Do not update status of individual line items
        Append the existing claimGUID into the historicClaimGUID List
        Add Claim details to record
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        self.updateInstanceStatus(instance, PrescriptionStatus.CLAIMED)
        instance[self.FIELD_CLAIM][self.FIELD_CLAIM_RECEIVED_DATE] = context.claimDate
        instance[self.FIELD_CLAIM][self.FIELD_CLAIM_STATUS] = self.FIELD_CLAIMED_DISPLAY_NAME
        instance[self.FIELD_CLAIM][self.FIELD_CLAIM_REBUILD] = True
        if self.FIELD_HISTORIC_CLAIMS not in instance[self.FIELD_CLAIM]:
            instance[self.FIELD_CLAIM][self.FIELD_HISTORIC_CLAIM_GUIDS] = []
        _claimGUID = instance[self.FIELD_CLAIM][self.FIELD_CLAIM_GUID]
        instance[self.FIELD_CLAIM][self.FIELD_HISTORIC_CLAIM_GUIDS].append(_claimGUID)
        instance[self.FIELD_CLAIM][self.FIELD_CLAIM_GUID] = context.dispenseClaimID

    def updateForReturn(self, _, _retainNomination=False):
        """
        If this is a nominated prescription then check that the nominated performer is in
        the nomination history and clear the current value.

        The status then needs to be changed for the prescription and the line items
        """

        self.clearDispensingOrganisation(self._currentInstanceData)

        self.updateInstanceStatus(self._currentInstanceData, PrescriptionStatus.TO_BE_DISPENSED)
        self.updateLineItemStatus(
            self._currentInstanceData, LineItemStatus.WITH_DISPENSER, LineItemStatus.TO_BE_DISPENSED
        )
        if _retainNomination:
            return

        _nomDetails = self.prescriptionRecord[self.FIELD_NOMINATION]
        if _nomDetails[self.FIELD_NOMINATED]:
            if (
                _nomDetails[self.FIELD_NOMINATED_PERFORMER]
                not in _nomDetails[self.FIELD_NOMINATION_HISTORY]
            ):
                _nomDetails[self.FIELD_NOMINATION_HISTORY].append(
                    _nomDetails[self.FIELD_NOMINATED_PERFORMER]
                )
            _nomDetails[self.FIELD_NOMINATED_PERFORMER] = None

    def clearDispensingOrganisation(self, _instance):
        """
        Clear the dispensing organisation from the instance
        """
        _instance[self.FIELD_DISPENSE][self.FIELD_DISPENSING_ORGANIZATION] = None

    def checkActionApplicability(self, targetInstance, action, context):
        """
        The batch worker will always use 'Available' as the target reference, if this isn't
        the target instance then the update has come from a test or admin system that needs
        to take action on a specific instance, so skip the applicability test.
        """

        if targetInstance != self.BATCH_STATUS_AVAILABLE:
            self.setInstanceToActionUpdate(targetInstance, context, action)
        else:
            self.findInstancesToActionUpdate(context, action)

    def setInstanceToActionUpdate(self, targetInstance, context, action):
        """
        Set the instance to action update based on the value passed in the request
        """
        context.instancesToUpdate = str(targetInstance)
        self.logObject.writeLog(
            "EPS0407b",
            None,
            {
                "internalID": self.internalID,
                "passedAction": str(action),
                "instancesToUpdate": str(targetInstance),
            },
        )

    def findInstancesToActionUpdate(self, context, action):
        """
        Check all available instances for any that match the activity and have passed the
        next activity date. This date check is important, as all instances of a prescription
        will have 'expire' as the NAD status to start with.
        """
        issuesToUpdate = []
        rejectedList = []

        activityToLookFor = self.ACTIVITY_LOOKUP[action]
        handleDate = context.handleTime.strftime(TimeFormats.STANDARD_DATE_FORMAT)

        for issue in self.issues:
            # Special case to reset the NextActivityDate for prescriptions that were migrated without a NAD
            if (issue.status == PrescriptionStatus.AWAITING_RELEASE_READY) and (
                action == self.ADMIN_ACTION_RESET_NAD
            ):
                issuesToUpdate.append(issue)
            # Special case to allow the reset of the current instance
            if action == self.SPECIAL_RESET_CURRENT_INSTANCE:
                issuesToUpdate.append(issue)
                # break the loop once at least one issue has been identified.
                if issuesToUpdate:
                    break
            # Special case to return the dispense notification to Spine in the case that it is 'hung'
            if action == self.SPECIAL_DISPENSE_RESET:
                self._confirmDispenseResetOnIssue(issuesToUpdate, issue)
            # Special case to apply cancellations to those that weren't set post migration - issue 110898
            if action == self.SPECIAL_APPLY_PENDING_CANCELLATIONS:
                self._confirmCancellationsToApply(issuesToUpdate, issue)
                # break the loop once the first issue has been identified.
                if issuesToUpdate:
                    break
            # NOTE: SPII-10495 some migrated prescriptions don't have the 'activity' field
            # populated, so guard against this to avoid killing process.
            if issue.next_activity is not None:
                # Note: string comparison of dates in YYYYMMDD format
                actionIsDue = issue.next_activity_date_str <= handleDate

                if (activityToLookFor == issue.next_activity) and actionIsDue:
                    issuesToUpdate.append(issue)
                else:
                    rejectionRef = str(issue.number)
                    rejectionRef += "|" + issue.next_activity
                    rejectionRef += "|" + issue.next_activity_date_str
                    rejectedList.append(rejectionRef)

        if issuesToUpdate:
            # Note: calling code currently expects issue numbers as strings
            context.instancesToUpdate = [str(issue.number) for issue in issuesToUpdate]
            self.logObject.writeLog(
                "EPS0407",
                None,
                {
                    "internalID": self.internalID,
                    "passedAction": str(action),
                    "instancesToUpdate": context.instancesToUpdate,
                },
            )
        else:
            self.logObject.writeLog(
                "EPS0405",
                None,
                {
                    "internalID": self.internalID,
                    "handleDate": handleDate,
                    "passedAction": activityToLookFor,
                    "recordAction": str(rejectedList),
                },
            )

    def _confirmCancellationsToApply(self, issuesToUpdate, issue):
        """
        Only apply pending cancellations to those issuse that are safe to cancel. It is
        fine to reapply cancellations that have already been successful, and cancellation
        takes precedence over expiry so no need to check the detailed status, only that
        the prescription is in a cancellable state.
        The cancellation worker will apply the cancellation to the first available issue and
        all subsequent issues (due to constraints with active prescriptions, issue n+x must
        be cancellable if issue n is cancellable). So only need to identify the first issue
        """
        if issue.status in PrescriptionStatus.CANCELLABLE_STATES:
            issuesToUpdate.append(issue)

    def _confirmDispenseResetOnIssue(self, issuesToUpdate, issue):
        """
        This code is to handle an exception that happened at go-live whereby some
        prescriptions could not be read and need to be reset in bulk. The conditions for
        reset are:
        1) The issue state is still 0002 - With Dispenser, i.e. it has not progressed to
        with-dispenser active, dispensed or been returned, cancelled or expired.
        2) The prescription issue was downloaded on the 24th, 25th, 26th or 27th August 2014,
        (this is the time that the issue was resolved in Live.)
        The second check is required to protect against the scenario where the one issue
        was downloaded within the target window, but this was successfully processed and
        subsequently dispensed, releasing a new issue which may be status 0002, but will
        not have a release date within the target window.
        """
        # declared here as this whole method should be removed post clean-up
        _specialDispenseResetDates = [
            "20140824",
            "20140825",
            "20140826",
            "20140827",
            "20140828",
            "20140829",
            "20140830",
            "20140831",
            "20140901",
            "20140902",
            "20140903",
            "20140904",
            "20140905",
            "20140906",
            "20140907",
            "20140908",
        ]

        if issue.status != PrescriptionStatus.WITH_DISPENSER:
            return

        _releaseDate = issue.release_date
        if _releaseDate and str(_releaseDate) in _specialDispenseResetDates:
            issuesToUpdate.append(issue)

    def updateByAction(self, context, nomDownloadDateEnabled=True):
        """
        Update the record by performing the necessary logic to carry out the specified
        action.

        These actions are responsible for maintaining consistent record state, so the
        calling code does not need to do this.

        Deletion is applied to the whole record (all issues), but other actions will
        apply to all issues in instancesToUpdate. Note that expiring an issue will
        expire all future issues as well.
        """
        action = context.action

        # prescription-wide actions
        if action == self.NEXTACTIVITY_DELETE:
            self._updateDelete(context)
        else:
            # instance-specific actions
            if context.instancesToUpdate:
                for issueNumber in context.instancesToUpdate:
                    # make sure this is really an int, and not a str
                    issueNumberInt = int(issueNumber)
                    self.performInstanceSpecificUpdates(
                        issueNumberInt, context, nomDownloadDateEnabled
                    )

    def performInstanceSpecificUpdates(self, targetIssueNumber, context, nomDownloadDateEnabled):
        """
        Perform the actions that would be specific to an instance and could apply to more
        than one instance.
        Return after nominated download as only Expire and Create No Claim should add a
        completion date and release the next instance
        Release next instance and roll forward instance are both safe to re-apply as they
        check first for the correct instance state (awaiting release ready).

        :type targetIssueNumber: int
        :type context: ???
        """
        issue = self.get_issue(targetIssueNumber)

        # dispatch based on action

        if context.action == self.ACTIVITY_NOMINATED_DOWNLOAD:
            # make an issue available for download
            self._updateMakeAvailableForNominatedDownload(issue)

        elif context.action == self.SPECIAL_RESET_CURRENT_INSTANCE:
            _oldCurrentIssueNumber, _newCurrentIssueNumber = self.resetCurrentInstance()
            if _oldCurrentIssueNumber != _newCurrentIssueNumber:
                self.logObject.writeLog(
                    "EPS0401c",
                    None,
                    {
                        "internalID": self.internalID,
                        "oldCurrentIssue": _oldCurrentIssueNumber,
                        "newCurrentIssue": _newCurrentIssueNumber,
                        "prescriptionID": context.prescriptionID,
                    },
                )
                self.currentIssueNumber = _newCurrentIssueNumber
            else:
                context.updatesToApply = False

        elif context.action == self.SPECIAL_DISPENSE_RESET:
            # Special case to reset the dispense status. This needs to perform a dispense
            # proposal return and then re-set the nominated performer
            self.updateForReturn(None, True)

        elif context.action == self.SPECIAL_APPLY_PENDING_CANCELLATIONS:
            # No action to be taken at this level, just pass.
            pass

        elif context.action == self.NEXTACTIVITY_EXPIRE:
            # NOTE (SPII-10316): when requested to expire an issue, we must expire all
            # subsequent issues as well, and set the current issue indicator to point at
            # the last issue
            issuesToExpire = self.get_issues_in_range(issue.number, None)
            for issueToExpire in issuesToExpire:
                issueToExpire.expire(context.handleTime, self)

            self.currentIssueNumber = self.maxRepeats

        elif context.action == self.NEXTACTIVITY_CREATENOCLAIM:
            self._createNoClaim(issue, context.handleTime)
            issue.mark_completed(context.handleTime, self)
            self._moveToNextIssueIfPossible(issue.number, context, nomDownloadDateEnabled)

        elif context.action == self.ADMIN_ACTION_RESET_NAD:
            # Log that the prescription has been touched, but no change should be made
            self.logObject.writeLog(
                "EPS0401b",
                None,
                {"internalID": self.internalID, "prescriptionID": context.prescriptionID},
            )
        else:
            # invalid action
            self.logObject.writeLog(
                "EPS0401",
                None,
                {
                    "internalID": self.internalID,
                    "action": str(context.action),
                },
            )

    def _moveToNextIssueIfPossible(self, issueNumber, context, nomDownloadDateEnabled):
        """
        Release the next issue, if possible, and mark it as the current issue

        :type issueNumber: int
        :type context : ???
        """
        # if this isn't the last issue...
        if issueNumber < self.maxRepeats:
            # Note: we know this is a Repeat Dispensing prescription, as it has multiple
            # issues
            context.prescriptionRepeatLow = context.targetInstance
            self.releaseNextInstance(
                context,
                self.getDaysSupply(),
                self.NOMINATED_DOWNLOAD_LEAD_DAYS,
                nomDownloadDateEnabled,
                str(issueNumber),
            )
            self.rollForwardInstance()

    def getDaysSupply(self):
        """
        Return the days supply from the prescription record, this will have been set to the
        value passed in the original prescription, or the default 28 days
        """
        _daysSupply = self.prescriptionRecord[self.FIELD_PRESCRIPTION][self.FIELD_DAYS_SUPPLY]
        # Habdle records that were migrated with null daysSupply rather than 0.
        if not _daysSupply:
            return 0
        if isinstance(_daysSupply, int):
            return _daysSupply
        # Habdle records that were migrated with blank space in the daysSupply rather than 0.
        if not _daysSupply.strip():
            return 0
        return int(_daysSupply)

    def _createNoClaim(self, issue, _handleTime):
        """
        Update the prescription status to No Claimed.

        :type issue: PrescriptionIssue
        :type _handleTime: datetime.datetime
        """
        issue.updateStatus(PrescriptionStatus.NO_CLAIMED, self)

        _handleTimeStr = _handleTime.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        issue.claim.received_date_str = _handleTimeStr
        self.logAttributeChange(self.FIELD_CLAIM_RECEIVED_DATE, "", _handleTimeStr, None)

        self.logObject.writeLog("EPS0406", None, {"internalID": self.internalID})

    def _updateMakeAvailableForNominatedDownload(self, issue):
        """
        Update the prescription state to make it available for nominated download

        :type issue: PrescriptionIssue
        """
        issue.updateStatus(PrescriptionStatus.TO_BE_DISPENSED, self)

        self.logObject.writeLog("EPS0402", None, {"internalID": self.internalID})

    def _verifyRecordDeletion(self):
        """
        Confirm that it is ok to delete the record by checking through the next activities
        of each of the prescription issues, if not then log and return false
        """
        for _issueKey in self.prescriptionRecord[self.FIELD_INSTANCES]:
            _issue = self._get_prescription_instance_data(_issueKey)
            _nextActivityforIssue = _issue.get(self.FIELD_NEXT_ACTIVITY, {}).get(
                self.FIELD_ACTIVITY
            )
            if _nextActivityforIssue == self.NEXTACTIVITY_DELETE:
                continue

            self.logObject.writeLog(
                "EPS0404b",
                None,
                {
                    "internalID": self.internalID,
                    "prescriptionID": self.id,
                    "nextActivity": _nextActivityforIssue,
                    "issue": _issueKey,
                },
            )
            return False
        return True

    def _updateDelete(self, context):
        """
        Update the entire prescription to delete it
        """
        if not self._verifyRecordDeletion():
            return

        _docList = []
        if self.prescriptionRecord.get(self.FIELDS_DOCUMENTS) is not None:
            for _document in self.prescriptionRecord[self.FIELDS_DOCUMENTS]:
                _docList.append(_document)
        if _docList:
            context.documentsToDelete = _docList

        context.recordToDelete = context.prescriptionID[:-1]

        context.updatesToApply = False

        self.logObject.writeLog(
            "EPS0404",
            None,
            {
                "internalID": self.internalID,
                "recordRef": context.recordToDelete,
                "documentRefs": context.documentsToDelete,
            },
        )

    def updateByAdmin(self, context):
        """
        Set values from admin message straight into record
        Log each change
        Changes are not validated - the whole record will be validated once the full lot
        of amendments have been made

        If record is a prescription that has not yet been acted upon, there will be no
        previous status

        Perform the prescription level changes
        Determine the instance or range of instances to be updated
        Reset the context.currentInstance as this is used later in the validation
        Run the instance update(s)
        """
        currentInstance = context.currentInstance

        if context.handleOverdueExpiry:
            self.handleOverdueExpiry(context)
        # nominatedPerformer will be None in the removal scenario so check for nominatedPerformerType too
        if context.nominatedPerformerType or context.nominatedPerformer:
            self.updateNominatedPerformer(context)

        [_range, _startInstance, _endInstance] = self.instancesToUpdate(currentInstance)
        context.currentInstance = self.returnCurrentInstance()

        # find out which issues need updating
        lowest = int(_startInstance)
        highest = int(_endInstance) if _range else lowest
        issue_numbers_to_update = self.get_issue_numbers_in_range(lowest, highest)

        # update the issues
        for issueNumber in issue_numbers_to_update:
            self._makeAdminInstanceUpdates(context, issueNumber)

        return [True, None, None]

    def isExpiryOverdue(self):
        """
        Check the expected Expiry date on the record, if in the past return True
        """
        nad = self.return_next_activity_nad_bin()
        return self._isExpiryOverdue(nad)

    def isNextActivityPurge(self):
        """
        Check if records next activity is purge
        """
        nextActivity = self.return_next_activity_nad_bin()
        if nextActivity:
            if nextActivity[0].startswith(self.NEXTACTIVITY_PURGE):
                return True
        return False

    @staticmethod
    def _isExpiryOverdue(nad):
        """
        return True if Expiry is overdue or index isn't set
        """
        if not nad:
            return False
        if nad[0] is None:  # badly behaved prescriptions from pre-golive
            return False
        if not nad[0][:6] == PrescriptionRecord.NEXTACTIVITY_EXPIRE:
            return False
        if nad[0][7:15] >= datetime.datetime.now().strftime(TimeFormats.STANDARD_DATE_FORMAT):
            return False
        return True

    def handleOverdueExpiry(self, context):
        """
        Check the expected Expiry date on the record, if in the past, expire the line
        and prescription.
        """
        nad = context.epsRecord.return_next_activity_nad_bin()
        if not self._isExpiryOverdue(nad):
            return

        self.logObject.writeLog("EPS0335", None, {"internalID": self.internalID})
        context.overdueExpiry = True

        # Only set the status to Expired if not already part of the admin update
        if (
            not context.prescriptionStatus
            or context.prescriptionStatus not in PrescriptionStatus.EXPIRY_IMMUTABLE_STATES
        ):
            context.prescriptionStatus = PrescriptionStatus.EXPIRED

        # Set the completion date if not already part of the admin update
        if not context.completionDate:
            context.completionDate = datetime.datetime.now().strftime(
                TimeFormats.STANDARD_DATE_FORMAT
            )

        # Create a LineDict if one does not already exist and ensure that all LineItems are included
        if not context.lineDict:
            context.lineDict = {}
        for _lineItem in context.epsRecord.currentIssue.line_items:
            if _lineItem.id in context.lineDict:
                continue
            context.lineDict[_lineItem.id] = LineItemStatus.EXPIRED

    def instancesToUpdate(self, targetInstance):
        """
        Check the targetInstance value passed in the admin update request and set a
        range or single instance target accordingly.

        The targetInstance will be provided as either a integer or 'All', 'Available'
        or 'Current', where the behaviour is:
        All = all instances, including any past (complete) instances
        Available = current through to final instance, not including any past instances
        Current = the recorded current instance only, not a range

        Otherwise, the targetInstance passed is an integer identifying the target
        instance.
        """
        recordedCurrentInstance = self.returnCurrentInstance()
        recordedMaxInstance = str(self.maxRepeats)

        _instanceRange = False
        _endInstance = None

        if targetInstance == self.BATCH_STATUS_ALL:
            _instanceRange = True
            _startInstance = "1"
            _endInstance = recordedMaxInstance
        elif targetInstance == self.BATCH_STATUS_AVAILABLE:
            _instanceRange = True
            _startInstance = recordedCurrentInstance
            _endInstance = recordedMaxInstance
        elif targetInstance == self.BATCH_STATUS_CURRENT:
            _startInstance = recordedCurrentInstance
        else:
            _startInstance = targetInstance

        if _instanceRange:
            self.logObject.writeLog(
                "EPS0297a",
                None,
                dict(
                    {
                        "internalID": self.internalID,
                        "startInstance": _startInstance,
                        "endInstance": _endInstance,
                    }
                ),
            )
        else:
            self.logObject.writeLog(
                "EPS0297b",
                None,
                dict({"internalID": self.internalID, "startInstance": _startInstance}),
            )

        return [_instanceRange, _startInstance, _endInstance]

    def makeWithdrawalUpdates(self, context):
        """
        Apply instance specific updates into record
        """

        _targetInstance = context.targetInstance
        _prescription = self.prescriptionRecord
        _instance = _prescription[self.FIELD_INSTANCES][_targetInstance]
        _instance[self.FIELD_DISPENSE] = context.dispenseElement
        _instance[self.FIELD_LINE_ITEMS] = context.lineItems
        _instance[self.FIELD_PREVIOUS_STATUS] = _instance[self.FIELD_PRESCRIPTION_STATUS]
        _instance[self.FIELD_PRESCRIPTION_STATUS] = context.prescriptionStatus
        _instance[self.FIELD_LAST_DISPENSE_STATUS] = context.lastDispenseStatus
        _instance[self.FIELD_COMPLETION_DATE] = context.completionDate

    def _makeAdminInstanceUpdates(self, context, instanceNumber):
        """
        Apply instance specific updates into record
        """

        currentInstance = str(instanceNumber)
        context.updateInstance = instanceNumber
        _prescription = self.prescriptionRecord
        _instance = _prescription[self.FIELD_INSTANCES][currentInstance]
        _dispense = _instance[self.FIELD_DISPENSE]
        _claim = _instance[self.FIELD_CLAIM]

        if context.prescriptionStatus:
            self.logAttributeChange(
                self.FIELD_PRESCRIPTION_STATUS,
                _instance[self.FIELD_PRESCRIPTION_STATUS],
                context.prescriptionStatus,
                context.fieldsToUpdate,
            )
            _instance[self.FIELD_PREVIOUS_STATUS] = _instance[self.FIELD_PRESCRIPTION_STATUS]
            _instance[self.FIELD_PRESCRIPTION_STATUS] = context.prescriptionStatus

        if context.completionDate:
            self.logAttributeChange(
                self.FIELD_COMPLETION_DATE,
                _instance[self.FIELD_COMPLETION_DATE],
                context.completionDate,
                context.fieldsToUpdate,
            )
            _instance[self.FIELD_COMPLETION_DATE] = context.completionDate

        if context.dispenseWindowLowDate:
            self.logAttributeChange(
                self.FIELD_DISPENSE_WINDOW_LOW_DATE,
                _instance[self.FIELD_DISPENSE_WINDOW_LOW_DATE],
                context.dispenseWindowLowDate,
                context.fieldsToUpdate,
            )
            _instance[self.FIELD_DISPENSE_WINDOW_LOW_DATE] = context.dispenseWindowLowDate

        if context.nominatedDownloadDate:
            self.logAttributeChange(
                self.FIELD_NOMINATED_DOWNLOAD_DATE,
                _instance[self.FIELD_NOMINATED_DOWNLOAD_DATE],
                context.nominatedDownloadDate,
                context.fieldsToUpdate,
            )
            _instance[self.FIELD_NOMINATED_DOWNLOAD_DATE] = context.nominatedDownloadDate

        if context.releaseDate:
            self.logAttributeChange(
                self.FIELD_RELEASE_DATE,
                _instance[self.FIELD_RELEASE_DATE],
                context.releaseDate,
                context.fieldsToUpdate,
            )
            _instance[self.FIELD_RELEASE_DATE] = context.releaseDate

        if context.dispensingOrganization:
            self.logAttributeChange(
                self.FIELD_DISPENSING_ORGANIZATION,
                _dispense[self.FIELD_DISPENSING_ORGANIZATION],
                context.dispensingOrganization,
                context.fieldsToUpdate,
            )
            _dispense[self.FIELD_DISPENSING_ORGANIZATION] = context.dispensingOrganization

        # This is to reset the dispensing org
        if context.dispensingOrgNullFlavor:
            self.logAttributeChange(
                self.FIELD_DISPENSING_ORGANIZATION,
                _dispense[self.FIELD_DISPENSING_ORGANIZATION],
                "None",
                context.fieldsToUpdate,
            )
            _dispense[self.FIELD_DISPENSING_ORGANIZATION] = None

        if context.lastDispenseDate:
            self.logAttributeChange(
                self.FIELD_LAST_DISPENSE_DATE,
                _dispense[self.FIELD_LAST_DISPENSE_DATE],
                context.lastDispenseDate,
                context.fieldsToUpdate,
            )
            _dispense[self.FIELD_LAST_DISPENSE_DATE] = context.lastDispenseDate

        if context.claimSentDate:
            self.logAttributeChange(
                self.FIELD_CLAIM_SENT_DATE,
                _claim[self.FIELD_CLAIM_RECEIVED_DATE],
                context.claimSentDate,
                context.fieldsToUpdate,
            )
            _claim[self.FIELD_CLAIM_RECEIVED_DATE] = context.claimSentDate

        for lineItemID in context.lineDict:
            for currentLineItem in _instance[self.FIELD_LINE_ITEMS]:
                if currentLineItem[self.FIELD_ID] != lineItemID:
                    continue
                _currentLineStatus = currentLineItem[self.FIELD_STATUS]
                if context.overdueExpiry:
                    if _currentLineStatus in LineItemStatus.EXPIRY_IMMUTABLE_STATES:
                        continue
                    _changedLineStatus = LineItemStatus.EXPIRED
                else:
                    _changedLineStatus = context.lineDict[lineItemID]
                self.logObject.writeLog(
                    "EPS0072",
                    None,
                    {
                        "internalID": self.internalID,
                        "prescriptionID": context.prescriptionID,
                        "lineItemChanged": lineItemID,
                        "previousStatus": _currentLineStatus,
                        "newStatus": _changedLineStatus,
                    },
                )
                currentLineItem[self.FIELD_STATUS] = _changedLineStatus

    def logAttributeChange(self, itemChanged, previousValue, newValue, fieldsToUpdate):
        """
        Used by the update record function to change an existing attribute on the record
        Both old and new values as well as the field name are logged
        """
        if fieldsToUpdate is not None:
            fieldsToUpdate.append(itemChanged)

        self.logObject.writeLog(
            "EPS0071",
            None,
            {
                "internalID": self.internalID,
                "itemChanged": itemChanged,
                "previousValue": previousValue,
                "newValue": newValue,
            },
        )

    def _extractDispenseDateFromContext(self, context):
        """
        Get the Dispense date from context, or use handleTime if not available.

        :type context: ???
        :rtype: str
        """
        dispenseDate = context.handleTime.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        if hasattr(context, self.FIELD_DISPENSE_DATE):
            if context.dispenseDate is not None:
                dispenseDate = context.dispenseDate
        return dispenseDate

    def _extractDispenseDatetimeFromContext(self, context):
        """
        Get the Dispense datetime from context, or use handleTime if not available.

        :type context: ???
        :rtype: str
        """
        dispenseTime = context.handleTime.strftime(TimeFormats.STANDARD_DATE_TIME_FORMAT)
        if hasattr(context, self.FIELD_DISPENSE_TIME):
            if context.dispenseTime is not None:
                dispenseTime = context.dispenseTime
        return dispenseTime

    def _calculateNominatedDownloadDate(self, prescribeDate, daysSupply, leadDays, nextIssueNumber):
        """
        Calculate the date for nominated download, taking into account lead time and supply length.

        :type prescribeDate: str
        :type daysSupply: int
        :type leadDays: int
        :rtype: datetime.datetime
        :type nextIssueNumber: str
        """
        nominatedDownloadDate = datetime.datetime.strptime(
            prescribeDate, TimeFormats.STANDARD_DATE_FORMAT
        )
        duration = daysSupply * (int(nextIssueNumber) - 1)
        nominatedDownloadDate += relativedelta(days=+duration)
        nominatedDownloadDate += relativedelta(days=-leadDays)
        return nominatedDownloadDate

    def _calculateNominatedDownloadDateOld(self, dispenseDate, daysSupply, leadDays):
        """
        Calculate the date for nominated download, taking into account lead time and supply length.

        :type dispenseDate: str
        :type daysSupply: int
        :type leadDays: int
        :rtype: datetime.datetime
        """
        nominatedDownloadDate = datetime.datetime.strptime(
            dispenseDate, TimeFormats.STANDARD_DATE_FORMAT
        )
        nominatedDownloadDate += relativedelta(days=+daysSupply)
        nominatedDownloadDate += relativedelta(days=-leadDays)
        return nominatedDownloadDate

    def returnNextIssueNumber(self, _issueNumber=None):
        """
        Wrapper for _findNextFutureIssueNumber, allows an optional start issue to be passed in
        otherwise will use the current issue number
        """
        if not _issueNumber:
            _issueNumber = self.currentIssueNumber

        return self._findNextFutureIssueNumber(str(_issueNumber))

    def _findNextFutureIssueNumber(self, issue_number_str, skipCheckForCorrectStatus=False):
        """
        Find the next issue number after the specified one, if valid.

        :type issue_number_str: str or ???
        :rtype: str or None
        """
        if not issue_number_str:
            return None

        nextIssueNumber = int(issue_number_str) + 1

        # make sure the prescription actually has this issue
        if nextIssueNumber not in self.issue_numbers:
            return None

        if skipCheckForCorrectStatus:
            return str(nextIssueNumber)

        # examine the issue to make sure it's in the correct state
        nextIssue = self.get_issue(nextIssueNumber)
        if not nextIssue.status == PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE:
            return None

        # if we get this far, then we have a valid next issue, so return its number
        # Note: calling code is currently expecting a str, so convert,until we've had
        # a chance to refactor properly
        return str(nextIssueNumber)

    def setNextInstancePriorIssueDate(self, context, currentIssueNumberStr=None):
        """
        Set the prior issue date for the next instance, this is done as part of the
        dispense notification process, but may form part of a standard dispense, a
        dispense amendment or a rebuild dispense history.
        """
        if not currentIssueNumberStr:
            currentIssueNumberStr = context.prescriptionRepeatLow

        # find the number of the next issue, if there is a valid one. Don't check for
        # valid status of the next instance as this could be a rebuild or amendment
        # and the next issue may already be active.
        nextIssueNumberStr = self._findNextFutureIssueNumber(
            currentIssueNumberStr, skipCheckForCorrectStatus=True
        )
        if nextIssueNumberStr:
            instance = self._get_prescription_instance_data(nextIssueNumberStr)
            instance[self.FIELD_PREVIOUS_ISSUE_DATE] = self._extractDispenseDatetimeFromContext(
                context
            )

    def releaseNextInstance(
        self,
        context,
        daysSupply,
        nomDownLeadDays,
        nomDownloadDateEnabled,
        currentIssueNumberStr=None,
    ):
        """
        If not a repeat prescription (and no prescriptionRepeatLow provided),
        no future issue to release. Otherwise, use the prescriptionRepeatLow to
        determine the next issue - if it is there then change the status of that
        issue to awaiting-release-ready, and set the dispenseWindowLowDate

        Note that it is possible that this will be invoked as part of an amendment.
        """
        if not currentIssueNumberStr:
            currentIssueNumberStr = context.prescriptionRepeatLow

        # find the number of the next issue, if there is a valid one
        nextIssueNumberStr = self._findNextFutureIssueNumber(currentIssueNumberStr)
        if nextIssueNumberStr is None:
            # give up if there is no next issue
            self.pendingInstanceChange = None
            return

        # update the issue
        _dispenseDate = self._extractDispenseDateFromContext(context)
        _prescribeDate = context.epsRecord.returnPrescriptionTime()
        if nomDownloadDateEnabled:
            if _prescribeDate is None:
                self.logObject.writeLog(
                    "EPS0676",
                    None,
                    dict({"internalID": self.internalID, "prescriptionID": context.prescriptionID}),
                )
            nominatedDownloadDate = self._calculateNominatedDownloadDate(
                _prescribeDate[:8], daysSupply, nomDownLeadDays, nextIssueNumberStr
            )
            self.logObject.writeLog(
                "EPS0675",
                None,
                dict(
                    {
                        "internalID": self.internalID,
                        "prescriptionID": context.prescriptionID,
                        "nominatedDownloadDate": nominatedDownloadDate.strftime(
                            TimeFormats.STANDARD_DATE_FORMAT
                        ),
                        "prescribeDate": _prescribeDate,
                        "daysSupply": str(daysSupply),
                        "leadDays": str(nomDownLeadDays),
                        "issueNumber": nextIssueNumberStr,
                    }
                ),
            )
        else:
            nominatedDownloadDate = self._calculateNominatedDownloadDateOld(
                _dispenseDate, daysSupply, nomDownLeadDays
            )

        if nominatedDownloadDate >= datetime.datetime(
            context.handleTime.year, context.handleTime.month, context.handleTime.day
        ):
            _newPrescriptionStatus = PrescriptionStatus.AWAITING_RELEASE_READY
        else:
            _newPrescriptionStatus = PrescriptionStatus.TO_BE_DISPENSED

        instance = self._get_prescription_instance_data(nextIssueNumberStr)
        instance[self.FIELD_PREVIOUS_STATUS] = instance[self.FIELD_PRESCRIPTION_STATUS]
        instance[self.FIELD_PRESCRIPTION_STATUS] = _newPrescriptionStatus
        instance[self.FIELD_DISPENSE_WINDOW_LOW_DATE] = _dispenseDate
        instance[self.FIELD_NOMINATED_DOWNLOAD_DATE] = nominatedDownloadDate.strftime(
            TimeFormats.STANDARD_DATE_FORMAT
        )

        # mark so that we know to update the prescription's current issue number
        self.pendingInstanceChange = nextIssueNumberStr

    def addReleaseDocumentRef(self, relReqDocumentRef):
        """
        Add the reference to the release request document to the instance.
        """
        self._currentInstanceData[self.FIELD_RELEASE_REQUEST_MGS_REF] = relReqDocumentRef

    def addReleaseDispenserDetails(self, relDispenserDetails):
        """
        Add the dispenser details from the release request document to the instance.
        """
        self._currentInstanceData[self.FIELD_RELEASE_DISPENSER_DETAILS] = relDispenserDetails

    def addDispenseDocumentRef(self, dnDocumentRef, _targetInstance=None):
        """
        Add the reference to the dispense notification document to the instance.
        """
        _instance = (
            self._get_prescription_instance_data(_targetInstance)
            if _targetInstance
            else self._currentInstanceData
        )
        _instance[self.FIELD_DISPENSE][
            self.FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF
        ] = dnDocumentRef

    def checkStatusComplete(self, _prescriptionStatus):
        """
        Check if the passed prescription status is in a complete state and return the
        appropriate boolean
        """
        return _prescriptionStatus in PrescriptionStatus.COMPLETED_STATES

    def clearDispenseNotificationsFromHistory(self, _targetInstance):
        """
        Clear all but the release from the dispense history
        """

        _instance = self._get_prescription_instance_data(_targetInstance)
        _newDispenseHistory = {}
        if self.FIELD_RELEASE in _instance[self.FIELD_DISPENSE_HISTORY]:
            _releaseSnippet = copy(_instance[self.FIELD_DISPENSE_HISTORY][self.FIELD_RELEASE])
            _newDispenseHistory[self.FIELD_RELEASE] = _releaseSnippet
        _instance[self.FIELD_DISPENSE_HISTORY] = copy(_newDispenseHistory)

    def createDispenseHistoryEntry(self, dnDocumentGuid, _targetInstance=None):
        """
        Create a dispense history entry to be used in future if the dispense notification
        is withdrawn. Also need to include the current prescription status

        Use the copy function to take a copy of it as it is prior to the changes
        otherwise a link is created and the data will be added at the post-update state.

        Use the last dispense date from the record unless the last dispense time is passed
        in (used for release only).
        """
        _instance = (
            self._get_prescription_instance_data(_targetInstance)
            if _targetInstance
            else self._currentInstanceData
        )
        _instance[self.FIELD_DISPENSE_HISTORY][dnDocumentGuid] = {}
        _dispenseEntry = _instance[self.FIELD_DISPENSE_HISTORY][dnDocumentGuid]
        _dispenseEntry[self.FIELD_DISPENSE] = copy(_instance[self.FIELD_DISPENSE])
        _dispenseEntry[self.FIELD_PRESCRIPTION_STATUS] = copy(
            _instance[self.FIELD_PRESCRIPTION_STATUS]
        )
        _dispenseEntry[self.FIELD_LAST_DISPENSE_STATUS] = copy(
            _instance[self.FIELD_LAST_DISPENSE_STATUS]
        )
        _lineItems = []
        for lineItem in _instance[self.FIELD_LINE_ITEMS]:
            _lineItem = copy(lineItem)
            _lineItems.append(_lineItem)
        _dispenseEntry[self.FIELD_LINE_ITEMS] = copy(_lineItems)
        _dispenseEntry[self.FIELD_COMPLETION_DATE] = copy(_instance[self.FIELD_COMPLETION_DATE])

        _instanceLastDispense = copy(_instance[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_DATE])
        if not _instanceLastDispense:
            _releaseDate = copy(_instance[self.FIELD_RELEASE_DATE])
            _dispenseEntry[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_DATE] = _releaseDate
        else:
            _dispenseEntry[self.FIELD_DISPENSE][
                self.FIELD_LAST_DISPENSE_DATE
            ] = _instanceLastDispense

    def createReleaseHistoryEntry(self, releaseTime, _dispensingOrg):
        """
        Create a dispense history entry specific to the release action

        Use the copy function to take a copy of it as it is prior to the changes
        otherwise a link is created and the data will be added at the post-update state.

        Set the line item status to 0008 as any withdrawal can only return the
        prescription back to 'with dispenser' state.

        Use the release date as the last dispense date to support next activity
        calculation if the dispense history is withdrawn.
        """

        _instance = self._currentInstanceData

        _instance[self.FIELD_DISPENSE_HISTORY][self.FIELD_RELEASE] = {}
        _dispenseEntry = _instance[self.FIELD_DISPENSE_HISTORY][self.FIELD_RELEASE]
        _dispenseEntry[self.FIELD_DISPENSE] = copy(_instance[self.FIELD_DISPENSE])
        _dispenseEntry[self.FIELD_PRESCRIPTION_STATUS] = copy(
            _instance[self.FIELD_PRESCRIPTION_STATUS]
        )
        _dispenseEntry[self.FIELD_LAST_DISPENSE_STATUS] = copy(
            _instance[self.FIELD_LAST_DISPENSE_STATUS]
        )
        _lineItems = []
        for lineItem in _instance[self.FIELD_LINE_ITEMS]:
            _lineItem = copy(lineItem)
            if (
                _lineItem[self.FIELD_STATUS] != LineItemStatus.CANCELLED
                and _lineItem[self.FIELD_STATUS] != LineItemStatus.EXPIRED
            ):
                _lineItem[self.FIELD_STATUS] = LineItemStatus.WITH_DISPENSER
            _lineItems.append(_lineItem)
        _dispenseEntry[self.FIELD_LINE_ITEMS] = _lineItems
        _dispenseEntry[self.FIELD_COMPLETION_DATE] = copy(_instance[self.FIELD_COMPLETION_DATE])
        _releaseTimeStr = releaseTime.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        _dispenseEntry[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_DATE] = _releaseTimeStr
        _dispenseEntry[self.FIELD_DISPENSE][self.FIELD_DISPENSING_ORGANIZATION] = _dispensingOrg

    def addDispenseDocumentGuid(self, dnDocumentGuid, _targetInstance=None):
        """
        Add the reference to the dispense notification document to the instance.
        """
        _instance = (
            self._get_prescription_instance_data(_targetInstance)
            if _targetInstance
            else self._currentInstanceData
        )
        _instance[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_NOTIFICATION_GUID] = dnDocumentGuid

    def addClaimDocumentRef(self, dnClaimRef, instanceNumber):
        """
        Add the reference to the dispense claim document to the instance.
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        instance[self.FIELD_CLAIM][self.FIELD_DISPENSE_CLAIM_MSG_REF] = dnClaimRef

    def returnCompletionDate(self, instanceNumber):
        """
        Return the completion date for the requested instance
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        return instance[self.FIELD_COMPLETION_DATE]

    def addClaimAmendDocumentRef(self, dnClaimRef, instanceNumber):
        """
        Add the old claim reference to the dispense claim MsgRef history and add the new
        document to the instance.
        """
        instance = self._get_prescription_instance_data(instanceNumber)

        if not instance[self.FIELD_CLAIM][self.FIELD_HISTORIC_DISPENSE_CLAIM_MSG_REF]:
            instance[self.FIELD_CLAIM][self.FIELD_HISTORIC_DISPENSE_CLAIM_MSG_REF] = []

        _historicClaimMsgRef = instance[self.FIELD_CLAIM][self.FIELD_DISPENSE_CLAIM_MSG_REF]

        instance[self.FIELD_CLAIM][self.FIELD_HISTORIC_DISPENSE_CLAIM_MSG_REF].append(
            _historicClaimMsgRef
        )
        instance[self.FIELD_CLAIM][self.FIELD_DISPENSE_CLAIM_MSG_REF] = dnClaimRef

    def updateInstanceStatus(self, instance, newStatus):
        """
        Method for updating the status of the current instance
        """
        if self.FIELD_PRESCRIPTION_STATUS in instance:
            instance[self.FIELD_PREVIOUS_STATUS] = instance[self.FIELD_PRESCRIPTION_STATUS]
        else:
            instance[self.FIELD_PREVIOUS_STATUS] = False
        instance[self.FIELD_PRESCRIPTION_STATUS] = newStatus

    def updateLineItemStatus(self, issueDict, statusToCheck, newStatus):
        """
        Roll through the line items checking for those who have current status of
        statusToCheck, then update to newStatus and change the previous status.
        Note that this is safe for cancelled and expired line items as it will only update
        if the 'statusToCheck' matches.

        :type issueDict: dict
        :type statusToCheck: str
        :type newStatus: str
        """
        issue = PrescriptionIssue(issueDict)
        for lineItem in issue.line_items:
            if lineItem.status == statusToCheck:
                lineItem.update_status(newStatus)

    def updateLineItemStatusFromDispense(self, instance, dn_lineItems):
        """
        Roll through the line itesm on the dispense notification, and update the
        prescription record line items to the revised previousStatus and status
        """
        for dn_lineItem in dn_lineItems:
            for lineItem in instance[self.FIELD_LINE_ITEMS]:
                if lineItem[self.FIELD_ID] == dn_lineItem[self.FIELD_ID]:
                    lineItem[self.FIELD_PREVIOUS_STATUS] = lineItem[self.FIELD_STATUS]
                    lineItem[self.FIELD_STATUS] = dn_lineItem[self.FIELD_STATUS]

    def setExemptionDates(self):
        """
        Set the exemption dates
        """
        _patientDetails = self.prescriptionRecord[self.FIELD_PATIENT]
        _birthTime = _patientDetails[self.FIELD_BIRTH_TIME]

        lowerAgeLimit = datetime.datetime.strptime(_birthTime, TimeFormats.STANDARD_DATE_FORMAT)
        lowerAgeLimit += relativedelta(years=PrescriptionRecord._YOUNG_AGE_EXEMPTION, days=-1)
        lowerAgeLimit = lowerAgeLimit.isoformat()[0:10].replace("-", "")
        higherAgeLimit = datetime.datetime.strptime(_birthTime, TimeFormats.STANDARD_DATE_FORMAT)
        higherAgeLimit += relativedelta(years=PrescriptionRecord._OLD_AGE_EXEMPTION)
        higherAgeLimit = higherAgeLimit.isoformat()[0:10].replace("-", "")
        _patientDetails[self.FIELD_LOWER_AGE_LIMIT] = lowerAgeLimit
        _patientDetails[self.FIELD_HIGHER_AGE_LIMIT] = higherAgeLimit

    def returnMessageRef(self, docType):
        """
        Return message references for different document types
        """
        if docType == "Prescription":
            return self.prescriptionRecord[self.FIELD_PRESCRIPTION][self.FIELD_PRESCRIPTION_MSG_REF]
        if docType == "ReleaseRequest":
            return self._currentInstanceData[self.FIELD_RELEASE_REQUEST_MGS_REF]
        else:
            raise EpsSystemError("developmentFailure")

    def returnReleaseDispenserDetails(self, _targetInstance):
        """
        Return release dispenser details of the target instance
        """
        _instance = self._get_prescription_instance_data(_targetInstance)
        return _instance.get(self.FIELD_RELEASE_DISPENSER_DETAILS)

    def fetchReleaseResponseParameters(self):
        """
        A dictionary of response parameters is required for generating the response
        message to the release request - these are parameters which will be used to
        translate and update the original prescription message
        """
        releaseData = {}
        _patientDetails = self.prescriptionRecord[self.FIELD_PATIENT]
        _prescDetails = self.prescriptionRecord[self.FIELD_PRESCRIPTION]

        releaseData[self.FIELD_LOWER_AGE_LIMIT] = quoted(
            _patientDetails[self.FIELD_LOWER_AGE_LIMIT]
        )
        releaseData[self.FIELD_HIGHER_AGE_LIMIT] = quoted(
            _patientDetails[self.FIELD_HIGHER_AGE_LIMIT]
        )

        if self._currentInstanceData.get(self.FIELD_PREVIOUS_ISSUE_DATE):
            # SPII-10490 - handle this date not being present
            _previousIssueData = quoted(self._currentInstanceData[self.FIELD_PREVIOUS_ISSUE_DATE])
            releaseData[self.FIELD_PREVIOUS_ISSUE_DATE] = _previousIssueData

        # !!! This is for backwards compatibility - does not make sense, should really be
        # the current status.  However Spine 1 returns previous status !!!
        # Note that we also have to remap the prescription status here if this is a GUID
        # release for a '0000' (internal only) prescription status.
        _previousPrescStatus = self._currentInstanceData[self.FIELD_PREVIOUS_STATUS]
        if _previousPrescStatus == PrescriptionStatus.AWAITING_RELEASE_READY:
            _previousPrescStatus = PrescriptionStatus.TO_BE_DISPENSED

        releaseData[self.FIELD_PRESCRIPTION_STATUS] = quoted(_previousPrescStatus)

        _displayName = PrescriptionStatus.PRESCRIPTION_DISPLAY_LOOKUP[_previousPrescStatus]
        releaseData[self.FIELD_PRESCRIPTION_STATUS_DISPLAY_NAME] = quoted(_displayName)
        releaseData[self.FIELD_PRESCRIPTION_CURRENT_INSTANCE] = quoted(str(self.currentIssueNumber))
        releaseData[self.FIELD_PRESCRIPTION_MAX_REPEATS] = quoted(
            _prescDetails[self.FIELD_MAX_REPEATS]
        )

        for lineItem in self.currentIssue.line_items:
            _lineItemRef = "lineItem" + str(lineItem.order)
            _itemStatus = (
                lineItem.previousStatus
                if lineItem.status == LineItemStatus.WITH_DISPENSER
                else lineItem.status
            )

            releaseData[_lineItemRef + "Status"] = quoted(_itemStatus)
            _itemDisplayName = LineItemStatus.ITEM_DISPLAY_LOOKUP[_itemStatus]
            releaseData[_lineItemRef + "StatusDisplayName"] = quoted(_itemDisplayName)

            self.addLineItemRepeatData(releaseData, _lineItemRef, lineItem)

        return releaseData

    def addLineItemRepeatData(self, releaseData, lineItemRef, lineItem):
        """
        Add line item information (only done for repeat prescriptions)
        Note that due to inconsistency of repeat numbers, it is possible that the
        current instance for the whole prescription is greater than the line item maxRepeats
        in which case the line item maxRepeats should be used.

        :type releaseData: dict
        :type lineItemRef: str
        :type lineItem: PrescriptionLineItem
        """
        _lineInstance = self.currentIssueNumber

        if lineItem.maxRepeats < self.currentIssueNumber:
            _lineInstance = lineItem.maxRepeats

        releaseData[lineItemRef + "MaxRepeats"] = quoted(str(lineItem.maxRepeats))
        releaseData[lineItemRef + "CurrentInstance"] = quoted(str(_lineInstance))

    def validateLinePrescriptionStatus(self, prescriptionStatus, lineItemStatus):
        """
        Compare lineItem status with the prescription status and confirm that the combination is valid
        """
        if lineItemStatus in LineItemStatus.VALID_STATES[prescriptionStatus]:
            return True

        self.logObject.writeLog(
            "EPS0259",
            None,
            {
                "internalID": self.internalID,
                "lineItemStatus": lineItemStatus,
                "prescriptionStatus": prescriptionStatus,
            },
        )

        return False

    def forceCurrentInstanceIncrement(self):
        """
        Force the current instance number to be incremented.
        This is a serious undertaking, but is required where an issue is missing.
        """
        oldCurrentIssueNumber = self.currentIssueNumber

        if self.currentIssueNumber == self.maxRepeats:
            self.logObject.writeLog(
                "EPS0625b",
                None,
                {
                    "internalID": self.internalID,
                    "currentIssueNumber": oldCurrentIssueNumber,
                    "reason": "already at maxRepeats",
                },
            )
            return

        # Count upwards from the current issue number to maxRepeats, looking either for
        # an issue that exists
        newCurrentIssueNumber = False
        for i in range(self.currentIssueNumber, self.maxRepeats + 1):
            try:
                newCurrentIssueNumber = i
                break
            except KeyError:
                continue

        if not newCurrentIssueNumber:
            self.logObject.writeLog(
                "EPS0625b",
                None,
                {
                    "internalID": self.internalID,
                    "currentIssueNumber": oldCurrentIssueNumber,
                    "reason": "no issues available",
                },
            )
            return

        self.logObject.writeLog(
            "EPS0625",
            None,
            {
                "internalID": self.internalID,
                "oldCurrentIssueNumber": oldCurrentIssueNumber,
                "newCurrentIssueNumber": newCurrentIssueNumber,
            },
        )

        self.currentIssueNumber = newCurrentIssueNumber

    def resetCurrentInstance(self):
        """
        Rotate through the instances to find the first instance which is either in a
        future or active state.  Then reset the currentInstance to be this instance.
        This is used in Admin updates.  If no future/active instances - then it should
        be the last instance

        :returns: a list containing the old and new "current instance" number as strings
        :rtype: [str, str]
        """

        # see if we can find an issue from the current one upwards in an active or future state
        newCurrentIssueNumber = None
        acceptableStates = PrescriptionStatus.ACTIVE_STATES + PrescriptionStatus.FUTURE_STATES
        for issue in self.getIssuesFromCurrentUpwards():
            if issue.status in acceptableStates:
                newCurrentIssueNumber = issue.number
                break

        # if we didn't find one, then just set to the last issue
        if newCurrentIssueNumber is None:
            newCurrentIssueNumber = self.issue_numbers[-1]

        # update the current instance number
        oldCurrentIssueNumber = self.currentIssueNumber
        self.currentIssueNumber = newCurrentIssueNumber

        return (oldCurrentIssueNumber, newCurrentIssueNumber)

    def checkCurrentInstanceToCancelByPR_ID(self):
        """
        Check for the prescription being in a cancellable status
        """
        return self._currentInstanceStatus in PrescriptionStatus.CANCELLABLE_STATES

    def checkCurrentInstanceWDispenserByPR_ID(self):
        """
        Check for the prescription being in a with dispenser status
        """
        return self._currentInstanceStatus in PrescriptionStatus.WITH_DISPENSER_STATES

    def checkIncludePerformerDetailByPR_ID(self):
        """
        Check whether the prescription status is such that the performer node should be
        included in the cancellation response message.
        """
        return self._currentInstanceStatus in PrescriptionStatus.INCLUDE_PERFORMER_STATES

    def checkCurrentInstanceToCancelByLI_ID(self, lineItemRef):
        """
        Check for the line item being in a cancellable status
        """
        return self._checkCurrentInstanceByLineItem(
            lineItemRef, LineItemStatus.ITEM_CANCELLABLE_STATES
        )

    def checkCurrentInstanceWDispenserByLI_ID(self, lineItemRef):
        """
        Check for the line item being in a with dispenser status
        """
        return self._checkCurrentInstanceByLineItem(
            lineItemRef, LineItemStatus.ITEM_WITH_DISPENSER_STATES
        )

    def checkIncludePerformerDetailByLI_ID(self, lineItemRef):
        """
        Check whether the line item status is such that the performer node should be
        included in the cancellation response message.
        """
        return self._checkCurrentInstanceByLineItem(
            lineItemRef, LineItemStatus.INCLUDE_PERFORMER_STATES
        )

    def _checkCurrentInstanceByLineItem(self, lineItemRef, lineItemStates):
        """
        Check for the line item being in one of the specified states
        """
        for lineItem in self._currentInstanceData[
            self.FIELD_LINE_ITEMS
        ]:  # noqa: SIM110 - More readable as is
            if (lineItemRef == lineItem[self.FIELD_ID]) and (
                lineItem[self.FIELD_STATUS] in lineItemStates
            ):
                return True
        return False

    def checkNhsNumberMatch(self, context):
        """
        Check if the nhsNumber on the prescription record matches the nhsNumber in the
        cancellation. Return True or False.
        """
        return self._nhsNumber == context.nhsNumber

    def returnErrorForInvalidCancelByPR_ID(self):
        """
        Raise the correct cancellation code matching the status of the current
        instance
        """
        prescStatus = self._currentInstanceStatus

        self.logObject.writeLog(
            "EPS0262",
            None,
            {
                "internalID": self.internalID,
                "currentInstance": str(self.currentIssueNumber),
                "cancellationType": self.FIELD_PRESCRIPTION,
                "currentStatus": prescStatus,
            },
        )

        # return values below are to be mapped to equivalent ErrorBase1719 in Spine.
        if prescStatus in PrescriptionStatus.COMPLETED_STATES:
            if prescStatus == PrescriptionStatus.EXPIRED:
                return EpsErrorBase.NOT_CANCELLED_EXPIRED
            elif prescStatus == PrescriptionStatus.CANCELLED:
                return EpsErrorBase.NOT_CANCELLED_CANCELLED
            elif prescStatus == PrescriptionStatus.NOT_DISPENSED:
                return EpsErrorBase.NOT_CANCELLED_NOT_DISPENSED
            else:
                return EpsErrorBase.NOT_CANCELLED_DISPENSED

        if prescStatus == PrescriptionStatus.WITH_DISPENSER:
            return EpsErrorBase.NOT_CANCELLED_WITH_DISPENSER
        if prescStatus == PrescriptionStatus.WITH_DISPENSER_ACTIVE:
            return EpsErrorBase.NOT_CANCELLED_WITH_DISPENSER_ACTIVE

    def returnErrorForInvalidCancelByLI_ID(self, context):
        """
        Confirm if line item exists.  If it does raise the error associated with the
        line item status
        """
        _lineItemStatus = None
        for lineItem in self._currentInstanceData[self.FIELD_LINE_ITEMS]:
            if context.cancelLineItemRef != lineItem[self.FIELD_ID]:
                continue
            _lineItemStatus = lineItem[self.FIELD_STATUS]

        self.logObject.writeLog(
            "EPS0262",
            None,
            {
                "internalID": self.internalID,
                "currentInstance": str(self.currentIssueNumber),
                "cancellationType": "lineItem",
                "currentStatus": _lineItemStatus,
            },
        )

        # return values below are to be mapped to equivalent ErrorBase1719 in Spine.
        if not _lineItemStatus:
            return EpsErrorBase.PRESCRIPTION_NOT_FOUND

        if _lineItemStatus == LineItemStatus.FULLY_DISPENSED:
            return EpsErrorBase.NOT_CANCELLED_DISPENSED
        if _lineItemStatus == LineItemStatus.NOT_DISPENSED:
            return EpsErrorBase.NOT_CANCELLED_NOT_DISPENSED
        if _lineItemStatus == LineItemStatus.CANCELLED:
            return EpsErrorBase.NOT_CANCELLED_CANCELLED
        if _lineItemStatus == LineItemStatus.EXPIRED:
            return EpsErrorBase.NOT_CANCELLED_EXPIRED
        else:
            return EpsErrorBase.NOT_CANCELLED_WITH_DISPENSER_ACTIVE

    def applyCancellation(self, cancellationObj, _rangeToCancelStartIssue=None):
        """
        Loop through the valid cancellations on the context and change the prescription
        status as appropriate
        """
        _instances = self.prescriptionRecord[self.FIELD_INSTANCES]

        # only apply from the start issue upwards
        if not _rangeToCancelStartIssue:
            _rangeToCancelStartIssue = self.currentIssueNumber
        _rangeToUpdate = self.get_issues_in_range(int(_rangeToCancelStartIssue), None)

        issueNumbers = [issue.number for issue in _rangeToUpdate]
        for issueNumber in issueNumbers:
            instance = _instances[str(issueNumber)]
            if cancellationObj[self.FIELD_CANCELLATION_TARGET] == "LineItem":
                self.processLineCancellation(instance, cancellationObj)
            else:
                self.processInstanceCancellation(instance, cancellationObj)
        # the current issue may have become cancelled, so find the new current one?
        self.resetCurrentInstance()
        return [cancellationObj[self.FIELD_CANCELLATION_ID], issueNumbers]

    def removePendingCancellations(self):
        """
        Once the pending cancellations have been completed, remove any pending
        cancellations from the record
        """
        self.prescriptionRecord[self.FIELD_PENDING_CANCELLATIONS] = False

    def processInstanceCancellation(self, instance, cancellationObj):
        """
        Change the prescription status, and set the completion date
        """
        instance[self.FIELD_PREVIOUS_STATUS] = instance[self.FIELD_PRESCRIPTION_STATUS]
        instance[self.FIELD_PRESCRIPTION_STATUS] = PrescriptionStatus.CANCELLED
        instance[self.FIELD_CANCELLATIONS].append(cancellationObj)
        _completionDate = datetime.datetime.strptime(
            cancellationObj[self.FIELD_CANCELLATION_TIME], TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        instance[self.FIELD_COMPLETION_DATE] = _completionDate.strftime(
            TimeFormats.STANDARD_DATE_FORMAT
        )

    def processLineCancellation(self, instance, cancellationObj):
        """
        Loop through the line items to find one relevant to the cancellation,
        If all line items now inactive then cancel the instance
        """
        activeLineItem = False
        for lineItem in instance[self.FIELD_LINE_ITEMS]:
            if cancellationObj[self.FIELD_CANCEL_LINE_ITEM_REF] != lineItem[self.FIELD_ID]:
                if lineItem[self.FIELD_STATUS] in LineItemStatus.ACTIVE_STATES:
                    activeLineItem = True
                continue
            lineItem[self.FIELD_PREVIOUS_STATUS] = lineItem[self.FIELD_STATUS]
            lineItem[self.FIELD_STATUS] = LineItemStatus.CANCELLED
        instance[self.FIELD_CANCELLATIONS].append(cancellationObj)

        if not activeLineItem:
            self.processInstanceCancellation(instance, cancellationObj)

    def returnPendingCancellations(self):
        """
        Return the list of pendingCancellations (should be False if none exist)
        """
        return self._pendingCancellations

    def returnCancellationObject(self, context, _hl7, _reasons):
        """
        Create an object (dict) which describes a cancellation
        """
        cancellationObj = self.set_all_snippet_details(
            PrescriptionRecord.INSTANCE_CANCELLATION_DETAILS, context
        )
        cancellationObj[self.FIELD_REASONS] = _reasons
        cancellationObj[self.FIELD_HL7] = _hl7
        return cancellationObj

    def checkPendingCancellationUniqueWDisp(self, cancellationObj):
        """
        Check whether the pending cancellation is unique. If not unique, return false and
        a boolean to indicate whether the requesting organisation matches.
        If there are no pendingCancellations already on the prescription then return
        immediately, indicating that the cancellation is unique.

        For both the pending cancellation (if exists) and the cancellationObject, if the
        target is a LineItem, set the target variable to be a string of
        LineItem_<<LineItemRef>> for logging purposes.

        This method is used for pending cancellations when the prescription is with
        dispenser, therefore whilst it is similar to the method used when
        the prescription has not yet been received by Spine
        (checkPendingCancellationUnique), in this case a whole prescription cancellation
        is treated independently to individual line item cancellations, as the action of
        the dispenser could mean that either one, both or neither cancellations are
        possible.
        """
        if not self._pendingCancellations:
            return [True, None]

        cancellationTarget = str(cancellationObj[self.FIELD_CANCELLATION_TARGET])
        cancellationOrg = str(cancellationObj[self.FIELD_AGENT_ORGANIZATION])
        if cancellationTarget == "LineItem":
            cancellationTarget = "LineItem_" + str(cancellationObj[self.FIELD_CANCEL_LINE_ITEM_REF])

        orgMatch = True
        for _pendingCancellation in self._pendingCancellations:
            pendingTarget = str(_pendingCancellation[self.FIELD_CANCELLATION_TARGET])
            if pendingTarget == "LineItem":
                pendingTarget = "LineItem_" + str(
                    _pendingCancellation[self.FIELD_CANCEL_LINE_ITEM_REF]
                )
            pendingOrg = str(_pendingCancellation[self.FIELD_AGENT_ORGANIZATION])
            if pendingTarget == cancellationTarget:
                if pendingOrg != cancellationOrg:
                    orgMatch = False
                self.logObject.writeLog(
                    "EPS0264a",
                    None,
                    dict(
                        {
                            "internalID": self.internalID,
                            "pendingOrg": pendingOrg,
                            "cancellationTarget": cancellationTarget,
                            "cancellationOrg": cancellationOrg,
                        }
                    ),
                )
                return [False, orgMatch]

        return [True, None]

    def checkPendingCancellationUnique(self, cancellationObj):
        """
        Check whether the pending cancellation is unique. If not unique, return false and
        a boolean to indicate whether the requesting organisation matches.
        If there are no pendingCancellations already on the prescription then return
        immediately, indicating that the cancellation is unique.

        For both the pending cancellation (if exists) and the cancellationObject, if the
        target is a LineItem, set the target variable to be a string of
        LineItem_<<LineItemRef>> for logging purposes.

        This method is used for pending cancellations when the prescription has not yet
        been received by Spine, therefore whilst it is similar to the method used when
        the prescription is With Dispenser (checkPendingCancellationUniqueWDisp) except
        that in this case a whole prescription cancellation takes precedence over
        individual line item cancellations.
        """

        if not self._pendingCancellations:
            return [True, None]

        cancellationTarget = str(cancellationObj[self.FIELD_CANCELLATION_TARGET])
        cancellationOrg = str(cancellationObj[self.FIELD_AGENT_ORGANIZATION])
        if cancellationTarget == "LineItem":
            cancellationTarget = "LineItem_" + str(cancellationObj[self.FIELD_CANCEL_LINE_ITEM_REF])

        wholePrescriptionCancellation = False
        orgMatch = True
        for _pendingCancellation in self._pendingCancellations:
            pendingTarget = str(_pendingCancellation[self.FIELD_CANCELLATION_TARGET])
            pendingOrg = str(_pendingCancellation[self.FIELD_AGENT_ORGANIZATION])
            if pendingTarget == self.FIELD_PRESCRIPTION:
                wholePrescriptionCancellation = True
            if pendingTarget == "LineItem":
                pendingTarget = "LineItem_" + str(
                    _pendingCancellation[self.FIELD_CANCEL_LINE_ITEM_REF]
                )
            if (pendingTarget == cancellationTarget) or wholePrescriptionCancellation:
                if pendingOrg != cancellationOrg:
                    orgMatch = False
                self.logObject.writeLog(
                    "EPS0264a",
                    None,
                    dict(
                        {
                            "internalID": self.internalID,
                            "pendingOrg": pendingOrg,
                            "cancellationTarget": cancellationTarget,
                            "cancellationOrg": cancellationOrg,
                        }
                    ),
                )
                return [False, orgMatch]

        return [True, None]

    def setUnsuccessfulCancellation(self, cancellationObj, failureReason):
        """
        Set on the record details of the cancellation that has been unsuccessful,
        including the a reason. Note that this is used for unsuccessful pending
        cancellations and where a cancellation is a duplicate, and does not apply to
        cancellations that are simply not valid.
        """
        _failedCs = self.prescriptionRecord[self.FIELD_PRESCRIPTION][
            self.FIELD_UNSUCCESSFUL_CANCELLATIONS
        ]
        cancellationObj["failureReason"] = failureReason

        if not _failedCs:
            _failedCs = []
        _failedCs.append(cancellationObj)

        self.prescriptionRecord[self.FIELD_PRESCRIPTION][
            self.FIELD_UNSUCCESSFUL_CANCELLATIONS
        ] = _failedCs

    def setPendingCancellation(self, cancellationObj, prescriptionPresent):
        """
        Set the default Prescription Pending Cancellation status code and then
        Append a cancellation object to the pendingCancellations
        """

        if not prescriptionPresent:
            instance = self._get_prescription_instance_data("1")
            self.updateInstanceStatus(instance, PrescriptionStatus.PENDING_CANCELLATION)

        _pendingCs = self._pendingCancellations

        if not _pendingCs:
            _pendingCs = [cancellationObj]
            _cancellationDate = datetime.datetime.strptime(
                cancellationObj[self.FIELD_CANCELLATION_TIME], TimeFormats.STANDARD_DATE_TIME_FORMAT
            )
            cancellationDate = _cancellationDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
            if not self.prescriptionRecord[self.FIELD_PRESCRIPTION][self.FIELD_PRESCRIPTION_TIME]:
                self.prescriptionRecord[self.FIELD_PRESCRIPTION][
                    self.FIELD_PRESCRIPTION_TIME
                ] = cancellationDate
                self.logObject.writeLog(
                    "EPS0340",
                    None,
                    dict(
                        {
                            "internalID": self.internalID,
                            "cancellationDate": cancellationDate,
                            "prescriptionID": self.returnPrescriptionID(),
                        }
                    ),
                )
        else:
            _pendingCs.append(cancellationObj)

        self._pendingCancellations = _pendingCs

    def setInitialPrescriptionStatus(self, handleTime):
        """
        Create the initial prescription status. For repeat dispense prescriptions, this
        needs to consider both the prescription date and the dispense window low dates,
        therefore this common method will be overridden.

        A prescription should not be available for download before its start date.

        :type handleTime: datetime.datetime
        """
        firstIssue = self.get_issue(1)

        futureThreshold = handleTime + datetime.timedelta(days=1)
        if self.time > futureThreshold:
            firstIssue.status = PrescriptionStatus.FUTURE_DATED_PRESCRIPTION
        else:
            firstIssue.status = PrescriptionStatus.TO_BE_DISPENSED

    @property
    def maxRepeats(self):
        """
        The maximum number of issues of this prescription.

        :rtype: int
        """
        return 1

    def returnInstanceDetailsForAmend(self, instanceNumber):
        """
        For dispense messages the following details are required:
        Instance status
        NHS Number
        Dispensing Organisation
        None (indicating not a repeat prescription so no maxRepeats)
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        instanceStatus = instance[self.FIELD_PRESCRIPTION_STATUS]
        dispensingOrg = instance[self.FIELD_DISPENSE][self.FIELD_DISPENSING_ORGANIZATION]

        return [str(self.currentIssueNumber), instanceStatus, self._nhsNumber, dispensingOrg, None]

    def returnDispenseHistoryEvents(self, _targetInstance):
        """
        Return the dispense history events for a specific instance
        """
        _instance = self._get_prescription_instance_data(_targetInstance)
        return _instance[self.FIELD_DISPENSE_HISTORY]

    def getWithdrawnStatus(self, _passedStatus):
        """
        Dispense Return can only go back as far as 'with dispenser-active' for repeat dispense
        prescriptions, so convert the status for with dispenser, otherwise, return what was provided.
        """
        return _passedStatus

    def returnPrescriptionType(self):
        """
        Return the prescription type from the prescription record
        """
        return self.prescriptionRecord[self.FIELD_PRESCRIPTION].get(
            self.FIELD_PRESCRIPTION_TYPE, ""
        )

    def returnPrescriptionTreatmentType(self):
        """
        Return the prescription treatment type from the prescription record
        """
        return self.prescriptionRecord[self.FIELD_PRESCRIPTION].get(
            self.FIELD_PRESCRIPTION_TREATMENT_TYPE, ""
        )

    def returnParentPrescriptionDocumentKey(self):
        """
        Return the parent prescription document key from the prescription record
        """
        return self.prescriptionRecord.get(self.FIELD_PRESCRIPTION, {}).get(
            self.FIELD_PRESCRIPTION_MSG_REF
        )

    def returnSignedTime(self):
        """
        Return the signed date/time from the prescription record
        """
        return self.prescriptionRecord[self.FIELD_PRESCRIPTION].get(self.FIELD_SIGNED_TIME, "")

    def returnChangeLog(self):
        """
        Return the change log from the prescription record
        """
        return self.prescriptionRecord.get(self.FIELD_CHANGE_LOG, [])

    def returnNominationData(self):
        """
        Return the nomination data from the prescription record
        """
        return self.prescriptionRecord.get(self.FIELD_NOMINATION)

    def returnPrescriptionField(self):
        """
        Return the complete prescription field
        """
        return self.prescriptionRecord[self.FIELD_PRESCRIPTION]


class SinglePrescribeRecord(PrescriptionRecord):
    """
    Class defined to handle single instance (acute) prescriptions
    """

    def __init__(self, logObject, internalID):
        """
        Allow the recordType attribute to be set
        """
        super(SinglePrescribeRecord, self).__init__(logObject, internalID)
        self.recordType = "Acute"

    def addLineItemRepeatData(self, releaseData, lineItemRef, lineItem):
        """
        Add line item information (This is not required for Acute prescriptions, but
        will invalidate the signature if provided in the prescription and not returned
        in the release.
        It the lineItem.maxRepeats is false (not provided inbound), then do not include
        it in the response, otherwise, both MaxRepeats and CurrentInstnace will be 1 for Acute.

        :type releaseData: dict
        :type lineItemRef: str
        :type lineItem: PrescriptionLineItem
        """
        # Handle the missing inbound maxRepeats
        if not lineItem.maxRepeats:
            return

        # Acute, so both values may only be '1'
        releaseData[lineItemRef + "MaxRepeats"] = quoted(str(1))
        releaseData[lineItemRef + "CurrentInstance"] = quoted(str(1))

    def returnDetailsForDispense(self):
        """
        For dispense messages the following details are required:
        - Issue number
        - Issue status
        - NHS Number
        - Dispensing Organisation
        - None (indicating not a repeat prescription so no maxRepeats)
        """
        currentIssue = self.currentIssue
        details = [
            str(currentIssue.number),
            currentIssue.status,
            self._nhsNumber,
            currentIssue.dispensing_organization,
            None,
        ]
        return details

    def returnDetailsForClaim(self, instanceNumberStr):
        """
        For dispense messages the following details are required:
        - Issue status
        - NHS Number
        - Dispensing Organisation
        - None (indicating not a repeat prescription so no maxRepeats)
        """
        issueNumber = int(instanceNumberStr)
        issue = self.get_issue(issueNumber)
        details = [
            issue.claim,
            issue.status,
            self._nhsNumber,
            issue.dispensingOrganization,
            None,
        ]
        return details

    def returnLastDispenseDate(self, instanceNumber):
        """
        Return the lastDispenseDate for the requested instance
        """
        instance = self._get_prescription_instance_data(instanceNumber)
        lastDispenseDate = instance[self.FIELD_DISPENSE][self.FIELD_LAST_DISPENSE_DATE]
        return lastDispenseDate

    def returnLastDispMsgRef(self, instanceNumberStr):
        """
        returns the last dispense Msg Ref for the issue
        """
        issueNumber = int(instanceNumberStr)
        issue = self.get_issue(issueNumber)
        return issue.lastDispenseNotificationMsgRef


class RepeatPrescribeRecord(PrescriptionRecord):
    """
    Class defined to handle repeat prescribe prescriptions
    """

    def __init__(self, logObject, internalID):
        """
        Allow the recordType attribute to be set
        """
        super(RepeatPrescribeRecord, self).__init__(logObject, internalID)
        self.recordType = "RepeatPrescribe"


class RepeatDispenseRecord(PrescriptionRecord):
    """
    Class defined to handle repeat dispense prescriptions
    """

    def __init__(self, logObject, internalID):
        """
        Allow the recordType attribute to be set
        """
        super(RepeatDispenseRecord, self).__init__(logObject, internalID)
        self.recordType = "RepeatDispense"

    def create_instances(self, context, line_items):
        """
        Create all prescription instances

        Expire any lineItems that have a lower maxRepeats number than the instance number
        """

        instance_snippets = {}

        _rangeMax = int(context.max_repeats) + 1
        _futureInstanceStatus = PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE

        for instanceNumber in range(1, _rangeMax):
            instance_snippet = self.set_all_snippet_details(
                PrescriptionRecord.INSTANCE_DETAILS, context
            )
            instance_snippet[self.FIELD_LINE_ITEMS] = []
            for lineItem in line_items:
                _lineItemCopy = copy(lineItem)
                if int(_lineItemCopy[self.FIELD_MAX_REPEATS]) < instanceNumber:
                    _lineItemCopy[self.FIELD_STATUS] = LineItemStatus.EXPIRED
                instance_snippet[self.FIELD_LINE_ITEMS].append(_lineItemCopy)

            instance_snippet[self.FIELD_INSTANCE_NUMBER] = str(instanceNumber)
            if instanceNumber != 1:
                instance_snippet[self.FIELD_PRESCRIPTION_STATUS] = _futureInstanceStatus
            instance_snippet[self.FIELD_DISPENSE] = self.set_all_snippet_details(
                PrescriptionRecord.DISPENSE_DETAILS, context
            )
            instance_snippet[self.FIELD_CLAIM] = self.set_all_snippet_details(
                PrescriptionRecord.CLAIM_DETAILS, context
            )
            instance_snippet[self.FIELD_CANCELLATIONS] = []
            instance_snippet[self.FIELD_DISPENSE_HISTORY] = {}
            instance_snippets[str(instanceNumber)] = instance_snippet
            instance_snippet[self.FIELD_NEXT_ACTIVITY] = {}
            instance_snippet[self.FIELD_NEXT_ACTIVITY][self.FIELD_ACTIVITY] = None
            instance_snippet[self.FIELD_NEXT_ACTIVITY][self.FIELD_DATE] = None

        return instance_snippets

    def setInitialPrescriptionStatus(self, handleTime):
        """
        Create the initial prescription status. For repeat dispense prescriptions, this
        needs to consider both the prescription date and the dispense window low dates.

        If either the prescriptionTime or dispenseWindowLow date is in the future then
        the prescription needs to have a Future Dated Prescription status set and can
        not yet be downloaded.
        If the prescription is not Future Dated, the default To Be Dispensed should be used.

        Note that this only applies to the first instance, the remaining instances will
        already have a Future Repeat Dispense Instance status set.

        :type handleTime: datetime.datetime
        """
        firstIssue = self.get_issue(1)

        futureThreshold = handleTime + datetime.timedelta(days=1)
        isFutureDated = self.time > futureThreshold

        dispense_low_date = firstIssue.dispense_window_low_date
        if dispense_low_date is not None and dispense_low_date > futureThreshold:
            isFutureDated = True

        if isFutureDated:
            firstIssue.status = PrescriptionStatus.FUTURE_DATED_PRESCRIPTION
        else:
            firstIssue.status = PrescriptionStatus.TO_BE_DISPENSED

    def getWithdrawnStatus(self, _passedStatus):
        """
        Dispense Return can only go back as far as 'with dispenser-active' for repeat dispense
        prescriptions, so convert the status for with dispenser, otherwise, return what was provided.
        """
        if _passedStatus == PrescriptionStatus.WITH_DISPENSER:
            return PrescriptionStatus.WITH_DISPENSER_ACTIVE
        return _passedStatus

    @property
    def maxRepeats(self):
        """
        The maximum number of issues of this prescription.

        :rtype: int
        """
        maxRepeats = self.prescriptionRecord[self.FIELD_PRESCRIPTION][self.FIELD_MAX_REPEATS]
        return int(maxRepeats)

    @property
    def future_issues_available(self):
        """
        Return boolean to indicate if future issues are available or not. Always False for
        Acute and Repeat Prescribe

        :rtype: bool
        """
        return self.currentIssueNumber < self.maxRepeats


class NextActivityGenerator(object):
    """
    Used to create the next activity for a prescription instance
    """

    INPUT_LIST_1 = [
        PrescriptionRecord.FIELD_EXPIRY_PERIOD,
        PrescriptionRecord.FIELD_PRESCRIPTION_DATE,
        PrescriptionRecord.FIELD_NOMINATED_DOWNLOAD_DATE,
        PrescriptionRecord.FIELD_DISPENSE_WINDOW_HIGH_DATE,
    ]
    INPUT_LIST_2 = [
        PrescriptionRecord.FIELD_EXPIRY_PERIOD,
        PrescriptionRecord.FIELD_PRESCRIPTION_DATE,
        PrescriptionRecord.FIELD_DISPENSE_WINDOW_HIGH_DATE,
        PrescriptionRecord.FIELD_LAST_DISPENSE_DATE,
    ]
    INPUT_LIST_3 = [
        PrescriptionRecord.FIELD_EXPIRY_PERIOD,
        PrescriptionRecord.FIELD_PRESCRIPTION_DATE,
        PrescriptionRecord.FIELD_COMPLETION_DATE,
    ]
    INPUT_LIST_4 = [
        PrescriptionRecord.FIELD_EXPIRY_PERIOD,
        PrescriptionRecord.FIELD_PRESCRIPTION_DATE,
        PrescriptionRecord.FIELD_COMPLETION_DATE,
        PrescriptionRecord.FIELD_DISPENSE_WINDOW_HIGH_DATE,
        PrescriptionRecord.FIELD_LAST_DISPENSE_DATE,
        PrescriptionRecord.FIELD_CLAIM_SENT_DATE,
    ]
    INPUT_LIST_5 = [
        PrescriptionRecord.FIELD_PRESCRIBING_SITE_TEST_STATUS,
        PrescriptionRecord.FIELD_PRESCRIPTION_DATE,
        PrescriptionRecord.FIELD_CLAIM_SENT_DATE,
    ]
    INPUT_LIST_6 = [
        PrescriptionRecord.FIELD_EXPIRY_PERIOD,
        PrescriptionRecord.FIELD_PRESCRIPTION_DATE,
        PrescriptionRecord.FIELD_NOMINATED_DOWNLOAD_DATE,
        PrescriptionRecord.FIELD_DISPENSE_WINDOW_LOW_DATE,
    ]
    INPUT_LIST_7 = [
        PrescriptionRecord.FIELD_EXPIRY_PERIOD,
        PrescriptionRecord.FIELD_PRESCRIPTION_DATE,
    ]

    INPUT_BY_STATUS = {}
    INPUT_BY_STATUS[PrescriptionStatus.TO_BE_DISPENSED] = INPUT_LIST_1
    INPUT_BY_STATUS[PrescriptionStatus.WITH_DISPENSER] = INPUT_LIST_1
    INPUT_BY_STATUS[PrescriptionStatus.WITH_DISPENSER_ACTIVE] = INPUT_LIST_2
    INPUT_BY_STATUS[PrescriptionStatus.EXPIRED] = INPUT_LIST_3
    INPUT_BY_STATUS[PrescriptionStatus.CANCELLED] = INPUT_LIST_3
    INPUT_BY_STATUS[PrescriptionStatus.DISPENSED] = INPUT_LIST_4
    INPUT_BY_STATUS[PrescriptionStatus.NOT_DISPENSED] = INPUT_LIST_3
    INPUT_BY_STATUS[PrescriptionStatus.CLAIMED] = INPUT_LIST_5
    INPUT_BY_STATUS[PrescriptionStatus.NO_CLAIMED] = INPUT_LIST_5
    INPUT_BY_STATUS[PrescriptionStatus.AWAITING_RELEASE_READY] = INPUT_LIST_6
    INPUT_BY_STATUS[PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE] = INPUT_LIST_7
    INPUT_BY_STATUS[PrescriptionStatus.FUTURE_DATED_PRESCRIPTION] = INPUT_LIST_6
    INPUT_BY_STATUS[PrescriptionStatus.PENDING_CANCELLATION] = [
        PrescriptionRecord.FIELD_PRESCRIPTION_DATE
    ]

    FIELD_REPEAT_DISPENSE_EXPIRY_PERIOD = "repeatDispenseExpiryPeriod"
    FIELD_PRESCRIPTION_EXPIRY_PERIOD = "prescriptionExpiryPeriod"
    FIELD_WITH_DISPENSER_ACTIVE_EXPIRY_PERIOD = "withDispenserActiveExpiryPeriod"
    FIELD_EXPIRED_DELETE_PERIOD = "expiredDeletePeriod"
    FIELD_CANCELLED_DELETE_PERIOD = "cancelledDeletePeriod"
    FIELD_NOTIFICATION_DELAY_PERIOD = "notificationDelayPeriod"
    FIELD_CLAIMED_DELETE_PERIOD = "claimedDeletePeriod"
    FIELD_NOT_DISPENSED_DELETE_PERIOD = "notDispensedDeletePeriod"
    FIELD_RELEASE_VERSION = "releaseVersion"

    def __init__(self, logObject, internalID):
        self.logObject = logObject
        self.internalID = internalID

        # Map between prescription status and method for calculating index values
        self._indexMap = {}
        self._indexMap[PrescriptionStatus.TO_BE_DISPENSED] = self.unDispensed
        self._indexMap[PrescriptionStatus.WITH_DISPENSER] = self.unDispensed
        self._indexMap[PrescriptionStatus.WITH_DISPENSER_ACTIVE] = self.partDispensed
        self._indexMap[PrescriptionStatus.EXPIRED] = self.expired
        self._indexMap[PrescriptionStatus.CANCELLED] = self.cancelled
        self._indexMap[PrescriptionStatus.DISPENSED] = self.dispensed
        self._indexMap[PrescriptionStatus.NO_CLAIMED] = self.completed
        self._indexMap[PrescriptionStatus.NOT_DISPENSED] = self.notDispensed
        self._indexMap[PrescriptionStatus.CLAIMED] = self.completed
        self._indexMap[PrescriptionStatus.AWAITING_RELEASE_READY] = self.awaitingNominatedRelease
        self._indexMap[PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE] = self.unDispensed
        self._indexMap[PrescriptionStatus.FUTURE_DATED_PRESCRIPTION] = self.futureDated
        self._indexMap[PrescriptionStatus.PENDING_CANCELLATION] = self.awaitingCancellation

    def nextActivityDate(self, nadStatus, nadReference):
        """
        Function takes prescriptionStatus (this will be the prescriptionStatus to be
        if the function is called during an update process)
        Function takes nadStatus - a dictionary of information relevant to
        next-activity-date calculation
        Function takes nadreference - a dictionary of global variables relevant to
        next-activity-date calculation
        Function should return [nextActivity, nextActivityDate, expiryDate]
        """
        prescriptionStatus = nadStatus[PrescriptionRecord.FIELD_PRESCRIPTION_STATUS]

        for key in NextActivityGenerator.INPUT_BY_STATUS[prescriptionStatus]:
            if PrescriptionRecord.FIELD_CAPITAL_D_DATE in key:
                if nadStatus[key]:
                    nadStatus[key] = datetime.datetime.strptime(
                        nadStatus[key], TimeFormats.STANDARD_DATE_FORMAT
                    )
                elif key not in [
                    PrescriptionRecord.FIELD_NOMINATED_DOWNLOAD_DATE,
                    PrescriptionRecord.FIELD_DISPENSE_WINDOW_LOW_DATE,
                ]:
                    nadStatus[key] = datetime.datetime.now()

        self._calculateExpiryDate(nadStatus, nadReference)
        returnValue = self._indexMap[prescriptionStatus](nadStatus, nadReference)
        return returnValue

    def _calculateExpiryDate(self, nadStatus, nadReference):
        """
        Canculate the expiry date to be used in subsequent Next Activity calculations
        """
        if int(nadStatus[PrescriptionRecord.FIELD_INSTANCE_NUMBER]) > 1:
            _expiryDate = (
                nadStatus[PrescriptionRecord.FIELD_PRESCRIPTION_DATE]
                + nadReference[self.FIELD_REPEAT_DISPENSE_EXPIRY_PERIOD]
            )
        else:
            _expiryDate = (
                nadStatus[PrescriptionRecord.FIELD_PRESCRIPTION_DATE]
                + nadReference[self.FIELD_PRESCRIPTION_EXPIRY_PERIOD]
            )

        nadStatus[PrescriptionRecord.FIELD_EXPIRY_DATE] = _expiryDate
        _expiryDateStr = _expiryDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        nadStatus[PrescriptionRecord.FIELD_FORMATTED_EXPIRY_DATE] = _expiryDateStr

    def unDispensed(self, nadStatus, _):
        """
        return [nextActivity, nextActivityDate, expiryDate] for unDispensed prescription
        messages, covers:
        toBeDispensed
        withDispenser
        RepeatDispenseFutureInstance
        """
        nextActivity = PrescriptionRecord.NEXTACTIVITY_EXPIRE
        nextActivityDate = nadStatus[PrescriptionRecord.FIELD_FORMATTED_EXPIRY_DATE]
        return [nextActivity, nextActivityDate, nadStatus[PrescriptionRecord.FIELD_EXPIRY_DATE]]

    def partDispensed(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for partDispensed prescription
        messages
        """
        _maxDispenseTime = nadStatus[PrescriptionRecord.FIELD_LAST_DISPENSE_DATE]
        _maxDispenseTime += nadReference[self.FIELD_WITH_DISPENSER_ACTIVE_EXPIRY_PERIOD]
        expiryDate = min(_maxDispenseTime, nadStatus[PrescriptionRecord.FIELD_EXPIRY_DATE])

        if nadStatus[self.FIELD_RELEASE_VERSION] == PrescriptionRecord.R1_VERSION:
            nextActivity = PrescriptionRecord.NEXTACTIVITY_EXPIRE
            nextActivityDate = expiryDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        else:
            if not nadStatus[PrescriptionRecord.FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF]:
                nextActivity = PrescriptionRecord.NEXTACTIVITY_EXPIRE
                nextActivityDate = expiryDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
            else:
                nextActivity = PrescriptionRecord.NEXTACTIVITY_CREATENOCLAIM
                nextActivityDate = _maxDispenseTime.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, expiryDate]

    def expired(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for expired prescription
        messages
        """
        deletionDate = (
            nadStatus[PrescriptionRecord.FIELD_COMPLETION_DATE]
            + nadReference[self.FIELD_EXPIRED_DELETE_PERIOD]
        )
        nextActivity = PrescriptionRecord.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def cancelled(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for cancelled prescription
        messages
        """
        deletionDate = (
            nadStatus[PrescriptionRecord.FIELD_COMPLETION_DATE]
            + nadReference[self.FIELD_CANCELLED_DELETE_PERIOD]
        )
        nextActivity = PrescriptionRecord.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def dispensed(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for dispensed prescription
        messages.
        Note that if a claim is not received before the notification delay period expires,
        a no claim notification is sent to the PPD.
        """
        _completionDate = nadStatus[PrescriptionRecord.FIELD_COMPLETION_DATE]
        maxNotificationDate = _completionDate + nadReference[self.FIELD_NOTIFICATION_DELAY_PERIOD]
        if nadStatus[self.FIELD_RELEASE_VERSION] == PrescriptionRecord.R1_VERSION:  # noqa: SIM108
            nextActivity = PrescriptionRecord.NEXTACTIVITY_DELETE
        else:
            nextActivity = PrescriptionRecord.NEXTACTIVITY_CREATENOCLAIM
        nextActivityDate = maxNotificationDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def completed(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for completed prescription
        messages

        Note, all reference to claim sent date removed as this now only applies to already
        claimed and no-claimed prescriptions.
        """
        deletionDate = (
            nadStatus[PrescriptionRecord.FIELD_CLAIM_SENT_DATE]
            + nadReference[self.FIELD_CLAIMED_DELETE_PERIOD]
        )
        nextActivity = PrescriptionRecord.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def notDispensed(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for notDispensed prescription
        messages
        """
        deletionDate = (
            nadStatus[PrescriptionRecord.FIELD_COMPLETION_DATE]
            + nadReference[self.FIELD_NOT_DISPENSED_DELETE_PERIOD]
        )
        nextActivity = PrescriptionRecord.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def awaitingNominatedRelease(self, nadStatus, _):
        """
        return [nextActivity, nextActivityDate, expiryDate] for awaitingNominatedRelease
        prescription messages
        """
        readyDate = nadStatus[PrescriptionRecord.FIELD_DISPENSE_WINDOW_LOW_DATE]

        if nadStatus[PrescriptionRecord.FIELD_NOMINATED_DOWNLOAD_DATE]:
            readyDate = nadStatus[PrescriptionRecord.FIELD_NOMINATED_DOWNLOAD_DATE]

        readyDateString = readyDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)

        if readyDate < nadStatus[PrescriptionRecord.FIELD_EXPIRY_DATE]:
            nextActivity = PrescriptionRecord.NEXTACTIVITY_READY
            nextActivityDate = readyDateString
        else:
            nextActivity = PrescriptionRecord.NEXTACTIVITY_EXPIRE
            nextActivityDate = nadStatus[PrescriptionRecord.FIELD_FORMATTED_EXPIRY_DATE]
        return [nextActivity, nextActivityDate, nadStatus[PrescriptionRecord.FIELD_EXPIRY_DATE]]

    def futureDated(self, nadStatus, _):
        """
        return [nextActivity, nextActivityDate, expiryDate] for awaitingNominatedRelease
        prescription messages
        """
        if nadStatus[PrescriptionRecord.FIELD_DISPENSE_WINDOW_LOW_DATE]:
            readyDate = max(
                nadStatus[PrescriptionRecord.FIELD_DISPENSE_WINDOW_LOW_DATE],
                nadStatus[PrescriptionRecord.FIELD_PRESCRIPTION_DATE],
            )
        else:
            readyDate = nadStatus[PrescriptionRecord.FIELD_PRESCRIPTION_DATE]

        readyDateString = readyDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)

        if nadStatus[PrescriptionRecord.FIELD_NOMINATED_DOWNLOAD_DATE]:
            readyDate = nadStatus[PrescriptionRecord.FIELD_NOMINATED_DOWNLOAD_DATE]
        if readyDate < nadStatus[PrescriptionRecord.FIELD_EXPIRY_DATE]:
            nextActivity = PrescriptionRecord.NEXTACTIVITY_READY
            nextActivityDate = readyDateString
        else:
            nextActivity = PrescriptionRecord.NEXTACTIVITY_EXPIRE
            nextActivityDate = nadStatus[PrescriptionRecord.FIELD_FORMATTED_EXPIRY_DATE]
        return [nextActivity, nextActivityDate, nadStatus[PrescriptionRecord.FIELD_EXPIRY_DATE]]

    def awaitingCancellation(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for awaitingCancellation
        prescription messages
        """
        deletionDate = (
            nadStatus[PrescriptionRecord.FIELD_HANDLE_TIME]
            + nadReference[self.FIELD_CANCELLED_DELETE_PERIOD]
        )
        nextActivity = PrescriptionRecord.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]
