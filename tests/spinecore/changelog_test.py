"""
Created on 11 Feb 2014
"""

import copy
import sys
import unittest

from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.spinecore.changelog import ChangeLogProcessor, PrescriptionsChangeLogProcessor

CHANGE_LOG_TO_PRUNE = {
    "GUID1": {"SCN": 1, "InternalID": "INTERNALID"},
    "GUID2": {"SCN": 4, "InternalID": "INTERNALID"},
    "GUID3": {"SCN": 5, "InternalID": "INTERNALID"},
    "GUID4": {"SCN": 6, "InternalID": "INTERNALID"},
    "GUID5": {"SCN": 3, "InternalID": "INTERNALID"},
    "GUID6": {"SCN": 8, "InternalID": "INTERNALID"},
    "GUID7": {"SCN": 9, "InternalID": "INTERNALID"},
    "GUID8": {"SCN": "10", "InternalID": "INTERNALID"},
}


class ChangeLogProcessorTest(unittest.TestCase):
    """
    Tests for the ChangeLogProcessor
    """

    def testGeneralLogEntry_Empty(self):
        """
        test producing a general log with empty inputs
        """
        logOfChange = ChangeLogProcessor.logForGeneralUpdate(1)
        del logOfChange["Timestamp"]

        _expectedLog = {}
        _expectedLog["SCN"] = 1
        _expectedLog["InternalID"] = None
        _expectedLog["Source XSLT"] = None
        _expectedLog["Response Parameters"] = {}
        self.assertEqual(logOfChange, _expectedLog)

    def testPruningOfChangeLog(self):
        """
        Add a new entry into change log and show it is correctly pruned
        """
        _expectedChangeLog = copy.copy(CHANGE_LOG_TO_PRUNE)

        record = {}
        record["changeLog"] = copy.copy(CHANGE_LOG_TO_PRUNE)

        newLog = {"SCN": 12, "InternalID": "INTERNALID"}
        _newRecord = ChangeLogProcessor.updateChangeLog(record, newLog, "GUID9", 6)
        _newChangeLog = _newRecord["changeLog"]

        del _expectedChangeLog["GUID1"]
        del _expectedChangeLog["GUID2"]
        del _expectedChangeLog["GUID3"]
        del _expectedChangeLog["GUID5"]
        _expectedChangeLog["GUID9"] = newLog

        self.assertDictEqual(_newChangeLog, _expectedChangeLog)

    def testNotPruningOfChangeLog(self):
        """
        Add a new entry into change log and show that when DO_NOT_PRUNE is used it does not prune
        """
        _expectedChangeLog = copy.copy(CHANGE_LOG_TO_PRUNE)

        record = {}
        record["changeLog"] = copy.copy(CHANGE_LOG_TO_PRUNE)

        newLog = {"SCN": 12, "InternalID": "INTERNALID"}
        _newRecord = ChangeLogProcessor.updateChangeLog(
            record, newLog, "GUID9", ChangeLogProcessor.DO_NOT_PRUNE
        )
        _newChangeLog = _newRecord["changeLog"]

        _expectedChangeLog["GUID9"] = newLog

        self.assertDictEqual(_newChangeLog, _expectedChangeLog)

    def testHighestSCN(self):
        """
        test highest guid and scn returned
        """
        (guid, scn) = ChangeLogProcessor.getHighestSCN(CHANGE_LOG_TO_PRUNE)
        self.assertEqual(guid, "GUID8")
        self.assertEqual(scn, 10)

        record = {}
        record["changeLog"] = copy.copy(CHANGE_LOG_TO_PRUNE)

        newLog = {"SCN": 12, "InternalID": "INTERNALID"}
        _newRecord = ChangeLogProcessor.updateChangeLog(record, newLog, "GUID9", 6)
        _newChangeLog = _newRecord["changeLog"]

        (guid, scn) = ChangeLogProcessor.getHighestSCN(_newChangeLog)
        self.assertEqual(guid, "GUID9")
        self.assertEqual(scn, 12)

    def testGetSCN(self):
        """
        test return of SCN from changeLog entry
        """
        changeLogEntry = {"SCN": 1}
        scn = ChangeLogProcessor.getSCN(changeLogEntry)
        self.assertEqual(scn, 1)
        changeLogEntry = {"SCN": "1"}
        scn = ChangeLogProcessor.getSCN(changeLogEntry)
        self.assertEqual(scn, 1)
        changeLogEntry = {}
        scn = ChangeLogProcessor.getSCN(changeLogEntry)
        self.assertEqual(scn, ChangeLogProcessor.INVALID_SCN)
        changeLogEntry = {"SCN": sys.maxsize}
        scn = ChangeLogProcessor.getSCN(changeLogEntry)
        self.assertEqual(scn, sys.maxsize)

    def testListSCNs(self):
        """
        test the return of the list of SCNs present in a changeLog
        """
        changeLog = {"ABCD": {"SCN": 1}, "EFGH": {"SCN": 2}, "IJKL": {"SCN": 3}}
        scnList = sorted(ChangeLogProcessor.listSCNs(changeLog))
        self.assertEqual(scnList, [1, 2, 3])

        changeLog = {}
        scnList = ChangeLogProcessor.listSCNs(changeLog)
        scnList.sort()
        self.assertEqual(scnList, [])

        changeLog = {"ABCD": {}}
        scnList = ChangeLogProcessor.listSCNs(changeLog)
        scnList.sort()
        self.assertEqual(scnList, [ChangeLogProcessor.INVALID_SCN])

    def testGetMaxSCN(self):
        """
        Test retrieval of the highest SCN from changeLog
        """
        changeLog = {"ABCD": {"SCN": 1}, "IJKL": {"SCN": 3}, "EFGH": {"SCN": 2}}
        highestSCN = ChangeLogProcessor.getMaxSCN(changeLog)
        self.assertEqual(highestSCN, 3)

        changeLog = {"ABCD": {"SCN": 1}, "EFGH": {"SCN": 2}, "IJKL": {"SCN": 3}, "ZZZZ": {"SCN": 3}}
        highestSCN = ChangeLogProcessor.getMaxSCN(changeLog)
        self.assertEqual(highestSCN, 3)

        changeLog = {"ABCD": {}}
        highestSCN = ChangeLogProcessor.getMaxSCN(changeLog)
        self.assertEqual(highestSCN, ChangeLogProcessor.INVALID_SCN)

    def testGetAllGuidsForSCN(self):
        """
        test retrieval of list of GUIDS that are keys for changelog entries which have a particular SCN
        """
        changeLog = {"ABCD": {"SCN": 1}, "EFGH": {"SCN": 2}, "IJKL": {"SCN": 3}, "ZZZZ": {"SCN": 3}}
        guidList = sorted(ChangeLogProcessor.getAllGuidsForSCN(changeLog, 1))
        self.assertEqual(guidList, ["ABCD"])

        guidList = ChangeLogProcessor.getAllGuidsForSCN(changeLog, 3)
        guidList.sort()
        self.assertEqual(guidList, ["IJKL", "ZZZZ"])

        guidList = ChangeLogProcessor.getAllGuidsForSCN(changeLog, "3")
        guidList.sort()
        self.assertEqual(guidList, ["IJKL", "ZZZZ"])

        guidList = ChangeLogProcessor.getAllGuidsForSCN(changeLog, "7")
        guidList.sort()
        self.assertEqual(guidList, [])

    def testGetMaxSCNGuids(self):
        """
        test retrieval of all GUIDS that have the highest SCN in the changeLog entry
        """
        changeLog = {"ABCD": {"SCN": 1}, "IJKL": {"SCN": 3}, "EFGH": {"SCN": 2}}
        guidList = sorted(ChangeLogProcessor.getMaxSCNGuids(changeLog))
        self.assertEqual(guidList, ["IJKL"])

        changeLog = {"ABCD": {"SCN": 1}, "EFGH": {"SCN": 2}, "IJKL": {"SCN": 3}, "ZZZZ": {"SCN": 3}}
        guidList = ChangeLogProcessor.getMaxSCNGuids(changeLog)
        guidList.sort()
        self.assertEqual(guidList, ["IJKL", "ZZZZ"])

        changeLog = {"ABCD": {}, "EFGH": {}}
        guidList = ChangeLogProcessor.getMaxSCNGuids(changeLog)
        guidList.sort()
        self.assertEqual(guidList, ["ABCD", "EFGH"])

        changeLog = {"ABCD": {}, "EFGH": {}, "IJKL": {"SCN": 3}}
        guidList = ChangeLogProcessor.getMaxSCNGuids(changeLog)
        guidList.sort()
        self.assertEqual(guidList, ["IJKL"])

        changeLog = {}
        guidList = ChangeLogProcessor.getMaxSCNGuids(changeLog)
        self.assertEqual(guidList, [])

    def testGetAllGuids(self):
        """
        test getting the list of all GUID keys for a changeLog
        """
        changeLog = {"ABCD": {"SCN": 1}, "EFGH": {"SCN": 2}, "IJKL": {"SCN": 3}, "ZZZZ": {"SCN": 3}}
        guidList = sorted(ChangeLogProcessor.getAllGuids(changeLog))
        self.assertEqual(guidList, ["ABCD", "EFGH", "IJKL", "ZZZZ"])

        changeLog = {"ABCD": {}, "EFGH": {}}
        guidList = ChangeLogProcessor.getAllGuids(changeLog)
        guidList.sort()
        self.assertEqual(guidList, ["ABCD", "EFGH"])

        changeLog = {}
        guidList = ChangeLogProcessor.getAllGuids(changeLog)
        self.assertEqual(guidList, [])

    def testSettingInitialChangeLogOnDataMigration(self):
        """
        Set an initial change log onto a record which does not have one
        """
        record = {}
        internalID = "INTERNALID"
        reasonGUID = "DataMigration"
        ChangeLogProcessor.setInitialChangeLog(record, internalID, reasonGUID)

        _changeLog = record[ChangeLogProcessor.RECORD_CHANGELOG_REF]
        del _changeLog["DataMigration"]["Timestamp"]

        self.assertDictEqual(
            _changeLog,
            {
                "DataMigration": {
                    "SCN": 1,
                    "InternalID": "INTERNALID",
                    "Source XSLT": None,
                    "Response Parameters": {},
                }
            },
        )


