from eps_spine_shared.common.dynamodb_client import EpsDynamoDbClient


class DynamoDbClient(EpsDynamoDbClient):
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
    def serialiseForDynamoDb(self, item):
        """Convert item into DynamoDB format."""
        return self.serialise_for_dynamodb(item)

    def deserialiseFromDynamoDb(self, item):
        """Convert item from DynamoDB format."""
        return self.deserialise_from_dynamodb(item)

    def addConditionExpression(self, putKwargs, isUpdate, item):
        """Adds a condition expression to the put kwargs based on whether the item is being updated."""
        return self.add_condition_expression(putKwargs, isUpdate, item)

    def putItem(self, internalID, item, isUpdate=False, logItemSize=True):
        """Insert an item into the configured DynamoDB table as a single put, after serialising and logging its size."""
        return self.put_item(internalID, item, isUpdate, logItemSize)

    def transactWriteItems(self, internalID, items, isUpdate=False, logItemSize=True):
        """
        Insert items into the configured DynamoDB table as a single transaction,
        after serialising and logging its size.
        """
        return self.transact_write_items(internalID, items, isUpdate, logItemSize)

    def addLastModifiedToItem(self, item):
        """Add last modified timestamp and day to items."""
        return self.add_last_modified_to_item(item)

    def insertItems(self, internalID, items, isUpdate=False, logItemSize=True):
        """Perform a put_item or a transact_write_items depending on the number of items."""
        return self.insert_items(internalID, items, isUpdate, logItemSize)

    def getItem(self, internalID, pk, sk, expectExists=True, expectNone=False):
        """Return an item from the DynamoDB table."""
        return self.get_item(internalID, pk, sk, expectExists, expectNone)

    def queryIndex(self, indexName, keyConditionExpression, filterExpression):
        """Return the items that match the supplied expressions, for the given index."""
        return self.query_index(indexName, keyConditionExpression, filterExpression)

    def queryIndexWithLimit(self, indexName, keyConditionExpression, filterExpression, limit):
        """
        Return the items that match the supplied expressions, for the given index.
        Will return item count up to the given limit.
        """
        return self.query_index_with_limit(
            indexName, keyConditionExpression, filterExpression, limit
        )

    def queryIndexYield(self, indexName, keyConditionExpression, filterExpression=None):
        """
        Return the items that match the supplied expressions, for the given index.
        Uses yield to allow retrieval of a large number of items.
        """
        return self.query_index_yield(indexName, keyConditionExpression, filterExpression)

    def buildFilterExpression(self, filterDict):
        """Build a filter expression for use in the index query."""
        return self.build_filter_expression(filterDict)

    def deleteItem(self, pk, sk):
        """Delete an item from the table."""
        return self.delete_item(pk, sk)
