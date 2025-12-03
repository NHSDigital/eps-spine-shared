import base64
import copy
import functools
import sys
import time
import zlib
from datetime import datetime, timedelta, timezone
from random import randint

import simplejson
from dateutil.relativedelta import relativedelta

from eps_spine_shared.common import indexes
from eps_spine_shared.common.dynamodb_client import EpsDataStoreError, EpsDynamoDbClient
from eps_spine_shared.common.dynamodb_common import (
    NEXT_ACTIVITY_DATE_PARTITIONS,
    Attribute,
    Key,
    ProjectedAttribute,
    SortKey,
    determine_release_version,
    prescription_id_without_check_digit,
    replace_decimals,
)
from eps_spine_shared.common.dynamodb_index import PrescriptionsDynamoDbIndex, PrescriptionStatus
from eps_spine_shared.nhsfundamentals.timeutilities import (
    TimeFormats,
    convertSpineDate,
    timeNowAsString,
)


def timer(func):
    """
    Decorator to be used to time methods.
    """

    @functools.wraps(func)
    def wrapperTimer(*args, **kwargs):
        self = args[0]
        internalID = args[1]
        startTime = time.perf_counter()
        value = func(*args, **kwargs)
        endTime = time.perf_counter()
        runTimeMs = (endTime - startTime) * 1000
        runTimeMs = float(f"{runTimeMs:.2f}")
        self.logObject.writeLog(
            "DDB0002",
            None,
            {
                "cls": type(self).__name__,
                "func": func.__name__,
                "duration": runTimeMs,
                "internalID": internalID,
            },
        )
        return value

    return wrapperTimer


