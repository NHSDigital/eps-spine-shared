import base64
import os
import string
import zlib
from random import random
from unittest import TestCase
from uuid import uuid4

import simplejson
from moto import mock_aws

from eps_spine_shared.common.dynamodb_common import SortKey
from eps_spine_shared.common.dynamodb_datastore import EpsDynamoDbDataStore
from eps_spine_shared.common.prescription.record import PrescriptionStatus
from tests.mock_logger import MockLogObject

PRESC_ORG = "X26"
DISP_ORG = "X27"
NOM_ORG = "X28"
CREATION_TIME = "20230911101112"


def set_aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-2"


class DynamoDbTest(TestCase):
    """
    Parent class for DynamoDB tests.
    """

    def setUp(self) -> None:
        """
        Instantiate class to be tested.
        """
        set_aws_credentials()
        self.mock_aws = mock_aws()
        self.mock_aws.start()

        self.logger: MockLogObject = MockLogObject()

        self.datastore: EpsDynamoDbDataStore = EpsDynamoDbDataStore(
            self.logger, None, "spine-eps-datastore"
        )
        self.keys = []
        self.internal_id = str(uuid4())

    def tearDown(self) -> None:
        """
        Stop moto mocking and clean up resources.
        """
        self.mock_aws.stop()

    def generate_prescription_id(self):
        """
        Create a random id with the format of a prescription id.
        """
        parts = [random.choices(string.ascii_uppercase + string.digits, k=6) for _ in range(3)]
        return "-".join([".".join(part) for part in parts])

    def generate_document_key(self):
        """
        Create a placeholder document key and queue it for cleanup
        """
        document_key = str(uuid4())
        self.keys.append((document_key, SortKey.DOCUMENT.value))
        return document_key

    def generate_record_key(self):
        """
        Returns a prescription id excluding the check digit
        """
        return self.generate_prescription_id()[:-1]

    def generate_nhs_number(self):
        """
        Create a random number in the range of test NHS numbers and return it as a string.
        """
        return str(random.randrange(9000000000, 9999999999))

    def get_new_record_keys(self, prescription_id=None):
        """
        Gives unique primary/secondary keys to use on a record item.
        Adds to the list of keys to be deleted in tearDown.
        """
        record_key = prescription_id[:19] if prescription_id else self.generate_record_key()
        nhs_number = self.generate_nhs_number()

        self.keys.append((record_key, SortKey.RECORD.value))
        return record_key, nhs_number

    def get_record(self, nhs_number, creation_time=CREATION_TIME):
        return {
            "patient": {"nhsNumber": nhs_number},
            "prescription": {
                "prescriptionTime": creation_time,
                "daysSupply": 28,
                "prescribingOrganization": PRESC_ORG,
            },
            "instances": {
                "1": {
                    "prescriptionStatus": PrescriptionStatus.TO_BE_DISPENSED,
                    "dispense": {"dispensingOrganization": DISP_ORG},
                }
            },
            "indexes": {
                "nextActivityNAD_bin": ["createNoClaim_20250104"],
                "nhsNumberDate_bin": [
                    f"{nhs_number}|{creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}"
                ],
                "nhsNumber_bin": [nhs_number],
                "nhsNumberPrescDispDate_bin": [
                    f"{nhs_number}|{PRESC_ORG}|{DISP_ORG}|{creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}"
                ],
                "nhsNumberPrescriberDate_bin": [
                    f"{nhs_number}|{PRESC_ORG}|{creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}"
                ],
                "nhsNumberDispenserDate_bin": [
                    f"{nhs_number}|{DISP_ORG}|{creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}"
                ],
                "prescDispDate_bin": [
                    f"{PRESC_ORG}|{DISP_ORG}|{creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}"
                ],
                "prescriberDate_bin": [
                    f"{PRESC_ORG}|{creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}"
                ],
                "dispenserDate_bin": [
                    f"{DISP_ORG}|{creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}"
                ],
            },
            "SCN": 1,
        }

    def get_document_content(self, content={"a": 1, "b": True}):  # noqa: B006
        """
        Gets base64 encoded compressed string of document content.
        """
        return base64.b64encode(zlib.compress(simplejson.dumps(content).encode("utf-8"))).decode(
            "utf-8"
        )
