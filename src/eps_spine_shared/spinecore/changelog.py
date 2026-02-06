import datetime
import re
import uuid

from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.nhsfundamentals.time_utilities import TimeFormats


class ChangeLogProcessor(object):
    """
    Keep the change log within the record

    The methods here assume that a None is never passed as change log, if necessary pass {} instead.
    """

    TIMESTAMP = "Timestamp"
    SCN = "SCN"
    SYS_SDS = "agentSystemSDS1"
    PRS_SDS = "agentPersonSDSPerson"
    UPDATES = "updatesApplied"
    XSLT = "Source XSLT"
    RSP_PARAMS = "Response Parameters"
    NOTIFICATIONS = "Notifications"
    INTERNAL_ID = "InternalID"
    INTERACTION_ID = "interactionID"
    TIME_PREPARED = "timePreparedForUpdate"
    INSTANCE = "instance"

    RECORD_SCN_REF = "SCN"
    RECORD_CHANGELOG_REF = "changeLog"

    INITIAL_SCN = 1

    DO_NOT_PRUNE = -1
    PRUNE_POINT = 12
    INVALID_SCN = -1

    @classmethod
    def logForGeneralUpdate(cls, sCN, internalID=None, xslt=None, rspParameters=None):
        """
        Add a general change log update, nothing specific to a domain
        """
        if not rspParameters:
            rspParameters = {}

        logOfChange = {}
        _timeOfChange = datetime.datetime.now().strftime(TimeFormats.STANDARD_DATE_TIME_FORMAT)
        logOfChange[cls.TIMESTAMP] = _timeOfChange
        logOfChange[cls.SCN] = sCN
        logOfChange[cls.INTERNAL_ID] = internalID
        logOfChange[cls.XSLT] = xslt
        logOfChange[cls.RSP_PARAMS] = rspParameters
        return logOfChange

    @classmethod
    def updateChangeLog(cls, record, newLog, messageID, prunePoint=None):
        """
        Take a change log from the record, add the new log to it, and prune to the prune
        point
        """
        if not prunePoint:
            prunePoint = cls.PRUNE_POINT

        changeLog = record.get(cls.RECORD_CHANGELOG_REF, {})
        changeLog[messageID] = newLog

        cls.pruneChangeLog(changeLog, prunePoint)

        record[cls.RECORD_CHANGELOG_REF] = changeLog
        return record

    @classmethod
    def pruneChangeLog(cls, changeLog, prunePoint):
        """
        Prune to the prune point
        """
        if prunePoint != cls.DO_NOT_PRUNE:
            _, _highestSCN = cls.getHighestSCN(changeLog)
            if _highestSCN != cls.INVALID_SCN:
                _scnToPrune = _highestSCN - prunePoint
                pruneList = []
                for guid, changeLogEntry in changeLog.items():
                    _entrySCN = int(changeLogEntry.get(cls.SCN, cls.INVALID_SCN))
                    if _entrySCN < _scnToPrune:
                        pruneList.append(guid)

                for guid in pruneList:
                    del changeLog[guid]

    @classmethod
    def getHighestSCN(cls, changeLog):
        """
        Return the (guid, scn) from the first changeLog found with the highest SCN
        """
        (highestGUID, highestSCN) = (None, cls.INVALID_SCN)
        for _guid in changeLog:
            _scn = int(changeLog[_guid].get(cls.SCN, cls.INVALID_SCN))
            if _scn > highestSCN:
                highestGUID = _guid
                highestSCN = _scn
        return (highestGUID, highestSCN)

    @classmethod
    def getSCN(cls, changeLogEntry):
        """
        Retrieve the SCN as an int from the provided changeLog entry
        """
        scnNumber = int(changeLogEntry.get(cls.SCN, cls.INVALID_SCN))
        return scnNumber

    @classmethod
    def listSCNs(cls, changeLog):
        """
        Performs list comprehension on the changeLog dictionary to retrieve all the SCNs from changeLog

        Duplicates will be present and changeLog entries with no SCN will be represented with the
        INVALID_SCN constant
        """
        scnNumberList = [cls.getSCN(changeLog[x]) for x in changeLog]
        return scnNumberList

    @classmethod
    def getMaxSCN(cls, changeLog):
        """
        Return the highest SCN value from the provided changeLog
        """
        scnNumberList = cls.listSCNs(changeLog)
        if not scnNumberList:
            return cls.INVALID_SCN
        highestSCN = max(scnNumberList)
        return highestSCN

    @classmethod
    def getAllGuidsForSCN(cls, changeLog, searchScn):
        """
        For the provided SCN return the GUID Keys of all the changeLog entries that have that SCN

        Usually this will be a single GUID, but in the case of tickled records there can be multiple.
        """
        searchScn = int(searchScn)
        guidList = [k for k in changeLog if cls.getSCN(changeLog[k]) == searchScn]
        return guidList

    @classmethod
    def getMaxSCNGuids(cls, changeLog):
        """
        Finds the highest SCN in the changeLog and returns all the GUIDs that have that SCN
        """
        highestSCN = cls.getMaxSCN(changeLog)
        guidList = cls.getAllGuidsForSCN(changeLog, highestSCN)
        return guidList

    @classmethod
    def getAllGuids(cls, changeLog):
        """
        Return a list of all the GUID keys from the provided changeLog
        """
        return list(changeLog.keys())

    @classmethod
    def getLastChangeTime(cls, changeLog):
        """
        Returns the last change time
        """
        try:
            guid = cls.getMaxSCNGuids(changeLog)[0]
        except IndexError:
            return None
        return changeLog[guid].get(cls.TIMESTAMP)

    @classmethod
    def setInitialChangeLog(cls, record, internalID, reasonGUID=None):
        """
        If no change log is present set an initial change log on the record.  It may
        use a GUID as a key or a string explaining the reason for initiating the
        change log.
        """
        changeLog = record.get(cls.RECORD_CHANGELOG_REF)
        if changeLog:
            return

        scn = int(record.get(cls.RECORD_SCN_REF, cls.INITIAL_SCN))
        if not reasonGUID:
            reasonGUID = str(uuid.uuid4()).upper()
        changeLog = {}
        changeLog[reasonGUID] = cls.logForGeneralUpdate(scn, internalID)

        record[cls.RECORD_CHANGELOG_REF] = changeLog


