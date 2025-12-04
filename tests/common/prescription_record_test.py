import json
import os.path
from datetime import datetime, timedelta
from unittest.case import TestCase
from unittest.mock import MagicMock, Mock

from dateutil.relativedelta import relativedelta

from eps_spine_shared.common.prescription_record import (
    NextActivityGenerator,
    PrescriptionRecord,
    PrescriptionTreatmentType,
    RepeatDispenseRecord,
    RepeatPrescribeRecord,
    SinglePrescribeRecord,
)
from eps_spine_shared.errors import EpsSystemError
from eps_spine_shared.nhsfundamentals.timeutilities import TimeFormats
from tests.mock_logger import MockLogObject


def loadTestExampleJson(mockLogObject, filename):
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
        prescription = SinglePrescribeRecord(mockLogObject, "test")
    elif treatmentType == PrescriptionTreatmentType.REPEAT_PRESCRIBING:
        prescription = RepeatPrescribeRecord(mockLogObject, "test")
    elif treatmentType == PrescriptionTreatmentType.REPEAT_DISPENSING:
        prescription = RepeatDispenseRecord(mockLogObject, "test")
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


class ReturnChangedIssueListTest(TestCase):
    """
    Returns the list of changed issues.
    """

    def setUp(self):
        """
        Set up all valid values - tests will overwrite these where required.
        """

        mock = Mock()
        attrs = {"writeLog.return_value": None}
        mock.configure_mock(**attrs)
        logObject = mock
        internalID = "test"

        self.mockRecord = RepeatDispenseRecord(logObject, internalID)
        self.preChangeDict = {
            "issue1": {"lineItems": {"1": "0001", "2": "0001"}, "prescription": "0006"},
            "issue2": {"lineItems": {"1": "0008", "2": "0008"}, "prescription": "0002"},
            "issue3": {"lineItems": {"1": "0007", "2": "0007"}, "prescription": "9000"},
        }
        self.postChangeDict = {
            "issue1": {"lineItems": {"1": "0001", "2": "0001"}, "prescription": "0006"},
            "issue2": {"lineItems": {"1": "0008", "2": "0008"}, "prescription": "0002"},
            "issue3": {"lineItems": {"1": "0007", "2": "0007"}, "prescription": "9000"},
        }
        self.maxRepeats = 3
        self.expectedResult = None

    def runReturnChangedIssueListTest(self):
        """
        Execute the test
        """
        resultSet = self.mockRecord.return_changed_issue_list(
            self.preChangeDict, self.postChangeDict, self.maxRepeats
        )
        self.assertEqual(resultSet, self.expectedResult)

    def testIdenticalDicts(self):
        """
        No difference in content
        """
        self.expectedResult = []
        self.runReturnChangedIssueListTest()

    def testIdenticalDictsOutOfOrder(self):
        """
        Out of order elements, but key:value pairs unchanged
        """
        self.postChangeDict = {
            "issue1": {"lineItems": {"1": "0001", "2": "0001"}, "prescription": "0006"},
            "issue3": {"prescription": "9000", "lineItems": {"2": "0007", "1": "0007"}},
            "issue2": {"lineItems": {"2": "0008", "1": "0008"}, "prescription": "0002"},
        }
        self.expectedResult = []
        self.runReturnChangedIssueListTest()

    def testMissingIssueFromPreChangeDict(self):
        """
        Issue missing from pre change dict
        """
        del self.preChangeDict["issue2"]
        self.expectedResult = ["2"]
        self.runReturnChangedIssueListTest()

    def testMissingIssueFromPostChangeDict(self):
        """
        Issue missing from pre change dict
        """
        del self.postChangeDict["issue2"]
        self.expectedResult = ["2"]
        self.runReturnChangedIssueListTest()

    def testSingleItemStatusChange(self):
        """
        Test that a single line item difference is identified
        """
        self.postChangeDict["issue1"]["lineItems"]["1"] = "0002"
        self.expectedResult = ["1"]
        self.runReturnChangedIssueListTest()

    def testSinglePrescriptionStatusChange(self):
        """
        Test that a single prescription difference is identified
        """
        self.postChangeDict["issue1"]["prescription"] = "0007"
        self.expectedResult = ["1"]
        self.runReturnChangedIssueListTest()

    def testMultipleCombinationStatusChange(self):
        """
        Test that a multiple line item and prescription differences are identified
        """
        self.postChangeDict["issue1"]["lineItems"]["1"] = "0002"
        self.postChangeDict["issue1"]["lineItems"]["2"] = "0003"
        self.postChangeDict["issue3"]["prescription"] = "0006"
        self.postChangeDict["issue3"]["prescription"] = "0007"
        self.expectedResult = ["1", "3"]
        self.runReturnChangedIssueListTest()


