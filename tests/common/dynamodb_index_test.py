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
from eps_spine_shared.common.prescription.records import (
    PrescriptionRecord,
    PrescriptionStatus,
)
from tests.dynamodb_test import (
    CREATION_TIME,
    DISP_ORG,
    NOM_ORG,
    PRESC_ORG,
    DynamoDbTest,
)


class DynamoDbIndexTest(DynamoDbTest):
    """
    Tests relating to DynamoDbIndex.
    """

    def getErdRecord(self, nhsNumber, creationTime=CREATION_TIME):
        """
        Get record and add instance and index entry to represent eRD.
        """
        record = self.getRecord(nhsNumber, creationTime)
        record["instances"]["2"] = {
            "prescriptionStatus": PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE,
            "dispense": {"dispensingOrganization": "X28"},
        }
        record["indexes"]["nhsNumberDate_bin"].append(
            f"{nhsNumber}|{creationTime}|R2|{PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE}"
        )
        return record

    def getNominatedRecord(self, nhsNumber, creationTime=CREATION_TIME):
        """
        Get record and add nomination and index entry to represent nominated.
        """
        record = self.getRecord(nhsNumber, creationTime)
        record.update({"nomination": {"nominatedPerformer": NOM_ORG}})
        record["indexes"]["nomPharmStatus_bin"] = [
            f"{NOM_ORG}_{PrescriptionStatus.TO_BE_DISPENSED}"
        ]
        return record

    def modifyPrescriber(self, record):
        """
        Modify prescriber org of given record.
        """
        record["prescription"]["prescribingOrganization"] = "NOPE"

    def modifyDispenser(self, record):
        """
        Modify dispenser org of given record.
        """
        record["instances"]["1"]["dispense"]["dispensingOrganization"] = "NOPE"

    def modifyStatus(self, record):
        """
        Modify status of given record.
        """
        record["instances"]["1"][
            "prescriptionStatus"
        ] = PrescriptionStatus.FUTURE_DATED_PRESCRIPTION

    def addBallastToRecord(self, record):
        """
        Add ballast to the index attribute of the record to increase its size.
        """
        builtRecord = self.datastore.build_record("", record, "Acute", None)

        bodySize = sys.getsizeof(builtRecord["body"])
        itemDeepCopy = copy.deepcopy(builtRecord)
        del itemDeepCopy["body"]
        recordWithoutBodySize = sys.getsizeof(json.dumps(itemDeepCopy))
        recordSize = bodySize + recordWithoutBodySize

        ballast = ""
        while (getsizeof(ballast) * 2) + recordSize < 400_000:
            ballast = ballast + "a"
        record["indexes"]["ballast"] = ballast

    def createModifyInsertRecord(self, internalID, nhsNumber, modification=None, nominated=False):
        """
        Create a record, modifying so as not to be returned by a query and adding its keys to those to be cleaned-up.
        """
        recordId = self.generateRecordKey()
        self.keys.append((recordId, SortKey.RECORD.value))
        record = self.getNominatedRecord(nhsNumber) if nominated else self.getRecord(nhsNumber)
        if modification:
            modification(record)
        self.datastore.insert_eps_record_object(internalID, recordId, record)
        return recordId

    def testBuildTermsWithRegex(self):
        """
        Test building terms from indexes of returned records, including regex checks.
        """
        nhsNumber = self.generateNhsNumber()
        releaseVersion = "R2"
        items = [
            {
                Key.PK.name: self.generatePrescriptionId(),
                ProjectedAttribute.INDEXES.name: {
                    indexes.INDEX_NHSNUMBER_DATE.lower(): [
                        f"{nhsNumber}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                        f"{nhsNumber}|{CREATION_TIME}|R1|{PrescriptionStatus.TO_BE_DISPENSED}",
                        f"{nhsNumber}|{CREATION_TIME}|R2|{PrescriptionStatus.AWAITING_RELEASE_READY}",
                    ]
                },
            }
        ]
        termRegex = r"\|\d{8,14}\|" + releaseVersion + r"\|" + PrescriptionStatus.TO_BE_DISPENSED
        terms = self.datastore.indexes.build_terms(items, indexes.INDEX_NHSNUMBER_DATE, termRegex)

        self.assertEqual(len(terms), 1)

    def test_return_terms_by_nhs_number_date(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberDate records.
        """
        nhsNumber = self.generateNhsNumber()
        creationTimes = ["20230911000000", "20230912000000", "20230913000000", "20230914000000"]

        recordValues = [
            SimpleNamespace(id=self.generateRecordKey(), creationTime=time)
            for time in creationTimes
        ]

        for values in recordValues:
            record = self.getRecord(nhsNumber, values.creationTime)
            self.datastore.insert_eps_record_object(self.internalID, values.id, record)
            self.keys.append((values.id, SortKey.RECORD.value))

        startDate = "20230912"
        endDate = "20230913"
        rangeStart = indexes.SEPERATOR.join([nhsNumber, startDate])
        rangeEnd = indexes.SEPERATOR.join([nhsNumber, endDate])

        terms = self.datastore.return_terms_by_nhs_number_date(
            self.internalID, rangeStart, rangeEnd
        )

        expected = [
            (
                f"{nhsNumber}|{values.creationTime}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                values.id,
            )
            for values in recordValues[1:-1]
        ]

        self.assertEqual(expected, terms)

    def testReturnTermsByNhsNumberSameDate(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberDate records.
        Start and end date are the same.
        """
        nhsNumber = self.generateNhsNumber()
        creationTimes = ["20230911000000", "20230911000000"]

        recordValues = [
            SimpleNamespace(id=self.generateRecordKey(), creationTime=time)
            for time in creationTimes
        ]

        for values in recordValues:
            record = self.getRecord(nhsNumber, values.creationTime)
            self.datastore.insert_eps_record_object(self.internalID, values.id, record)
            self.keys.append((values.id, SortKey.RECORD.value))

        date = "20230911"
        rangeStart = indexes.SEPERATOR.join([nhsNumber, date])
        rangeEnd = indexes.SEPERATOR.join([nhsNumber, date])

        terms = self.datastore.return_terms_by_nhs_number_date(
            self.internalID, rangeStart, rangeEnd
        )

        expected = [
            (
                f"{nhsNumber}|{values.creationTime}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                values.id,
            )
            for values in recordValues
        ]

        self.assertEqual(sorted(expected), sorted(terms))

    def test_return_terms_by_nhs_number(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberDate records, without startDate.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        terms = self.datastore.return_terms_by_nhs_number(self.internalID, nhsNumber)

        expected = [(nhsNumber, prescriptionId)]

        self.assertEqual(expected, terms)

    def testExcludeNextActivityPurge(self):
        """
        Test querying against a record index and excluding records with a nextActivity of purge.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        prescriptionId2 = self.generateRecordKey()
        self.keys.append((prescriptionId2, SortKey.RECORD.value))
        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId2, record)

        terms = self.datastore.return_terms_by_nhs_number(self.internalID, nhsNumber)

        expected = [(nhsNumber, prescriptionId), (nhsNumber, prescriptionId2)]
        self.assertEqual(sorted(expected), sorted(terms))

        record["indexes"]["nextActivityNAD_bin"] = ["purge_20241114"]
        record["SCN"] = record["SCN"] + 1
        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId2, record, isUpdate=True
        )

        terms = self.datastore.return_terms_by_nhs_number(self.internalID, nhsNumber)

        expected = [(nhsNumber, prescriptionId)]
        self.assertEqual(expected, terms)

    def test_return_terms_by_nhs_number_multiple(self):
        """
        Test querying against the nhsNumberDate index and returning multiple nhsNumberDate records, without startDate.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        self.createModifyInsertRecord(self.internalID, nhsNumber)

        terms = self.datastore.return_terms_by_nhs_number(self.internalID, nhsNumber)

        self.assertEqual(len(terms), 2)

    def testReturnTermsByNomPharmStatus(self):
        """
        Test querying against the nomPharmStatus index and returning nomPharmStatus records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getNominatedRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyStatus, nominated=True)

        terms = self.datastore.get_nom_pharm_records_unfiltered(self.internalID, NOM_ORG)

        expected = [prescriptionId]

        self.assertEqual(expected, terms)

    def testReturnTermsByNomPharmStatusWithBatchSize(self):
        """
        Test querying against the nomPharmStatus index via the get_nominated_pharmacy_records method and returning
        a defined number of nomPharmStatus records.
        """
        prescriptionIds = []
        for _ in range(3):
            prescriptionId, nhsNumber = self.getNewRecordKeys()
            record = self.getNominatedRecord(nhsNumber)
            self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)
            self.createModifyInsertRecord(
                self.internalID, nhsNumber, self.modifyStatus, nominated=True
            )
            prescriptionIds.append(prescriptionId)

        returnedPrescriptionIds, discardedCount = self.datastore.get_nominated_pharmacy_records(
            NOM_ORG, 2, self.internalID
        )

        self.assertEqual(discardedCount, 1)
        self.assertEqual(len(returnedPrescriptionIds), 2)
        self.assertTrue(set(returnedPrescriptionIds).issubset(set(prescriptionIds)))

    def testReturnTermsByNomPharmStatusWithPagination(self):
        """
        Test querying against the nomPharmStatus index and returning nomPharmStatus records.
        Index attribute value is made artificially large, so that when projected into the index,
        the combined returned items breach the pagination threshold.
        """
        totalTerms = 7
        nhsNumber = self.generateNhsNumber()
        [
            self.createModifyInsertRecord(
                self.internalID, nhsNumber, self.addBallastToRecord, nominated=True
            )
            for _ in range(totalTerms)
        ]

        terms = self.datastore.get_nom_pharm_records_unfiltered(self.internalID, NOM_ORG)

        self.assertEqual(len(terms), totalTerms)

    def testReturnTermsByNomPharmStatusUnfilteredWithLimit(self):
        """
        Test querying against the nomPharmStatus index and returning nomPharmStatus records.
        Provide a limit for the query to adhere to.
        """
        totalTerms = 3
        limit = 2
        nhsNumber = self.generateNhsNumber()
        [
            self.createModifyInsertRecord(self.internalID, nhsNumber, nominated=True)
            for _ in range(totalTerms)
        ]

        terms = self.datastore.get_nom_pharm_records_unfiltered(
            self.internalID, NOM_ORG, limit=limit
        )

        self.assertEqual(len(terms), limit)

    def testReturnTermsByNomPharmStatusUnfilteredWithLimitAndPagination(self):
        """
        Test querying against the nomPharmStatus index and returning nomPharmStatus records.
        Provide a limit for the query to adhere to combined with pagination.
        """
        totalTerms = 7
        limit = 6
        nhsNumber = self.generateNhsNumber()
        [
            self.createModifyInsertRecord(
                self.internalID, nhsNumber, self.addBallastToRecord, nominated=True
            )
            for _ in range(totalTerms)
        ]

        terms = self.datastore.get_nom_pharm_records_unfiltered(
            self.internalID, NOM_ORG, limit=limit
        )

        self.assertEqual(len(terms), limit)

    def testReturnTermsByNomPharm(self):
        """
        Test querying against the nomPharmStatus index using only the odsCode and returning nomPharmStatus records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getNominatedRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        idOfPrescriptionWithOtherStatus = self.createModifyInsertRecord(
            self.internalID, nhsNumber, self.modifyStatus, nominated=True
        )

        terms = self.datastore.get_all_pids_by_nominated_pharmacy(self.internalID, NOM_ORG)

        expected = [prescriptionId, idOfPrescriptionWithOtherStatus]

        expected.sort()
        terms.sort()

        self.assertEqual(expected, terms)

    def test_return_terms_by_nhs_number_date_erd(self):
        """
        Test querying against the nhsNumberDate index and returning multiple nhsNumberDates per record.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getErdRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        rangeStart = f"{nhsNumber}|20230911"
        rangeEnd = f"{nhsNumber}|20230912"
        terms = self.datastore.return_terms_by_nhs_number_date(
            self.internalID, rangeStart, rangeEnd
        )

        expected = [
            (
                f"{nhsNumber}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescriptionId,
            ),
            (
                f"{nhsNumber}|{CREATION_TIME}|R2|{PrescriptionStatus.REPEAT_DISPENSE_FUTURE_INSTANCE}",
                prescriptionId,
            ),
        ]

        self.assertEqual(expected, terms)

    def testReturnTermsByNhsNumberPrescriberDispenserDate(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberPrescriberDispenserDate records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId, self.getRecord(nhsNumber)
        )

        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyPrescriber)
        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyDispenser)

        startDate = "20230911"
        endDate = "20230912"
        rangeStart = indexes.SEPERATOR.join([nhsNumber, PRESC_ORG, DISP_ORG, startDate])
        rangeEnd = indexes.SEPERATOR.join([nhsNumber, PRESC_ORG, DISP_ORG, endDate])

        terms = self.datastore.return_terms_by_index_date(
            self.internalID, indexes.INDEX_NHSNUMBER_PRDSDATE, rangeStart, rangeEnd
        )

        expected = [
            (
                f"{nhsNumber}|{PRESC_ORG}|{DISP_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescriptionId,
            )
        ]

        self.assertEqual(expected, terms)

    def testReturnTermsByNhsNumberPrescriberDate(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberPrescriberDate records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId, self.getRecord(nhsNumber)
        )

        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyPrescriber)

        startDate = "20230911"
        endDate = "20230912"
        rangeStart = indexes.SEPERATOR.join([nhsNumber, PRESC_ORG, startDate])
        rangeEnd = indexes.SEPERATOR.join([nhsNumber, PRESC_ORG, endDate])

        terms = self.datastore.return_terms_by_index_date(
            self.internalID, indexes.INDEX_NHSNUMBER_PRDATE, rangeStart, rangeEnd
        )

        expected = [
            (
                f"{nhsNumber}|{PRESC_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescriptionId,
            )
        ]

        self.assertEqual(expected, terms)

    def testReturnTermsByNhsNumberDispenserDate(self):
        """
        Test querying against the nhsNumberDate index and returning nhsNumberDispenserDate records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId, self.getRecord(nhsNumber)
        )

        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyDispenser)

        startDate = "20230911"
        endDate = "20230912"
        rangeStart = indexes.SEPERATOR.join([nhsNumber, DISP_ORG, startDate])
        rangeEnd = indexes.SEPERATOR.join([nhsNumber, DISP_ORG, endDate])

        terms = self.datastore.return_terms_by_index_date(
            self.internalID, indexes.INDEX_NHSNUMBER_DSDATE, rangeStart, rangeEnd
        )

        expected = [
            (
                f"{nhsNumber}|{DISP_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescriptionId,
            )
        ]

        self.assertEqual(expected, terms)

    def testReturnTermsByPrescriberDispenserDate(self):
        """
        Test querying against the prescriberDate index and returning prescDispDate records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId, self.getRecord(nhsNumber)
        )

        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyPrescriber)
        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyDispenser)

        startDate = "20230911"
        endDate = "20230912"
        rangeStart = indexes.SEPERATOR.join([PRESC_ORG, DISP_ORG, startDate])
        rangeEnd = indexes.SEPERATOR.join([PRESC_ORG, DISP_ORG, endDate])

        terms = self.datastore.return_terms_by_index_date(
            self.internalID, indexes.INDEX_PRESCRIBER_DSDATE, rangeStart, rangeEnd
        )

        expected = [
            (
                f"{PRESC_ORG}|{DISP_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}",
                prescriptionId,
            )
        ]

        self.assertEqual(expected, terms)

    def testReturnTermsByPrescriberDate(self):
        """
        Test querying against the prescriberDate index and returning prescriberDate records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId, self.getRecord(nhsNumber)
        )

        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyPrescriber)

        startDate = "20230911"
        endDate = "20230912"
        rangeStart = indexes.SEPERATOR.join([PRESC_ORG, startDate])
        rangeEnd = indexes.SEPERATOR.join([PRESC_ORG, endDate])

        terms = self.datastore.return_terms_by_index_date(
            self.internalID, indexes.INDEX_PRESCRIBER_DATE, rangeStart, rangeEnd
        )

        expected = [
            (f"{PRESC_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}", prescriptionId)
        ]

        self.assertEqual(expected, terms)

    def testReturnTermsByDispenserDate(self):
        """
        Test querying against the dispenserDate index and returning dispenserDate records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId, self.getRecord(nhsNumber)
        )

        self.createModifyInsertRecord(self.internalID, nhsNumber, self.modifyDispenser)

        startDate = "20230911"
        endDate = "20230912"
        rangeStart = indexes.SEPERATOR.join([DISP_ORG, startDate])
        rangeEnd = indexes.SEPERATOR.join([DISP_ORG, endDate])

        terms = self.datastore.return_terms_by_index_date(
            self.internalID, indexes.INDEX_DISPENSER_DATE, rangeStart, rangeEnd
        )

        expected = [
            (f"{DISP_ORG}|{CREATION_TIME}|R2|{PrescriptionStatus.TO_BE_DISPENSED}", prescriptionId)
        ]

        self.assertEqual(expected, terms)

    def testItemsWithoutBatchClaimIdNotAddedToClaimIdIndex(self):
        """
        Test claimId index doesn't contain any items without a batchClaimId attribute.
        """
        batchClaimIds = []
        for _ in range(2):
            batchId = str(uuid4())
            batchClaimIds.append(batchId)
            self.keys.append((batchId, SortKey.CLAIM.value))

        batchClaims = [
            {
                Key.PK.name: batchClaimIds[0],
                Key.SK.name: SortKey.CLAIM.value,
                Attribute.BATCH_CLAIM_ID.name: batchClaimIds[0],
                ProjectedAttribute.BODY.name: "testBody",
            },
            {
                Key.PK.name: batchClaimIds[1],
                Key.SK.name: SortKey.CLAIM.value,
                ProjectedAttribute.BODY.name: "testBody",
            },
        ]
        [self.datastore.client.putItem(self.internalID, batchClaim) for batchClaim in batchClaims]

        keyConditionExpression = BotoKey(Key.SK.name).eq(SortKey.CLAIM.value)
        items = self.datastore.client.queryIndex(GSI.CLAIM_ID.name, keyConditionExpression, None)
        self.assertEqual(len(items), 1)

    def testQueryNextActivityDate(self):
        """
        Test querying against the nextActivityDate index and returning lists of prescription keys.
        """
        expected = []
        for _ in range(3):
            prescriptionId, nhsNumber = self.getNewRecordKeys()
            expected.append(prescriptionId)
            record = self.getRecord(nhsNumber)
            self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        actual = self.datastore.return_pids_due_for_next_activity(
            self.internalID, "createNoClaim_20250103", "createNoClaim_20250105"
        )
        flat = [i for generator in actual for i in generator]
        self.assertEqual(len(flat), 3)

    def testQueryNextActivitySameDate(self):
        """
        Test querying against the nextActivityDate index and
        returning lists of prescription keys when dates are the same.
        """
        expected = []
        for _ in range(3):
            prescriptionId, nhsNumber = self.getNewRecordKeys()
            expected.append(prescriptionId)
            record = self.getRecord(nhsNumber)
            self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        actual = self.datastore.return_pids_due_for_next_activity(
            self.internalID, "createNoClaim_20250104", "createNoClaim_20250104"
        )
        flat = [i for generator in actual for i in generator]
        self.assertEqual(len(flat), 3)

    # (a,) notation is to force a single item tuple as expected by parameterized.expand
    @parameterized.expand(
        [
            (PrescriptionRecord.NEXTACTIVITY_EXPIRE,),
            (PrescriptionRecord.NEXTACTIVITY_CREATENOCLAIM,),
            (PrescriptionRecord.NEXTACTIVITY_DELETE,),
            (PrescriptionRecord.NEXTACTIVITY_PURGE,),
            (PrescriptionRecord.NEXTACTIVITY_READY,),
        ]
    )
    def testQueryNextActivityDateAllActivities(self, nextActivity):
        """
        Test query works against all next activities
        """
        nextActivityNAD_bin = f"{nextActivity}_20250104"

        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)
        record["indexes"]["nextActivityNAD_bin"] = [nextActivityNAD_bin]
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        actual = self.datastore.return_pids_due_for_next_activity(
            self.internalID, nextActivityNAD_bin, nextActivityNAD_bin
        )
        flat = [i for generator in actual for i in generator]
        self.assertEqual(flat, [prescriptionId])

    def testQueryNextActivityDateShards(self):
        """
        Test query works against records on all shards
        """
        expected = []

        def add_record(nextActivity):
            """
            Add a record to the table with a given next activity shard, and append its prescriptionId to expected list
            """
            prescriptionId, nhsNumber = self.getNewRecordKeys()
            record = self.getRecord(nhsNumber)
            item = self.datastore.build_record(prescriptionId, record, None, None)

            item[Attribute.NEXT_ACTIVITY.name] = nextActivity

            self.datastore.client.insertItems(self.internalID, [item], False)
            expected.append([prescriptionId])

        # Add unsharded record
        add_record("createNoClaim")

        # Add a record on each shard
        for shard in range(1, NEXT_ACTIVITY_DATE_PARTITIONS + 1):
            add_record(f"createNoClaim.{shard}")

        actual = self.datastore.return_pids_due_for_next_activity(
            self.internalID, "createNoClaim_20250104", "createNoClaim_20250104"
        )
        consumed = [list(generator) for generator in list(actual)]

        self.assertEqual(expected, consumed)

    def testQueryClaimNotificationStoreTime(self):
        """
        Test querying against the claimNotificationStoreTime index and returning lists of document keys.
        """
        documentKeys = []

        def createDocuments(docRefTitle):
            for i in range(3):
                index = {
                    indexes.INDEX_STORE_TIME_DOC_REF_TITLE: [f"{docRefTitle}_2024091110111{i}"],
                    indexes.INDEX_DELETE_DATE: ["20250911"],
                    indexes.INDEX_PRESCRIPTION_ID: [self.generatePrescriptionId()],
                }

                documentKey = f"20240911_{docRefTitle}_{i}"
                documentKeys.append(documentKey)
                self.keys.append((documentKey, SortKey.DOCUMENT.value))

                content = self.getDocumentContent()
                self.datastore.insert_eps_document_object(
                    self.internalID, documentKey, {"content": content}, index
                )

        [createDocuments(docRefTitle) for docRefTitle in ["ClaimNotification", "Other"]]

        queryResponse = self.datastore.return_claim_notification_ids_between_store_dates(
            self.internalID, "20240911101111", "20240912101111"
        )

        actual = list(queryResponse)
        expected = [["20240911_ClaimNotification_1", "20240911_ClaimNotification_2"], []]

        self.assertEqual(actual, expected)

    def testQueryClaimNotificationStoreTimeBoundaries(self):
        """
        Test querying against the claimNotificationStoreTime index and returning lists of document keys.
        Creates two documents relating to each boundary argument. Asserts that one of each pair is returned.
        """
        documentKeys = []

        def createDocuments(storeDate):
            for i in range(2):
                index = {
                    indexes.INDEX_STORE_TIME_DOC_REF_TITLE: [
                        f"ClaimNotification_{storeDate}10111{i}"
                    ],
                    indexes.INDEX_DELETE_DATE: ["20250911"],
                    indexes.INDEX_PRESCRIPTION_ID: [self.generatePrescriptionId()],
                }

                documentKey = f"{storeDate}_ClaimNotification_{i}"
                documentKeys.append(documentKey)
                self.keys.append((documentKey, SortKey.DOCUMENT.value))

                content = self.getDocumentContent()
                self.datastore.insert_eps_document_object(
                    self.internalID, documentKey, {"content": content}, index
                )

        [createDocuments(storeDate) for storeDate in ["20240911", "20240912"]]

        queryResponse = self.datastore.return_claim_notification_ids_between_store_dates(
            self.internalID, "20240911101111", "20240912101110"
        )

        actual = list(queryResponse)
        expected = [["20240911_ClaimNotification_1"], ["20240912_ClaimNotification_0"]]

        self.assertEqual(actual, expected)

    def testGetDateRangeForQuery(self):
        """
        Test method for creating dates to query indexes against.
        Method is inclusive, so slightly less than one day gives both relevant days.
        """
        startDatetimeStr = "20250911101112"
        endDatetimeStr = "20250912101111"

        actual = self.datastore.indexes._getDateRangeForQuery(startDatetimeStr, endDatetimeStr)
        expected = ["20250911", "20250912"]

        self.assertEqual(actual, expected)

    @parameterized.expand(
        [
            ["queryNhsNumberDate", ["index", "nhsNumber"], [], str],
            ["queryPrescriberDate", ["index", "org"], [], str],
            ["queryDispenserDate", ["index", "org"], [], str],
            ["queryNextActivityDate", [], [], lambda x: f"_{x}"],
        ]
    )
    def testInvalidRanges(self, index, preargs, postargs, inputFormatter=None):
        """
        Test querying against indexes with invalid ranges.
        """
        inputValues = [2, 1]
        if inputFormatter:
            inputValues = [inputFormatter(i) for i in inputValues]

        args = preargs + inputValues + postargs

        self.assertEqual(list(getattr(self.datastore.indexes, index)(*args)), [])

    def testQueryBatchClaimIdSequenceNumber(self):
        """
        Test querying against the claimIdSequenceNumber(Nwssp) indexes and returning lists of batch claim IDs.
        """
        batchClaim1 = [str(uuid4()), 1, False]
        batchClaim2 = [str(uuid4()), 2, False]

        nwsspBatchClaim1 = [str(uuid4()), 1, True]
        nwsspBatchClaim2 = [str(uuid4()), 2, True]

        for batchClaim in [batchClaim1, batchClaim2, nwsspBatchClaim1, nwsspBatchClaim2]:
            batchClaimId, sqnValue, nwssp = batchClaim
            self.keys.append((batchClaimId, SortKey.CLAIM.value))

            batchClaim = {
                "Batch GUID": batchClaimId,
                "Claim ID List": [],
                "Handle Time": "20241111121314",
                "Sequence Number": sqnValue,
                "Batch XML": b"<xml />",
            }
            if nwssp:
                batchClaim["Nwssp Sequence Number"] = sqnValue

            self.datastore.store_batch_claim(self.internalID, batchClaim)

        returnedBatchClaimIds = self.datastore.find_batch_claim_from_seq_number(1)
        self.assertEqual(returnedBatchClaimIds, [batchClaim1[0]])

        returnedBatchClaimIds = self.datastore.find_batch_claim_from_seq_number(2, True)
        self.assertEqual(returnedBatchClaimIds, [nwsspBatchClaim2[0]])

    @parameterized.expand(
        [
            [("20240911", "20240912"), ("20240911000000", "20240912000000")],
            [("2024091112", "2024091213"), ("20240911120000", "20240912130000")],
            [("20240911121314", "20240912131415"), ("20240911121314", "20240912131415")],
        ]
    )
    def testPadOrTrimDate(self, inputDates, expectedDates):
        """
        Test padding or trimming dates used in index queries.
        """
        startDate, endDate = inputDates
        expectedStartDate, expectedEndDate = expectedDates

        actualStartDate = self.datastore.indexes.pad_or_trim_date(startDate)
        actualEndDate = self.datastore.indexes.pad_or_trim_date(endDate)

        self.assertEqual(expectedStartDate, actualStartDate)
        self.assertEqual(expectedEndDate, actualEndDate)

    @patch("random.randint")
    def testLastModifiedIndex(self, patchedRandint):
        """
        Test lastModified index by calling directly. It is not used from application code.
        """
        patchedRandint.return_value = 7

        indexName = GSI.LAST_MODIFIED.name
        pk = str(uuid4())
        self.keys.append((pk, "SK"))

        dateTime = datetime.datetime.now() + datetime.timedelta(weeks=30)

        dateTimeDecimal = Decimal(str(dateTime.timestamp()))
        dateTimeInt = int(dateTime.timestamp())

        day = dateTime.strftime("%Y%m%d")
        item = {Key.PK.name: pk, Key.SK.name: "SK"}

        with freeze_time(dateTime):
            self.datastore.client.insertItems(self.internalID, [item], logItemSize=False)

        for timestamp in [dateTimeDecimal, dateTimeInt]:
            keyConditionExpression = BotoKey(Attribute.LM_DAY.name).eq(f"{day}.7") & BotoKey(
                Attribute.RIAK_LM.name
            ).gte(timestamp)

            items = self.datastore.client.queryIndex(indexName, keyConditionExpression, None)

            self.assertEqual(len(items), 1)
