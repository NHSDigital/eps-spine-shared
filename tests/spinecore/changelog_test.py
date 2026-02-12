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

    def test_general_log_entry_empty(self):
        """
        test producing a general log with empty inputs
        """
        log_of_change = ChangeLogProcessor.log_for_general_update(1)
        del log_of_change["Timestamp"]

        expected_log = {}
        expected_log["SCN"] = 1
        expected_log["InternalID"] = None
        expected_log["Source XSLT"] = None
        expected_log["Response Parameters"] = {}
        self.assertEqual(log_of_change, expected_log)

    def test_pruning_of_change_log(self):
        """
        Add a new entry into change log and show it is correctly pruned
        """
        expected_change_log = copy.copy(CHANGE_LOG_TO_PRUNE)
        record = {}
        record["changeLog"] = copy.copy(CHANGE_LOG_TO_PRUNE)

        new_log = {"SCN": 12, "InternalID": "INTERNALID"}
        new_record = ChangeLogProcessor.update_change_log(record, new_log, "GUID9", 6)
        new_change_log = new_record["changeLog"]

        del expected_change_log["GUID1"]
        del expected_change_log["GUID2"]
        del expected_change_log["GUID3"]
        del expected_change_log["GUID5"]
        expected_change_log["GUID9"] = new_log

        self.assertDictEqual(new_change_log, expected_change_log)

    def test_not_pruning_of_change_log(self):
        """
        Add a new entry into change log and show that when DO_NOT_PRUNE is used it does not prune
        """
        expected_change_log = copy.copy(CHANGE_LOG_TO_PRUNE)
        record = {}
        record["changeLog"] = copy.copy(CHANGE_LOG_TO_PRUNE)

        new_log = {"SCN": 12, "InternalID": "INTERNALID"}
        new_record = ChangeLogProcessor.update_change_log(
            record, new_log, "GUID9", ChangeLogProcessor.DO_NOT_PRUNE
        )
        new_change_log = new_record["changeLog"]

        expected_change_log["GUID9"] = new_log

        self.assertDictEqual(new_change_log, expected_change_log)

    def test_highest_scn(self):
        """
        test highest guid and scn returned
        """
        (guid, scn) = ChangeLogProcessor.get_highest_scn(CHANGE_LOG_TO_PRUNE)
        self.assertEqual(guid, "GUID8")
        self.assertEqual(scn, 10)

        record = {}
        record["changeLog"] = copy.copy(CHANGE_LOG_TO_PRUNE)

        new_log = {"SCN": 12, "InternalID": "INTERNALID"}
        new_record = ChangeLogProcessor.update_change_log(record, new_log, "GUID9", 6)
        new_change_log = new_record["changeLog"]

        (guid, scn) = ChangeLogProcessor.get_highest_scn(new_change_log)
        self.assertEqual(guid, "GUID9")
        self.assertEqual(scn, 12)

    def test_get_scn(self):
        """
        test return of SCN from changeLog entry
        """
        change_log_entry = {"SCN": 1}
        scn = ChangeLogProcessor.get_scn(change_log_entry)
        self.assertEqual(scn, 1)

        change_log_entry = {"SCN": "1"}
        scn = ChangeLogProcessor.get_scn(change_log_entry)
        self.assertEqual(scn, 1)

        change_log_entry = {}
        scn = ChangeLogProcessor.get_scn(change_log_entry)
        self.assertEqual(scn, ChangeLogProcessor.INVALID_SCN)

        change_log_entry = {"SCN": sys.maxsize}
        scn = ChangeLogProcessor.get_scn(change_log_entry)
        self.assertEqual(scn, sys.maxsize)

    def test_list_scns(self):
        """
        test the return of the list of SCNs present in a changeLog
        """
        change_log = {"ABCD": {"SCN": 1}, "EFGH": {"SCN": 2}, "IJKL": {"SCN": 3}}
        scn_list = sorted(ChangeLogProcessor.list_scns(change_log))
        self.assertEqual(scn_list, [1, 2, 3])

        change_log = {}
        scn_list = ChangeLogProcessor.list_scns(change_log)
        scn_list.sort()
        self.assertEqual(scn_list, [])

        change_log = {"ABCD": {}}
        scn_list = ChangeLogProcessor.list_scns(change_log)
        scn_list.sort()
        self.assertEqual(scn_list, [ChangeLogProcessor.INVALID_SCN])

    def test_get_max_scn(self):
        """
        Test retrieval of the highest SCN from changeLog
        """
        change_log = {"ABCD": {"SCN": 1}, "IJKL": {"SCN": 3}, "EFGH": {"SCN": 2}}
        highest_scn = ChangeLogProcessor.get_max_scn(change_log)
        self.assertEqual(highest_scn, 3)

        change_log = {
            "ABCD": {"SCN": 1},
            "EFGH": {"SCN": 2},
            "IJKL": {"SCN": 3},
            "ZZZZ": {"SCN": 3},
        }
        highest_scn = ChangeLogProcessor.get_max_scn(change_log)
        self.assertEqual(highest_scn, 3)

        change_log = {"ABCD": {}}
        highest_scn = ChangeLogProcessor.get_max_scn(change_log)
        self.assertEqual(highest_scn, ChangeLogProcessor.INVALID_SCN)

    def test_get_all_guids_for_scn(self):
        """
        test retrieval of list of GUIDS that are keys for changelog entries which have a particular SCN
        """
        change_log = {
            "ABCD": {"SCN": 1},
            "EFGH": {"SCN": 2},
            "IJKL": {"SCN": 3},
            "ZZZZ": {"SCN": 3},
        }
        guid_list = sorted(ChangeLogProcessor.get_all_guids_for_scn(change_log, 1))
        self.assertEqual(guid_list, ["ABCD"])

        guid_list = ChangeLogProcessor.get_all_guids_for_scn(change_log, 3)
        guid_list.sort()
        self.assertEqual(guid_list, ["IJKL", "ZZZZ"])

        guid_list = ChangeLogProcessor.get_all_guids_for_scn(change_log, "3")
        guid_list.sort()
        self.assertEqual(guid_list, ["IJKL", "ZZZZ"])

        guid_list = ChangeLogProcessor.get_all_guids_for_scn(change_log, "7")
        guid_list.sort()
        self.assertEqual(guid_list, [])

    def test_get_max_scn_guids(self):
        """
        test retrieval of all GUIDS that have the highest SCN in the changeLog entry
        """
        change_log = {"ABCD": {"SCN": 1}, "IJKL": {"SCN": 3}, "EFGH": {"SCN": 2}}
        guid_list = sorted(ChangeLogProcessor.get_max_scn_guids(change_log))
        self.assertEqual(guid_list, ["IJKL"])

        change_log = {
            "ABCD": {"SCN": 1},
            "EFGH": {"SCN": 2},
            "IJKL": {"SCN": 3},
            "ZZZZ": {"SCN": 3},
        }
        guid_list = ChangeLogProcessor.get_max_scn_guids(change_log)
        guid_list.sort()
        self.assertEqual(guid_list, ["IJKL", "ZZZZ"])

        change_log = {"ABCD": {}, "EFGH": {}}
        guid_list = ChangeLogProcessor.get_max_scn_guids(change_log)
        guid_list.sort()
        self.assertEqual(guid_list, ["ABCD", "EFGH"])

        change_log = {"ABCD": {}, "EFGH": {}, "IJKL": {"SCN": 3}}
        guid_list = ChangeLogProcessor.get_max_scn_guids(change_log)
        guid_list.sort()
        self.assertEqual(guid_list, ["IJKL"])

        change_log = {}
        guid_list = ChangeLogProcessor.get_max_scn_guids(change_log)
        self.assertEqual(guid_list, [])

    def test_get_all_guids(self):
        """
        test getting the list of all GUID keys for a changeLog
        """
        change_log = {
            "ABCD": {"SCN": 1},
            "EFGH": {"SCN": 2},
            "IJKL": {"SCN": 3},
            "ZZZZ": {"SCN": 3},
        }
        guid_list = sorted(ChangeLogProcessor.get_all_guids(change_log))
        self.assertEqual(guid_list, ["ABCD", "EFGH", "IJKL", "ZZZZ"])

        change_log = {"ABCD": {}, "EFGH": {}}
        guid_list = ChangeLogProcessor.get_all_guids(change_log)
        guid_list.sort()
        self.assertEqual(guid_list, ["ABCD", "EFGH"])

        change_log = {}
        guid_list = ChangeLogProcessor.get_all_guids(change_log)
        self.assertEqual(guid_list, [])

    def test_setting_initial_change_log_on_data_migration(self):
        """
        Set an initial change log onto a record which does not have one
        """
        record = {}
        internal_id = "INTERNALID"
        reason_guid = "DataMigration"
        ChangeLogProcessor.set_initial_change_log(record, internal_id, reason_guid)

        change_log = record[ChangeLogProcessor.RECORD_CHANGELOG_REF]
        del change_log["DataMigration"]["Timestamp"]

        self.assertDictEqual(
            change_log,
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

    def test_prune_prescription_change_log(self):
        """
        Prune the record as expected
        """
        change_log = copy.copy(PR_CHANGE_LOG_TO_PRUNE)

        PrescriptionsChangeLogProcessor.prune_change_log(change_log, 80)

        present_guids = [
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

        for guid in present_guids:
            self.assertIn(guid, list(change_log.keys()))

        self.assertEqual(len(present_guids), len(list(change_log.keys())))

    def test_prune_prescription_change_log_high_prune_point(self):
        """
        Increase the prune point, and confirm now no pruning
        """
        change_log = copy.copy(PR_CHANGE_LOG_TO_PRUNE)
        PrescriptionsChangeLogProcessor.prune_change_log(change_log, 180)
        self.assertDictEqual(change_log, PR_CHANGE_LOG_TO_PRUNE)

    def test_unprunable_change_log(self):
        """
        Make the change log unprunable below the prune point
        """
        change_log = copy.copy(PR_CHANGE_LOG_TO_PRUNE)
        for scn in range(100, 200):
            change_log["GUID" + str(scn)] = {"SCN": scn, "interactionID": "PORX_IN090101UK09"}

        with self.assertRaises(EpsSystemError):
            PrescriptionsChangeLogProcessor.prune_change_log(change_log, 50)