class IncludeNextActivityForInstanceTest(TestCase):
    """
    Test Case for testing the Include Next Activity for Instance Test
    """

    def setUp(self):
        """
        Set up all valid values - tests will overwrite these where required.
        """

        mock = Mock()
        attrs = {"writeLog.return_value": None}
        mock.configure_mock(**attrs)
        logObject = mock
        internalID = "test"

        self.mockRecord = PrescriptionRecord(logObject, internalID)

    def testincludeNextActivity_1(self):
        """
        Test that 'True' is returned for acute, current, first and final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 1,
         - nextActivity = expire
        """
        _activity = self.mockRecord.NEXTACTIVITY_EXPIRE
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 1))

    def testincludeNextActivity_2(self):
        """
        Test that 'True' is returned for acute, current, first and final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 1,
         - nextActivity = createNoClaim
        """
        _activity = self.mockRecord.NEXTACTIVITY_CREATENOCLAIM
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 1))

    def testincludeNextActivity_3(self):
        """
        Test that 'True' is returned for acute, current, first and final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 1,
         - nextActivity = ready
        """
        _activity = self.mockRecord.NEXTACTIVITY_READY
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 1))

    def testincludeNextActivity_4(self):
        """
        Test that 'True' is returned for acute, current, first and final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 1,
         - nextActivity = delete
        """
        _activity = self.mockRecord.NEXTACTIVITY_DELETE
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 1))

    def testincludeNextActivity_5(self):
        """
        Test that 'True' is returned for repeat dispense, current and first issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = expire
        """
        _activity = self.mockRecord.NEXTACTIVITY_EXPIRE
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 3))

    def testincludeNextActivity_6(self):
        """
        Test that 'True' is returned for repeat dispense, current but not final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = createNoClaim
        """
        _activity = self.mockRecord.NEXTACTIVITY_CREATENOCLAIM
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 3))

    def testincludeNextActivity_7(self):
        """
        Test that 'True' is returned for repeat dispense, current but not final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = ready
        """
        _activity = self.mockRecord.NEXTACTIVITY_READY
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 3))

    def testincludeNextActivity_8(self):
        """
        Test that 'False' is returned for repeat dispense, current but not final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = delete
        """
        _activity = self.mockRecord.NEXTACTIVITY_DELETE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 3))

    def testincludeNextActivity_9(self):
        """
        Test that 'False' is returned for repeat dispense, previous issue when:
         - currentInstance = 2,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = expire
        """
        _activity = self.mockRecord.NEXTACTIVITY_EXPIRE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 1, 2, 3))

    def testincludeNextActivity_10(self):
        """
        Test that 'True' is returned for repeat dispense, previous issue when:
         - currentInstance = 2,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = createNoClaim
        """
        _activity = self.mockRecord.NEXTACTIVITY_CREATENOCLAIM
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 2, 3))

    def testincludeNextActivity_11(self):
        """
        Test that 'False' is returned for repeat dispense, previous issue when:
         - currentInstance = 2,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = ready
        """
        _activity = self.mockRecord.NEXTACTIVITY_READY
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 1, 2, 3))

    def testincludeNextActivity_12(self):
        """
        Test that 'False' is returned for repeat dispense, previous issue when:
         - currentInstance = 2,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = delete
        """
        _activity = self.mockRecord.NEXTACTIVITY_DELETE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 1, 2, 3))

    def testincludeNextActivity_13(self):
        """
        Test that 'True' is returned for repeat dispense, current but not first or final issue when:
         - currentInstance = 2,
         - instanceNumber = 2,
         - maxRepeats = 3,
         - nextActivity = expire
        """
        _activity = self.mockRecord.NEXTACTIVITY_EXPIRE
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 2, 2, 3))

    def testincludeNextActivity_14(self):
        """
        Test that 'True' is returned for repeat dispense, current but not first or final issue when:
         - currentInstance = 2,
         - instanceNumber = 2,
         - maxRepeats = 3,
         - nextActivity = createNoClaim
        """
        _activity = self.mockRecord.NEXTACTIVITY_CREATENOCLAIM
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 2, 2, 3))

    def testincludeNextActivity_15(self):
        """
        Test that 'True' is returned for repeat dispense, current but not first or final issue when:
         - currentInstance = 2,
         - instanceNumber = 2,
         - maxRepeats = 3,
         - nextActivity = ready
        """
        _activity = self.mockRecord.NEXTACTIVITY_READY
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 2, 2, 3))

    def testincludeNextActivity_16(self):
        """
        Test that 'False' is returned for repeat dispense, current but not first or final issue when:
         - currentInstance = 2,
         - instanceNumber = 2,
         - maxRepeats = 3,
         - nextActivity = delete
        """
        _activity = self.mockRecord.NEXTACTIVITY_DELETE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 2, 2, 3))

    def testincludeNextActivity_17(self):
        """
        Test that 'True' is returned for repeat dispense, current and final issue when:
         - currentInstance = 3,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = expire
        """
        _activity = self.mockRecord.NEXTACTIVITY_EXPIRE
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 3, 3, 3))

    def testincludeNextActivity_18(self):
        """
        Test that 'True' is returned for repeat dispense, current and final issue when:
         - currentInstance = 3,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = createNoClaim
        """
        _activity = self.mockRecord.NEXTACTIVITY_CREATENOCLAIM
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 3, 3, 3))

    def testincludeNextActivity_19(self):
        """
        Test that 'True' is returned for repeat dispense, current and final issue when:
         - currentInstance = 3,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = ready
        """
        _activity = self.mockRecord.NEXTACTIVITY_READY
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 3, 3, 3))

    def testincludeNextActivity_20(self):
        """
        Test that 'True' is returned for repeat dispense, current and final issue when:
         - currentInstance = 3,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = delete
        """
        _activity = self.mockRecord.NEXTACTIVITY_DELETE
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 3, 3, 3))

    def testincludeNextActivity_21(self):
        """
        Test that 'False' is returned for repeat dispense, future issue when:
         - currentInstance = 1,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = expire
        """
        _activity = self.mockRecord.NEXTACTIVITY_EXPIRE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 3, 1, 3))

    def testincludeNextActivity_22(self):
        """
        Test that 'False' is returned for repeat dispense, future issue when:
         - currentInstance = 1,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = createNoClaim
        """
        _activity = self.mockRecord.NEXTACTIVITY_CREATENOCLAIM
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 3, 1, 3))

    def testincludeNextActivity_23(self):
        """
        Test that 'False' is returned for repeat dispense, future issue when:
         - currentInstance = 1,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = ready
        """
        _activity = self.mockRecord.NEXTACTIVITY_READY
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 3, 1, 3))

    def testincludeNextActivity_24(self):
        """
        Test that 'False' is returned for repeat dispense, future issue when:
         - currentInstance = 1,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = delete
        """
        _activity = self.mockRecord.NEXTACTIVITY_DELETE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 3, 1, 3))

    def testincludeNextActivity_25(self):
        """
        Test that 'True' is returned for acute, curent, first and final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 1,
         - nextActivity = purge
        """
        _activity = self.mockRecord.NEXTACTIVITY_PURGE
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 1))

    def testincludeNextActivity_26(self):
        """
        Test that 'False' is returned for repeat dispense, current but not final issue when:
         - currentInstance = 1,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = purge
        """
        _activity = self.mockRecord.NEXTACTIVITY_PURGE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 1, 1, 3))

    def testincludeNextActivity_27(self):
        """
        Test that 'False' is returned for repeat dispense, previous issue when:
         - currentInstance = 2,
         - instanceNumber = 1,
         - maxRepeats = 3,
         - nextActivity = purge
        """
        _activity = self.mockRecord.NEXTACTIVITY_PURGE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 1, 2, 3))

    def testincludeNextActivity_28(self):
        """
        Test that 'False' is returned for repeat dispense, current but not first or final issue when:
         - currentInstance = 2,
         - instanceNumber = 2,
         - maxRepeats = 3,
         - nextActivity = purge
        """
        _activity = self.mockRecord.NEXTACTIVITY_PURGE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 2, 2, 3))

    def testincludeNextActivity_29(self):
        """
        Test that 'True' is returned for repeat dispense, current and final issue when:
         - currentInstance = 3,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = purge
        """
        _activity = self.mockRecord.NEXTACTIVITY_PURGE
        self.assertTrue(self.mockRecord._includeNextActivityForInstance(_activity, 3, 3, 3))

    def testincludeNextActivity_30(self):
        """
        Test that 'False' is returned for repeat dispense, future issue when:
         - currentInstance = 1,
         - instanceNumber = 3,
         - maxRepeats = 3,
         - nextActivity = purge
        """
        _activity = self.mockRecord.NEXTACTIVITY_PURGE
        self.assertFalse(self.mockRecord._includeNextActivityForInstance(_activity, 3, 1, 3))