class DemographicsChangeLogProcessor(ChangeLogProcessor):
    """
    Change Log Processor specifically for demographic records
    """

    # Demographic record uses 'serialChangeNumber' rather than the default 'SCN'
    RECORD_SCN_REF = "serialChangeNumber"

    @classmethod
    def logForDomainUpdate(cls, updateContext, internalID):
        """
        Create a change log for this expected change - requires attributes to be set on
        context object
        """
        logOfChange = cls.logForGeneralUpdate(
            updateContext.pdsRecord.get(cls.RECORD_SCN_REF, cls.INITIAL_SCN),
            internalID,
            updateContext.responseDetails.get(cls.XSLT),
            updateContext.responseDetails.get(cls.RSP_PARAMS),
        )

        logOfChange[cls.SYS_SDS] = updateContext.agentSystem
        logOfChange[cls.PRS_SDS] = updateContext.agentPerson
        logOfChange[cls.UPDATES] = updateContext.updatesApplied
        logOfChange[cls.NOTIFICATIONS] = updateContext.notificationsToQueue
        return logOfChange

    @staticmethod
    def getHighestGpLinksTransactionNumber(changeLog, sender, recipient):
        """
        Return the highest GP Links transaction number which has been included in the change log, or None (if there
        aren't any).
        """
        maxNumber = -1

        gpLinksKeyPattern = re.compile(
            "^{}_{}_[0-9]+_[0-9]+_(?P<transactionNumber>[0-9]+)$".format(
                sender.upper(), recipient.upper()
            )
        )

        for key in changeLog.keys():  # noqa: SIM118
            match = gpLinksKeyPattern.match(key)
            # Ignore keys which aren't related to GP Links transactions
            if match is None:
                continue
            transactionNumber = int(match.group("transactionNumber"))
            if transactionNumber > maxNumber:
                maxNumber = transactionNumber

        return maxNumber


