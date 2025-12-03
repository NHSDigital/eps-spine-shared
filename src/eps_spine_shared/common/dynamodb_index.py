import re
from datetime import datetime, timedelta
from typing import Tuple

from boto3.dynamodb.conditions import Attr
from boto3.dynamodb.conditions import Key as BotoKey

from eps_spine_shared.common import indexes
from eps_spine_shared.common.dynamodb_client import EpsDynamoDbClient
from eps_spine_shared.common.dynamodb_common import (
    GSI,
    NEXT_ACTIVITY_DATE_PARTITIONS,
    Attribute,
    Key,
    ProjectedAttribute,
    SortKey,
)
from eps_spine_shared.common.prescription_record import PrescriptionStatus
from eps_spine_shared.nhsfundamentals.timeutilities import TimeFormats


class PrescriptionsDynamoDbIndex:
    """
    The prescriptions message store specific DynamoDB client.
    """

    def __init__(self, logObject, client: EpsDynamoDbClient):
        """
        Instantiate the DynamoDB client.
        """
        self.logObject = logObject
        self.client = client

    def nhsNumberDate(self, rangeStart, rangeEnd, termRegex):
        """
        Query the nhsNumberDate index.
        """
        # POC - Use context in these methods, rather than rangeStart and rangeEnd.
        nhsNumber, startDate = rangeStart.split(indexes.SEPERATOR)
        endDate = rangeEnd.split(indexes.SEPERATOR)[-1]

        return self.queryNhsNumberDate(
            indexes.INDEX_NHSNUMBER_DATE, nhsNumber, startDate, endDate, termRegex=termRegex
        )

    def nhsNumberPrescDispDate(self, rangeStart, rangeEnd, termRegex):
        """
        Query the nhsNumberDate index, filtering on prescriber and dispenser.
        """
        nhsNumber, prescriberOrg, dispenserOrg, startDate = rangeStart.split(indexes.SEPERATOR)
        endDate = rangeEnd.split(indexes.SEPERATOR)[-1]
        filterExpression = Attr(Attribute.PRESCRIBER_ORG.name).eq(prescriberOrg) & Attr(
            Attribute.DISPENSER_ORG.name
        ).contains(dispenserOrg)

        return self.queryNhsNumberDate(
            indexes.INDEX_NHSNUMBER_PRDSDATE,
            nhsNumber,
            startDate,
            endDate,
            filterExpression,
            termRegex,
        )

    def nhsNumberPrescDate(self, rangeStart, rangeEnd, termRegex):
        """
        Query the nhsNumberDate index, filtering on prescriber.
        """
        nhsNumber, prescriberOrg, startDate = rangeStart.split(indexes.SEPERATOR)
        endDate = rangeEnd.split(indexes.SEPERATOR)[-1]
        filterExpression = Attr(Attribute.PRESCRIBER_ORG.name).eq(prescriberOrg)

        return self.queryNhsNumberDate(
            indexes.INDEX_NHSNUMBER_PRDATE,
            nhsNumber,
            startDate,
            endDate,
            filterExpression,
            termRegex,
        )

    def nhsNumberDispDate(self, rangeStart, rangeEnd, termRegex):
        """
        Query the nhsNumberDate index, filtering on dispenser.
        """
        nhsNumber, dispenserOrg, startDate = rangeStart.split(indexes.SEPERATOR)
        endDate = rangeEnd.split(indexes.SEPERATOR)[-1]
        filterExpression = Attr(Attribute.DISPENSER_ORG.name).contains(dispenserOrg)

        return self.queryNhsNumberDate(
            indexes.INDEX_NHSNUMBER_DSDATE,
            nhsNumber,
            startDate,
            endDate,
            filterExpression,
            termRegex,
        )

    def prescDispDate(self, rangeStart, rangeEnd, termRegex):
        """
        Query the prescriberDate index, filtering on dispenser.
        """
        prescriberOrg, dispenserOrg, startDate = rangeStart.split(indexes.SEPERATOR)
        endDate = rangeEnd.split(indexes.SEPERATOR)[-1]
        filterExpression = Attr(Attribute.DISPENSER_ORG.name).contains(dispenserOrg)

        return self.queryPrescriberDate(
            indexes.INDEX_PRESCRIBER_DSDATE,
            prescriberOrg,
            startDate,
            endDate,
            filterExpression,
            termRegex,
        )

    def prescDate(self, rangeStart, rangeEnd, termRegex):
        """
        Query the prescriberDate index.
        """
        prescriberOrg, startDate = rangeStart.split(indexes.SEPERATOR)
        endDate = rangeEnd.split(indexes.SEPERATOR)[-1]

        return self.queryPrescriberDate(
            indexes.INDEX_PRESCRIBER_DATE, prescriberOrg, startDate, endDate, termRegex=termRegex
        )

    def dispDate(self, rangeStart, rangeEnd, termRegex):
        """
        Query the dispenserDate index.
        """
        dispenserOrg, startDate = rangeStart.split(indexes.SEPERATOR)
        endDate = rangeEnd.split(indexes.SEPERATOR)[-1]

        return self.queryDispenserDate(
            indexes.INDEX_DISPENSER_DATE, dispenserOrg, startDate, endDate, termRegex=termRegex
        )

    def nomPharmStatus(self, rangeStart, _, termRegex):
        """
        Query the nomPharmStatus index for terms.
        """
        odsCode, status = rangeStart.split("_")

        return self.queryNomPharmStatusTerms(
            indexes.INDEX_NOMPHARM, odsCode, status, termRegex=termRegex
        )

    def buildTerms(self, items, indexName, termRegex):
        """
        Build terms from items returned by the index query.
        """
        # POC - Project the body into the index and do away with 'terms' altogether.
        terms = []
        for item in items:
            indexTerms = item.get(ProjectedAttribute.INDEXES.name, {}).get(indexName.lower())
            if not indexTerms:
                continue
            [
                terms.append((indexTerm, item[Key.PK.name]))
                for indexTerm in indexTerms
                # POC - termRegex can be replaced by filter expressions for status and releaseVersion.
                if ((not termRegex) or re.search(termRegex, indexTerm))
            ]
        return terms

    def padOrTrimDate(self, date):
        """
        Ensure the date length is fourteen characters, if present.
        """
        if not date:
            return None

        if len(date) >= 14:
            return date[:14]

        while len(date) < 14:
            date = date + "0"
        return date

    def queryNhsNumberDate(
        self, index, nhsNumber, startDate=None, endDate=None, filterExpression=None, termRegex=None
    ):
        """
        Return the epsRecord terms which match the supplied range and regex for the nhsNumberDate index.
        """
        startDate, endDate = [self.padOrTrimDate(date) for date in [startDate, endDate]]

        pkExpression = BotoKey(Attribute.NHS_NUMBER.name).eq(nhsNumber)
        skExpression = None
        if startDate and endDate:
            [valid, skExpression] = self._getValidRangeCondition(
                Attribute.CREATION_DATETIME.name, startDate, endDate
            )

            if not valid:
                return []
        elif startDate:
            skExpression = BotoKey(Attribute.CREATION_DATETIME.name).gte(startDate)
        elif endDate:
            skExpression = BotoKey(Attribute.CREATION_DATETIME.name).lte(endDate)

        keyConditionExpression = pkExpression if not skExpression else pkExpression & skExpression
        items = self.client.queryIndex(
            GSI.NHS_NUMBER_DATE.name, keyConditionExpression, filterExpression
        )

        return self.buildTerms(items, index, termRegex)

    def queryPrescriberDate(
        self, index, prescriberOrg, startDate, endDate, filterExpression=None, termRegex=None
    ):
        """
        Return the epsRecord terms which match the supplied range and regex for the prescriberDate index.
        """
        startDate, endDate = [self.padOrTrimDate(date) for date in [startDate, endDate]]

        pkExpression = BotoKey(Attribute.PRESCRIBER_ORG.name).eq(prescriberOrg)
        [valid, skExpression] = self._getValidRangeCondition(
            Attribute.CREATION_DATETIME.name, startDate, endDate
        )

        if not valid:
            return []

        items = self.client.queryIndex(
            GSI.PRESCRIBER_DATE.name, pkExpression & skExpression, filterExpression
        )

        return self.buildTerms(items, index, termRegex)

    def queryDispenserDate(
        self, index, dispenserOrg, startDate, endDate, filterExpression=None, termRegex=None
    ):
        """
        Return the epsRecord terms which match the supplied range and regex for the dispenserDate index.
        """
        startDate, endDate = [self.padOrTrimDate(date) for date in [startDate, endDate]]

        pkExpression = BotoKey(Attribute.DISPENSER_ORG.name).eq(dispenserOrg)
        [valid, skExpression] = self._getValidRangeCondition(
            Attribute.CREATION_DATETIME.name, startDate, endDate
        )

        if not valid:
            return []

        items = self.client.queryIndex(
            GSI.DISPENSER_DATE.name, pkExpression & skExpression, filterExpression
        )

        return self.buildTerms(items, index, termRegex)

    def queryNomPharmStatus(self, odsCode, allStatuses=False, limit=None):
        """
        Return the nomPharmStatus prescription keys which match the supplied ODS code.
        Query using the nominatedPharmacyStatus index. If allStatuses is False, only return prescriptions
        with status TO_BE_DISPENSED (0001).
        """
        keyConditionExpression = BotoKey(Attribute.NOMINATED_PHARMACY.name).eq(odsCode)

        isReadyCondition = (
            BotoKey(Attribute.IS_READY.name).eq(int(True))
            if not allStatuses
            else BotoKey(Attribute.IS_READY.name).between(0, 1)
        )
        keyConditionExpression = keyConditionExpression & isReadyCondition

        items = self.client.queryIndexWithLimit(
            GSI.NOMINATED_PHARMACY_STATUS.name, keyConditionExpression, None, limit
        )

        return [item[Key.PK.name] for item in items]

    def queryNomPharmStatusTerms(self, index, odsCode, status, termRegex=None):
        """
        Return the nomPharmStatus terms which match the supplied ODS code and status.
        Query using the nominatedPharmacyStatus index, with isReady derived from the status.
        """
        isReady = status == PrescriptionStatus.TO_BE_DISPENSED

        keyConditionExpression = BotoKey(Attribute.NOMINATED_PHARMACY.name).eq(odsCode) & BotoKey(
            Attribute.IS_READY.name
        ).eq(int(isReady))

        filterExpression = Attr(ProjectedAttribute.STATUS.name).contains(status)

        items = self.client.queryIndex(
            GSI.NOMINATED_PHARMACY_STATUS.name, keyConditionExpression, filterExpression
        )

        return self.buildTerms(items, index, termRegex)

    def queryClaimId(self, claimId):
        """
        Search for an existing batch claim containing the given claimId.
        """
        keyConditionExpression = BotoKey(Key.SK.name).eq(SortKey.CLAIM.value)
        filterExpression = Attr(ProjectedAttribute.CLAIM_IDS.name).contains(claimId)

        items = self.client.queryIndex(GSI.CLAIM_ID.name, keyConditionExpression, filterExpression)

        return [item[Key.PK.name] for item in items]

    def queryNextActivityDate(self, rangeStart, rangeEnd):
        """
        Yields the epsRecord keys which match the supplied nextActivity and date range for the nextActivity index.

        nextActivity is suffix-sharded with NEXT_ACTIVITY_DATE_PARTITIONS to avoid hot partitions on ddb.
        This means NEXT_ACTIVITY_DATE_PARITIONS + 1 queries are performed, one for each partition
        and one for the non-partitioned nextActivityDate index.
        """
        nextActivity, startDate = rangeStart.split("_")
        endDate = rangeEnd.split("_")[-1]

        [valid, skExpression] = self._getValidRangeCondition(
            Attribute.NEXT_ACTIVITY_DATE.name, startDate, endDate
        )

        if not valid:
            return []

        shards = [None] + list(range(1, NEXT_ACTIVITY_DATE_PARTITIONS + 1))

        for shard in shards:
            yield from self._queryNextActivityDateShard(nextActivity, skExpression, shard)

    def _queryNextActivityDateShard(self, nextActivity, skExpression, shard):
        """
        Return a generator for the epsRecord keys which match the supplied nextActivity and date range
        for a given pk shard.
        """
        expectedNextActivity = nextActivity if shard is None else f"{nextActivity}.{shard}"
        pkExpression = BotoKey(Attribute.NEXT_ACTIVITY.name).eq(expectedNextActivity)

        return self.client.queryIndexYield(GSI.NEXT_ACTIVITY_DATE.name, pkExpression & skExpression)

    def _getDateRangeForQuery(self, startDatetimeStr, endDatetimeStr):
        """
        Get days included in the given range. For use in claimNotificationStoreTime index query.
        """
        startDatetime = datetime.strptime(startDatetimeStr, TimeFormats.STANDARD_DATE_TIME_FORMAT)
        endDatetime = datetime.strptime(endDatetimeStr, TimeFormats.STANDARD_DATE_TIME_FORMAT)

        return [
            (startDatetime + timedelta(days=d)).strftime(TimeFormats.STANDARD_DATE_FORMAT)
            for d in range((endDatetime.date() - startDatetime.date()).days + 1)
        ]

    def queryClaimNotificationStoreTime(self, internalID, startDatetimeStr, endDatetimeStr):
        """
        Search for claim notification documents whose store times fall within the specified window.
        """
        [valid, skExpression] = self._getValidRangeCondition(
            Attribute.STORE_TIME.name, startDatetimeStr, endDatetimeStr
        )

        if not valid:
            return []

        dates = self._getDateRangeForQuery(startDatetimeStr, endDatetimeStr)
        generators = []

        for date in dates:
            pkExpression = BotoKey(Attribute.CLAIM_NOTIFICATION_STORE_DATE.name).eq(date)
            self.logObject.writeLog(
                "DDB0013",
                None,
                {
                    "date": date,
                    "startTime": startDatetimeStr,
                    "endTime": endDatetimeStr,
                    "internalID": internalID,
                },
            )
            generators.append(
                self.client.queryIndexYield(
                    GSI.CLAIM_NOTIFICATION_STORE_TIME.name, pkExpression & skExpression, None
                )
            )

        for generator in generators:
            yield from generator

    def _getValidRangeCondition(self, key, start, end) -> Tuple[bool, object]:
        """
        Returns a range condition if the start < end
        """
        if end == start:
            return True, BotoKey(key).eq(start)
        if end < start:
            return False, None
        else:
            return True, BotoKey(key).between(start, end)

    def queryBatchClaimIdSequenceNumber(self, sequenceNumber, nwssp=False):
        """
        Query the claimIdSequenceNumber index for batch claim IDs based on sequence number.
        """
        indexName = (
            GSI.CLAIM_ID_SEQUENCE_NUMBER_NWSSP.name if nwssp else GSI.CLAIM_ID_SEQUENCE_NUMBER.name
        )
        keyName = Attribute.SEQUENCE_NUMBER_NWSSP.name if nwssp else Attribute.SEQUENCE_NUMBER.name

        keyConditionExpression = BotoKey(keyName).eq(sequenceNumber)

        items = self.client.queryIndex(indexName, keyConditionExpression, None)

        return [
            item[Key.PK.name]
            for item in items
            if item[Key.PK.name] not in ["claimSequenceNumber", "claimSequenceNumberNwssp"]
        ]
