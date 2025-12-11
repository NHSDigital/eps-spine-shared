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


def get_nad_references():
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


def _load_test_prescription(mock_log_object, prescription_id):
    """
    Load prescription data from JSON files in the test resources directory.
    """
    test_dir_path = path.dirname(__file__)
    full_path = path.join(test_dir_path, "prescription", "resources", prescription_id + ".json")
    with open(full_path) as json_file:
        prescription_dict = simplejson.load(json_file)
        json_file.close()

    treatment_type = prescription_dict["prescription"]["prescriptionTreatmentType"]
    if treatment_type == PrescriptionTreatmentType.ACUTE_PRESCRIBING:
        prescription = SinglePrescribeRecord(mock_log_object, "test")
    elif treatment_type == PrescriptionTreatmentType.REPEAT_PRESCRIBING:
        prescription = RepeatPrescribeRecord(mock_log_object, "test")
    elif treatment_type == PrescriptionTreatmentType.REPEAT_DISPENSING:
        prescription = RepeatDispenseRecord(mock_log_object, "test")
    else:
        raise ValueError("Unknown treatment type %s" % str(treatment_type))

    prescription.create_record_from_store(prescription_dict)

    return prescription


class PrescriptionIndexFactoryTest(TestCase):
    """
    Tests for PrescriptionIndexFactory
    """

    def setUp(self):
        """
        Common init code
        """
        self.log_object = MockLogObject()

    @freeze_time("2025-07-15")
    def test_build_indexes(self):
        """
        Test that build_indexes method creates indexes as expected.
        """
        prescription_id = "7D9625-Z72BF2-11E3A"
        nad_references = get_nad_references()
        index_factory = EpsIndexFactory(self.log_object, prescription_id, [], nad_references)

        context = Mock()
        context.epsRecord = _load_test_prescription(self.log_object, prescription_id)

        record_indexes = index_factory.build_indexes(context)
        for key, value in record_indexes.items():
            record_indexes[key] = sorted(value)

        expected_indexes = {
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
        self.assertEqual(record_indexes, expected_indexes)
