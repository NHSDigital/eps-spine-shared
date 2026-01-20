import copy
import datetime
import json
import sys
from decimal import Decimal
from sys import getsizeof
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from boto3.dynamodb.conditions import Key as BotoKey
from freezegun import freeze_time
from parameterized import parameterized

from eps_spine_shared.common import indexes
from eps_spine_shared.common.dynamodb_common import (
    GSI,
    NEXT_ACTIVITY_DATE_PARTITIONS,
    Attribute,
    Key,
    ProjectedAttribute,
    SortKey,
)
from eps_spine_shared.common.prescription import fields
from eps_spine_shared.common.prescription.record import (
    PrescriptionStatus,
)
from tests.dynamodb_test import (
    CREATION_TIME,
    DISP_ORG,
    NOM_ORG,
    PRESC_ORG,
    DynamoDbTest,
)


class EpsDynamoDbIndexTest(DynamoDbTest):
    """
    Tests relating to DynamoDbIndex.
    """

    def get_erd_record(self, nhs_number, creation_time=CREATION_TIME):
        """
        Get record and add instance and index entry to represent eRD.
        """
        record = self.get_record(nhs_number, creation_time)
        record["instances"]["2"] = {
            "prescriptionStatus": PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE,
            "dispense": {"dispensingOrganization": "X28"},
        }
        record["indexes"]["nhsNumberDate_bin"].append(
            f"{nhs_number}|{creation_time}|R2|{PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE}"
        )
        return record

    def get_nominated_record(self, nhs_number, creation_time=CREATION_TIME):
        """
        Get record and add nomination and index entry to represent nominated.
        """
        record = self.get_record(nhs_number, creation_time)
        record.update({"nomination": {"nominatedPerformer": NOM_ORG}})
        record["indexes"]["nomPharmStatus_bin"] = [
            f"{NOM_ORG}_{PrescriptionStatus.TO_BE_DISPENSED}"
        ]
        return record

    def modify_prescriber(self, record):
        """
        Modify prescriber org of given record.
        """
        record["prescription"]["prescribingOrganization"] = "NOPE"

    def modify_dispenser(self, record):
        """
        Modify dispenser org of given record.
        """
        record["instances"]["1"]["dispense"]["dispensingOrganization"] = "NOPE"

    def modify_status(self, record):
        """
        Modify status of given record.
        """
        record["instances"]["1"][
            "prescriptionStatus"
        ] = PrescriptionStatus.FUTURE_DATED_PRESCRIPTION

    def add_ballast_to_record(self, record):
        """
        Add ballast to the index attribute of the record to increase its size.
        """
        built_record = self.datastore.build_record("", record, "Acute", None)

        body_size = sys.getsizeof(built_record["body"])
        item_deep_copy = copy.deepcopy(built_record)
        del item_deep_copy["body"]
        record_without_body_size = sys.getsizeof(json.dumps(item_deep_copy))
        record_size = body_size + record_without_body_size

        ballast = ""
        while (getsizeof(ballast) * 2) + record_size < 400_000:
            ballast = ballast + "a"
        record["indexes"]["ballast"] = ballast

    def create_modify_insert_record(
        self, internal_id, nhs_number, modification=None, nominated=False
    ):
        """
        Create a record, modifying so as not to be returned by a query and adding its keys to those to be cleaned-up.
        """
        record_id = self.generate_record_key()
        self.keys.append((record_id, SortKey.RECORD.value))
        record = self.get_nominated_record(nhs_number) if nominated else self.get_record(nhs_number)
        if modification:
            modification(record)
        self.datastore.insert_eps_record_object(internal_id, record_id, record)
        return record_id

    def test_build_terms_with_regex(self):
        """
        Test building terms from indexes of returned records, including regex checks.
        """
        nhs_number = self.generate_nhs_number()
        release_version = "R2"
        items = [
            {
                Key.PK.name: self.generate_prescription_id(),
                ProjectedAttribute.INDEXES.name: {
                    indexes.INDEX_NHSNUMBER_DATE.lower(): [
                        f"{nhs_number}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                        f"{nhs_number}|{CREATION_TIME}|R1|{PrescriptionStatus.TO_BE_DISPENSED}",
                        f"{nhs_number}|{CREATION_TIME}|R2|{PrescriptionStatus.AWAITING_RELEASE_READY}",
                    ]
                },
            }
        ]
        term_regex = r"\|\d{8,14}\|" + release_version + r"\|" + PrescriptionStatus.TO_BE_DISPENSED
        terms = self.datastore.indexes.build_terms(items, indexes.INDEX_NHSNUMBER_DATE, term_regex)

        self.assertEqual(len(terms), 1)

    def test_build_terms_with_cleared_indexes(self):
        """
        Test that items with cleared indexes attributes (only nextActivityNAD_bin) aren't included by buildTerms.
        """
        items = [
            {
                Key.PK.name: self.generate_prescription_id(),
                ProjectedAttribute.INDEXES.name: {
                    indexes.INDEX_NEXTACTIVITY.lower(): ["purge_20260101"]
                },
            }
        ]
        terms = self.datastore.indexes.build_terms(items, indexes.INDEX_NHSNUMBER_DATE, None)

        self.assertEqual(len(terms), 0)

    def test_return_terms_by_nhs_number_date(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberDate records.
        """
        nhs_number = self.generate_nhs_number()
        creation_times = ["20230911000000", "20230912000000", "20230913000000", "20230914000000"]

        record_values = [
            SimpleNamespace(id=self.generate_record_key(), creation_time=time)
            for time in creation_times
        ]

        for values in record_values:
            record = self.get_record(nhs_number, values.creation_time)
            self.datastore.insert_eps_record_object(self.internal_id, values.id, record)
            self.keys.append((values.id, SortKey.RECORD.value))

        start_date = "20230912"
        end_date = "20230913"
        range_start = indexes.SEPERATOR.join([nhs_number, start_date])
        range_end = indexes.SEPERATOR.join([nhs_number, end_date])

        terms = self.datastore.return_terms_by_nhs_number_date(
            self.internal_id, range_start, range_end
        )

        expected = [
            (
                f"{nhs_number}|{values.creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                values.id,
            )
            for values in record_values[1:-1]
        ]

        self.assertEqual(expected, terms)

    def test_return_terms_by_nhs_number_same_date(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberDate records.
        Start and end date are the same.
        """
        nhs_number = self.generate_nhs_number()
        creation_times = ["20230911000000", "20230911000000"]

        record_values = [
            SimpleNamespace(id=self.generate_record_key(), creation_time=time)
            for time in creation_times
        ]

        for values in record_values:
            record = self.get_record(nhs_number, values.creation_time)
            self.datastore.insert_eps_record_object(self.internal_id, values.id, record)
            self.keys.append((values.id, SortKey.RECORD.value))

        date = "20230911"
        range_start = indexes.SEPERATOR.join([nhs_number, date])
        range_end = indexes.SEPERATOR.join([nhs_number, date])

        terms = self.datastore.return_terms_by_nhs_number_date(
            self.internal_id, range_start, range_end
        )

        expected = [
            (
                f"{nhs_number}|{values.creation_time}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                values.id,
            )
            for values in record_values
        ]

        self.assertEqual(sorted(expected), sorted(terms))

    def test_return_terms_by_nhs_number(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberDate records, without startDate.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        record = self.get_record(nhs_number)
        self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        terms = self.datastore.return_terms_by_nhs_number(self.internal_id, nhs_number)

        expected = [(nhs_number, prescription_id)]

        self.assertEqual(expected, terms)

    def test_exclude_next_activity_purge(self):
        """
        Test querying against a record index and excluding records with a nextActivity of purge.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        record = self.get_record(nhs_number)
        self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        prescription_id2 = self.generate_record_key()
        self.keys.append((prescription_id2, SortKey.RECORD.value))
        record = self.get_record(nhs_number)
        self.datastore.insert_eps_record_object(self.internal_id, prescription_id2, record)

        terms = self.datastore.return_terms_by_nhs_number(self.internal_id, nhs_number)

        expected = [(nhs_number, prescription_id), (nhs_number, prescription_id2)]
        self.assertEqual(sorted(expected), sorted(terms))

        record["indexes"]["nextActivityNAD_bin"] = ["purge_20241114"]
        record["SCN"] = record["SCN"] + 1
        self.datastore.insert_eps_record_object(
            self.internal_id, prescription_id2, record, is_update=True
        )

        terms = self.datastore.return_terms_by_nhs_number(self.internal_id, nhs_number)

        expected = [(nhs_number, prescription_id)]
        self.assertEqual(expected, terms)

    def test_return_terms_by_nhs_number_multiple(self):
        """
        Test querying against the nhsNumberDate index and returning multiple nhsNumberDate records, without startDate.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        record = self.get_record(nhs_number)
        self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        self.create_modify_insert_record(self.internal_id, nhs_number)

        terms = self.datastore.return_terms_by_nhs_number(self.internal_id, nhs_number)

        self.assertEqual(len(terms), 2)

    def test_return_terms_by_nom_pharm_status(self):
        """
        Test querying against the nomPharmStatus index and returning nomPharmStatus records.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        record = self.get_nominated_record(nhs_number)
        self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        self.create_modify_insert_record(
            self.internal_id, nhs_number, self.modify_status, nominated=True
        )

        terms = self.datastore.get_nom_pharm_records_unfiltered(self.internal_id, NOM_ORG)

        expected = [prescription_id]

        self.assertEqual(expected, terms)

    def test_return_terms_by_nom_pharm_status_with_batch_size(self):
        """
        Test querying against the nomPharmStatus index via the get_nominated_pharmacy_records method and returning
        a defined number of nomPharmStatus records.
        """
        prescription_ids = []
        for _ in range(3):
            prescription_id, nhs_number = self.get_new_record_keys()
            record = self.get_nominated_record(nhs_number)
            self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)
            self.create_modify_insert_record(
                self.internal_id, nhs_number, self.modify_status, nominated=True
            )
            prescription_ids.append(prescription_id)

        returned_prescription_ids, discarded_count = self.datastore.get_nominated_pharmacy_records(
            NOM_ORG, 2, self.internal_id
        )

        self.assertEqual(discarded_count, 1)
        self.assertEqual(len(returned_prescription_ids), 2)
        self.assertTrue(set(returned_prescription_ids).issubset(set(prescription_ids)))

    def test_return_terms_by_nom_pharm_status_with_pagination(self):
        """
        Test querying against the nomPharmStatus index and returning nomPharmStatus records.
        Index attribute value is made artificially large, so that when projected into the index,
        the combined returned items breach the pagination threshold.
        """
        total_terms = 7
        nhs_number = self.generate_nhs_number()
        [
            self.create_modify_insert_record(
                self.internal_id, nhs_number, self.add_ballast_to_record, nominated=True
            )
            for _ in range(total_terms)
        ]

        terms = self.datastore.get_nom_pharm_records_unfiltered(self.internal_id, NOM_ORG)

        self.assertEqual(len(terms), total_terms)

    def test_return_terms_by_nom_pharm_status_unfiltered_with_limit(self):
        """
        Test querying against the nomPharmStatus index and returning nomPharmStatus records.
        Provide a limit for the query to adhere to.
        """
        total_terms = 3
        limit = 2
        nhs_number = self.generate_nhs_number()
        [
            self.create_modify_insert_record(self.internal_id, nhs_number, nominated=True)
            for _ in range(total_terms)
        ]

        terms = self.datastore.get_nom_pharm_records_unfiltered(
            self.internal_id, NOM_ORG, limit=limit
        )

        self.assertEqual(len(terms), limit)

    def test_return_terms_by_nom_pharm_status_unfiltered_with_limit_and_pagination(self):
        """
        Test querying against the nomPharmStatus index and returning nomPharmStatus records.
        Provide a limit for the query to adhere to combined with pagination.
        """
        total_terms = 7
        limit = 6
        nhs_number = self.generate_nhs_number()
        [
            self.create_modify_insert_record(
                self.internal_id, nhs_number, self.add_ballast_to_record, nominated=True
            )
            for _ in range(total_terms)
        ]

        terms = self.datastore.get_nom_pharm_records_unfiltered(
            self.internal_id, NOM_ORG, limit=limit
        )

        self.assertEqual(len(terms), limit)

    def test_return_terms_by_nom_pharm(self):
        """
        Test querying against the nomPharmStatus index using only the odsCode and returning nomPharmStatus records.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        record = self.get_nominated_record(nhs_number)
        self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        id_of_prescription_with_other_status = self.create_modify_insert_record(
            self.internal_id, nhs_number, self.modify_status, nominated=True
        )

        terms = self.datastore.get_all_pids_by_nominated_pharmacy(self.internal_id, NOM_ORG)

        expected = [prescription_id, id_of_prescription_with_other_status]

        expected.sort()
        terms.sort()

        self.assertEqual(expected, terms)

    def test_return_terms_by_nhs_number_date_erd(self):
        """
        Test querying against the nhsNumberDate index and returning multiple nhsNumberDates per record.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        record = self.get_erd_record(nhs_number)
        self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        range_start = f"{nhs_number}|20230911"
        range_end = f"{nhs_number}|20230912"
        terms = self.datastore.return_terms_by_nhs_number_date(
            self.internal_id, range_start, range_end
        )

        expected = [
            (
                f"{nhs_number}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescription_id,
            ),
            (
                f"{nhs_number}|{CREATION_TIME}|R2|{PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE}",
                prescription_id,
            ),
        ]

        self.assertEqual(expected, terms)

    def test_return_terms_by_nhs_number_prescriber_dispenser_date(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberPrescriberDispenserDate records.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        self.datastore.insert_eps_record_object(
            self.internal_id, prescription_id, self.get_record(nhs_number)
        )

        self.create_modify_insert_record(self.internal_id, nhs_number, self.modify_prescriber)
        self.create_modify_insert_record(self.internal_id, nhs_number, self.modify_dispenser)

        start_date = "20230911"
        end_date = "20230912"
        range_start = indexes.SEPERATOR.join([nhs_number, PRESC_ORG, DISP_ORG, start_date])
        range_end = indexes.SEPERATOR.join([nhs_number, PRESC_ORG, DISP_ORG, end_date])

        terms = self.datastore.return_terms_by_index_date(
            self.internal_id, indexes.INDEX_NHSNUMBER_PRDSDATE, range_start, range_end
        )

        expected = [
            (
                f"{nhs_number}|{PRESC_ORG}|{DISP_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescription_id,
            )
        ]

        self.assertEqual(expected, terms)

    def test_return_terms_by_nhs_number_prescriber_date(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberPrescriberDate records.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        self.datastore.insert_eps_record_object(
            self.internal_id, prescription_id, self.get_record(nhs_number)
        )

        self.create_modify_insert_record(self.internal_id, nhs_number, self.modify_prescriber)

        start_date = "20230911"
        end_date = "20230912"
        range_start = indexes.SEPERATOR.join([nhs_number, PRESC_ORG, start_date])
        range_end = indexes.SEPERATOR.join([nhs_number, PRESC_ORG, end_date])

        terms = self.datastore.return_terms_by_index_date(
            self.internal_id, indexes.INDEX_NHSNUMBER_PRDATE, range_start, range_end
        )

        expected = [
            (
                f"{nhs_number}|{PRESC_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescription_id,
            )
        ]

        self.assertEqual(expected, terms)

    def test_return_terms_by_nhs_number_dispenser_date(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberDispenserDate records.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        self.datastore.insert_eps_record_object(
            self.internal_id, prescription_id, self.get_record(nhs_number)
        )

        self.create_modify_insert_record(self.internal_id, nhs_number, self.modify_dispenser)

        start_date = "20230911"
        end_date = "20230912"
        range_start = indexes.SEPERATOR.join([nhs_number, DISP_ORG, start_date])
        range_end = indexes.SEPERATOR.join([nhs_number, DISP_ORG, end_date])

        terms = self.datastore.return_terms_by_index_date(
            self.internal_id, indexes.INDEX_NHSNUMBER_DSDATE, range_start, range_end
        )

        expected = [
            (
                f"{nhs_number}|{DISP_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescription_id,
            )
        ]

        self.assertEqual(expected, terms)

    def test_return_terms_by_prescriber_dispenser_date(self):
        """
        Test querying against the prescriberDate index and returning prescDispDate records.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        self.datastore.insert_eps_record_object(
            self.internal_id, prescription_id, self.get_record(nhs_number)
        )

        self.create_modify_insert_record(self.internal_id, nhs_number, self.modify_prescriber)
        self.create_modify_insert_record(self.internal_id, nhs_number, self.modify_dispenser)

        start_date = "20230911"
        end_date = "20230912"
        range_start = indexes.SEPERATOR.join([PRESC_ORG, DISP_ORG, start_date])
        range_end = indexes.SEPERATOR.join([PRESC_ORG, DISP_ORG, end_date])

        terms = self.datastore.return_terms_by_index_date(
            self.internal_id, indexes.INDEX_PRESCRIBER_DSDATE, range_start, range_end
        )

        expected = [
            (
                f"{PRESC_ORG}|{DISP_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescription_id,
            )
        ]

        self.assertEqual(expected, terms)

    def test_return_terms_by_prescriber_date(self):
        """
        Test querying against the prescriberDate index and returning prescriberDate records.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        self.datastore.insert_eps_record_object(
            self.internal_id, prescription_id, self.get_record(nhs_number)
        )

        self.create_modify_insert_record(self.internal_id, nhs_number, self.modify_prescriber)

        start_date = "20230911"
        end_date = "20230912"
        range_start = indexes.SEPERATOR.join([PRESC_ORG, start_date])
        range_end = indexes.SEPERATOR.join([PRESC_ORG, end_date])

        terms = self.datastore.return_terms_by_index_date(
            self.internal_id, indexes.INDEX_PRESCRIBER_DATE, range_start, range_end
        )

        expected = [
            (
                f"{PRESC_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescription_id,
            )
        ]

        self.assertEqual(expected, terms)

    def test_return_terms_by_dispenser_date(self):
        """
        Test querying against the dispenserDate index and returning dispenserDate records.
        """
        prescription_id, nhs_number = self.get_new_record_keys()
        self.datastore.insert_eps_record_object(
            self.internal_id, prescription_id, self.get_record(nhs_number)
        )

        self.create_modify_insert_record(self.internal_id, nhs_number, self.modify_dispenser)

        start_date = "20230911"
        end_date = "20230912"
        range_start = indexes.SEPERATOR.join([DISP_ORG, start_date])
        range_end = indexes.SEPERATOR.join([DISP_ORG, end_date])

        terms = self.datastore.return_terms_by_index_date(
            self.internal_id, indexes.INDEX_DISPENSER_DATE, range_start, range_end
        )

        expected = [
            (f"{DISP_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}", prescription_id)
        ]

        self.assertEqual(expected, terms)

    def test_items_without_batch_claim_id_not_added_to_claim_id_index(self):
        """
        Test claimId index doesn't contain any items without a batchClaimId attribute.
        """
        batch_claim_ids = []
        for _ in range(2):
            batch_id = str(uuid4())
            batch_claim_ids.append(batch_id)
            self.keys.append((batch_id, SortKey.CLAIM.value))

        batch_claims = [
            {
                Key.PK.name: batch_claim_ids[0],
                Key.SK.name: SortKey.CLAIM.value,
                Attribute.BATCH_CLAIM_ID.name: batch_claim_ids[0],
                ProjectedAttribute.BODY.name: "testBody",
            },
            {
                Key.PK.name: batch_claim_ids[1],
                Key.SK.name: SortKey.CLAIM.value,
                ProjectedAttribute.BODY.name: "testBody",
            },
        ]
        [
            self.datastore.client.put_item(self.internal_id, batch_claim)
            for batch_claim in batch_claims
        ]

        key_condition_expression = BotoKey(Key.SK.name).eq(SortKey.CLAIM.value)
        items = self.datastore.client.query_index(GSI.CLAIM_ID.name, key_condition_expression, None)
        self.assertEqual(len(items), 1)

    def test_query_next_activity_date(self):
        """
        Test querying against the nextActivityDate index and returning lists of prescription keys.
        """
        expected = []
        for _ in range(3):
            prescription_id, nhs_number = self.get_new_record_keys()
            expected.append(prescription_id)
            record = self.get_record(nhs_number)
            self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        actual = self.datastore.return_pids_due_for_next_activity(
            self.internal_id, "createNoClaim_20250103", "createNoClaim_20250105"
        )
        flat = [i for generator in actual for i in generator]
        self.assertEqual(len(flat), 3)

    def test_query_next_activity_same_date(self):
        """
        Test querying against the nextActivityDate index and
        returning lists of prescription keys when dates are the same.
        """
        expected = []
        for _ in range(3):
            prescription_id, nhs_number = self.get_new_record_keys()
            expected.append(prescription_id)
            record = self.get_record(nhs_number)
            self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        actual = self.datastore.return_pids_due_for_next_activity(
            self.internal_id, "createNoClaim_20250104", "createNoClaim_20250104"
        )
        flat = [i for generator in actual for i in generator]
        self.assertEqual(len(flat), 3)

    # (a,) notation is to force a single item tuple as expected by parameterized.expand
    @parameterized.expand(
        [
            (fields.NEXTACTIVITY_EXPIRE,),
            (fields.NEXTACTIVITY_CREATENOCLAIM,),
            (fields.NEXTACTIVITY_DELETE,),
            (fields.NEXTACTIVITY_PURGE,),
            (fields.NEXTACTIVITY_READY,),
        ]
    )
    def test_query_next_activity_date_all_activities(self, next_activity):
        """
        Test query works against all next activities
        """
        next_activity_nad_bin = f"{next_activity}_20250104"

        prescription_id, nhs_number = self.get_new_record_keys()
        record = self.get_record(nhs_number)
        record["indexes"]["nextActivityNAD_bin"] = [next_activity_nad_bin]
        self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        actual = self.datastore.return_pids_due_for_next_activity(
            self.internal_id, next_activity_nad_bin, next_activity_nad_bin
        )
        flat = [i for generator in actual for i in generator]
        self.assertEqual(flat, [prescription_id])

    def test_query_next_activity_date_shards(self):
        """
        Test query works against records on all shards
        """
        expected = []

        def add_record(next_activity):
            """
            Add a record to the table with a given next activity shard, and append its prescriptionId to expected list
            """
            prescription_id, nhs_number = self.get_new_record_keys()
            record = self.get_record(nhs_number)
            item = self.datastore.build_record(prescription_id, record, None, None)

            item[Attribute.NEXT_ACTIVITY.name] = next_activity

            self.datastore.client.insert_items(self.internal_id, [item], False)
            expected.append([prescription_id])

        # Add unsharded record
        add_record("createNoClaim")

        # Add a record on each shard
        for shard in range(1, NEXT_ACTIVITY_DATE_PARTITIONS + 1):
            add_record(f"createNoClaim.{shard}")

        actual = self.datastore.return_pids_due_for_next_activity(
            self.internal_id, "createNoClaim_20250104", "createNoClaim_20250104"
        )
        consumed = [list(generator) for generator in list(actual)]

        self.assertEqual(expected, consumed)

    def test_query_claim_notification_store_time(self):
        """
        Test querying against the claimNotificationStoreTime index and returning lists of document keys.
        """
        document_keys = []

        def create_documents(doc_ref_title):
            for i in range(3):
                index = {
                    indexes.INDEX_STORE_TIME_DOC_REF_TITLE: [f"{doc_ref_title}_2024091110111{i}"],
                    indexes.INDEX_DELETE_DATE: ["20250911"],
                    indexes.INDEX_PRESCRIPTION_ID: [self.generate_prescription_id()],
                }

                document_key = f"20240911_{doc_ref_title}_{i}"
                document_keys.append(document_key)
                self.keys.append((document_key, SortKey.DOCUMENT.value))

                content = self.get_document_content()
                self.datastore.insert_eps_document_object(
                    self.internal_id, document_key, {"content": content}, index
                )

        [create_documents(doc_ref_title) for doc_ref_title in ["ClaimNotification", "Other"]]

        query_response = self.datastore.return_claim_notification_ids_between_store_dates(
            self.internal_id, "20240911101111", "20240912101111"
        )

        actual = list(query_response)
        expected = [["20240911_ClaimNotification_1", "20240911_ClaimNotification_2"], []]

        self.assertEqual(actual, expected)

    def test_query_claim_notification_store_time_boundaries(self):
        """
        Test querying against the claimNotificationStoreTime index and returning lists of document keys.
        Creates two documents relating to each boundary argument. Asserts that one of each pair is returned.
        """
        document_keys = []

        def create_documents(store_date):
            for i in range(2):
                index = {
                    indexes.INDEX_STORE_TIME_DOC_REF_TITLE: [
                        f"ClaimNotification_{store_date}10111{i}"
                    ],
                    indexes.INDEX_DELETE_DATE: ["20250911"],
                    indexes.INDEX_PRESCRIPTION_ID: [self.generate_prescription_id()],
                }

                document_key = f"{store_date}_ClaimNotification_{i}"
                document_keys.append(document_key)
                self.keys.append((document_key, SortKey.DOCUMENT.value))

                content = self.get_document_content()
                self.datastore.insert_eps_document_object(
                    self.internal_id, document_key, {"content": content}, index
                )

        [create_documents(store_date) for store_date in ["20240911", "20240912"]]

        query_response = self.datastore.return_claim_notification_ids_between_store_dates(
            self.internal_id, "20240911101111", "20240912101110"
        )

        actual = list(query_response)
        expected = [["20240911_ClaimNotification_1"], ["20240912_ClaimNotification_0"]]

        self.assertEqual(actual, expected)

    def test_get_date_range_for_query(self):
        """
        Test method for creating dates to query indexes against.
        Method is inclusive, so slightly less than one day gives both relevant days.
        """
        start_datetime_str = "20250911101112"
        end_datetime_str = "20250912101111"

        actual = self.datastore.indexes._get_date_range_for_query(
            start_datetime_str, end_datetime_str
        )
        expected = ["20250911", "20250912"]

        self.assertEqual(actual, expected)

    @parameterized.expand(
        [
            ["query_nhs_number_date", ["index", "nhsNumber"], [], str],
            ["query_prescriber_date", ["index", "org"], [], str],
            ["query_dispenser_date", ["index", "org"], [], str],
            ["query_next_activity_date", [], [], lambda x: f"_{x}"],
        ]
    )
    def test_invalid_ranges(self, index, preargs, postargs, input_formatter=None):
        """
        Test querying against indexes with invalid ranges.
        """
        input_values = [2, 1]
        if input_formatter:
            input_values = [input_formatter(i) for i in input_values]

        args = preargs + input_values + postargs

        self.assertEqual(list(getattr(self.datastore.indexes, index)(*args)), [])

    def test_query_batch_claim_id_sequence_number(self):
        """
        Test querying against the claimIdSequenceNumber(Nwssp) indexes and returning lists of batch claim IDs.
        """
        batch_claim1 = [str(uuid4()), 1, False]
        batch_claim2 = [str(uuid4()), 2, False]

        nwssp_batch_claim1 = [str(uuid4()), 1, True]
        nwssp_batch_claim2 = [str(uuid4()), 2, True]

        for batch_claim in [batch_claim1, batch_claim2, nwssp_batch_claim1, nwssp_batch_claim2]:
            batch_claim_id, sqn_value, nwssp = batch_claim
            self.keys.append((batch_claim_id, SortKey.CLAIM.value))

            batch_claim = {
                "Batch GUID": batch_claim_id,
                "Claim ID List": [],
                "Handle Time": "20241111121314",
                "Sequence Number": sqn_value,
                "Batch XML": b"<xml />",
            }
            if nwssp:
                batch_claim["Nwssp Sequence Number"] = sqn_value

            self.datastore.store_batch_claim(self.internal_id, batch_claim)

        returned_batch_claim_ids = self.datastore.find_batch_claim_from_seq_number(1)
        self.assertEqual(returned_batch_claim_ids, [batch_claim1[0]])

        returned_batch_claim_ids = self.datastore.find_batch_claim_from_seq_number(2, True)
        self.assertEqual(returned_batch_claim_ids, [nwssp_batch_claim2[0]])

    @parameterized.expand(
        [
            [("20240911", "20240912"), ("20240911000000", "20240912000000")],
            [("2024091112", "2024091213"), ("20240911120000", "20240912130000")],
            [("20240911121314", "20240912131415"), ("20240911121314", "20240912131415")],
        ]
    )
    def test_pad_or_trim_date(self, input_dates, expected_dates):
        """
        Test padding or trimming dates used in index queries.
        """
        start_date, end_date = input_dates
        expected_start_date, expected_end_date = expected_dates

        actual_start_date = self.datastore.indexes.pad_or_trim_date(start_date)
        actual_end_date = self.datastore.indexes.pad_or_trim_date(end_date)

        self.assertEqual(expected_start_date, actual_start_date)
        self.assertEqual(expected_end_date, actual_end_date)

    @patch("random.randint")
    def test_last_modified_index(self, patched_randint):
        """
        Test lastModified index by calling directly. It is not used from application code.
        """
        patched_randint.return_value = 7

        index_name = GSI.LAST_MODIFIED.name
        pk = str(uuid4())
        self.keys.append((pk, "SK"))

        date_time = datetime.datetime.now() + datetime.timedelta(weeks=30)

        date_time_decimal = Decimal(str(date_time.timestamp()))
        date_time_int = int(date_time.timestamp())

        day = date_time.strftime("%Y%m%d")
        item = {Key.PK.name: pk, Key.SK.name: "SK"}

        with freeze_time(date_time):
            self.datastore.client.insert_items(self.internal_id, [item], log_item_size=False)

        for timestamp in [date_time_decimal, date_time_int]:
            key_condition_expression = BotoKey(Attribute.LM_DAY.name).eq(f"{day}.7") & BotoKey(
                Attribute.RIAK_LM.name
            ).gte(timestamp)

            items = self.datastore.client.query_index(index_name, key_condition_expression, None)

            self.assertEqual(len(items), 1)
