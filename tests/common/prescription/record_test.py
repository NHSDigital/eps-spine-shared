import json
import os.path
from datetime import datetime, timedelta
from unittest.case import TestCase
from unittest.mock import MagicMock, Mock

from eps_spine_shared.common.prescription.record import PrescriptionRecord
from eps_spine_shared.common.prescription.repeat_dispense import RepeatDispenseRecord
from eps_spine_shared.common.prescription.repeat_prescribe import RepeatPrescribeRecord
from eps_spine_shared.common.prescription.single_prescribe import SinglePrescribeRecord
from eps_spine_shared.common.prescription.types import PrescriptionTreatmentType
from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.nhsfundamentals.timeutilities import TimeFormats
from tests.mock_logger import MockLogObject


def loadTestExampleJson(mock_log_object, filename):
    """
    Load prescription data from JSON files in the test resources directory.

    :type filename: str
    :rtype: PrescriptionRecord
    """
    # load the JSON dict
    testDirPath = os.path.dirname(__file__)
    fullPath = os.path.join(testDirPath, "resources", filename)
    with open(fullPath) as jsonFile:
        prescriptionDict = json.load(jsonFile)
        jsonFile.close()

    # wrap it in a PrescriptionRecord - need to create the
    # appropriate subclass based on treatment type
    treatmentType = prescriptionDict["prescription"]["prescriptionTreatmentType"]
    if treatmentType == PrescriptionTreatmentType.ACUTE_PRESCRIBING:
        prescription = SinglePrescribeRecord(mock_log_object, "test")
    elif treatmentType == PrescriptionTreatmentType.REPEAT_PRESCRIBING:
        prescription = RepeatPrescribeRecord(mock_log_object, "test")
    elif treatmentType == PrescriptionTreatmentType.REPEAT_DISPENSING:
        prescription = RepeatDispenseRecord(mock_log_object, "test")
    else:
        raise ValueError("Unknown treatment type %s" % str(treatmentType))

    prescription.create_record_from_store(prescriptionDict)

    return prescription


class MockInteractionWorker(object):
    """
    Mock interaction worker
    """

    def __init__(self):
        mock = Mock()
        attrs = {"writeLog.return_value": None}
        mock.configure_mock(**attrs)
        self.logObject = mock

        self.servicesDict = {"Style Sheets": None}


