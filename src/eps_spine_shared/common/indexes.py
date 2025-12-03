from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.nhsfundamentals.timeutilities import timeNowAsString

INDEX_NHSNUMBER_DATE = "nhsNumberDate_bin"
INDEX_NHSNUMBER_PRDATE = "nhsNumberPrescriberDate_bin"
INDEX_NHSNUMBER_PRDSDATE = "nhsNumberPrescDispDate_bin"
INDEX_NHSNUMBER_DSDATE = "nhsNumberDispenserDate_bin"
INDEX_PRESCRIBER_DATE = "prescriberDate_bin"
INDEX_PRESCRIBER_DSDATE = "prescDispDate_bin"
INDEX_PRESCRIBER_STATUS = "prescribingSiteStatus_bin"
INDEX_DISPENSER_DATE = "dispenserDate_bin"
INDEX_DISPENSER_STATUS = "dispensingSiteStatus_bin"

INDEX_NEXTACTIVITY = "nextActivityNAD_bin"
INDEX_NOMPHARM = "nomPharmStatus_bin"
INDEX_NHSNUMBER = "nhsNumber_bin"
INDEX_DELETE_DATE = "backstopdeletedate_bin"
INDEX_PRESCRIPTION_ID = "prescriptionid_bin"
INDEX_STORE_TIME_DOC_REF_TITLE = "storetimebydocreftitle_bin"

REGEX_INDICES = [
    INDEX_NHSNUMBER_DATE,
    INDEX_NHSNUMBER_PRDATE,
    INDEX_NHSNUMBER_PRDSDATE,
    INDEX_NHSNUMBER_DSDATE,
    INDEX_PRESCRIBER_DATE,
    INDEX_PRESCRIBER_DSDATE,
    INDEX_DISPENSER_DATE,
]

SEPERATOR = "|"
INDEX_DELTA = "delta_bin"


