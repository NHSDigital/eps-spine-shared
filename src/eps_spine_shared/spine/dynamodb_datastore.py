from eps_spine_shared.common.dynamodb_datastore import PrescriptionsDynamoDbDataStore


class DynamoDbDataStore(PrescriptionsDynamoDbDataStore):
    """
    Wrapper class for PrescriptionsDynamoDbDataStore that provides backward compatibility
    with camelCase method signatures.
    """

    def __init__(
        self,
        logObject,
        awsEndpointUrl: str,
        tableName: str,
        roleArn: str = None,
        roleSessionName: str = None,
        stsEndpointUrl: str = None,
    ):
        super().__init__(
            log_object=logObject,
            aws_endpoint_url=awsEndpointUrl,
            table_name=tableName,
            role_arn=roleArn,
            role_session_name=roleSessionName,
            sts_endpoint_url=stsEndpointUrl,
        )
        # Maintain backward compatibility with camelCase attributes
        self.logObject = logObject
        self.tableName = tableName
        self.awsEndpointUrl = awsEndpointUrl
        self.roleArn = roleArn
        self.roleSessionName = roleSessionName
        self.stsEndpointUrl = stsEndpointUrl

    # Override parent methods with camelCase signatures for backward compatibility

    def base64DecodeDocumentContent(self, internalID, document):
        """base64 decode document content in order to store as binary type in DynamoDB."""
        return self.base64_decode_document_content(internalID, document)

    def getExpireAt(self, delta, fromDatetime=None):
        """Returns an int timestamp to be used as an expireAt attribute."""
        return self.get_expire_at(delta, fromDatetime)

    def buildDocument(self, internalID, document, index):
        """Build EPS Document object to be inserted into DynamoDB."""
        return self.build_document(internalID, document, index)

    def insertEpsDocumentObject(self, internalID, documentKey, document, index=None):
        """Insert EPS Document object into the configured table."""
        return self.insert_eps_document_object(internalID, documentKey, document, index)

    def convertIndexKeysToLowerCase(self, index):
        """Convert all keys in an index dict to lower case."""
        return self.convert_index_keys_to_lower_case(index)

    def buildRecord(self, prescriptionId, record, recordType, indexes):
        """Build EPS Record object to be inserted into DynamoDB."""
        return self.build_record(prescriptionId, record, recordType, indexes)

    def insertEpsRecordObject(
        self, internalID, prescriptionId, record, index=None, recordType=None, isUpdate=False
    ):
        """Insert EPS Record object into the configured table."""
        return self.insert_eps_record_object(
            internalID, prescriptionId, record, index, recordType, isUpdate
        )

    def insertEpsWorkList(self, internalID, messageId, workList, index=None):
        """Insert EPS WorkList object into the configured table."""
        return self.insert_eps_work_list(internalID, messageId, workList, index)

    def isRecordPresent(self, internalID, prescriptionId) -> bool:
        """Returns a boolean indicating the presence of a record."""
        return self.is_record_present(internalID, prescriptionId)

    def returnTermsByNhsNumberDate(self, internalID, rangeStart, rangeEnd, termRegex=None):
        """Return the epsRecord terms which match the supplied range and regex for the nhsNumberDate index."""
        return self.return_terms_by_nhs_number_date(internalID, rangeStart, rangeEnd, termRegex)

    def returnTermsByIndexDate(self, internalID, index, rangeStart, rangeEnd=None, termRegex=None):
        """Return the epsRecord terms which match the supplied range and regex for the supplied index."""
        return self.return_terms_by_index_date(internalID, index, rangeStart, rangeEnd, termRegex)

    def returnTermsByNhsNumber(self, internalID, nhsNumber):
        """Return the epsRecord terms which match the supplied NHS number."""
        return self.return_terms_by_nhs_number(internalID, nhsNumber)

    def returnPidsForNominationChange(self, internalID, nhsNumber):
        """Return the epsRecord list which match the supplied NHS number."""
        return self.return_pids_for_nomination_change(internalID, nhsNumber)

    def getNominatedPharmacyRecords(self, nominatedPharmacy, batchSize, internalID):
        """Run an index query to get the to-be-dispensed prescriptions for this nominated pharmacy."""
        return self.get_nominated_pharmacy_records(nominatedPharmacy, batchSize, internalID)

    def getNomPharmRecordsUnfiltered(self, internalID, nominatedPharmacy, limit=None):
        """
        Query the nomPharmStatus index to get the unfiltered,
        to-be-dispensed prescriptions for the given pharmacy.
        """
        return self.get_nom_pharm_records_unfiltered(internalID, nominatedPharmacy, limit)

    def returnRecordForProcess(self, internalID, prescriptionId, expectExists=True):
        """Look for and return an epsRecord object."""
        return self.return_record_for_process(internalID, prescriptionId, expectExists)

    def base64EncodeDocumentContent(self, internalID, documentBody):
        """base64 encode document content and convert to string, to align with return type of original datastore."""
        return self.base64_encode_document_content(internalID, documentBody)

    def returnDocumentForProcess(self, internalID, documentKey, expectExists=True):
        """Look for and return an epsDocument object."""
        return self.return_document_for_process(internalID, documentKey, expectExists)

    def returnRecordForUpdate(self, internalID, prescriptionId):
        """Look for and return an epsRecord object, but with dataObject on self so that an update can be applied."""
        return self.return_record_for_update(internalID, prescriptionId)

    def getPrescriptionRecordData(self, internalID, prescriptionId, expectExists=True):
        """Gets the prescription record from the data store and return just the data."""
        return self.get_prescription_record_data(internalID, prescriptionId, expectExists)

    def getWorkList(self, internalID, messageId):
        """Look for and return a workList object."""
        return self.get_work_list(internalID, messageId)

    def compressWorkListXml(self, internalID, workList):
        """Compresses the XML contained in the work list, if present."""
        return self.compress_work_list_xml(internalID, workList)

    def decompressWorkListXml(self, internalID, body):
        """Decompresses the XML contained in the work list, if present."""
        return self.decompress_work_list_xml(internalID, body)

    def fetchNextSequenceNumber(self, internalID, maxSequenceNumber, readOnly=False):
        """Fetch the next sequence number for a batch claim message."""
        return self.fetch_next_sequence_number(internalID, maxSequenceNumber, readOnly)

    def fetchNextSequenceNumberNwssp(self, internalID, maxSequenceNumber, readOnly=False):
        """Fetch the next sequence number for a welsh batch claim message."""
        return self.fetch_next_sequence_number_nwssp(internalID, maxSequenceNumber, readOnly)

    def storeBatchClaim(self, internalID, batchClaimOriginal):
        """batchClaims need to be stored by their GUIDs with a claims sort key."""
        return self.store_batch_claim(internalID, batchClaimOriginal)

    def fetchBatchClaim(self, internalID, batchClaimId):
        """Retrieves the batch claim and returns the batch message for the calling application to handle."""
        return self.fetch_batch_claim(internalID, batchClaimId)

    def deleteClaimNotification(self, internalID, claimId):
        """Delete the claim notification document from the table, and return True if the deletion was successful."""
        return self.delete_claim_notification(internalID, claimId)

    def deleteDocument(self, internalID, documentKey, deleteNotification=False):
        """Delete a document from the table. Return a boolean indicator of success."""
        return self.delete_document(internalID, documentKey, deleteNotification)

    def deleteRecord(self, internalID, recordKey):
        """Delete a record from the table."""
        return self.delete_record(internalID, recordKey)

    def returnPIDsDueForNextActivity(self, internalID, nextActivityStart, nextActivityEnd):
        """Returns all the epsRecord keys for prescriptions whose nextActivity is the same as that provided."""
        return self.return_pids_due_for_next_activity(
            internalID, nextActivityStart, nextActivityEnd
        )

    def returnPrescriptionIdsForNomPharm(self, internalID, nominatedPharmacyIndexTerm):
        """Returns the epsRecord keys relating to the given nominated pharmacy term."""
        return self.return_prescription_ids_for_nom_pharm(internalID, nominatedPharmacyIndexTerm)

    def returnClaimNotificationIDsBetweenStoreDates(self, internalID, startDate, endDate):
        """
        Returns all the epsDocument keys for claim notification documents
        whose store dates are in the given window.
        """
        return self.return_claim_notification_ids_between_store_dates(
            internalID, startDate, endDate
        )

    def getAllPIDsByNominatedPharmacy(self, internalID, nominatedPharmacy):
        """Run an index query to get all prescriptions for this nominated pharmacy."""
        return self.get_all_pids_by_nominated_pharmacy(internalID, nominatedPharmacy)

    def checkItemExists(self, internalID, pk, sk, expectExists) -> bool:
        """Returns False as covered by condition expression."""
        return self.check_item_exists(internalID, pk, sk, expectExists)

    def findBatchClaimfromSeqNumber(self, sequenceNumber, nwssp=False):
        """
        Run a query against the sequence number index looking for
        the batch GUID (key) on the basis of sequence number.
        """
        return self.find_batch_claim_from_seq_number(sequenceNumber, nwssp)