PR_CHANGE_LOG_TO_PRUNE = {
    "GUID1": {"SCN": 1, "interactionID": "PORX_IN090101UK01"},
    "GUID2": {"SCN": 4, "interactionID": "PORX_IN090101UK04"},
    "GUID3": {"SCN": 5, "interactionID": "PORX_IN090101UK05"},
    "GUID4": {"SCN": 6, "interactionID": "PORX_IN090101UK05"},
    "GUID5": {"SCN": 3, "interactionID": "PORX_IN060102UK29"},
    "GUID6": {"SCN": 8, "interactionID": "PORX_IN060102UK30"},
    "GUID7": {"SCN": 9, "interactionID": "PORX_IN060102UK30"},
    "GUID8": {"SCN": 33, "interactionID": "PORX_IN060102UK30"},
    "GUID9": {"SCN": 34, "interactionID": "PORX_IN060102UK30"},
    "GUIDA": {"SCN": 35, "interactionID": "PORX_IN060102UK30"},
    "GUIDB": {"SCN": 36, "interactionID": "PORX_IN060102UK30"},
    "GUIDC": {"SCN": 37, "interactionID": "PORX_IN060102UK30"},
    "GUIDD": {"SCN": 40, "interactionID": "PORX_IN060102UK30"},
    "GUIDE": {"SCN": 41, "interactionID": "PORX_IN060102UK30"},
    "GUIDF": {"SCN": 42, "interactionID": "PORX_IN060102UK30"},
    "GUIDX": {"SCN": 43, "interactionID": "PORX_IN090101UK09"},
    "GUIDZ": {"SCN": 82, "interactionID": "PORX_IN060102UK30"},
}