class PrescriptionsChangeLogProcessor(ChangeLogProcessor):
    """
    Change Log Processor specifically for prescriptions records
    """

    FROM_STATUS = "fromStatus"
    TO_STATUS = "toStatus"
    INS_FROM_STATUS = "instanceFromStatus"
    INS_TO_STATUS = "instanceToStatus"
    PRE_CHANGE_STATUS_DICT = "preChangeStatusDict"
    POST_CHANGE_STATUS_DICT = "postChangeStatusDict"
    CHANGED_ISSUES_LIST = "issuesAlteredByChange"
    PRE_CHANGE_CURRENT_ISSUE = "preChangeCurrentIssue"
    POST_CHANGE_CURRENT_ISSUE = "postChangeCurrentIssue"
    TOUCHED = "touched"
    AGENT_ROLE_PROFILE_CODE_ID = "agentRoleProfileCodeId"
    AGENT_PERSON_ROLE = "agentPersonRole"
    AGENT_PERSON_ORG_CODE = "agentPersonOrgCode"

    MIN_INITIALHISTORY = 16
    MIN_RECENTHISTORY = 16
    REPEATING_ACTIONS = [
        "PORX_IN060102UK30",
        "PORX_IN060102SM30",
        "PORX_IN132004UK30",
        "PORX_IN132004SM30",
        "PORX_IN132004UK04",
        "PORX_IN100101UK31",
        "PORX_IN100101SM31",
        "PORX_IN100101UK04",
        "PORX_IN020101UK31",
        "PORX_IN020102UK31",
        "PORX_IN020101SM31",
        "PORX_IN020102SM31",
        "PORX_IN020101UK04",
        "PORX_IN020102UK04",
        "PORX_IN060102GB01",
        "PRESCRIPTION_DISPENSE_PROPOSAL_RETURN",
    ]

    REGEX_ALPHANUMERIC8 = re.compile(r"^[A-Za-z0-9\-]{1,8}$")

    @classmethod
    def logForDomainUpdate(cls, updateContext, internalID):
        """
        Create a change log for this expected change - requires attribute to be set on
        context object
        """

        logOfChange = cls.logForGeneralUpdate(
            updateContext.epsRecord.get_scn(),
            internalID,
            updateContext.responseDetails.get(cls.XSLT),
            updateContext.responseDetails.get(cls.RSP_PARAMS),
        )
        logOfChange = updateContext.workDescriptionObject.createInitialEventLog(logOfChange)

        _instance = (
            str(updateContext.updateInstance)
            if updateContext.updateInstance
            else str(updateContext.instanceID)
        )

        logOfChange[cls.TIME_PREPARED] = updateContext.handleTime.strftime(
            TimeFormats.STANDARD_DATE_TIME_FORMAT
        )

        # NOTE: FROM_STATUS and TO_STATUS seem to be legacy fields, that have been
        # superceded by the INS_FROM_STATUS and INS_TO_STATUS fields set below.
        # The only reference to TO_STATUS seems to be in PrescriptionJsonQueryResponse.cfg
        # template used by the prescription detail view web service
        logOfChange[cls.FROM_STATUS] = updateContext.epsRecord.return_previous_prescription_status(
            updateContext.instanceID, False
        )
        logOfChange[cls.TO_STATUS] = updateContext.epsRecord.return_prescription_status(
            updateContext.instanceID, False
        )

        # Event history lines for UI
        # **** NOTE THAT THESE ARE WRONG, THEY REFER TO THE FINAL ISSUE, WHICH MAY NOT BE THE ISSUE THAT WAS UPDATED
        logOfChange[cls.INSTANCE] = _instance
        logOfChange[cls.INS_FROM_STATUS] = (
            updateContext.epsRecord.return_previous_prescription_status(_instance, False)
        )
        logOfChange[cls.INS_TO_STATUS] = updateContext.epsRecord.return_prescription_status(
            _instance, False
        )
        logOfChange[cls.AGENT_ROLE_PROFILE_CODE_ID] = updateContext.agentRoleProfileCodeId
        logOfChange[cls.AGENT_PERSON_ROLE] = updateContext.agentPersonRole
        orgCode = updateContext.agentOrganization
        hasDispenserCode = hasattr(updateContext, "dispenserCode") and updateContext.dispenserCode
        if (
            not orgCode
            and hasDispenserCode
            and cls.REGEX_ALPHANUMERIC8.match(updateContext.dispenserCode)
        ):
            orgCode = updateContext.dispenserCode
        logOfChange[cls.AGENT_PERSON_ORG_CODE] = orgCode

        # To help with troubleshooting, the following change entris are added
        _preChangeIssueStatuses = updateContext.epsRecord.return_prechange_issue_status_dict()
        _postChangeIssueStatuses = updateContext.epsRecord.create_issue_current_status_dict()
        logOfChange[cls.PRE_CHANGE_STATUS_DICT] = _preChangeIssueStatuses
        logOfChange[cls.POST_CHANGE_STATUS_DICT] = _postChangeIssueStatuses
        logOfChange[cls.CHANGED_ISSUES_LIST] = updateContext.epsRecord.return_changed_issue_list(
            _preChangeIssueStatuses, _postChangeIssueStatuses, None, updateContext.changedIssuesList
        )
        # To help with troubleshooting, the following currentIssue values are added
        logOfChange[cls.PRE_CHANGE_CURRENT_ISSUE] = (
            updateContext.epsRecord.return_prechange_current_issue()
        )
        logOfChange[cls.POST_CHANGE_CURRENT_ISSUE] = updateContext.epsRecord.current_issue_number
        if hasattr(updateContext, cls.TOUCHED) and updateContext.touched:
            logOfChange[cls.TOUCHED] = updateContext.touched

        return logOfChange

    @classmethod
    def pruneChangeLog(cls, changeLog, prunePoint):
        """
        Prune if other the  prune point
        Prune the change log where there is a series of change log entries for the same
        interactionID - and the change is neither recent nor part of the early history

        The intention if we get a repeating interaction we don't continue to explode the
        changeLog with all the history
        """
        invertedChangeLog = {}
        maxSCN = 0
        for guid, changeLogEntry in changeLog.items():
            _SCN = int(changeLogEntry.get(cls.SCN, cls.INVALID_SCN))
            invertedChangeLog[_SCN] = (guid, changeLogEntry.get(cls.INTERACTION_ID))
            maxSCN = max(maxSCN, _SCN)

        if maxSCN <= prunePoint:
            # Don't make any changes
            return

        _iclSCNKeys = list(invertedChangeLog.keys())
        _iclSCNKeys.sort(reverse=True)
        _guidsToPrune = []
        for _iclSCN in _iclSCNKeys:
            if _iclSCN > (maxSCN - cls.MIN_RECENTHISTORY) or _iclSCN < cls.MIN_INITIALHISTORY:
                continue
            _thisIntID = invertedChangeLog.get(_iclSCN, (None, None))[1]
            (_previousGUID, _previousIntID) = invertedChangeLog.get(_iclSCN - 1, (None, None))
            _oneBeforeIntID = invertedChangeLog.get(_iclSCN - 2, (None, None))[1]
            if (
                _thisIntID
                and _thisIntID in cls.REPEATING_ACTIONS
                and _thisIntID == _previousIntID
                and _previousIntID == _oneBeforeIntID
            ):
                _guidsToPrune.append(_previousGUID)

        for guid in _guidsToPrune:
            del changeLog[guid]

        if len(changeLog) > prunePoint:
            # If we have breached the prune point but can't safely prune - stop before
            # The un-pruned record becomes an issue
            raise EpsSystemError(EpsSystemError.SYSTEM_FAILURE)