class PrescriptionIndexFactory(object):
    """
    Factory for building index details for prescription record
    """

    def __init__(self, logObject, internalID, testPrescribingSites, nadReference):
        """
        Make internalID available for logging in indexer
        Requires nadreference - a set of timedeltas to be used when calculating the next
        activity index
        requires testPrescribingSites - used to differentiate for claims
        """
        self.logObject = logObject
        self.internalID = internalID
        self.testPrescribingSites = testPrescribingSites
        self.nadReference = nadReference

    def buildIndexes(self, context):
        """
        Create the index values to be used when storing the epsRecord.  There may be
        separate index terms for each individual instance (but only unique index terms
        for the prescription should be returned).

        There are four potential indexes for the epsRecord store:
        nextActivityNAD - the next activity which is due for this prescription and the
        date which it is due (should only contain a single term)
        prescribingSiteStatus - the statuses of the prescription concatenated with the
        prescribing site (to be used in reporting and troubleshooting)
        dispensingSiteStatus - as above (not added until release has occurred)
        nomPharmStatus - as above for any nominated pharmacy (may also be used when bulk
        changes in nomination occur)
        nhsNumber - to be used when managing changes in nomination
        delta - to be used when confirming changes are synchronised between clusters
        """
        indexDict = {}
        try:
            self._addPrescibingSiteStatusIndex(context.epsRecord, indexDict)
            self._addDispensingSiteStatusIndex(context.epsRecord, indexDict)
            self._addNominatedPharmacyStatusIndex(context.epsRecord, indexDict)
            self._addNextActivityNextActivityDateIndex(context, indexDict)
            self._addNHSNumberIndex(context.epsRecord, indexDict)

            # Adding extra indexes for prescription search
            # overloading each of these indexes with Release version and prescription status in preparation for
            # Riak 1.4
            self._addNHSNumberDateIndex(context.epsRecord, indexDict)
            self._addNHSNumberPresciberDateIndex(context.epsRecord, indexDict)
            self._addNHSNumberPresciberDispenserDateIndex(context.epsRecord, indexDict)
            self._addNHSNumberDispenserDateIndex(context.epsRecord, indexDict)
            self._addPresciberDateIndex(context.epsRecord, indexDict)
            self._addPresciberDispenserDateIndex(context.epsRecord, indexDict)
            self._addDispenserDateIndex(context.epsRecord, indexDict)
            self._addDeltaIndex(context.epsRecord, indexDict)
        except EpsSystemError as e:
            self.logObject.writeLog(
                "EPS0124", None, {"internalID": self.internalID, "creatingIndex": e.errorTopic}
            )
            raise EpsSystemError(EpsSystemError.MESSAGE_FAILURE) from e

        return indexDict

    def _addNHSNumberDateIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        nhsNumber = epsRecord.returnNHSNumber()
        prescriptionTime = epsRecord.returnPrescriptionTime()
        nhsNumberDate_bin = nhsNumber + SEPERATOR + prescriptionTime
        indexDict[INDEX_NHSNUMBER_DATE] = epsRecord.addReleaseAndStatus(nhsNumberDate_bin)

    def _addNHSNumberPresciberDateIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        nhsNumber = epsRecord.returnNHSNumber()
        prescriber = epsRecord.returnPrescribingOrganisation()
        prescriptionTime = epsRecord.returnPrescriptionTime()
        index = nhsNumber + SEPERATOR + prescriber + SEPERATOR + prescriptionTime
        _newIndexes = epsRecord.addReleaseAndStatus(index)
        indexDict[INDEX_NHSNUMBER_PRDATE] = _newIndexes

    def _addNHSNumberPresciberDispenserDateIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        _resultList = epsRecord.returnNhsNumberPrescriberDispenserDateIndex()
        [success, nhsNumberPrescDispDate_bin] = _resultList
        if not success:
            raise EpsSystemError(INDEX_NHSNUMBER_PRDSDATE)
        if nhsNumberPrescDispDate_bin:
            _newIndexes = epsRecord.addReleaseAndStatus(nhsNumberPrescDispDate_bin, False)
            indexDict[INDEX_NHSNUMBER_PRDSDATE] = _newIndexes

    def _addPresciberDateIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        prescriber = epsRecord.returnPrescribingOrganisation()
        prescriptionTime = epsRecord.returnPrescriptionTime()
        prescriberDate_bin = prescriber + SEPERATOR + prescriptionTime
        indexDict[INDEX_PRESCRIBER_DATE] = epsRecord.addReleaseAndStatus(prescriberDate_bin)

    def _addNHSNumberDispenserDateIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        _resultList = epsRecord.returnNhsNumberDispenserDateIndex()
        [success, nhsNumberDispenserDate_bin] = _resultList
        if not success:
            raise EpsSystemError(INDEX_NHSNUMBER_DSDATE)
        if nhsNumberDispenserDate_bin:
            _newIndexes = epsRecord.addReleaseAndStatus(nhsNumberDispenserDate_bin, False)
            indexDict[INDEX_NHSNUMBER_DSDATE] = _newIndexes

    def _addPresciberDispenserDateIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        _resultList = epsRecord.returnPrescriberDispenserDateIndex()
        [success, prescDispDate_bin] = _resultList
        if not success:
            raise EpsSystemError(INDEX_PRESCRIBER_DSDATE)
        if prescDispDate_bin:
            _newIndexes = epsRecord.addReleaseAndStatus(prescDispDate_bin, False)
            indexDict[INDEX_PRESCRIBER_DSDATE] = _newIndexes

    def _addDispenserDateIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        _resultList = epsRecord.returnDispenserDateIndex()
        [success, dispenserDate_bin] = _resultList
        if not success:
            raise EpsSystemError(INDEX_DISPENSER_DATE)
        if dispenserDate_bin:
            _newIndexes = epsRecord.addReleaseAndStatus(dispenserDate_bin, False)
            indexDict[INDEX_DISPENSER_DATE] = _newIndexes

    def _addNextActivityNextActivityDateIndex(self, context, indexDict):
        """
        See buildIndexes
        """
        _resultList = context.epsRecord.returnNextActivityIndex(
            self.testPrescribingSites, self.nadReference, context
        )

        [nextActivity, nextActivityDate] = _resultList
        nextActivityNAD_bin = (
            f"{nextActivity}_{nextActivityDate}"
            if nextActivityDate and nextActivity
            else nextActivity
        )
        indexDict[INDEX_NEXTACTIVITY] = [nextActivityNAD_bin]

    def _addPrescibingSiteStatusIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        _resultList = epsRecord.returnPrescSiteStatusIndex()
        [success, prescSite, prescriptionStatus] = _resultList
        if not success:
            raise EpsSystemError(INDEX_PRESCRIBER_STATUS)
        indexDict[INDEX_PRESCRIBER_STATUS] = []
        for status in prescriptionStatus:
            indexDict[INDEX_PRESCRIBER_STATUS].append(prescSite + "_" + status)

    def _addDispensingSiteStatusIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        _resultList = epsRecord.returnDispSiteStatusIndex()
        [success, dispSiteStatuses] = _resultList
        if not success:
            raise EpsSystemError(INDEX_DISPENSER_STATUS)
        indexDict[INDEX_DISPENSER_STATUS] = list(dispSiteStatuses)

    def _addNominatedPharmacyStatusIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        [nomPharmacy, prescriptionStatus] = epsRecord.returnNomPharmStatusIndex()

        if nomPharmacy:
            indexDict[INDEX_NOMPHARM] = []
            for status in prescriptionStatus:
                indexDict[INDEX_NOMPHARM].append(nomPharmacy + "_" + status)

            self.logObject.writeLog(
                "EPS0617",
                None,
                {
                    "internalID": self.internalID,
                    "nomPharmacy": nomPharmacy,
                    "indexes": indexDict[INDEX_NOMPHARM],
                },
            )
        else:
            self.logObject.writeLog("EPS0618", None, {"internalID": self.internalID})

    def _addNHSNumberIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        nhsNumber = epsRecord.returnNHSNumber()
        indexDict[INDEX_NHSNUMBER] = [nhsNumber]

    def _addDeltaIndex(self, epsRecord, indexDict):
        """
        See buildIndexes
        """
        indexDict[INDEX_DELTA] = [timeNowAsString() + SEPERATOR + str(epsRecord.getSCN())]
