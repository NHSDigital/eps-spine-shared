import base64
import binascii
import zlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Thread
from unittest.mock import Mock, patch
from uuid import uuid4

import simplejson
from boto3.dynamodb.types import Binary
from freezegun import freeze_time
from parameterized import parameterized

from eps_spine_shared.common import indexes
from eps_spine_shared.common.dynamodb_client import EpsDataStoreError
from eps_spine_shared.common.dynamodb_common import (
    NEXT_ACTIVITY_DATE_PARTITIONS,
    Attribute,
    Key,
    ProjectedAttribute,
    SortKey,
    replace_decimals,
)
from eps_spine_shared.common.dynamodb_datastore import EpsDynamoDbDataStore
from eps_spine_shared.common.prescription_record import PrescriptionStatus
from eps_spine_shared.nhsfundamentals.timeutilities import TimeFormats
from tests.dynamodb_test import DynamoDbTest
from tests.mock_logger import MockLogObject


class DynamoDbDataStoreTest(DynamoDbTest):
    """
    Tests relating to DynamoDbDataStore.
    """

    def testInsertRecord(self):
        """
        Test datastore can insert records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)

        response = self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        self.assertEqual(response["ResponseMetadata"]["HTTPStatusCode"], 200)

    def testIncludeRecordType(self):
        """
        Test datastore can insert records including recordType and retrieve records with it included.
        """
        repeatDispense = "RepeatDispense"
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)

        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId, record, None, repeatDispense
        )
        returnedRecord = self.datastore.return_record_for_process(self.internalID, prescriptionId)

        self.assertEqual(returnedRecord["recordType"], repeatDispense)

    def testInsertDuplicate(self):
        """
        Test datastore will not overwrite records.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        record["instances"]["1"]["prescriptionStatus"] = PrescriptionStatus.AWAITING_RELEASE_READY

        with self.assertRaises(EpsDataStoreError) as cm:
            self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)
        self.assertEqual(cm.exception.errorTopic, EpsDataStoreError.DUPLICATE_ERROR)

        returnedRecord = self.datastore.return_record_for_process(self.internalID, prescriptionId)
        returnedRecordStatus = returnedRecord["value"]["instances"]["1"]["prescriptionStatus"]

        self.assertEqual(returnedRecordStatus, PrescriptionStatus.TO_BE_DISPENSED)
        self.assertEqual(self.logger.logOccurrenceCount("DDB0021"), 1)

    def testInsertMultiple(self):
        """
        Test client can insert multiple items.
        """
        items = []
        for _ in range(2):
            recordKey, _ = self.getNewRecordKeys()
            items.append({Key.PK.name: recordKey, Key.SK.name: "DEF"})

        response = self.datastore.client.insertItems(self.internalID, items)

        self.assertEqual(response["ResponseMetadata"]["HTTPStatusCode"], 200)

    def testClientPut(self):
        """
        Test put_item is used when one item.
        """
        mockClient = Mock()
        self.datastore.client.client = mockClient
        self.datastore.client.insertItems(self.internalID, [{}], logItemSize=False)
        mockClient.put_item.assert_called_once()

    def testClientTransact(self):
        """
        Test transact_write_items is used when multiple items.
        """
        mockClient = Mock()
        self.datastore.client.client = mockClient
        self.datastore.client.insertItems(self.internalID, [{}, {}], logItemSize=False)
        mockClient.transact_write_items.assert_called_once()

    def test_return_record_for_process(self):
        """
        Test querying against the prescriptionId index and
        returning a record with additional required attributes.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.assertFalse(self.datastore.isRecordPresent(self.internalID, prescriptionId))

        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        returnedRecord = self.datastore.return_record_for_process(self.internalID, prescriptionId)

        expectedRecord = {"value": record, "vectorClock": "vc", "releaseVersion": "R2"}

        self.assertEqual(expectedRecord, returnedRecord)
        self.assertEqual(type(returnedRecord["value"]["prescription"]["daysSupply"]), int)

    def test_return_record_for_update(self):
        """
        Test querying against the prescriptionId index and
        returning a record with additional required attributes, including setting it on the dataStore.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.assertFalse(self.datastore.is_record_present(self.internalID, prescriptionId))

        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        returnedRecord = self.datastore.return_record_for_update(self.internalID, prescriptionId)

        expectedRecord = {"value": record, "vectorClock": "vc", "releaseVersion": "R2"}

        self.assertEqual(expectedRecord, returnedRecord)
        self.assertEqual(record, self.datastore.dataObject)

    def test_change_eps_object(self):
        """
        Test update to existing record.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.assertFalse(self.datastore.is_record_present(self.internalID, prescriptionId))

        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        record["SCN"] = 2
        self.datastore.insert_eps_record_object(
            self.internalID, prescriptionId, record, isUpdate=True
        )

        updatedRecord = self.datastore.return_record_for_process(self.internalID, prescriptionId)

        expectedRecord = {"value": record, "vectorClock": "vc", "releaseVersion": "R2"}

        self.assertEqual(expectedRecord, updatedRecord)

    def testChangeEPSObjectSameScn(self):
        """
        Test failed update to existing record due to no increment to SCN.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.assertFalse(self.datastore.is_record_present(self.internalID, prescriptionId))

        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        modifiedRecord = self.getRecord(nhsNumber)
        modifiedRecord["instances"]["1"][
            "prescriptionStatus"
        ] = PrescriptionStatus.AWAITING_RELEASE_READY

        with self.assertRaises(EpsDataStoreError) as cm:
            self.datastore.insert_eps_record_object(
                self.internalID, prescriptionId, modifiedRecord, isUpdate=True
            )
        self.assertEqual(cm.exception.errorTopic, EpsDataStoreError.CONDITIONAL_UPDATE_FAILURE)

        self.assertEqual(self.logger.logOccurrenceCount("DDB0022"), 1)

        updatedRecord = self.datastore.return_record_for_process(self.internalID, prescriptionId)

        expectedRecord = {"value": record, "vectorClock": "vc", "releaseVersion": "R2"}

        self.assertEqual(expectedRecord, updatedRecord)

    def testTimer(self):
        """
        Test timer decorator writes desired log.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)

        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        occurrences = self.logger.getLogOccurrences("DDB0002")
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0]["func"], "insert_eps_record_object")
        self.assertEqual(occurrences[0]["cls"], "EpsDynamoDbDataStore")

    def testInsertAndGetEPSWorkList(self):
        """
        Test insertion and retrieval of EPS worklist, compressing/decompressing its XML.
        """
        messageId = str(uuid4())
        self.keys.append((messageId, SortKey.WORK_LIST.value))

        xml = "<data />"
        xmlBytes = xml.encode("utf-8")

        for responseDetails in [xml, xmlBytes]:
            workList = {
                Key.SK.name: SortKey.WORK_LIST.value,
                "keyList": [],
                "responseDetails": {"XML": responseDetails},
            }
            self.datastore.insert_eps_work_list(self.internalID, messageId, workList)

            returnedWorkList = self.datastore.get_work_list(self.internalID, messageId)

            self.assertEqual(returnedWorkList["responseDetails"]["XML"], xmlBytes)
            self.assertEqual(workList["responseDetails"]["XML"], responseDetails)

    def testFetchNextSequenceNumber(self):
        """
        Test fetching and incrementing claims sequence number.
        """
        self.keys.append((self.datastore.CLAIM_SEQUENCE_NUMBER_KEY, SortKey.SEQUENCE_NUMBER.value))
        self.datastore.client.deleteItem(
            self.datastore.CLAIM_SEQUENCE_NUMBER_KEY, SortKey.SEQUENCE_NUMBER.value
        )

        sequenceNumber = self.datastore.fetch_next_sequence_number(self.internalID, 2)
        self.assertEqual(sequenceNumber, 1)

        sequenceNumber = self.datastore.fetch_next_sequence_number(self.internalID, 2, True)
        self.assertEqual(sequenceNumber, 2)

        sequenceNumber = self.datastore.fetch_next_sequence_number(self.internalID, 2)
        self.assertEqual(sequenceNumber, 2)

        sequenceNumber = self.datastore.fetch_next_sequence_number(self.internalID, 2)
        self.assertEqual(sequenceNumber, 1)

    def testFetchNextSequenceNumberNwssp(self):
        """
        Test fetching and incrementing claims sequence number.
        """
        self.keys.append(
            (self.datastore.NWSSP_CLAIM_SEQUENCE_NUMBER_KEY, SortKey.SEQUENCE_NUMBER.value)
        )
        self.datastore.client.deleteItem(
            self.datastore.NWSSP_CLAIM_SEQUENCE_NUMBER_KEY, SortKey.SEQUENCE_NUMBER.value
        )

        sequenceNumber = self.datastore.fetch_next_sequence_number_nwssp(self.internalID, 2)
        self.assertEqual(sequenceNumber, 1)

        sequenceNumber = self.datastore.fetch_next_sequence_number_nwssp(self.internalID, 2, True)
        self.assertEqual(sequenceNumber, 2)

        sequenceNumber = self.datastore.fetch_next_sequence_number_nwssp(self.internalID, 2)
        self.assertEqual(sequenceNumber, 2)

        sequenceNumber = self.datastore.fetch_next_sequence_number_nwssp(self.internalID, 2)
        self.assertEqual(sequenceNumber, 1)

    @patch("random.randint")
    def testStoreBatchClaim(self, patchedRandint):
        """
        Test creating and storing a batch claim.
        """
        patchedRandint.return_value = 7

        self.keys.append(("batchGuid", SortKey.CLAIM.value))
        batchClaim = {
            "Batch GUID": "batchGuid",
            "Claim ID List": ["claimId1", "claimId2"],
            "Handle Time": "handleTime",
            "Sequence Number": 1,
            "Nwssp Sequence Number": 2,
            "Batch XML": b"<xml />",
        }
        dtNow = datetime.now(timezone.utc)
        with freeze_time(dtNow):
            self.datastore.store_batch_claim(self.internalID, batchClaim)

        returnedBatchClaim = self.datastore.client.getItem(
            self.internalID, "batchGuid", SortKey.CLAIM.value
        )
        replace_decimals(returnedBatchClaim)
        returnedBatchClaim["body"]["Batch XML"] = bytes(returnedBatchClaim["body"]["Batch XML"])

        expected = {
            Key.PK.name: "batchGuid",
            Key.SK.name: SortKey.CLAIM.value,
            ProjectedAttribute.BODY.name: batchClaim,
            ProjectedAttribute.INDEXES.name: {
                self.datastore.INDEX_CLAIMID: ["claimId1", "claimId2"],
                self.datastore.INDEX_CLAIMHANDLETIME: ["handleTime"],
                self.datastore.INDEX_CLAIM_SEQNUMBER: [1],
                self.datastore.INDEX_SCN: [
                    f"{dtNow.strftime(TimeFormats.STANDARD_DATE_TIME_FORMAT)}|1"
                ],
                self.datastore.INDEX_CLAIM_SEQNUMBER_NWSSP: [2],
            },
            ProjectedAttribute.CLAIM_IDS.name: ["claimId1", "claimId2"],
            Attribute.SEQUENCE_NUMBER_NWSSP.name: 2,
            ProjectedAttribute.EXPIRE_AT.name: int(
                (dtNow + timedelta(days=self.datastore.DEFAULT_EXPIRY_DAYS)).timestamp()
            ),
            Attribute.RIAK_LM.name: float(str(dtNow.timestamp())),
            Attribute.LM_DAY.name: dtNow.strftime("%Y%m%d") + ".7",
            Attribute.BATCH_CLAIM_ID.name: "batchGuid",
        }
        self.assertEqual(returnedBatchClaim, expected)

        fetchedBatchClaim = self.datastore.fetch_batch_claim(self.internalID, "batchGuid")
        batchXml = fetchedBatchClaim["Batch XML"]
        self.assertEqual(batchXml, "<xml />")

    def testDeleteClaimNotification(self):
        """
        Test deleting a claim notification from the table.
        """
        documentKey = uuid4()
        notificationKey = self.datastore.NOTIFICATION_PREFIX + str(documentKey)
        content = self.getDocumentContent()
        self.datastore.insert_eps_document_object(
            self.internalID, notificationKey, {"content": content}
        )

        returnedBody = self.datastore.return_document_for_process(self.internalID, notificationKey)
        self.assertEqual(returnedBody, {"content": content})

        self.datastore.delete_claim_notification(self.internalID, documentKey)
        self.assertRaises(
            EpsDataStoreError,
            self.datastore.return_document_for_process,
            notificationKey,
            self.internalID,
        )

    def testReturnClaimNotification(self):
        """
        Test returning a claim notification from the table.
        Claim notification has content under payload key instead of content, so won't be b64 decoded/encoded.
        """
        documentKey = uuid4()
        notificationKey = self.datastore.NOTIFICATION_PREFIX + str(documentKey)
        content = self.getDocumentContent()
        index = {
            indexes.INDEX_STORE_TIME_DOC_REF_TITLE: ["ClaimNotification_20250911"],
            indexes.INDEX_DELETE_DATE: ["20250911"],
            indexes.INDEX_PRESCRIPTION_ID: str(uuid4()),
        }
        self.datastore.insert_eps_document_object(
            self.internalID, notificationKey, {"payload": content}, index
        )

        returnedBody = self.datastore.return_document_for_process(self.internalID, notificationKey)
        self.assertEqual(returnedBody, {"payload": content})

    def testDeleteDocument(self):
        """
        Test deleting a document from the table.
        """
        documentKey = self.generateDocumentKey()
        content = self.getDocumentContent()
        self.datastore.insert_eps_document_object(
            self.internalID, documentKey, {"content": content}
        )

        self.assertTrue(self.datastore.delete_document(self.internalID, documentKey))

    def testDeleteRecord(self):
        """
        Test deleting a record from the table.
        """
        recordKey = self.generateRecordKey()
        nhsNumber = self.generateNhsNumber()
        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, recordKey, record)

        self.datastore.delete_record(self.internalID, recordKey)

        self.assertFalse(
            self.datastore.client.getItem(
                self.internalID, recordKey, SortKey.RECORD.value, expectExists=False
            )
        )

    def test_convert_index_keys_to_lower_case(self):
        """
        Test converting all keys in a dict to lower case. Returns unchanged if unexpected type.
        """
        indexDict = {
            "nhsNumber_bin": ["nhsNumberA", "nhsNumberB"],
            "nhsNumberPrescDispDate_bin": [
                "nhsNumberA|prescA|dispA|dateA",
                "nhsNumberB|prescB|dispB|dateB",
            ],
            "nextActivityNAD_bin": ["purge", "delete"],
        }

        expected = {
            "nhsnumber_bin": ["nhsNumberA", "nhsNumberB"],
            "nhsnumberprescdispdate_bin": [
                "nhsNumberA|prescA|dispA|dateA",
                "nhsNumberB|prescB|dispB|dateB",
            ],
            "nextactivitynad_bin": ["purge", "delete"],
        }

        convertedDict = self.datastore.convert_index_keys_to_lower_case(indexDict)

        self.assertEqual(convertedDict, expected)

        indexWrongType = "NoTaDiCt"
        convertedWrongType = self.datastore.convert_index_keys_to_lower_case(indexWrongType)

        self.assertEqual(convertedWrongType, indexWrongType)

    @patch("random.randint")
    def testAddLastModifiedToItem(self, patchedRandint):
        """
        Test adding last modified timestamp and date to items.
        """
        patchedRandint.return_value = 7

        item = {"a": 1}

        dateTime = datetime(
            year=2025, month=9, day=11, hour=10, minute=11, second=12, microsecond=123456
        )
        with freeze_time(dateTime):
            self.datastore.client.addLastModifiedToItem(item)

        expected = {"a": 1, "_riak_lm": Decimal("1757585472.123456"), "_lm_day": "20250911.7"}
        self.assertEqual(item, expected)

    @parameterized.expand(
        [
            ["string that is not base64 encoded", ValueError, "Document content not b64 encoded"],
            ["xxx", binascii.Error, "Incorrect padding"],
        ]
    )
    def testDocumentDecodeError(self, content, expectedErrorType, expectedLogValue):
        """
        Test error handling when base64 decoding the document.
        """
        document = {"content": content}
        with self.assertRaises(expectedErrorType):
            self.datastore.insert_eps_document_object(self.internalID, None, document)

        logValue = self.datastore.logObject.getLoggedValue("DDB0031", "error")
        self.assertEqual(logValue, expectedLogValue)

    def testDocumentEncodeError(self):
        """
        Test error handling when base64 encoding the document.
        """
        documentKey = "testDocument"
        self.keys.append((documentKey, SortKey.DOCUMENT.value))
        document = {
            Key.PK.name: documentKey,
            Key.SK.name: SortKey.DOCUMENT.value,
            ProjectedAttribute.BODY.name: {"content": None},
        }
        self.datastore.client.putItem(self.internalID, document, logItemSize=False)

        with self.assertRaises(TypeError):
            self.datastore.return_document_for_process(self.internalID, documentKey)

        wasLogged = self.datastore.logObject.wasLogged("DDB0032")
        self.assertTrue(wasLogged)

    def testBatchClaimXmlDecodeError(self):
        """
        Test error handling when decoding the batch claim xml.
        """
        batchClaimKey = "testBatchClaim"
        self.keys.append((batchClaimKey, SortKey.CLAIM.value))
        batchClaim = {
            Key.PK.name: batchClaimKey,
            Key.SK.name: SortKey.CLAIM.value,
            ProjectedAttribute.BODY.name: {"Batch XML": None},
        }
        self.datastore.client.putItem(self.internalID, batchClaim, logItemSize=False)

        with self.assertRaises(TypeError):
            self.datastore.fetch_batch_claim(self.internalID, batchClaimKey)

        wasLogged = self.datastore.logObject.wasLogged("DDB0033")
        self.assertTrue(wasLogged)

    def testRecordExpireAtDatetimeFormat(self):
        """
        Test that the expireAt attribute added to a record defaults to 18 months from its creation.
        Provided prescriptionTime is in %Y%m%d%H%M%S format.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()

        dateTime = datetime(
            year=2025,
            month=9,
            day=11,
            hour=10,
            minute=11,
            second=12,
            microsecond=123456,
            tzinfo=timezone.utc,
        )
        dateTimeString = datetime.strftime(dateTime, TimeFormats.STANDARD_DATE_TIME_FORMAT)
        record = self.getRecord(nhsNumber, dateTimeString)

        expectedTimestamp = int(
            datetime(
                year=2027, month=3, day=11, hour=10, minute=11, second=12, tzinfo=timezone.utc
            ).timestamp()
        )

        builtRecord = self.datastore.build_record(prescriptionId, record, None, None)

        expireAt = builtRecord["expireAt"]
        self.assertEqual(expireAt, expectedTimestamp)

    def testRecordExpireAtDateFormat(self):
        """
        Test that the expireAt attribute added to a record defaults to 18 months from its creation.
        Provided prescriptionTime is in %Y%m%d format.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()

        dateTime = datetime(
            year=2025,
            month=9,
            day=11,
            hour=10,
            minute=11,
            second=12,
            microsecond=123456,
            tzinfo=timezone.utc,
        )
        dateString = datetime.strftime(dateTime, TimeFormats.STANDARD_DATE_FORMAT)
        record = self.getRecord(nhsNumber, dateString)

        expectedTimestamp = int(
            datetime(year=2027, month=3, day=11, tzinfo=timezone.utc).timestamp()
        )

        builtRecord = self.datastore.build_record(prescriptionId, record, None, None)

        expireAt = builtRecord["expireAt"]
        self.assertEqual(expireAt, expectedTimestamp)

    def testDocumentExpireAt(self):
        """
        Test that the expireAt attribute added to a document
        defaults to 18 months from when it is written to the database.
        """
        content = self.getDocumentContent()
        document = {"content": content}

        dateTime = datetime(
            year=2025,
            month=9,
            day=11,
            hour=10,
            minute=11,
            second=12,
            microsecond=123456,
            tzinfo=timezone.utc,
        )

        expectedTimestamp = int(
            datetime(
                year=2027, month=3, day=11, hour=10, minute=11, second=12, tzinfo=timezone.utc
            ).timestamp()
        )

        with freeze_time(dateTime):
            builtDocument = self.datastore.build_document(self.internalID, document, None)

        expireAt = builtDocument["expireAt"]
        self.assertEqual(expireAt, expectedTimestamp)

    def testDocumentExpireAtFromIndex(self):
        """
        Test that the expireAt attribute added to a document matches that provided in the index.
        """
        content = self.getDocumentContent()
        document = {"content": content}
        index = {
            indexes.INDEX_STORE_TIME_DOC_REF_TITLE: [
                f"{self.datastore.STORE_TIME_DOC_REF_TITLE_PREFIX}_20250911"
            ],
            indexes.INDEX_DELETE_DATE: ["20250911"],
            indexes.INDEX_PRESCRIPTION_ID: str(uuid4()),
        }

        expectedTimestamp = int(
            datetime(year=2025, month=9, day=11, tzinfo=timezone.utc).timestamp()
        )

        builtDocument = self.datastore.build_document(self.internalID, document, index)

        expireAt = builtDocument["expireAt"]
        self.assertEqual(expireAt, expectedTimestamp)

    def testConcurrentInserts(self):
        """
        Test that concurrent inserts to a record will raise a EpsDataStoreError and log correctly
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)

        exceptionsThrown = []

        def insertRecord(datastore, insertArgs):
            try:
                datastore.insert_eps_record_object(*insertArgs)
            except Exception as e:
                exceptionsThrown.append(e)

        # Create several processes that try to insert the record concurrently
        processes = []
        loggers = []
        for _ in range(2):
            logger = MockLogObject()
            loggers.append(logger)

            datastore = EpsDynamoDbDataStore(logger, None, "spine-eps-datastore")

            process = Thread(
                target=insertRecord, args=(datastore, (self.internalID, prescriptionId, record))
            )
            processes.append(process)

        # Start processes
        for process in processes:
            process.start()

        # Wait for processes to finish
        for process in processes:
            process.join()

        logs = set()
        [logs.add(log) for logger in loggers for log in logger.calledReferences]
        self.assertTrue("DDB0021" in logs, "Expected a log DDB0021 for concurrent insert failure")

        self.assertEqual(
            len(exceptionsThrown), 1, "Expected exception to be thrown for concurrent insertions"
        )
        self.assertTrue(
            isinstance(exceptionsThrown[0], EpsDataStoreError),
            "Expected EpsDataStoreError for concurrent insertions",
        )
        self.assertEqual(
            exceptionsThrown[0].errorTopic,
            EpsDataStoreError.DUPLICATE_ERROR,
            "Expected EpsDataStoreError.DUPLICATE_ERROR for concurrent insertions",
        )

    def testConcurrentUpdates(self):
        """
        Test that concurrent updates to a record will raise a EpsDataStoreError and log correctly
        """
        # Insert the initial record
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        record = self.getRecord(nhsNumber)

        response = self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        self.assertEqual(response["ResponseMetadata"]["HTTPStatusCode"], 200)

        # Make a change to the record
        record["prescription"]["daysSupply"] = 30
        record["SCN"] = 5

        exceptionsThrown = []

        def changeRecord(datastore, changeArgs):
            try:
                datastore.insert_eps_record_object(*changeArgs)
            except Exception as e:
                exceptionsThrown.append(e)

        # Create several processes that try to update the record concurrently
        processes = []
        loggers = []
        for _ in range(2):
            logger = MockLogObject()
            loggers.append(logger)

            datastore = EpsDynamoDbDataStore(logger, None, "spine-eps-datastore")

            index = None
            recordType = None
            isUpdate = True

            process = Thread(
                target=changeRecord,
                args=(
                    datastore,
                    (self.internalID, prescriptionId, record, index, recordType, isUpdate),
                ),
            )
            processes.append(process)

        # Start processes
        for process in processes:
            process.start()

        # Wait for processes to finish
        for process in processes:
            process.join()

        logs = set()
        [logs.add(log) for logger in loggers for log in logger.calledReferences]
        self.assertTrue("DDB0022" in logs, "Expected a log DDB0022 for concurrent update failure")

        self.assertEqual(
            len(exceptionsThrown), 1, "Expected exception to be thrown for concurrent updates"
        )
        self.assertTrue(
            isinstance(exceptionsThrown[0], EpsDataStoreError),
            "Expected EpsDataStoreError for concurrent updates",
        )
        self.assertEqual(
            exceptionsThrown[0].errorTopic,
            EpsDataStoreError.CONDITIONAL_UPDATE_FAILURE,
            "Expected EpsDataStoreError.CONDITIONAL_UPDATE_FAILURE for concurrent updates",
        )

    def testAddClaimNotificationStoreDate(self):
        """
        Test that the claimNotificationStoreDate attribute is added only when docRefTitle is ClaimNotification.
        """
        content = self.getDocumentContent()
        document = {"content": content}

        for docRefTitle in ["ClaimNotification", "Other"]:
            index = {
                indexes.INDEX_STORE_TIME_DOC_REF_TITLE: [f"{docRefTitle}_20250911"],
                indexes.INDEX_DELETE_DATE: ["20250911"],
                indexes.INDEX_PRESCRIPTION_ID: str(uuid4()),
            }

            builtDocument = self.datastore.build_document(self.internalID, document, index)

            if docRefTitle == "ClaimNotification":
                claimNotificationStoreDate = builtDocument["claimNotificationStoreDate"]
                self.assertEqual("20250911", claimNotificationStoreDate)
            else:
                self.assertTrue("claimNotificationStoreDate" not in builtDocument)

    def testRecordNextActivitySharding(self):
        """
        Test that building a record correctly shards the nextActivity attribute
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()

        record = self.getRecord(nhsNumber)

        item = self.datastore.build_record(prescriptionId, record, None, None)

        nextActivity = item[Attribute.NEXT_ACTIVITY.name]
        activity, shard = nextActivity.split(".")
        shard = int(shard)

        self.assertEqual(activity, "createNoClaim")
        self.assertTrue(shard >= 1 and shard <= NEXT_ACTIVITY_DATE_PARTITIONS)

    @parameterized.expand(
        [
            [
                ["C51BB3D6-6948-11F0-9F54-EDAF56A204B4N", "C51BB3D6-6948-11F0-9F54-EDAF56A204B4"],
                "R1.7",
            ],
            [["5HLBWE-U5QENL-24XBU", "5HLBWE-U5QENL-24XBUX"], "R2.7"],
            [["5HLBWE-U5QENL-24XB"], "UNKNOWN"],
        ]
    )
    def test_build_record_adds_release_version(self, prescriptionIds, expected):
        """
        Test that the build_record method adds an R1/R2 releaseVersion attribute to a record.
        Defaults to UNKNOWN when id is too short.
        """
        nhsNumber = self.generateNhsNumber()
        record = self.getRecord(nhsNumber)

        for prescriptionId in prescriptionIds:
            with patch("random.randint") as patchedRandint:
                patchedRandint.return_value = 7
                item = self.datastore.build_record(prescriptionId, record, None, None)
                self.assertEqual(item["releaseVersion"], expected)

    @parameterized.expand(
        [
            [
                ["C51BB3D6-6948-11F0-9F54-EDAF56A204B4N", "C51BB3D6-6948-11F0-9F54-EDAF56A204B4"],
                "R1",
            ],
            [["5HLBWE-U5QENL-24XBU", "5HLBWE-U5QENL-24XBUX"], "R2"],
            [["5HLBWE-U5QENL-24XB"], "UNKNOWN"],
        ]
    )
    def testBuildRecordToReturnAddsReleaseVersion(self, prescriptionIds, expected):
        """
        Test that the _build_record_to_return method adds an R1/R2 releaseVersion attribute to a record
        if it is missing. Defaults to UNKNOWN when id is too short.
        """
        for prescriptionId in prescriptionIds:
            item = {"pk": prescriptionId}
            record = self.datastore._build_record_to_return(item, {})
            self.assertEqual(record["releaseVersion"], expected)

    def test_is_record_present(self):
        """
        Ensure that the is_record_present returns the correct boolean depending on presence of a record.
        """
        prescriptionId, nhsNumber = self.getNewRecordKeys()
        self.assertFalse(self.datastore.is_record_present(self.internalID, prescriptionId))

        record = self.getRecord(nhsNumber)
        self.datastore.insert_eps_record_object(self.internalID, prescriptionId, record)

        self.assertTrue(self.datastore.is_record_present(self.internalID, prescriptionId))

    def testClaimNotificationBinaryEncoding(self):
        """
        Ensure that fetching documents handles stringified and binary payloads
        """
        documentKey = self.generateDocumentKey()
        content = self.getDocumentContent()
        index = {
            indexes.INDEX_STORE_TIME_DOC_REF_TITLE: ["ClaimNotification_20250911"],
            indexes.INDEX_DELETE_DATE: ["20250911"],
        }
        self.datastore.insertEPSDocumentObject(
            self.internalID, documentKey, {"payload": content}, index
        )

        # Document should be stored as a string in DynamoDB
        self.assertTrue(
            isinstance(
                self.datastore.client.getItem(self.internalID, documentKey, SortKey.DOCUMENT.value)[
                    "body"
                ]["payload"],
                str,
            )
        )

        stringResponse = self.datastore.return_document_for_process(self.internalID, documentKey)

        binaryContent = base64.b64encode(
            zlib.compress(simplejson.dumps({"a": 1, "b": True}).encode("utf-8"))
        )
        documentKey2 = self.generateDocumentKey()
        self.datastore.insertEPSDocumentObject(
            self.internalID, documentKey2, {"payload": binaryContent}, index
        )

        # Document should be stored as a binary in DynamoDB
        self.assertTrue(
            isinstance(
                self.datastore.client.getItem(
                    self.internalID, documentKey2, SortKey.DOCUMENT.value
                )["body"]["payload"],
                Binary,
            )
        )

        binaryResponse = self.datastore.return_document_for_process(self.internalID, documentKey2)

        self.assertEqual(stringResponse, binaryResponse)