class SetUpNadReferences(TestCase):
    """
    Provides nadReference setUp for child classes
    """

    def setUp(self):
        """
        Set up all valid values - tests will overwrite these where required.
        """
        self.testclass = NextActivityGenerator(None, None)

        self.nadReference = {}
        self.nadReference["prescriptionExpiryPeriod"] = relativedelta(months=+6)
        self.nadReference["repeatDispenseExpiryPeriod"] = relativedelta(months=+12)
        self.nadReference["dataCleansePeriod"] = relativedelta(months=+6)
        self.nadReference["withDispenserActiveExpiryPeriod"] = relativedelta(days=+180)
        self.nadReference["expiredDeletePeriod"] = relativedelta(days=+90)
        self.nadReference["cancelledDeletePeriod"] = relativedelta(days=+180)
        self.nadReference["claimedDeletePeriod"] = relativedelta(days=+9)
        self.nadReference["notDispensedDeletePeriod"] = relativedelta(days=+30)
        self.nadReference["nominatedDownloadDateLeadTime"] = relativedelta(days=+5)
        self.nadReference["notificationDelayPeriod"] = relativedelta(days=+180)
        self.nadReference["purgedDeletePeriod"] = relativedelta(days=+365)

        self.nadStatus = {}
        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionDate"] = "20120101"
        self.nadStatus["prescribingSiteTestStatus"] = True
        self.nadStatus["dispenseWindowHighDate"] = "20121231"
        self.nadStatus["dispenseWindowLowDate"] = "20120101"
        # The nominated download date is the date that the next issue should be released
        # for download (already taking account of the lead time)
        self.nadStatus["nominatedDownloadDate"] = "20120101"
        self.nadStatus["lastDispenseDate"] = "20120101"
        self.nadStatus["completionDate"] = "20120101"
        self.nadStatus["claimSentDate"] = "20120101"
        self.nadStatus["handleTime"] = "20120101"
        self.nadStatus["prescriptionStatus"] = "0001"
        self.nadStatus["instanceNumber"] = 1
        self.nadStatus["releaseVersion"] = "R2"
        self.nadStatus["lastDispenseNotificationMsgRef"] = "20180918150922275520_2FA340_2"