class ClinicalsChangeLogProcessor(ChangeLogProcessor):
    """
    Change Log Processor specifically for clinicals patient records
    """

    SYS_SDS = "agentSystemSDS"
    PRS_SDS = "agentPerson"
    PRUNE_POINT = 48

    @classmethod
    def logForDomainUpdate(cls, updateContext, internalID, interactionID=None):
        """
        Create a change log for this expected change - requires attributes to be set on
        context object
        """
        logOfChange = cls.logForGeneralUpdate(
            updateContext.patientRecord.get_scn(),
            internalID,
            updateContext.responseDetails.get(cls.XSLT),
            updateContext.responseDetails.get(cls.RSP_PARAMS),
        )

        logOfChange[cls.TIME_PREPARED] = updateContext.handleTime.strftime(
            TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        logOfChange[cls.INTERACTION_ID] = interactionID
        logOfChange[cls.SYS_SDS] = updateContext.agentSystem
        logOfChange[cls.PRS_SDS] = updateContext.agentPerson
        return logOfChange

    @classmethod
    def logForNotificationUpdate(cls, interactionID, updateTime, scn, internalID):
        """
        Create a change log for this expected change from a notification worker - doesn't use
        context and sets a subset of the items used by logForDomainUpdate
        """
        logOfChange = cls.logForGeneralUpdate(scn, internalID)
        logOfChange[cls.TIME_PREPARED] = updateTime.strftime(TimeFormats.STANDARD_DATE_TIME_FORMAT)
        logOfChange[cls.INTERACTION_ID] = interactionID
        return logOfChange

    @classmethod
    def logForTickleClinicalRecord(cls, updateContext, interactionID, internalID):
        """
        Create a change log for this expected change from a notification worker - doesn't use
        context and sets a subset of the items used by logForDomainUpdate
        """
        logOfChange = cls.logForGeneralUpdate(updateContext.patientRecord.get_scn(), internalID)
        logOfChange[cls.TIME_PREPARED] = updateContext.handleTime.strftime(
            TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        logOfChange[cls.INTERACTION_ID] = interactionID
        logOfChange[cls.SYS_SDS] = "SYSTEM"
        return logOfChange
