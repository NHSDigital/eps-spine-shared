from eps_spine_shared.common.dynamodb_client import EpsDynamoDbClient
from eps_spine_shared.common.dynamodb_index import EpsDynamoDbIndex


class DynamoDbIndex(EpsDynamoDbIndex):
    """
    Wrapper class for backward compatibility with camelCase method names.
    Inherits from EpsDynamoDbIndex and provides camelCase method signatures
    that delegate to the snake_case implementations.
    """

    def __init__(self, logObject, client: EpsDynamoDbClient):
        super().__init__(log_object=logObject, client=client)
        # Maintain backward compatibility with camelCase attribute
        self.logObject = logObject

    # Override parent methods with camelCase signatures for backward compatibility
    def nhsNumberDate(self, rangeStart, rangeEnd, termRegex):
        """Query the nhsNumberDate index."""
        return self.nhs_number_date(rangeStart, rangeEnd, termRegex)

    def nhsNumberPrescDispDate(self, rangeStart, rangeEnd, termRegex):
        """Query the nhsNumberDate index, filtering on prescriber and dispenser."""
        return self.nhs_number_presc_disp_date(rangeStart, rangeEnd, termRegex)

    def nhsNumberPrescDate(self, rangeStart, rangeEnd, termRegex):
        """Query the nhsNumberDate index, filtering on prescriber."""
        return self.nhs_number_presc_date(rangeStart, rangeEnd, termRegex)

    def nhsNumberDispDate(self, rangeStart, rangeEnd, termRegex):
        """Query the nhsNumberDate index, filtering on dispenser."""
        return self.nhs_number_disp_date(rangeStart, rangeEnd, termRegex)

    def prescDispDate(self, rangeStart, rangeEnd, termRegex):
        """Query the prescriberDate index, filtering on dispenser."""
        return self.presc_disp_date(rangeStart, rangeEnd, termRegex)

    def prescDate(self, rangeStart, rangeEnd, termRegex):
        """Query the prescriberDate index."""
        return self.presc_date(rangeStart, rangeEnd, termRegex)

    def dispDate(self, rangeStart, rangeEnd, termRegex):
        """Query the dispenserDate index."""
        return self.disp_date(rangeStart, rangeEnd, termRegex)

    def nomPharmStatus(self, rangeStart, _, termRegex):
        """Query the nomPharmStatus index for terms."""
        return self.nom_pharm_status(rangeStart, _, termRegex)

    def buildTerms(self, items, indexName, termRegex):
        """Build terms from items returned by the index query."""
        return self.build_terms(items, indexName, termRegex)

    def padOrTrimDate(self, date):
        """Ensure the date length is fourteen characters, if present."""
        return self.pad_or_trim_date(date)

    def queryNhsNumberDate(
        self, index, nhsNumber, startDate=None, endDate=None, filterExpression=None, termRegex=None
    ):
        """Return the epsRecord terms which match the supplied range and regex for the nhsNumberDate index."""
        return self.query_nhs_number_date(
            index, nhsNumber, startDate, endDate, filterExpression, termRegex
        )

    def queryPrescriberDate(
        self, index, prescriberOrg, startDate, endDate, filterExpression=None, termRegex=None
    ):
        """Return the epsRecord terms which match the supplied range and regex for the prescriberDate index."""
        return self.query_prescriber_date(
            index, prescriberOrg, startDate, endDate, filterExpression, termRegex
        )

    def queryDispenserDate(
        self, index, dispenserOrg, startDate, endDate, filterExpression=None, termRegex=None
    ):
        """Return the epsRecord terms which match the supplied range and regex for the dispenserDate index."""
        return self.query_dispenser_date(
            index, dispenserOrg, startDate, endDate, filterExpression, termRegex
        )

    def queryNomPharmStatus(self, odsCode, allStatuses=False, limit=None):
        """Return the nomPharmStatus prescription keys which match the supplied ODS code."""
        return self.query_nom_pharm_status(odsCode, allStatuses, limit)

    def queryNomPharmStatusTerms(self, index, odsCode, status, termRegex=None):
        """Return the nomPharmStatus terms which match the supplied ODS code and status."""
        return self.query_nom_pharm_status_terms(index, odsCode, status, termRegex)

    def queryClaimId(self, claimId):
        """Search for an existing batch claim containing the given claimId."""
        return self.query_claim_id(claimId)

    def queryNextActivityDate(self, rangeStart, rangeEnd):
        """Yields the epsRecord keys which match the supplied nextActivity and date range for the nextActivity index."""
        return self.query_next_activity_date(rangeStart, rangeEnd)

    def _queryNextActivityDateShard(self, nextActivity, skExpression, shard):
        """
        Return a generator for the epsRecord keys which match the supplied nextActivity and date range
        for a given pk shard.
        """
        return self._query_next_activity_date_shard(nextActivity, skExpression, shard)

    def _getDateRangeForQuery(self, startDatetimeStr, endDatetimeStr):
        """Get days included in the given range. For use in claimNotificationStoreTime index query."""
        return self._get_date_range_for_query(startDatetimeStr, endDatetimeStr)

    def queryClaimNotificationStoreTime(self, internalID, startDatetimeStr, endDatetimeStr):
        """Search for claim notification documents whose store times fall within the specified window."""
        return self.query_claim_notification_store_time(
            internalID, startDatetimeStr, endDatetimeStr
        )

    def _getValidRangeCondition(self, key, start, end):
        """Returns a range condition if the start < end"""
        return self._get_valid_range_condition(key, start, end)

    def queryBatchClaimIdSequenceNumber(self, sequenceNumber, nwssp=False):
        """Query the claimIdSequenceNumber index for batch claim IDs based on sequence number."""
        return self.query_batch_claim_id_sequence_number(sequenceNumber, nwssp)