class ReturnNextActivityIndexTest(SetUpNadReferences):
    """
    Test Case for testing the next activity index generator
    """

    def performTestNextActivityDate(self, _expectedResult):
        """
        Test Runner for next activity and next activity date method. Takes the created
        nadStatus (on self) and compares it to the expected result
        """
        _results = self.testclass.nextActivityDate(self.nadStatus, self.nadReference)
        [_nextActivity, _nextActivityDate, _ignore] = _results
        self.assertTrue([_nextActivity, _nextActivityDate] == _expectedResult)

    def testNextActivityDateScenario1(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0001"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.performTestNextActivityDate(["expire", "20120430"])

    def testNextActivityDateScenario2(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0001"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.performTestNextActivityDate(["expire", "20120229"])

    def testNextActivityDateScenario3(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0001"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.performTestNextActivityDate(["expire", "20120430"])

    def testNextActivityDateScenario4(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0001"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.performTestNextActivityDate(["expire", "20120229"])

    def testNextActivityDateScenario5(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0001"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["dispenseWindowHighDate"] = "20120601"
        self.performTestNextActivityDate(["expire", "20120430"])

    def testNextActivityDateScenario6(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - check that expiry is not limited by Dispense Window
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0001"
        self.nadStatus["prescriptionDate"] = "20120131"
        self.nadStatus["dispenseWindowHighDate"] = "20120401"
        self.performTestNextActivityDate(["expire", "20120731"])

    def testNextActivityDateScenario7(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0002"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.performTestNextActivityDate(["expire", "20120229"])

    def testNextActivityDateScenario8(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0002"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.performTestNextActivityDate(["expire", "20120430"])

    def testNextActivityDateScenario9(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0002"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.performTestNextActivityDate(["expire", "20120229"])

    def testNextActivityDateScenario10(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0002"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.performTestNextActivityDate(["expire", "20120430"])

    def testNextActivityDateScenario11(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0002"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.nadStatus["dispenseWindowHighDate"] = "20120601"
        self.performTestNextActivityDate(["expire", "20120229"])

    def testNextActivityDateScenario12(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0002"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["dispenseWindowHighDate"] = "20120601"
        self.performTestNextActivityDate(["expire", "20120430"])

    def testNextActivityDateScenario13(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - check that expiry is not limited by Dispense Window
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0002"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["dispenseWindowHighDate"] = "20120401"
        self.performTestNextActivityDate(["expire", "20120430"])

    def testNextActivityDateScenario14(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.nadStatus["lastDispenseDate"] = "20110928"
        self.performTestNextActivityDate(["createNoClaim", "20120326"])

    def testNextActivityDateScenario14b(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute R1 - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.nadStatus["lastDispenseDate"] = "20110928"
        self.nadStatus["releaseVersion"] = "R1"
        self.performTestNextActivityDate(["expire", "20120229"])

    def testNextActivityDateScenario15(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["lastDispenseDate"] = "20111130"
        self.performTestNextActivityDate(["createNoClaim", "20120528"])

    def testNextActivityDateScenario15b(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute R1 - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["lastDispenseDate"] = "20111130"
        self.nadStatus["releaseVersion"] = "R1"
        self.performTestNextActivityDate(["expire", "20120430"])

    def testNextActivityDateScenario16(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.nadStatus["lastDispenseDate"] = "20110928"
        self.performTestNextActivityDate(["createNoClaim", "20120326"])

    def testNextActivityDateScenario17(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["lastDispenseDate"] = "20111130"
        self.performTestNextActivityDate(["createNoClaim", "20120528"])

    def testNextActivityDateScenario18(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20110829"
        self.nadStatus["dispenseWindowHighDate"] = "20120601"
        self.nadStatus["lastDispenseDate"] = "20110928"
        self.performTestNextActivityDate(["createNoClaim", "20120326"])

    def testNextActivityDateScenario19(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["dispenseWindowHighDate"] = "20120601"
        self.nadStatus["lastDispenseDate"] = "20111130"
        self.performTestNextActivityDate(["createNoClaim", "20120528"])

    def testNextActivityDateScenario20(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - check that expiry date is not limited by Dispense Window
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["dispenseWindowHighDate"] = "20120401"
        self.nadStatus["lastDispenseDate"] = "20120301"
        self.performTestNextActivityDate(["createNoClaim", "20120828"])

    def testNextActivityDateScenario21(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - no claim window falls before expiry
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0003"
        self.nadStatus["prescriptionDate"] = "20111031"
        self.nadStatus["dispenseWindowHighDate"] = "20120601"
        self.nadStatus["lastDispenseDate"] = "20111031"
        self.performTestNextActivityDate(["createNoClaim", "20120428"])

    def testNextActivityDateScenario22(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0004"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120329"
        self.performTestNextActivityDate(["delete", "20120627"])

    def testNextActivityDateScenario23(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0004"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120329"
        self.performTestNextActivityDate(["delete", "20120627"])

    def testNextActivityDateScenario24(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0004"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120329"
        self.performTestNextActivityDate(["delete", "20120627"])

    def testNextActivityDateScenario25(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0005"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120329"
        self.performTestNextActivityDate(["delete", "20120925"])

    def testNextActivityDateScenario25a(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Specific test for migrated data scenario where completionDate is false not a valid
        date.
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0005"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = False
        expectedDate = datetime.now() + relativedelta(days=+180)
        self.performTestNextActivityDate(["delete", expectedDate.strftime("%Y%m%d")])

    def testNextActivityDateScenario26(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0005"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120329"
        self.performTestNextActivityDate(["delete", "20120925"])

    def testNextActivityDateScenario27(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0005"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120329"
        self.performTestNextActivityDate(["delete", "20120925"])

    def testNextActivityDateScenario28(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0006"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["dispenseWindowHighDate"] = "20120728"
        self.nadStatus["lastDispenseDate"] = "20110831"
        self.nadStatus["completionDate"] = "20110831"
        self.performTestNextActivityDate(["createNoClaim", "20120227"])

    def testNextActivityDateScenario28b(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute R1 - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0006"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["dispenseWindowHighDate"] = "20120728"
        self.nadStatus["lastDispenseDate"] = "20110831"
        self.nadStatus["completionDate"] = "20110831"
        self.nadStatus["releaseVersion"] = "R1"
        self.performTestNextActivityDate(["delete", "20120227"])

    def testNextActivityDateScenario29(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 31st -> 1st
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0006"
        self.nadStatus["prescriptionDate"] = "20110331"
        self.nadStatus["dispenseWindowHighDate"] = "20120330"
        self.nadStatus["lastDispenseDate"] = "20110831"
        self.nadStatus["completionDate"] = "20110831"
        self.performTestNextActivityDate(["createNoClaim", "20120227"])

    def testNextActivityDateScenario30(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0006"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["dispenseWindowHighDate"] = "20120728"
        self.nadStatus["lastDispenseDate"] = "20110831"
        self.nadStatus["completionDate"] = "20110831"
        self.performTestNextActivityDate(["createNoClaim", "20120227"])

    def testNextActivityDateScenario31(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0007"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120130"
        self.performTestNextActivityDate(["delete", "20120229"])

    def testNextActivityDateScenario32(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0007"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120130"
        self.performTestNextActivityDate(["delete", "20120229"])

    def testNextActivityDateScenario33(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0007"
        self.nadStatus["prescriptionDate"] = "20110729"
        self.nadStatus["completionDate"] = "20120130"
        self.performTestNextActivityDate(["delete", "20120229"])

    def testNextActivityDateScenario34(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0008"
        self.nadStatus["prescriptionDate"] = "20110731"
        self.nadStatus["completionDate"] = "20111231"
        self.nadStatus["claimSentDate"] = "20120101"
        self.performTestNextActivityDate(["delete", "20120110"])

    def testNextActivityDateScenario37(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Acute - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0001"
        self.nadStatus["prescriptionStatus"] = "0009"
        self.nadStatus["prescriptionDate"] = "20110731"
        self.nadStatus["completionDate"] = "20111231"
        self.nadStatus["claimSentDate"] = "20120101"
        self.performTestNextActivityDate(["delete", "20120110"])

    def testNextActivityDateScenario38(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0009"
        self.nadStatus["prescriptionDate"] = "20110731"
        self.nadStatus["completionDate"] = "20111231"
        self.nadStatus["claimSentDate"] = "20120101"
        self.performTestNextActivityDate(["delete", "20120110"])

    def testNextActivityDateScenario39(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - expiry falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0009"
        self.nadStatus["prescriptionDate"] = "20110731"
        self.nadStatus["completionDate"] = "20111231"
        self.nadStatus["claimSentDate"] = "20120101"
        self.performTestNextActivityDate(["delete", "20120110"])

    def testNextActivityDateScenario40(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - Nominated Release before Expiry
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0000"
        self.nadStatus["prescriptionDate"] = "20120731"
        self.nadStatus["nominatedDownloadDate"] = "20121101"
        self.performTestNextActivityDate(["ready", "20121101"])

    def testNextActivityDateScenario41(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Prescribe - Expiry before Nominated Release
        """

        self.nadStatus["prescriptionTreatmentType"] = "0002"
        self.nadStatus["prescriptionStatus"] = "0000"
        self.nadStatus["prescriptionDate"] = "20110731"
        self.nadStatus["nominatedDownloadDate"] = "20120301"
        self.performTestNextActivityDate(["expire", "20120131"])

    def testNextActivityDateScenario42(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - Nominated Release falls 29th Feb 2012
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0000"
        self.nadStatus["prescriptionDate"] = "20111101"
        self.nadStatus["nominatedDownloadDate"] = "20120229"
        self.performTestNextActivityDate(["ready", "20120229"])

    def testNextActivityDateScenario43(self):
        """
        Unit test for Next Activity and Next Activity Date Generator:
        Repeat Dispense - Expiry falls 30th Sep 2011
        """

        self.nadStatus["prescriptionTreatmentType"] = "0003"
        self.nadStatus["prescriptionStatus"] = "0000"
        self.nadStatus["prescriptionDate"] = "20110331"
        self.nadStatus["nominatedDownloadDate"] = "20120130"
        self.performTestNextActivityDate(["expire", "20110930"])


class BuildIndexesTest(TestCase):
    """
    Test Case for testing that indexes are built correctly
    """

    def setUp(self):
        """
        Set up all valid values - tests will overwrite these where required.
        """

        mock = Mock()
        attrs = {"writeLog.return_value": None}
        mock.configure_mock(**attrs)
        logObject = mock
        internalID = "test"

        self.prescription = PrescriptionRecord(logObject, internalID)
        self.prescription.prescriptionRecord = {}
        self.prescription.prescriptionRecord["prescription"] = {}
        self.prescription.prescriptionRecord["instances"] = {}
        self.prescription.prescriptionRecord["patient"] = {}
        self.prescription.prescriptionRecord["patient"]["nhsNumber"] = "TESTPatient"

    def testAddReleaseAndStatus_String(self):
        """
        tests that release and status are added to the passed in index.
        """
        isString = True
        indexPrefix = "indexPrefix"
        # set prescription to be 37 characters long ie R1
        temp = "0123456789012345678901234567890123456"
        self.prescription.prescriptionRecord["prescription"]["prescriptionID"] = temp
        self.prescription.prescriptionRecord["instances"]["0"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["prescriptionStatus"] = "0001"
        resultSet = self.prescription.addReleaseAndStatus(indexPrefix, isString)
        self.assertEqual(
            resultSet,
            ["indexPrefix|R1|0001"],
            "Failed to create expected release and status suffix",
        )

    def testAddReleaseAndStatus_List(self):
        """
        tests that release and status are added to the passed in index where the passed in index is a list of indexes.
        """
        isString = False
        indexPrefix = ["indexPrefix1", "indexPrefix2"]
        # set prescription to be 37 characters long ie R1
        temp = "0123456789012345678901234567890123456"
        self.prescription.prescriptionRecord["prescription"]["prescriptionID"] = temp
        self.prescription.prescriptionRecord["instances"]["0"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["prescriptionStatus"] = "0001"
        resultSet = self.prescription.addReleaseAndStatus(indexPrefix, isString)
        self.assertEqual(
            resultSet,
            ["indexPrefix1|R1|0001", "indexPrefix2|R1|0001"],
            "Failed to create expected release and status suffix for list of indexes",
        )

    def testAddReleaseAndStatus_StringMultipleStatus(self):
        """
        tests that release and multiple status are added to the passed in index.
        """
        isString = True
        indexPrefix = "indexPrefix"
        # set prescription to be 37 characters long ie R1
        temp = "0123456789012345678901234567890123456"
        self.prescription.prescriptionRecord["prescription"]["prescriptionID"] = temp
        self.prescription.prescriptionRecord["instances"]["0"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["prescriptionStatus"] = "0001"
        self.prescription.prescriptionRecord["instances"]["1"] = {}
        self.prescription.prescriptionRecord["instances"]["1"]["prescriptionStatus"] = "0002"
        resultSet = self.prescription.addReleaseAndStatus(indexPrefix, isString)
        self.assertEqual(
            sorted(resultSet),
            sorted(["indexPrefix|R1|0001", "indexPrefix|R1|0002"]),
            "Failed to create expected release and status suffix",
        )

    def testNhsNumPrescDispIndex(self):
        """
        Given a prescription for a specific NHS Number and Prescriber that has been dispensed
        that the correct index is created
        """
        self.prescription.prescriptionRecord["prescription"][
            "prescribingOrganization"
        ] = "TESTPrescriber"
        self.prescription.prescriptionRecord["prescription"]["prescriptionTime"] = "TESTtime"
        self.prescription.prescriptionRecord["instances"]["0"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["dispense"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["dispense"][
            "dispensingOrganization"
        ] = "TESTdispenser"

        [success, createdIndex] = self.prescription.returnNhsNumberPrescriberDispenserDateIndex()
        self.assertEqual(success, True, "Failed to successfully create index")
        expectedIndex = set(["TESTPatient|TESTPrescriber|TESTdispenser|TESTtime"])
        self.assertEqual(
            createdIndex,
            expectedIndex,
            "Created index " + str(createdIndex) + " expecting " + str(expectedIndex),
        )

    def testNhsNumPrescDispIndex_noDispenser(self):
        """
        Given a prescription for a specific NHS Number and Prescriber that has been dispensed
        that the correct index is created
        """
        self.prescription.prescriptionRecord["prescription"][
            "prescribingOrganization"
        ] = "TESTPrescriber"
        self.prescription.prescriptionRecord["prescription"]["prescriptionTime"] = "TESTtime"

        [success, createdIndex] = self.prescription.returnNhsNumberPrescriberDispenserDateIndex()
        self.assertEqual(success, True, "Failed to successfully create index")
        expectedIndex = set([])
        self.assertEqual(
            createdIndex,
            expectedIndex,
            "Created index " + str(createdIndex) + " expecting " + str(expectedIndex),
        )

    def testPrescDispIndex(self):
        """
        Given a prescription for a specific NHS Number and Prescriber that has been dispensed
        that the correct index is created
        """
        self.prescription.prescriptionRecord["prescription"][
            "prescribingOrganization"
        ] = "TESTPrescriber"
        self.prescription.prescriptionRecord["prescription"]["prescriptionTime"] = "TESTtime"
        self.prescription.prescriptionRecord["instances"]["0"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["dispense"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["dispense"][
            "dispensingOrganization"
        ] = "TESTdispenser"

        [success, createdIndex] = self.prescription.returnPrescriberDispenserDateIndex()
        self.assertEqual(success, True, "Failed to successfully create index")
        expectedIndex = set(["TESTPrescriber|TESTdispenser|TESTtime"])
        self.assertEqual(
            createdIndex,
            expectedIndex,
            "Created index " + str(createdIndex) + " expecting " + str(expectedIndex),
        )

    def testPrescDispIndex_noDispenser(self):
        """
        Given a prescription for a specific NHS Number and Prescriber that has been dispensed
        that the correct index is created
        """
        self.prescription.prescriptionRecord["prescription"][
            "prescribingOrganization"
        ] = "TESTPrescriber"
        self.prescription.prescriptionRecord["prescription"]["prescriptionTime"] = "TESTtime"

        [success, createdIndex] = self.prescription.returnPrescriberDispenserDateIndex()
        self.assertEqual(success, True, "Failed to successfully create index")
        expectedIndex = set([])
        self.assertEqual(
            createdIndex,
            expectedIndex,
            "Created index " + str(createdIndex) + " expecting " + str(expectedIndex),
        )

    def testDispIndex(self):
        """
        Given a prescription for a specific NHS Number and Prescriber that has been dispensed
        that the correct index is created
        """
        self.prescription.prescriptionRecord["prescription"][
            "prescribingOrganization"
        ] = "TESTPrescriber"
        self.prescription.prescriptionRecord["prescription"]["prescriptionTime"] = "TESTtime"
        self.prescription.prescriptionRecord["instances"]["0"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["dispense"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["dispense"][
            "dispensingOrganization"
        ] = "TESTdispenser"

        [success, createdIndex] = self.prescription.returnDispenserDateIndex()
        self.assertEqual(success, True, "Failed to successfully create index")
        expectedIndex = set(["TESTdispenser|TESTtime"])
        self.assertEqual(
            createdIndex,
            expectedIndex,
            "Created index " + str(createdIndex) + " expecting " + str(expectedIndex),
        )

    def testDispIndex_noDispenser(self):
        """
        Given a prescription for a specific NHS Number and Prescriber that has been dispensed
        that the correct index is created
        """
        self.prescription.prescriptionRecord["prescription"][
            "prescribingOrganization"
        ] = "TESTPrescriber"
        self.prescription.prescriptionRecord["prescription"]["prescriptionTime"] = "TESTtime"

        [success, createdIndex] = self.prescription.returnDispenserDateIndex()
        self.assertEqual(success, True, "Failed to successfully create index")
        expectedIndex = set([])
        self.assertEqual(
            createdIndex,
            expectedIndex,
            "Created index " + str(createdIndex) + " expecting " + str(expectedIndex),
        )

    def testNhsNumDispIndex(self):
        """
        Given a prescription for a specific NHS Number and Prescriber that has been dispensed
        that the correct index is created
        """
        self.prescription.prescriptionRecord["prescription"][
            "prescribingOrganization"
        ] = "TESTPrescriber"
        self.prescription.prescriptionRecord["prescription"]["prescriptionTime"] = "TESTtime"
        self.prescription.prescriptionRecord["instances"]["0"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["dispense"] = {}
        self.prescription.prescriptionRecord["instances"]["0"]["dispense"][
            "dispensingOrganization"
        ] = "TESTdispenser"

        [success, createdIndex] = self.prescription.returnNhsNumberDispenserDateIndex()
        self.assertEqual(success, True, "Failed to successfully create index")
        expectedIndex = set(["TESTPatient|TESTdispenser|TESTtime"])
        self.assertEqual(
            createdIndex,
            expectedIndex,
            "Created index " + str(createdIndex) + " expecting " + str(expectedIndex),
        )

    def testNhsNumDispIndex_noDispenser(self):
        """
        Given a prescription for a specific NHS Number and Prescriber that has been dispensed
        that the correct index is created
        """
        self.prescription.prescriptionRecord["prescription"][
            "prescribingOrganization"
        ] = "TESTPrescriber"
        self.prescription.prescriptionRecord["prescription"]["prescriptionTime"] = "TESTtime"

        [success, createdIndex] = self.prescription.returnNhsNumberDispenserDateIndex()
        self.assertEqual(success, True, "Failed to successfully create index")
        expectedIndex = set([])
        self.assertEqual(
            createdIndex,
            expectedIndex,
            "Created index " + str(createdIndex) + " expecting " + str(expectedIndex),
        )


class PrescriptionRecordTest(TestCase):
    """
    Test Case for PrescriptionRecord class
    """

    def setUp(self):
        self.mockLogObject = MagicMock()

    def testBasicProperties(self):
        """
        Test basic property access of a record loaded from JSON
        """
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")

        self.assertEqual(prescription.id, "7D9625-Z72BF2-11E3AC")
        self.assertEqual(prescription.maxRepeats, 3)

    def testCurrentIssue(self):
        """
        Test that we can access the current issue
        """
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")

        self.assertEqual(prescription.currentIssueNumber, 3)
        self.assertEqual(prescription.currentIssue.number, 3)
        self.assertEqual(prescription.currentIssue.status, "0006")

        # try changing the current issue number and make sure that this is picked up
        prescription.currentIssueNumber = 1
        self.assertEqual(prescription.currentIssueNumber, 1)
        self.assertEqual(prescription.currentIssue.number, 1)
        self.assertEqual(prescription.currentIssue.status, "0009")

    def testIssues(self):
        """
        Test that we can access the prescription issues
        """
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")

        self.assertEqual(prescription.issueNumbers, [1, 2, 3])

        issues = prescription.issues
        self.assertEqual(len(issues), 3)

        issueNumbers = [issue.number for issue in issues]
        self.assertEqual(issueNumbers, [1, 2, 3])

    def testClaims(self):
        """
        Test that we can access the prescription issue claims
        """
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")

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
        prescription = loadTestExampleJson(self.mockLogObject, "DD0180-ZBED5C-11E3A.json")

        # check the future issue can be found
        self.assertEqual(prescription._findNextFutureIssueNumber("1"), "2")

        # check that there are no more beyond the last issue
        self.assertEqual(prescription.maxRepeats, 2)
        self.assertEqual(prescription._findNextFutureIssueNumber("2"), None)

    def testFindNextFutureIssueNumber_issuesAlreadyDispensed(self):
        """
        Test that no future issues can be found if they're all dispensed.
        """
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")

        # chekc that dispensed issues can not be found
        self.assertEqual(prescription._findNextFutureIssueNumber("1"), None)
        self.assertEqual(prescription._findNextFutureIssueNumber("2"), None)

        # check that there are no more beyond the last issue
        self.assertEqual(prescription.maxRepeats, 3)
        self.assertEqual(prescription._findNextFutureIssueNumber("3"), None)

    def testGetIssueNumbersInRange(self):
        """
        Test that we can correctly retrieve ranges of issue numbers.
        """
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")

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

    def testMissingIssueNumbers(self):
        """
        Test that we can deal correctly with prescriptions with missing instances.
        """
        # this 12-issue prescription has issues 1 and 2 missing because of migration
        prescription = loadTestExampleJson(self.mockLogObject, "50EE48-B83002-490F7.json")

        self.assertEqual(prescription.issueNumbers, [3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
        self.assertEqual(prescription.missingIssueNumbers, [1, 2])

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

    def _assertFindInstancesToActionUpdate(
        self, prescription, handleTime, action, expectedIssueNumberStrs
    ):
        """
        Helper to test that findInstancesToActionUpdate() returns expected instances
        """
        mockContext = MagicMock()
        mockContext.handleTime = handleTime
        mockContext.instancesToUpdate = None
        prescription.findInstancesToActionUpdate(mockContext, action)
        self.assertEqual(mockContext.instancesToUpdate, expectedIssueNumberStrs)

    def testFindInstancesToActionUpdate(self):
        """
        Test that we can find instances that need updating at a particular time.
        """
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")

        # first, try a date that will pick up all next actions
        handleTime = datetime(year=2050, month=1, day=1)

        action = PrescriptionRecord.NEXTACTIVITY_DELETE
        self._assertFindInstancesToActionUpdate(prescription, handleTime, action, ["1"])

        action = PrescriptionRecord.NEXTACTIVITY_CREATENOCLAIM
        self._assertFindInstancesToActionUpdate(prescription, handleTime, action, ["2", "3"])

        action = PrescriptionRecord.NEXTACTIVITY_EXPIRE
        self._assertFindInstancesToActionUpdate(prescription, handleTime, action, None)

        # then try a date in the past that won't pick up actions
        handleTime = datetime(year=2010, month=1, day=1)
        action = PrescriptionRecord.NEXTACTIVITY_CREATENOCLAIM
        self._assertFindInstancesToActionUpdate(prescription, handleTime, action, None)

        # first, try a date that will pick up all next actions
        handleTime = datetime(year=2050, month=1, day=1)
        # same as above json but with nextActivityNAD_bin and instance 1 nextActivity set to purge
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3B.json")
        action = PrescriptionRecord.NEXTACTIVITY_PURGE
        self._assertFindInstancesToActionUpdate(prescription, handleTime, action, ["1"])

    def testFindInstancesToActionUpdate_missingInstances(self):
        """
        SPII-10492 - Test that we can find instances that need updating in a migrated
        prescription with missing instances.
        """
        # this 12-issue prescription has issues 1 and 2 missing because of migration
        prescription = loadTestExampleJson(self.mockLogObject, "50EE48-B83002-490F7.json")

        # first, try a date that will pick up all next actions
        handleTime = datetime(year=2050, month=1, day=1)

        action = PrescriptionRecord.NEXTACTIVITY_DELETE
        self._assertFindInstancesToActionUpdate(prescription, handleTime, action, ["3"])

        action = PrescriptionRecord.NEXTACTIVITY_EXPIRE
        self._assertFindInstancesToActionUpdate(
            prescription, handleTime, action, ["5", "6", "7", "8", "9", "10", "11", "12"]
        )

    def testResetCurrentInstance(self):
        """
        Test that resetting the current instance chooses the correct instance.
        """

        prescription = loadTestExampleJson(self.mockLogObject, "50EE48-B83002-490F7.json")
        self.assertEqual(prescription.currentIssueNumber, 4)
        (old, new) = prescription.resetCurrentInstance()
        self.assertEqual((old, new), (4, 4))
        self.assertEqual(prescription.currentIssueNumber, 4)

        prescription = loadTestExampleJson(self.mockLogObject, "DD0180-ZBED5C-11E3A.json")
        self.assertEqual(prescription.currentIssueNumber, 1)
        (old, new) = prescription.resetCurrentInstance()
        self.assertEqual((old, new), (1, 1))
        self.assertEqual(prescription.currentIssueNumber, 1)

        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")
        self.assertEqual(prescription.currentIssueNumber, 3)
        (old, new) = prescription.resetCurrentInstance()
        self.assertEqual((old, new), (3, 3))
        self.assertEqual(prescription.currentIssueNumber, 3)

    def testHandleOverdueExpiryNone(self):
        """
        SPII-31379 due to old prescrptions the NAD index is set to None
        """
        nad = [None]
        self.assertFalse(PrescriptionRecord._isExpiryOverdue(nad))

    def testHandleOverdueExpiryEmpty(self):
        """
        SPII-31379 due to old prescrptions the NAD index is empty
        """
        nad = []
        self.assertFalse(PrescriptionRecord._isExpiryOverdue(nad))

    def testHandleOverdueExpiryNotExpired(self):
        """
        Expiry is set to tomorrow
        """
        nad = [
            "expire:{}".format(
                (datetime.now() + timedelta(days=1)).strftime(TimeFormats.STANDARD_DATE_FORMAT)
            )
        ]
        self.assertFalse(PrescriptionRecord._isExpiryOverdue(nad))

    def testHandleOverdueExpiryExpired(self):
        """
        Expiry is set to yesterday
        """
        nad = [
            "expire:{}".format(
                (datetime.now() - timedelta(days=1)).strftime(TimeFormats.STANDARD_DATE_FORMAT)
            )
        ]
        self.assertTrue(PrescriptionRecord._isExpiryOverdue(nad))

    def testGetLineItemCancellations(self):
        """
        Test that we can get the line item cancellations for a prescription
        """
        prescription = loadTestExampleJson(self.mockLogObject, "23C1BC-Z75FB1-11EE84.json")
        currentIssue = prescription.currentIssue

        cancelledLineItemID = "02ED7776-21CD-4E7B-AC9D-D1DBFEE7B8CF"
        cancellations = currentIssue.get_line_item_cancellations(cancelledLineItemID)
        self.assertEqual(len(cancellations), 1)

        notCancelledLineItemID = "45D5FB11-D793-4D51-9ADD-95E0F54D2786"
        cancellations = currentIssue.get_line_item_cancellations(notCancelledLineItemID)
        self.assertEqual(len(cancellations), 0)

    def testGetLineItemFirstCancellationTime(self):
        prescription = loadTestExampleJson(self.mockLogObject, "23C1BC-Z75FB1-11EE84.json")
        currentIssue = prescription.currentIssue

        cancelledLineItemID = "02ED7776-21CD-4E7B-AC9D-D1DBFEE7B8CF"
        firstCancellationTime = currentIssue.get_line_item_first_cancellation_time(
            cancelledLineItemID
        )
        self.assertEqual(firstCancellationTime, "20240415101553")

        notCancelledLineItemID = "45D5FB11-D793-4D51-9ADD-95E0F54D2786"
        firstCancellationTime = currentIssue.get_line_item_first_cancellation_time(
            notCancelledLineItemID
        )
        self.assertEqual(firstCancellationTime, None)

    def testSetInitialPrescriptionStatusActivePrescription(self):
        """
        Test that a prescription with a start date of today or earlier is marked as TO_BE_DISPENSED.
        """
        prescription = loadTestExampleJson(self.mockLogObject, "7D9625-Z72BF2-11E3A.json")

        current_time = datetime.now()
        prescription.setInitialPrescriptionStatus(current_time)

        self.assertEqual(prescription.getIssue(1).status, "0001")

    def testSetInitialPrescriptionStatusFutureDated(self):
        """
        Test that a prescription with a future start date is marked as FUTURE_DATED_PRESCRIPTION.
        """

        prescription = loadTestExampleJson(self.mockLogObject, "0DA698-A83008-F50593.json")

        future_time = datetime.now() + timedelta(days=10)
        prescription.setInitialPrescriptionStatus(future_time)

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