class PrescriptionRecordTest(TestCase):
    """
    Test Case for PrescriptionRecord class
    """

    def setUp(self):
        self.mock_log_object = MagicMock()

    def testBasicProperties(self):
        """
        Test basic property access of a record loaded from JSON
        """
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")

        self.assertEqual(prescription.id, "7D9625-Z72BF2-11E3AC")
        self.assertEqual(prescription.max_repeats, 3)

    def test_current_issue(self):
        """
        Test that we can access the current issue
        """
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")

        self.assertEqual(prescription.current_issue_number, 3)
        self.assertEqual(prescription.current_issue.number, 3)
        self.assertEqual(prescription.current_issue.status, "0006")

        # try changing the current issue number and make sure that this is picked up
        prescription.current_issue_number = 1
        self.assertEqual(prescription.current_issue_number, 1)
        self.assertEqual(prescription.current_issue.number, 1)
        self.assertEqual(prescription.current_issue.status, "0009")

    def testIssues(self):
        """
        Test that we can access the prescription issues
        """
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")

        self.assertEqual(prescription.issueNumbers, [1, 2, 3])

        issues = prescription.issues
        self.assertEqual(len(issues), 3)

        issueNumbers = [issue.number for issue in issues]
        self.assertEqual(issueNumbers, [1, 2, 3])

    def testClaims(self):
        """
        Test that we can access the prescription issue claims
        """
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")

        issue = prescription.getIssue(1)
        claim = issue.claim

        self.assertEqual(claim.received_date_str, "20140408")

        # make sure we can also update the received date
        claim.received_date_str = "20131225"
        self.assertEqual(claim.received_date_str, "20131225")

    def testFindNextFutureIssueNumber_futureIssueAvailable(self):
        """
        Test that a future issue can be found in a prescription.
        """
        prescription = loadTestExampleJson(self.mock_log_object, "DD0180-ZBED5C-11E3A.json")

        # check the future issue can be found
        self.assertEqual(prescription._find_next_future_issue_number("1"), "2")

        # check that there are no more beyond the last issue
        self.assertEqual(prescription.max_repeats, 2)
        self.assertEqual(prescription._find_next_future_issue_number("2"), None)

    def testFindNextFutureIssueNumber_issuesAlreadyDispensed(self):
        """
        Test that no future issues can be found if they're all dispensed.
        """
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")

        # chekc that dispensed issues can not be found
        self.assertEqual(prescription._find_next_future_issue_number("1"), None)
        self.assertEqual(prescription._find_next_future_issue_number("2"), None)

        # check that there are no more beyond the last issue
        self.assertEqual(prescription.max_repeats, 3)
        self.assertEqual(prescription._find_next_future_issue_number("3"), None)

    def testGetIssueNumbersInRange(self):
        """
        Test that we can correctly retrieve ranges of issue numbers.
        """
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")

        self.assertEqual(prescription.issueNumbers, [1, 2, 3])

        # test lower bound only
        self.assertEqual(prescription.getIssueNumbersInRange(0, None), [1, 2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(1, None), [1, 2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(2, None), [2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(3, None), [3])
        self.assertEqual(prescription.getIssueNumbersInRange(4, None), [])

        # test upper bound only
        self.assertEqual(prescription.getIssueNumbersInRange(None, 4), [1, 2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(None, 3), [1, 2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(None, 2), [1, 2])
        self.assertEqual(prescription.getIssueNumbersInRange(None, 1), [1])
        self.assertEqual(prescription.getIssueNumbersInRange(None, 0), [])

        # test both bounds
        self.assertEqual(prescription.getIssueNumbersInRange(0, 4), [1, 2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(1, 3), [1, 2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(2, 3), [2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(2, 2), [2])
        self.assertEqual(prescription.getIssueNumbersInRange(2, 1), [])

        # test no bounds
        self.assertEqual(prescription.getIssueNumbersInRange(None, None), [1, 2, 3])
        self.assertEqual(prescription.getIssueNumbersInRange(), [1, 2, 3])

    def test_missing_issue_numbers(self):
        """
        Test that we can deal correctly with prescriptions with missing instances.
        """
        # this 12-issue prescription has issues 1 and 2 missing because of migration
        prescription = loadTestExampleJson(self.mock_log_object, "50EE48-B83002-490F7.json")

        self.assertEqual(prescription.issueNumbers, [3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
        self.assertEqual(prescription.missing_issue_numbers, [1, 2])

        # make sure the range fetches work as well
        self.assertEqual(
            prescription.getIssueNumbersInRange(None, None), [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        )
        self.assertEqual(
            prescription.getIssueNumbersInRange(2, None), [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        )
        self.assertEqual(
            prescription.getIssueNumbersInRange(3, None), [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        )
        self.assertEqual(
            prescription.getIssueNumbersInRange(4, None), [4, 5, 6, 7, 8, 9, 10, 11, 12]
        )
        self.assertEqual(
            prescription.getIssueNumbersInRange(None, 13), [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        )
        self.assertEqual(
            prescription.getIssueNumbersInRange(None, 12), [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        )
        self.assertEqual(
            prescription.getIssueNumbersInRange(None, 11), [3, 4, 5, 6, 7, 8, 9, 10, 11]
        )
        self.assertEqual(prescription.getIssueNumbersInRange(5, 8), [5, 6, 7, 8])
        self.assertEqual(prescription.getIssueNumbersInRange(10, 7), [])

    def _assert_find_instances_to_action_update(
        self, prescription, handleTime, action, expectedIssueNumberStrs
    ):
        """
        Helper to test that find_instances_to_action_update() returns expected instances
        """
        mockContext = MagicMock()
        mockContext.handleTime = handleTime
        mockContext.instancesToUpdate = None
        prescription.find_instances_to_action_update(mockContext, action)
        self.assertEqual(mockContext.instancesToUpdate, expectedIssueNumberStrs)

    def test_find_instances_to_action_update(self):
        """
        Test that we can find instances that need updating at a particular time.
        """
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")

        # first, try a date that will pick up all next actions
        handleTime = datetime(year=2050, month=1, day=1)

        action = PrescriptionRecord.NEXTACTIVITY_DELETE
        self._assert_find_instances_to_action_update(prescription, handleTime, action, ["1"])

        action = PrescriptionRecord.NEXTACTIVITY_CREATENOCLAIM
        self._assert_find_instances_to_action_update(prescription, handleTime, action, ["2", "3"])

        action = PrescriptionRecord.NEXTACTIVITY_EXPIRE
        self._assert_find_instances_to_action_update(prescription, handleTime, action, None)

        # then try a date in the past that won't pick up actions
        handleTime = datetime(year=2010, month=1, day=1)
        action = PrescriptionRecord.NEXTACTIVITY_CREATENOCLAIM
        self._assert_find_instances_to_action_update(prescription, handleTime, action, None)

        # first, try a date that will pick up all next actions
        handleTime = datetime(year=2050, month=1, day=1)
        # same as above json but with nextActivityNAD_bin and instance 1 nextActivity set to purge
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3B.json")
        action = PrescriptionRecord.NEXTACTIVITY_PURGE
        self._assert_find_instances_to_action_update(prescription, handleTime, action, ["1"])

    def test_find_instances_to_action_update_missingInstances(self):
        """
        SPII-10492 - Test that we can find instances that need updating in a migrated
        prescription with missing instances.
        """
        # this 12-issue prescription has issues 1 and 2 missing because of migration
        prescription = loadTestExampleJson(self.mock_log_object, "50EE48-B83002-490F7.json")

        # first, try a date that will pick up all next actions
        handleTime = datetime(year=2050, month=1, day=1)

        action = PrescriptionRecord.NEXTACTIVITY_DELETE
        self._assert_find_instances_to_action_update(prescription, handleTime, action, ["3"])

        action = PrescriptionRecord.NEXTACTIVITY_EXPIRE
        self._assert_find_instances_to_action_update(
            prescription, handleTime, action, ["5", "6", "7", "8", "9", "10", "11", "12"]
        )

    def test_reset_current_instance(self):
        """
        Test that resetting the current instance chooses the correct instance.
        """

        prescription = loadTestExampleJson(self.mock_log_object, "50EE48-B83002-490F7.json")
        self.assertEqual(prescription.current_issue_number, 4)
        (old, new) = prescription.reset_current_instance()
        self.assertEqual((old, new), (4, 4))
        self.assertEqual(prescription.current_issue_number, 4)

        prescription = loadTestExampleJson(self.mock_log_object, "DD0180-ZBED5C-11E3A.json")
        self.assertEqual(prescription.current_issue_number, 1)
        (old, new) = prescription.reset_current_instance()
        self.assertEqual((old, new), (1, 1))
        self.assertEqual(prescription.current_issue_number, 1)

        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")
        self.assertEqual(prescription.current_issue_number, 3)
        (old, new) = prescription.reset_current_instance()
        self.assertEqual((old, new), (3, 3))
        self.assertEqual(prescription.current_issue_number, 3)

    def test_handle_overdue_expiryNone(self):
        """
        SPII-31379 due to old prescrptions the NAD index is set to None
        """
        nad = [None]
        self.assertFalse(PrescriptionRecord._is_expiry_overdue(nad))

    def test_handle_overdue_expiryEmpty(self):
        """
        SPII-31379 due to old prescrptions the NAD index is empty
        """
        nad = []
        self.assertFalse(PrescriptionRecord._is_expiry_overdue(nad))

    def test_handle_overdue_expiryNotExpired(self):
        """
        Expiry is set to tomorrow
        """
        nad = [
            "expire:{}".format(
                (datetime.now() + timedelta(days=1)).strftime(TimeFormats.STANDARD_DATE_FORMAT)
            )
        ]
        self.assertFalse(PrescriptionRecord._is_expiry_overdue(nad))

    def test_handle_overdue_expiryExpired(self):
        """
        Expiry is set to yesterday
        """
        nad = [
            "expire:{}".format(
                (datetime.now() - timedelta(days=1)).strftime(TimeFormats.STANDARD_DATE_FORMAT)
            )
        ]
        self.assertTrue(PrescriptionRecord._is_expiry_overdue(nad))

    def testGetLineItemCancellations(self):
        """
        Test that we can get the line item cancellations for a prescription
        """
        prescription = loadTestExampleJson(self.mock_log_object, "23C1BC-Z75FB1-11EE84.json")
        current_issue = prescription.current_issue

        cancelledLineItemID = "02ED7776-21CD-4E7B-AC9D-D1DBFEE7B8CF"
        cancellations = current_issue.get_line_item_cancellations(cancelledLineItemID)
        self.assertEqual(len(cancellations), 1)

        notCancelledLineItemID = "45D5FB11-D793-4D51-9ADD-95E0F54D2786"
        cancellations = current_issue.get_line_item_cancellations(notCancelledLineItemID)
        self.assertEqual(len(cancellations), 0)

    def testGetLineItemFirstCancellationTime(self):
        prescription = loadTestExampleJson(self.mock_log_object, "23C1BC-Z75FB1-11EE84.json")
        current_issue = prescription.current_issue

        cancelledLineItemID = "02ED7776-21CD-4E7B-AC9D-D1DBFEE7B8CF"
        firstCancellationTime = current_issue.get_line_item_first_cancellation_time(
            cancelledLineItemID
        )
        self.assertEqual(firstCancellationTime, "20240415101553")

        notCancelledLineItemID = "45D5FB11-D793-4D51-9ADD-95E0F54D2786"
        firstCancellationTime = current_issue.get_line_item_first_cancellation_time(
            notCancelledLineItemID
        )
        self.assertEqual(firstCancellationTime, None)

    def testSetInitialPrescriptionStatusActivePrescription(self):
        """
        Test that a prescription with a start date of today or earlier is marked as TO_BE_DISPENSED.
        """
        prescription = loadTestExampleJson(self.mock_log_object, "7D9625-Z72BF2-11E3A.json")

        current_time = datetime.now()
        prescription.set_initial_prescription_status(current_time)

        self.assertEqual(prescription.getIssue(1).status, "0001")

    def testSetInitialPrescriptionStatusFutureDated(self):
        """
        Test that a prescription with a future start date is marked as FUTURE_DATED_PRESCRIPTION.
        """

        prescription = loadTestExampleJson(self.mock_log_object, "0DA698-A83008-F50593.json")

        future_time = datetime.now() + timedelta(days=10)
        prescription.set_initial_prescription_status(future_time)

        self.assertEqual(prescription.getIssue(1).status, "9001")


class PrescriptionRecordChangeLogTest(TestCase):
    """
    For testing aspects of the change log in the prescription record.
    """

    def setUp(self):
        self.logObject = MockLogObject()
        self.mockRecord = PrescriptionRecord(self.logObject, "test")

    def testErrorLogChangeLogTooBig(self):
        """
        When a change log cannot be pruned small enough an error is raised.
        """
        self.mockRecord.prescriptionRecord = {
            "prescription": {self.mockRecord.FIELD_PRESCRIPTION_ID: "testID"},
            "SCN": 10,
            "changeLog": {
                "438eb94f-9da7-46ca-ba2a-72c4f83b2a06": {"SCN": 10},
                "438eb94f-9da7-46ca-ba2a-72c4f83b2a46": {"SCN": 10},
            },
        }
        self.mockRecord.SCN_MAX = 1
        self.assertRaises(
            EpsSystemError,
            self.mockRecord.add_event_to_change_log,
            "ce6c4a39-e239-44c5-81e2-adf3612a7391",
            {},
        )
        self.assertTrue(self.logObject.wasLogged("EPS0336"))
        self.assertTrue(self.logObject.wasValueLogged("EPS0336", "prescriptionID", "testID"))
