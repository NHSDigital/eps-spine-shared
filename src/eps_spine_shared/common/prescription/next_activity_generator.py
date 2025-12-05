import datetime

from eps_spine_shared.common.prescription import fields
from eps_spine_shared.common.prescription.statuses import PrescriptionStatus
from eps_spine_shared.nhsfundamentals.timeutilities import TimeFormats


class NextActivityGenerator(object):
    """
    Used to create the next activity for a prescription instance
    """

    INPUT_LIST_1 = [
        fields.FIELD_EXPIRY_PERIOD,
        fields.FIELD_PRESCRIPTION_DATE,
        fields.FIELD_NOMINATED_DOWNLOAD_DATE,
        fields.FIELD_DISPENSE_WINDOW_HIGH_DATE,
    ]
    INPUT_LIST_2 = [
        fields.FIELD_EXPIRY_PERIOD,
        fields.FIELD_PRESCRIPTION_DATE,
        fields.FIELD_DISPENSE_WINDOW_HIGH_DATE,
        fields.FIELD_LAST_DISPENSE_DATE,
    ]
    INPUT_LIST_3 = [
        fields.FIELD_EXPIRY_PERIOD,
        fields.FIELD_PRESCRIPTION_DATE,
        fields.FIELD_COMPLETION_DATE,
    ]
    INPUT_LIST_4 = [
        fields.FIELD_EXPIRY_PERIOD,
        fields.FIELD_PRESCRIPTION_DATE,
        fields.FIELD_COMPLETION_DATE,
        fields.FIELD_DISPENSE_WINDOW_HIGH_DATE,
        fields.FIELD_LAST_DISPENSE_DATE,
        fields.FIELD_CLAIM_SENT_DATE,
    ]
    INPUT_LIST_5 = [
        fields.FIELD_PRESCRIBING_SITE_TEST_STATUS,
        fields.FIELD_PRESCRIPTION_DATE,
        fields.FIELD_CLAIM_SENT_DATE,
    ]
    INPUT_LIST_6 = [
        fields.FIELD_EXPIRY_PERIOD,
        fields.FIELD_PRESCRIPTION_DATE,
        fields.FIELD_NOMINATED_DOWNLOAD_DATE,
        fields.FIELD_DISPENSE_WINDOW_LOW_DATE,
    ]
    INPUT_LIST_7 = [
        fields.FIELD_EXPIRY_PERIOD,
        fields.FIELD_PRESCRIPTION_DATE,
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
    INPUT_BY_STATUS[PrescriptionStatus.PENDING_CANCELLATION] = [fields.FIELD_PRESCRIPTION_DATE]

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
        prescriptionStatus = nadStatus[fields.FIELD_PRESCRIPTION_STATUS]

        for key in NextActivityGenerator.INPUT_BY_STATUS[prescriptionStatus]:
            if fields.FIELD_CAPITAL_D_DATE in key:
                if nadStatus[key]:
                    nadStatus[key] = datetime.datetime.strptime(
                        nadStatus[key], TimeFormats.STANDARD_DATE_FORMAT
                    )
                elif key not in [
                    fields.FIELD_NOMINATED_DOWNLOAD_DATE,
                    fields.FIELD_DISPENSE_WINDOW_LOW_DATE,
                ]:
                    nadStatus[key] = datetime.datetime.now()

        self._calculateExpiryDate(nadStatus, nadReference)
        returnValue = self._indexMap[prescriptionStatus](nadStatus, nadReference)
        return returnValue

    def _calculateExpiryDate(self, nadStatus, nadReference):
        """
        Canculate the expiry date to be used in subsequent Next Activity calculations
        """
        if int(nadStatus[fields.FIELD_INSTANCE_NUMBER]) > 1:
            _expiryDate = (
                nadStatus[fields.FIELD_PRESCRIPTION_DATE]
                + nadReference[fields.FIELD_REPEAT_DISPENSE_EXPIRY_PERIOD]
            )
        else:
            _expiryDate = (
                nadStatus[fields.FIELD_PRESCRIPTION_DATE]
                + nadReference[fields.FIELD_PRESCRIPTION_EXPIRY_PERIOD]
            )

        nadStatus[fields.FIELD_EXPIRY_DATE] = _expiryDate
        _expiryDateStr = _expiryDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        nadStatus[fields.FIELD_FORMATTED_EXPIRY_DATE] = _expiryDateStr

    def unDispensed(self, nadStatus, _):
        """
        return [nextActivity, nextActivityDate, expiryDate] for unDispensed prescription
        messages, covers:
        toBeDispensed
        withDispenser
        RepeatDispenseFutureInstance
        """
        nextActivity = fields.NEXTACTIVITY_EXPIRE
        nextActivityDate = nadStatus[fields.FIELD_FORMATTED_EXPIRY_DATE]
        return [nextActivity, nextActivityDate, nadStatus[fields.FIELD_EXPIRY_DATE]]

    def partDispensed(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for partDispensed prescription
        messages
        """
        _maxDispenseTime = nadStatus[fields.FIELD_LAST_DISPENSE_DATE]
        _maxDispenseTime += nadReference[fields.FIELD_WITH_DISPENSER_ACTIVE_EXPIRY_PERIOD]
        expiryDate = min(_maxDispenseTime, nadStatus[fields.FIELD_EXPIRY_DATE])

        if nadStatus[fields.FIELD_RELEASE_VERSION] == fields.R1_VERSION:
            nextActivity = fields.NEXTACTIVITY_EXPIRE
            nextActivityDate = expiryDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        else:
            if not nadStatus[fields.FIELD_LAST_DISPENSE_NOTIFICATION_MSG_REF]:
                nextActivity = fields.NEXTACTIVITY_EXPIRE
                nextActivityDate = expiryDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
            else:
                nextActivity = fields.NEXTACTIVITY_CREATENOCLAIM
                nextActivityDate = _maxDispenseTime.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, expiryDate]

    def expired(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for expired prescription
        messages
        """
        deletionDate = (
            nadStatus[fields.FIELD_COMPLETION_DATE]
            + nadReference[fields.FIELD_EXPIRED_DELETE_PERIOD]
        )
        nextActivity = fields.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def cancelled(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for cancelled prescription
        messages
        """
        deletionDate = (
            nadStatus[fields.FIELD_COMPLETION_DATE]
            + nadReference[fields.FIELD_CANCELLED_DELETE_PERIOD]
        )
        nextActivity = fields.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def dispensed(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for dispensed prescription
        messages.
        Note that if a claim is not received before the notification delay period expires,
        a no claim notification is sent to the PPD.
        """
        _completionDate = nadStatus[fields.FIELD_COMPLETION_DATE]
        maxNotificationDate = _completionDate + nadReference[fields.FIELD_NOTIFICATION_DELAY_PERIOD]
        if nadStatus[fields.FIELD_RELEASE_VERSION] == fields.R1_VERSION:  # noqa: SIM108
            nextActivity = fields.NEXTACTIVITY_DELETE
        else:
            nextActivity = fields.NEXTACTIVITY_CREATENOCLAIM
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
            nadStatus[fields.FIELD_CLAIM_SENT_DATE]
            + nadReference[fields.FIELD_CLAIMED_DELETE_PERIOD]
        )
        nextActivity = fields.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def notDispensed(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for notDispensed prescription
        messages
        """
        deletionDate = (
            nadStatus[fields.FIELD_COMPLETION_DATE]
            + nadReference[fields.FIELD_NOT_DISPENSED_DELETE_PERIOD]
        )
        nextActivity = fields.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]

    def awaitingNominatedRelease(self, nadStatus, _):
        """
        return [nextActivity, nextActivityDate, expiryDate] for awaitingNominatedRelease
        prescription messages
        """
        readyDate = nadStatus[fields.FIELD_DISPENSE_WINDOW_LOW_DATE]

        if nadStatus[fields.FIELD_NOMINATED_DOWNLOAD_DATE]:
            readyDate = nadStatus[fields.FIELD_NOMINATED_DOWNLOAD_DATE]

        readyDateString = readyDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)

        if readyDate < nadStatus[fields.FIELD_EXPIRY_DATE]:
            nextActivity = fields.NEXTACTIVITY_READY
            nextActivityDate = readyDateString
        else:
            nextActivity = fields.NEXTACTIVITY_EXPIRE
            nextActivityDate = nadStatus[fields.FIELD_FORMATTED_EXPIRY_DATE]
        return [nextActivity, nextActivityDate, nadStatus[fields.FIELD_EXPIRY_DATE]]

    def futureDated(self, nadStatus, _):
        """
        return [nextActivity, nextActivityDate, expiryDate] for awaitingNominatedRelease
        prescription messages
        """
        if nadStatus[fields.FIELD_DISPENSE_WINDOW_LOW_DATE]:
            readyDate = max(
                nadStatus[fields.FIELD_DISPENSE_WINDOW_LOW_DATE],
                nadStatus[fields.FIELD_PRESCRIPTION_DATE],
            )
        else:
            readyDate = nadStatus[fields.FIELD_PRESCRIPTION_DATE]

        readyDateString = readyDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)

        if nadStatus[fields.FIELD_NOMINATED_DOWNLOAD_DATE]:
            readyDate = nadStatus[fields.FIELD_NOMINATED_DOWNLOAD_DATE]
        if readyDate < nadStatus[fields.FIELD_EXPIRY_DATE]:
            nextActivity = fields.NEXTACTIVITY_READY
            nextActivityDate = readyDateString
        else:
            nextActivity = fields.NEXTACTIVITY_EXPIRE
            nextActivityDate = nadStatus[fields.FIELD_FORMATTED_EXPIRY_DATE]
        return [nextActivity, nextActivityDate, nadStatus[fields.FIELD_EXPIRY_DATE]]

    def awaitingCancellation(self, nadStatus, nadReference):
        """
        return [nextActivity, nextActivityDate, expiryDate] for awaitingCancellation
        prescription messages
        """
        deletionDate = (
            nadStatus[fields.FIELD_HANDLE_TIME] + nadReference[fields.FIELD_CANCELLED_DELETE_PERIOD]
        )
        nextActivity = fields.NEXTACTIVITY_DELETE
        nextActivityDate = deletionDate.strftime(TimeFormats.STANDARD_DATE_FORMAT)
        return [nextActivity, nextActivityDate, None]