# Should not delete GUID 1-7 (initial history)
# Should not delete GUID 8, C, D - not piggy in middle
# Should not delete GUID F, X is different InteractionID
# Should not delete GUID z (recent history)


class PrescriptionChangeLogProcessorTest(unittest.TestCase):
    """
    Tests for the ChangeLogProcessor
    """

    def testPrunePrescriptionChangeLog(self):
        """
        Prune the record as expected
        """
        _changeLog = copy.copy(PR_CHANGE_LOG_TO_PRUNE)

        PrescriptionsChangeLogProcessor.pruneChangeLog(_changeLog, 80)

        _presentGUIDs = [
            "GUID1",
            "GUID2",
            "GUID3",
            "GUID4",
            "GUID5",
            "GUID6",
            "GUID7",
            "GUID8",
            "GUIDC",
            "GUIDD",
            "GUIDF",
            "GUIDX",
            "GUIDZ",
        ]

        for guid in _presentGUIDs:
            self.assertIn(guid, list(_changeLog.keys()))

        self.assertEqual(len(_presentGUIDs), len(list(_changeLog.keys())))

    def testPrunePrescriptionChangeLog_HghPrunePoint(self):
        """
        Increase the prune point, and confirm now no pruning
        """
        _changeLog = copy.copy(PR_CHANGE_LOG_TO_PRUNE)

        PrescriptionsChangeLogProcessor.pruneChangeLog(_changeLog, 180)
        self.assertDictEqual(_changeLog, PR_CHANGE_LOG_TO_PRUNE)

    def testUnprunableChangeLog(self):
        """
        Make the change log unprunable below the prune point
        """
        _changeLog = copy.copy(PR_CHANGE_LOG_TO_PRUNE)
        for scn in range(100, 200):
            _changeLog["GUID" + str(scn)] = {"SCN": scn, "interactionID": "PORX_IN090101UK09"}

        with self.assertRaises(EpsSystemError):
            PrescriptionsChangeLogProcessor.pruneChangeLog(_changeLog, 50)