class PrescriptionsDynamoDbDataStore:
    """
    The prescriptions message store specific DynamoDB client.
    """

    SEPARATOR = "#"
    CLAIM_SEQUENCE_NUMBER_KEY = "claimSequenceNumber"
    NWSSP_CLAIM_SEQUENCE_NUMBER_KEY = "claimSequenceNumberNwssp"
    INDEX_CLAIMID = "claimid_bin"
    INDEX_CLAIMHANDLETIME = "claimhandletime_bin"
    INDEX_CLAIM_SEQNUMBER = "seqnum_bin"
    INDEX_CLAIM_SEQNUMBER_NWSSP = "nwsspseqnum_bin"
    INDEX_SCN = "delta_bin"
    INDEX_WORKLISTDATE = "workListDate_bin"
    NOTIFICATION_PREFIX = "Notification_"
    STORE_TIME_DOC_REF_TITLE_PREFIX = "NominatedReleaseRequestMsgRef"
    DEFAULT_EXPIRY_DAYS = 56

    def __init__(
        self,
        logObject,
        awsEndpointUrl,
        tableName,
        roleArn=None,
        roleSessionName=None,
        stsEndpointUrl=None,
    ):
        """
        Instantiate the DynamoDB client.
        """
        self.logObject = logObject
        self.client = EpsDynamoDbClient(
            self.logObject, awsEndpointUrl, tableName, roleArn, roleSessionName, stsEndpointUrl
        )
        self.indexes = PrescriptionsDynamoDbIndex(self.logObject, self.client)

    def testConnection(self) -> bool:
        """
        No DynamoDB equivalent so returns True.
        """
        return True

    def base64DecodeDocumentContent(self, internalID, document):
        """
        base64 decode document content in order to store as binary type in DynamoDB.
        """
        if content := document.get("content"):
            try:
                decoded = base64.b64decode(document["content"].encode("utf-8"))
                if base64.b64encode(decoded).decode("utf-8") == content:
                    document["content"] = decoded
                else:
                    raise ValueError("Document content not b64 encoded")
            except Exception as e:  # noqa: BLE001
                self.logObject.writeLog(
                    "DDB0031", sys.exc_info(), {"error": str(e), "internalID": internalID}
                )
                raise e

    def getExpireAt(self, delta, fromDatetime=None):
        """
        Returns an int timestamp to be used as an expireAt attribute.
        This will determine when the item is deleted from the table.
        """
        if not fromDatetime:
            fromDatetime = datetime.now(timezone.utc)

        if not fromDatetime.tzinfo:
            fromDatetime = datetime.combine(fromDatetime.date(), fromDatetime.time(), timezone.utc)

        return int((fromDatetime + delta).timestamp())

    def buildDocument(self, internalID, document, index):
        """
        Build EPS Document object to be inserted into DynamoDB.
        """
        documentCopy = copy.deepcopy(document)
        self.base64DecodeDocumentContent(internalID, documentCopy)

        defaultExpireAt = self.getExpireAt(relativedelta(months=18))

        item = {
            Key.SK.name: SortKey.DOCUMENT.value,
            ProjectedAttribute.INDEXES.name: self.convertIndexKeysToLowerCase(index),
            ProjectedAttribute.BODY.name: documentCopy,
            ProjectedAttribute.EXPIRE_AT.name: defaultExpireAt,
        }

        if index:
            docRefTitle, storeTime = index[indexes.INDEX_STORE_TIME_DOC_REF_TITLE][0].split("_")
            item[Attribute.DOC_REF_TITLE.name] = docRefTitle

            if docRefTitle == "ClaimNotification":
                item[Attribute.CLAIM_NOTIFICATION_STORE_DATE.name] = storeTime[:8]

            item[Attribute.STORE_TIME.name] = storeTime

            deleteDate = index[indexes.INDEX_DELETE_DATE][0]
            deleteDateTime = datetime.strptime(deleteDate, TimeFormats.STANDARD_DATE_FORMAT)
            item[ProjectedAttribute.EXPIRE_AT.name] = int(deleteDateTime.timestamp())

        return item

    @timer
    def insertEPSDocumentObject(self, internalID, documentKey, document, index=None):
        """
        Insert EPS Document object into the configured table.
        """
        item = self.buildDocument(internalID, document, index)
        item[Key.PK.name] = documentKey
        return self.client.insertItems(internalID, [item], True)

    def convertIndexKeysToLowerCase(self, index):
        """
        Convert all keys in an index dict to lower case.
        """
        if not isinstance(index, dict):
            return index
        return {key.lower(): index[key] for key in index}

    def buildRecord(self, prescriptionId, record, recordType, indexes):
        """
        Build EPS Record object to be inserted into DynamoDB.
        """
        recordKey = prescription_id_without_check_digit(prescriptionId)

        if not indexes:
            indexes = record["indexes"]
        instances = record["instances"].values()

        nextActivityNad = indexes["nextActivityNAD_bin"][0]
        nextActivityNadSplit = nextActivityNad.split("_")
        nextActivity = nextActivityNadSplit[0]
        nextActivityIsPurge = nextActivity.lower() == "purge"

        nextActivityShard = randint(1, NEXT_ACTIVITY_DATE_PARTITIONS)
        shardedNextActivity = f"{nextActivity}.{nextActivityShard}"

        scn = record["SCN"]

        compressedRecord = zlib.compress(simplejson.dumps(record).encode("utf-8"))

        item = {
            Key.PK.name: recordKey,
            Key.SK.name: SortKey.RECORD.value,
            ProjectedAttribute.BODY.name: compressedRecord,
            Attribute.NEXT_ACTIVITY.name: shardedNextActivity,
            ProjectedAttribute.SCN.name: scn,
            ProjectedAttribute.INDEXES.name: self.convertIndexKeysToLowerCase(indexes),
        }
        if len(nextActivityNadSplit) == 2:
            item[Attribute.NEXT_ACTIVITY_DATE.name] = nextActivityNadSplit[1]

        if nextActivityIsPurge:
            return item

        # POC - Leverage methods in PrescriptionRecord to get some/all of these.
        creationDatetimeString = record["prescription"]["prescriptionTime"]
        nhsNumber = record["patient"]["nhsNumber"]

        prescriberOrg = record["prescription"]["prescribingOrganization"]

        statuses = list(set([instance["prescriptionStatus"] for instance in instances]))
        isReady = PrescriptionStatus.TO_BE_DISPENSED in statuses
        if PrescriptionStatus.TO_BE_DISPENSED in statuses:
            statuses.remove(PrescriptionStatus.TO_BE_DISPENSED)
            statuses.insert(0, PrescriptionStatus.TO_BE_DISPENSED)
        status = self.SEPARATOR.join(statuses)

        dispenserOrgs = []
        for instance in instances:
            org = instance.get("dispense", {}).get("dispensingOrganization")
            if org:
                dispenserOrgs.append(org)
        dispenserOrg = self.SEPARATOR.join(set(dispenserOrgs))

        nominatedPharmacy = record.get("nomination", {}).get("nominatedPerformer")

        creationDatetime = convertSpineDate(
            creationDatetimeString, TimeFormats.STANDARD_DATE_TIME_FORMAT
        )
        creationDatetimeUtc = datetime.combine(
            creationDatetime.date(), creationDatetime.time(), timezone.utc
        )
        expireAt = self.getExpireAt(relativedelta(months=18), creationDatetimeUtc)

        itemUpdate = {
            Attribute.CREATION_DATETIME.name: creationDatetimeString,
            Attribute.NHS_NUMBER.name: nhsNumber,
            Attribute.PRESCRIBER_ORG.name: prescriberOrg,
            ProjectedAttribute.STATUS.name: status,
            Attribute.IS_READY.name: int(isReady),
            ProjectedAttribute.EXPIRE_AT.name: expireAt,
        }
        if dispenserOrg:
            item[Attribute.DISPENSER_ORG.name] = dispenserOrg
        if nominatedPharmacy:
            item[Attribute.NOMINATED_PHARMACY.name] = nominatedPharmacy
            if not dispenserOrg:
                item[Attribute.DISPENSER_ORG.name] = nominatedPharmacy
        if recordType:
            item["recordType"] = recordType
        item["releaseVersion"] = determine_release_version(prescriptionId)

        item.update(itemUpdate)
        return item

    @timer
    def insertEPSRecordObject(
        self, internalID, prescriptionId, record, index=None, recordType=None, isUpdate=False
    ):
        """
        Insert EPS Record object into the configured table.
        """
        item = self.buildRecord(prescriptionId, record, recordType, index)

        return self.client.insertItems(internalID, [item], isUpdate)

    @timer
    def insertEPSWorkList(self, internalID, messageId, workList, index=None):
        """
        Insert EPS WorkList object into the configured table.
        """
        workListIndexes = {self.INDEX_WORKLISTDATE: [timeNowAsString()]}
        if index:
            workListIndexes = index

        expireAt = self.getExpireAt(timedelta(days=self.DEFAULT_EXPIRY_DAYS))
        item = {
            Key.PK.name: messageId,
            Key.SK.name: SortKey.WORK_LIST.value,
            ProjectedAttribute.EXPIRE_AT.name: expireAt,
            ProjectedAttribute.BODY.name: self.compressWorkListXml(internalID, workList),
            ProjectedAttribute.INDEXES.name: self.convertIndexKeysToLowerCase(workListIndexes),
        }
        return self.client.insertItems(internalID, [item], True)

    @timer
    def isRecordPresent(self, internalID, prescriptionId) -> bool:
        """
        Returns a boolean indicating the presence of a record.
        """
        recordKey = prescription_id_without_check_digit(prescriptionId)
        record = self.client.getItem(
            internalID, recordKey, SortKey.RECORD.value, expectExists=False
        )
        return True if record else False

    @timer
    def returnTermsByNhsNumberDate(self, internalID, rangeStart, rangeEnd, termRegex=None):
        """
        Return the epsRecord terms which match the supplied range and regex for the nhsNumberDate index.
        """
        return self.returnTermsByIndexDate(
            internalID, indexes.INDEX_NHSNUMBER_DATE, rangeStart, rangeEnd, termRegex
        )

    @timer
    def returnTermsByIndexDate(self, _internalID, index, rangeStart, rangeEnd=None, termRegex=None):
        """
        Return the epsRecord terms which match the supplied range and regex for the supplied index.
        """
        indexMap = {
            indexes.INDEX_NHSNUMBER_PRDSDATE: self.indexes.nhsNumberPrescDispDate,
            indexes.INDEX_NHSNUMBER_PRDATE: self.indexes.nhsNumberPrescDate,
            indexes.INDEX_NHSNUMBER_DSDATE: self.indexes.nhsNumberDispDate,
            indexes.INDEX_NHSNUMBER_DATE: self.indexes.nhsNumberDate,
            indexes.INDEX_PRESCRIBER_DSDATE: self.indexes.prescDispDate,
            indexes.INDEX_PRESCRIBER_DATE: self.indexes.prescDate,
            indexes.INDEX_DISPENSER_DATE: self.indexes.dispDate,
            indexes.INDEX_NOMPHARM: self.indexes.nomPharmStatus,
        }
        return indexMap[index](rangeStart, rangeEnd, termRegex)

    @timer
    def returnTermsByNhsNumber(self, _internalID, nhsNumber):
        """
        Return the epsRecord terms which match the supplied NHS number.
        """
        return self.indexes.queryNhsNumberDate(indexes.INDEX_NHSNUMBER, nhsNumber)

    @timer
    def returnPIDsForNominationChange(self, internalID, nhsNumber):
        """
        Return the epsRecord list which match the supplied NHS number.
        """
        pidList = self.returnTermsByNhsNumber(internalID, nhsNumber)

        prescriptions = []

        for pid in pidList:
            prescriptions.append(pid[1])

        return prescriptions

    def getNominatedPharmacyRecords(self, nominatedPharmacy, batchSize, internalID):
        """
        Run an index query to get the to-be-dispensed prescriptions for this nominated pharmacy.
        """
        keyList = self.getNomPharmRecordsUnfiltered(internalID, nominatedPharmacy)
        discardedKeyCount = max((len(keyList) - int(batchSize)), 0)
        keyList = keyList[:batchSize]
        return [keyList, discardedKeyCount]

    @timer
    def getNomPharmRecordsUnfiltered(self, _internalID, nominatedPharmacy, limit=None):
        """
        Query the nomPharmStatus index to get the unfiltered, to-be-dispensed prescriptions for the given pharmacy.
        """
        return self.indexes.queryNomPharmStatus(nominatedPharmacy, limit=limit)

    @timer
    def returnRecordForProcess(self, internalID, prescriptionId, expectExists=True):
        """
        Look for and return an epsRecord object.
        """
        recordKey = prescription_id_without_check_digit(prescriptionId)
        item = self.client.getItem(
            internalID, recordKey, SortKey.RECORD.value, expectExists=expectExists
        )
        if not item:
            return {}
        body = item.get(ProjectedAttribute.BODY.name)
        if body and not isinstance(body, dict):
            body = simplejson.loads(zlib.decompress(bytes(body)))

        return self._buildRecordToReturn(item, body)

    def _buildRecordToReturn(self, item, body):
        """
        Create the record in the format expected by the calling code.
        """
        replace_decimals(body)

        record = {"value": body, "vectorClock": "vc"}

        if recordType := item.get("recordType"):
            record["recordType"] = recordType

        shardedReleaseVersion = item.get(
            "releaseVersion", determine_release_version(item.get(Key.PK.name))
        )
        record["releaseVersion"] = shardedReleaseVersion.split(".")[0]

        return record

    def base64EncodeDocumentContent(self, internalID, documentBody):
        """
        base64 encode document content and convert to string, to align with return type of original datastore.
        """
        if documentBody and not isinstance(documentBody.get("content"), str):
            try:
                documentBody["content"] = base64.b64encode(bytes(documentBody["content"])).decode(
                    "utf-8"
                )
            except Exception as e:  # noqa: BLE001
                self.logObject.writeLog(
                    "DDB0032", sys.exc_info(), {"error": str(e), "internalID": internalID}
                )
                raise e

    @timer
    def returnDocumentForProcess(self, internalID, documentKey, expectExists=True):
        """
        Look for and return an epsDocument object.
        """
        item = self.client.getItem(
            internalID,
            documentKey,
            SortKey.DOCUMENT.value,
            expectNone=True,
            expectExists=expectExists,
        )
        if not item:
            return {}

        body = item.get(ProjectedAttribute.BODY.name)
        replace_decimals(body)

        if item.get(Attribute.DOC_REF_TITLE.name, "").lower() != "claimnotification":
            self.base64EncodeDocumentContent(internalID, body)

        return body

    @timer
    def returnRecordForUpdate(self, internalID, prescriptionId):
        """
        Look for and return an epsRecord object,
        but with dataObject on self so that an update can be applied.
        """
        recordKey = prescription_id_without_check_digit(prescriptionId)
        item = self.client.getItem(internalID, recordKey, SortKey.RECORD.value)
        body = item.get(ProjectedAttribute.BODY.name)
        if body and not isinstance(body, dict):
            body = simplejson.loads(zlib.decompress(bytes(body)))

        self.dataObject = body
        return self._buildRecordToReturn(item, body)

    def getPrescriptionRecordData(self, internalID, prescriptionID, expectExists=True):
        """
        Gets the prescription record from the data store and return just the data.
        :expectExists defaulted to True. Thus we expect the key should already exist, if
        no matches are found DDB will throw a EpsDataStoreError (Missing Record).
        """
        recordKey = prescription_id_without_check_digit(prescriptionID)
        dataObject = self.client.getItem(
            internalID, recordKey, SortKey.RECORD.value, expectExists=expectExists
        )

        if dataObject is None:
            return None

        return dataObject

    @timer
    def getWorkList(self, internalID, messageId):
        """
        Look for and return a workList object.
        """
        item = self.client.getItem(
            internalID, messageId, SortKey.WORK_LIST.value, expectExists=False, expectNone=True
        )
        if item is None:
            return None

        if body := item.get(ProjectedAttribute.BODY.name):
            replace_decimals(body)
            self.decompressWorkListXml(internalID, body)
        return body

    @timer
    def compressWorkListXml(self, _internalID, workList):
        """
        Compresses the XML contained in the work list, if present. Maintains original responseDetails on context.
        """
        workListDeepCopy = copy.deepcopy(workList)
        xmlBytes = workListDeepCopy.get("responseDetails", {}).get("XML")

        if xmlBytes:
            if isinstance(xmlBytes, str):
                xmlBytes = xmlBytes.encode("utf-8")
            # POC - Potential chars (unicode) that may cause compression to fail.
            compressedXml = zlib.compress(xmlBytes)
            workListDeepCopy["responseDetails"]["XML"] = compressedXml
        return workListDeepCopy

    @timer
    def decompressWorkListXml(self, _internalID, body):
        """
        Decompresses the XML contained in the work list, if present.
        """
        # POC - Possible requirement to recombine chunks here.
        compressedXml = body.get("responseDetails", {}).get("XML")

        # POC - Did compression succeed?
        if compressedXml:
            decompressedXml = zlib.decompress(bytes(compressedXml))
            body["responseDetails"]["XML"] = decompressedXml

    def _fetchNextSequenceNumber(self, internalID, key, maxSequenceNumber, readOnly=False):
        """
        Fetch the next sequence number from a given key.
        """
        item = self.client.getItem(
            internalID, key, SortKey.SEQUENCE_NUMBER.value, expectExists=False
        )
        isUpdate = True
        if not item:
            item = {
                Key.PK.name: key,
                Key.SK.name: SortKey.SEQUENCE_NUMBER.value,
                Attribute.SEQUENCE_NUMBER.name: 1,
            }
            isUpdate = False
        else:
            replace_decimals(item)
            sequenceNumber = item[Attribute.SEQUENCE_NUMBER.name]
            item[Attribute.SEQUENCE_NUMBER.name] = (
                sequenceNumber + 1 if sequenceNumber < maxSequenceNumber else 1
            )

        if not readOnly:
            tries = 0
            while True:
                try:
                    self.client.insertItems(internalID, [item], isUpdate, False)
                    break
                except EpsDataStoreError as e:
                    if e.errorTopic == EpsDataStoreError.CONDITIONAL_UPDATE_FAILURE and tries < 25:
                        sequenceNumber = item[Attribute.SEQUENCE_NUMBER.name]
                        item[Attribute.SEQUENCE_NUMBER.name] = (
                            sequenceNumber + 1 if sequenceNumber < maxSequenceNumber else 1
                        )
                        tries += 1
                    else:
                        raise

        return item[Attribute.SEQUENCE_NUMBER.name]

    @timer
    def fetchNextSequenceNumber(self, internalID, maxSequenceNumber, readOnly=False):
        """
        Fetch the next sequence number for a batch claim message.
        ONLY SINGLETON WORKER PROCESSES SHOULD CALL THIS - IT IS NOT AN ATOMIC ACTION.
        """
        return self._fetchNextSequenceNumber(
            internalID, self.CLAIM_SEQUENCE_NUMBER_KEY, maxSequenceNumber, readOnly
        )

    @timer
    def fetchNextSequenceNumberNwssp(self, internalID, maxSequenceNumber, readOnly=False):
        """
        Fetch the next sequence number for a welsh batch claim message

        ONLY SINGLETON WORKER PROCESSES SHOULD CALL THIS - IT IS NOT AN ATOMIC ACTION
        """
        return self._fetchNextSequenceNumber(
            internalID, self.NWSSP_CLAIM_SEQUENCE_NUMBER_KEY, maxSequenceNumber, readOnly
        )

    @timer
    def storeBatchClaim(self, internalID, batchClaimOriginal):
        """
        batchClaims need to be stored by their GUIDs with a claims sort key.
        They also require an index value for each claimID in the batch.
        A further index value is added with sequence number, for batch resend functionality.
        """
        batchClaim = copy.deepcopy(batchClaimOriginal)
        key = batchClaim["Batch GUID"]

        claimIdIndexTerms = batchClaim["Claim ID List"]
        handleTimeIndexTerm = batchClaim["Handle Time"]
        sequenceNumber = batchClaim["Sequence Number"]
        indexScnValue = f"{timeNowAsString()}|{sequenceNumber}"

        nwssp = "Nwssp Sequence Number" in batchClaim
        nwsspSequenceNumber = batchClaim.get("Nwssp Sequence Number")
        expireAt = self.getExpireAt(timedelta(days=self.DEFAULT_EXPIRY_DAYS))

        indexes = {
            self.INDEX_CLAIMID: claimIdIndexTerms,
            self.INDEX_CLAIMHANDLETIME: [handleTimeIndexTerm],
            self.INDEX_CLAIM_SEQNUMBER: [sequenceNumber],
            self.INDEX_SCN: [indexScnValue],
        }
        if nwssp:
            indexes[self.INDEX_CLAIM_SEQNUMBER_NWSSP] = [nwsspSequenceNumber]

        if batchClaim.get("Claim Metadata") and not batchClaim.get("Backward Incompatible"):
            batchClaim["Batch XML"] = ""

        item = {
            Key.PK.name: key,
            Key.SK.name: SortKey.CLAIM.value,
            ProjectedAttribute.BODY.name: batchClaim,
            ProjectedAttribute.EXPIRE_AT.name: expireAt,
            ProjectedAttribute.CLAIM_IDS.name: claimIdIndexTerms,
            ProjectedAttribute.INDEXES.name: self.convertIndexKeysToLowerCase(indexes),
            Attribute.BATCH_CLAIM_ID.name: key,
        }
        if nwssp:
            item[Attribute.SEQUENCE_NUMBER_NWSSP.name] = nwsspSequenceNumber
        else:
            item[Attribute.SEQUENCE_NUMBER.name] = sequenceNumber

        try:
            self.client.insertItems(internalID, [item], True)
        except Exception:  # noqa: BLE001
            self.logObject.writeLog("EPS0279", sys.exc_info(), {"internalID": key})
            return False
        return True

    def fetchBatchClaim(self, internalID, batchClaimId):
        """
        Retrieves the batch claim and returns the batch message for the calling application to handle.
        """
        item = self.client.getItem(
            internalID, batchClaimId, SortKey.CLAIM.value, expectExists=False
        )
        if not item:
            return {}

        body = item.get(ProjectedAttribute.BODY.name)
        replace_decimals(body)
        batchXml = body["Batch XML"]

        if not isinstance(batchXml, str):
            try:
                body["Batch XML"] = bytes(batchXml).decode("utf-8")
            except Exception as e:  # noqa: BLE001
                self.logObject.writeLog(
                    "DDB0033", sys.exc_info(), {"error": str(e), "internalID": internalID}
                )
                raise e

        return body

    @timer
    def deleteClaimNotification(self, internalID, claimID):
        """
        Delete the claim notification document from the table, and return True if the deletion was successful.
        """
        try:
            self.client.deleteItem(self.NOTIFICATION_PREFIX + str(claimID), SortKey.DOCUMENT.value)
        except Exception:  # noqa: BLE001
            self.logObject.writeLog(
                "EPS0289", sys.exc_info(), {"claimID": claimID, "internalID": internalID}
            )
            return False
        return True

    @timer
    def deleteDocument(self, internalID, documentKey, deleteNotification=False):
        """
        Delete a document from the table. Return a boolean indicator of success.
        """
        if (
            str(documentKey).lower().startswith(self.NOTIFICATION_PREFIX.lower())
            and not deleteNotification
        ):
            return True

        item = self.client.getItem(
            internalID, documentKey, SortKey.DOCUMENT.value, expectExists=False
        )

        if not item:
            self.logObject.writeLog(
                "EPS0601b", None, {"documentRef": documentKey, "internalID": internalID}
            )
            return False

        self.logObject.writeLog(
            "EPS0601", None, {"documentRef": documentKey, "internalID": internalID}
        )
        self.client.deleteItem(documentKey, SortKey.DOCUMENT.value)
        return True

    @timer
    def deleteRecord(self, internalID, recordKey):
        """
        Delete a record from the table.
        """
        self.logObject.writeLog("EPS0602", None, {"recordRef": recordKey, "internalID": internalID})
        self.client.deleteItem(recordKey, SortKey.RECORD.value)

    @timer
    def returnPIDsDueForNextActivity(self, _internalID, nextActivityStart, nextActivityEnd):
        """
        Returns all the epsRecord keys for prescriptions whose nextActivity is the same as that provided,
        and whose next activity date is within the date range provided.
        """
        return self.indexes.queryNextActivityDate(nextActivityStart, nextActivityEnd)

    @timer
    def returnPrescriptionIdsForNomPharm(self, _internalID, nominatedPharmacyIndexTerm):
        """
        Returns the epsRecord keys relating to the given nominated pharmacy term.
        """
        odsCode = nominatedPharmacyIndexTerm.split("_")[0]
        return self.indexes.queryNomPharmStatus(odsCode)

    @timer
    def returnClaimNotificationIDsBetweenStoreDates(self, internalID, startDate, endDate):
        """
        Returns all the epsDocument keys for claim notification documents whose store dates are in the given window.
        """
        return self.indexes.queryClaimNotificationStoreTime(internalID, startDate, endDate)

    @timer
    def getAllPIDsByNominatedPharmacy(self, _internalID, nominatedPharmacy):
        """
        Run an index query to get all prescriptions for this nominated pharmacy.
        """
        return self.indexes.queryNomPharmStatus(nominatedPharmacy, True)

    @timer
    def checkItemExists(self, internalID, pk, sk, expectExists) -> bool:
        """
        Returns False as covered by condition expression.
        """
        item = self.client.getItem(internalID, pk, sk, expectExists)
        if item:
            return True
        return False

    def findBatchClaimfromSeqNumber(self, sequenceNumber, nwssp=False):
        """
        Run a query against the sequence number index looking for the
        batch GUID (key) on the basis of sequence number.
        """
        return self.indexes.queryBatchClaimIdSequenceNumber(sequenceNumber, nwssp)
