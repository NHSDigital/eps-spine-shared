from os import path
from unittest.case import TestCase
from unittest.mock import Mock

import simplejson
from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from eps_spine_shared.common.indexes import EpsIndexFactory
from eps_spine_shared.common.prescription.repeat_dispense import RepeatDispenseRecord
from eps_spine_shared.common.prescription.repeat_prescribe import RepeatPrescribeRecord
from eps_spine_shared.common.prescription.single_prescribe import SinglePrescribeRecord
from eps_spine_shared.common.prescription.types import PrescriptionTreatmentType
from tests.mock_logger import MockLogObject


def getNADReferences():
    """
    Reference dictionary of information to be used during next activity
    date calculation
    """
    return {
        "prescriptionExpiryPeriod": relativedelta(months=6),
        "repeatDispenseExpiryPeriod": relativedelta(months=12),
        "dataCleansePeriod": relativedelta(months=6),
        "withDispenserActiveExpiryPeriod": relativedelta(days=180),
        "expiredDeletePeriod": relativedelta(days=90),
        "cancelledDeletePeriod": relativedelta(days=180),
        "claimedDeletePeriod": relativedelta(days=9),
        "notDispensedDeletePeriod": relativedelta(days=30),
        "nominatedDownloadDateLeadTime": relativedelta(days=5),
        "notificationDelayPeriod": relativedelta(days=180),
    }


def _loadTestPrescription(mock_log_object, prescriptionId):
    """
    Load prescription data from JSON files in the test resources directory.
    """
    testDirPath = path.dirname(__file__)
    fullPath = path.join(testDirPath, "resources", prescriptionId + ".json")
    with open(fullPath) as jsonFile:
        prescriptionDict = simplejson.load(jsonFile)
        jsonFile.close()

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


class PrescriptionIndexFactoryTest(TestCase):
    """
    Tests for PrescriptionIndexFactory
    """

    def setUp(self):
        """
        Common init code
        """
        self.logObject = MockLogObject()

    @freeze_time("2025-07-15")
    def testBuildIndexes(self):
        """
        Test that build_indexes method creates indexes as expected.
        """
        prescriptionId = "7D9625-Z72BF2-11E3A"
        nadReferences = getNADReferences()
        indexFactory = EpsIndexFactory(self.logObject, prescriptionId, [], nadReferences)

        context = Mock()
        context.epsRecord = _loadTestPrescription(self.logObject, prescriptionId)

        recordIndexes = indexFactory.build_indexes(context)
        for key, value in recordIndexes.items():
            recordIndexes[key] = sorted(value)

        expectedIndexes = {
            "prescribingSiteStatus_bin": ["Z99901_0006", "Z99901_0009"],
            "dispensingSiteStatus_bin": ["F001M_0006", "F001M_0009"],
            "nomPharmStatus_bin": ["F001M_0006", "F001M_0009"],
            "nextActivityNAD_bin": ["createNoClaim_20141005"],
            "nhsNumber_bin": ["9990406707"],
            "nhsNumberDate_bin": [
                "9990406707|20140408144130|R2|0006",
                "9990406707|20140408144130|R2|0009",
            ],
            "nhsNumberPrescriberDate_bin": [
                "9990406707|Z99901|20140408144130|R2|0006",
                "9990406707|Z99901|20140408144130|R2|0009",
            ],
            "nhsNumberPrescDispDate_bin": [
                "9990406707|Z99901|F001M|20140408144130|R2|0006",
                "9990406707|Z99901|F001M|20140408144130|R2|0009",
            ],
            "nhsNumberDispenserDate_bin": [
                "9990406707|F001M|20140408144130|R2|0006",
                "9990406707|F001M|20140408144130|R2|0009",
            ],
            "prescriberDate_bin": [
                "Z99901|20140408144130|R2|0006",
                "Z99901|20140408144130|R2|0009",
            ],
            "prescDispDate_bin": [
                "Z99901|F001M|20140408144130|R2|0006",
                "Z99901|F001M|20140408144130|R2|0009",
            ],
            "dispenserDate_bin": ["F001M|20140408144130|R2|0006", "F001M|20140408144130|R2|0009"],
            "delta_bin": ["20250715000000|10"],
        }
        self.assertEqual(recordIndexes, expectedIndexes)
