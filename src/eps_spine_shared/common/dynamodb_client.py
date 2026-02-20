import copy
import json
import random
import sys
from datetime import datetime, timezone
from decimal import Decimal

from boto3.dynamodb.conditions import Attr, ConditionExpressionBuilder
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from boto3.session import Session
from botocore.config import Config
from botocore.credentials import DeferredRefreshableCredentials
from botocore.exceptions import ClientError, NoCredentialsError

from eps_spine_shared.common.dynamodb_common import (
    CONDITION_EXPRESSION,
    REGION_NAME,
    SERVICE_NAME,
    Attribute,
    Key,
    ProjectedAttribute,
    SortKey,
)
from eps_spine_shared.errors import EpsNoCredentialsErrorWithRetry
from eps_spine_shared.logger import EpsLogger


class EpsDynamoDbClient:
    """
    The DynamoDB client specific to the prescriptions message store.
    """

    def __init__(
        self,
        log_object,
        aws_endpoint_url,
        table_name,
        role_arn=None,
        role_session_name=None,
        sts_endpoint_url=None,
    ):
        """
        Instantiate the DynamoDB client.
        """
        self.log_object = EpsLogger(log_object)
        self.table_name = table_name
        self.aws_endpoint_url = aws_endpoint_url
        self.role_arn = role_arn
        self.role_session_name = role_session_name
        self.sts_endpoint_url = sts_endpoint_url

        try:
            session = Session()

            if role_arn and role_session_name and sts_endpoint_url:
                credentials = DeferredRefreshableCredentials(
                    refresh_using=self._refreshed_credentials_with_retry, method="sts-assume-role"
                )
                session._session._credentials = credentials  # noqa: SLF001
            else:
                self.log_object.write_log(
                    "DDB0006",
                    None,
                    {
                        "role": role_arn,
                        "sessionName": role_session_name,
                        "endpoint": sts_endpoint_url,
                    },
                )

            resource_args = {"service_name": SERVICE_NAME, "region_name": REGION_NAME}
            if aws_endpoint_url:
                self.log_object.write_log("DDB0003", None, {"awsEndpointUrl": aws_endpoint_url})
                resource_args["endpoint_url"] = aws_endpoint_url
            else:
                self.log_object.write_log("DDB0004", None)

            self.resource = session.resource(**resource_args)
            self.table = self.resource.Table(table_name)

            self.client = session.client(**resource_args)
            self.deserialiser = TypeDeserializer()
            self.serialiser = TypeSerializer()
        except Exception as ex:
            self.log_object.write_log("DDB0000", sys.exc_info(), {"error": str(ex)})
            raise ex

        self.log_object.write_log("DDB0001", None, {"tableName": table_name})

    def _refreshed_credentials_with_retry(self, attempts=2) -> dict:
        """
        Retry _refreshed_credentials for a maximum number of attempts until credentials are returned or raise
        EpsNoCredentialsErrorWithRetry including the number of attempts.
        """
        for _ in range(attempts):
            try:
                return self._refreshed_credentials()
            except NoCredentialsError as e:
                latest_exception = e

        raise EpsNoCredentialsErrorWithRetry(attempts=attempts) from latest_exception

    def _refreshed_credentials(self) -> dict:
        """
        Refreshes the IAM credentials provided to us by STS for the duration of our session.
        This callback is invoked automatically by boto when we are past the lifetime of our
        session (uses boto3 default of refreshing 15 mins before expiry).
        DurationSeconds - duration of the role session
        RoleSessionName - becomes the User Name for subsequent api calls made with the credentials returned
        Returns:
            dict -> A dictionary containing our new set of credentials from STS as well as the
            expiration timestamp for the session.
        Adapted from nhs-aws-helpers
        """
        sts_session = Session()

        config = Config(
            connect_timeout=1,
            read_timeout=3,
            max_pool_connections=10,
            retries={"mode": "standard", "total_max_attempts": 4},
        )

        sts_client = sts_session.client(
            "sts", region_name=REGION_NAME, endpoint_url=self.sts_endpoint_url, config=config
        )

        params = {
            "RoleArn": self.role_arn,
            "RoleSessionName": self.role_session_name,
            "DurationSeconds": 3600,
        }

        # Any exceptions raised here must be caught and logged by the code using the client
        response = sts_client.assume_role(**params).get("Credentials")

        self.log_object.write_log(
            "DDB0005",
            None,
            {
                "role": self.role_arn,
                "sessionName": self.role_session_name,
                "endpoint": self.sts_endpoint_url,
            },
        )

        return {
            "access_key": response.get("AccessKeyId"),
            "secret_key": response.get("SecretAccessKey"),
            "token": response.get("SessionToken"),
            "expiry_time": response.get("Expiration").isoformat(),
        }

    def _log_item_size(self, internal_id, serialised_item):
        """
        Writes a log message including the item type and post-serialisation size in bytes.
        Bespoke sizing functions for items with compressed contents, as bytes won't serialise.
        """

        def default_size(item):
            return sys.getsizeof(json.dumps(item))

        def work_list_size(item):
            try:
                return sys.getsizeof(item["body"]["M"]["responseDetails"]["M"]["XML"]["B"])
            except KeyError:
                return default_size(item)

        def claim_size(claim):
            batch_xml = claim["body"]["M"]["Batch XML"]
            if "S" in batch_xml:
                return default_size(claim)
            batch_xml_size = sys.getsizeof(claim["body"]["M"]["Batch XML"]["B"])
            claim_deep_copy = copy.deepcopy(claim)
            del claim_deep_copy["body"]["M"]["Batch XML"]["B"]
            claim_without_batch_xml_size = sys.getsizeof(json.dumps(claim_deep_copy))
            return batch_xml_size + claim_without_batch_xml_size

        def record_size(record):
            body_size = sys.getsizeof(record["body"]["B"])
            record_deep_copy = copy.deepcopy(record)
            del record_deep_copy["body"]["B"]
            record_without_body_size = sys.getsizeof(json.dumps(record_deep_copy))
            return body_size + record_without_body_size

        def document_size(document):
            if document["pk"]["S"].startswith("Notification_"):
                return ppd_notification_size(document)

            if document["body"]["M"].get("content"):
                content_size = sys.getsizeof(document["body"]["M"]["content"]["B"])
                document_deep_copy = copy.deepcopy(document)
                del document_deep_copy["body"]["M"]["content"]["B"]
                document_without_body_size = sys.getsizeof(json.dumps(document_deep_copy))
                return content_size + document_without_body_size
            else:
                return default_size(document)

        def ppd_notification_size(document):
            document_deep_copy = copy.deepcopy(document)

            payload = None
            if document["body"]["M"]["payload"].get("B"):
                payload = document["body"]["M"]["payload"]["B"]
                del document_deep_copy["body"]["M"]["payload"]["B"]
            elif document["body"]["M"]["payload"].get("S"):
                payload = document["body"]["M"]["payload"]["S"]
                del document_deep_copy["body"]["M"]["payload"]["S"]

            payload_size = sys.getsizeof(payload)
            document_without_payload_size = sys.getsizeof(json.dumps(document_deep_copy))
            return payload_size + document_without_payload_size

        size_funcs = {
            SortKey.CLAIM.value: claim_size,
            SortKey.WORK_LIST.value: work_list_size,
            SortKey.RECORD.value: record_size,
            SortKey.DOCUMENT.value: document_size,
        }

        item_key = serialised_item["pk"]["S"]
        item_type = serialised_item["sk"]["S"]

        try:
            size = size_funcs.get(item_type, default_size)(serialised_item)
            self.log_object.write_log(
                "DDB0011",
                None,
                {
                    "itemType": item_type,
                    "table": self.table_name,
                    "key": item_key,
                    "size": size,
                    "internalID": internal_id,
                },
            )
        except Exception:  # noqa: BLE001
            self.log_object.write_log(
                "DDB0012",
                sys.exc_info(),
                {
                    "table": self.table_name,
                    "itemType": item_type,
                    "key": item_key,
                    "internalID": internal_id,
                },
            )

    def serialise_for_dynamodb(self, item):
        """
        Convert item into DynamoDB format.
        """
        return {k: self.serialiser.serialize(v) for k, v in item.items()}

    def deserialise_from_dynamodb(self, item):
        """
        Convert item from DynamoDB format.
        """
        return {k: self.deserialiser.deserialize(v) for k, v in item.items()}

    def add_condition_expression(self, put_kwargs, is_update, item):
        """
        Adds a condition expression to the put kwargs based on whether the item is being updated.
        """
        if not is_update:
            put_kwargs["ConditionExpression"] = CONDITION_EXPRESSION
        elif item[Key.SK.name] == SortKey.RECORD.value:
            put_kwargs["ExpressionAttributeNames"] = {"#currentScn": ProjectedAttribute.SCN.name}
            put_kwargs["ExpressionAttributeValues"] = self.serialise_for_dynamodb(
                {":newScn": item.get(ProjectedAttribute.SCN.name)}
            )
            put_kwargs["ConditionExpression"] = "#currentScn < :newScn"
        elif item[Key.SK.name] == SortKey.SEQUENCE_NUMBER.value:
            sequence_number = item.get(Attribute.SEQUENCE_NUMBER.name)
            if sequence_number == 1:
                return
            put_kwargs["ExpressionAttributeNames"] = {"#currentSqn": Attribute.SEQUENCE_NUMBER.name}
            put_kwargs["ExpressionAttributeValues"] = self.serialise_for_dynamodb(
                {":newSqn": sequence_number}
            )
            put_kwargs["ConditionExpression"] = "#currentSqn < :newSqn"

    def put_item(self, internal_id, item, is_update=False, log_item_size=True):
        """
        Insert an item into the configured DynamoDB table as a single put, after serialising and logging its size.
        """
        serialised_item = self.serialise_for_dynamodb(item)
        if log_item_size:
            self._log_item_size(internal_id, serialised_item)

        put_kwargs = {"TableName": self.table_name, "Item": serialised_item}
        self.add_condition_expression(put_kwargs, is_update, item)
        return self.client.put_item(**put_kwargs)

    def transact_write_items(self, internal_id, items, is_update=False, log_item_size=True):
        """
        Insert items into the configured DynamoDB table as a single transaction, after serialising and logging its size.
        """
        transact_items = []
        for item in items:
            serialised_item = self.serialise_for_dynamodb(item)
            if log_item_size:
                self._log_item_size(internal_id, serialised_item)
            transact_item = {
                "Put": {"TableName": self.table_name, "Item": self.serialise_for_dynamodb(item)}
            }
            self.add_condition_expression(transact_item["Put"], is_update, item)
            transact_items.append(transact_item)

        return self.client.transact_write_items(TransactItems=transact_items)

    def add_last_modified_to_item(self, item):
        """
        Add last modified timestamp and day to items.
        """
        dt_now = datetime.now(timezone.utc)
        last_modified_timestamp = Decimal(str(dt_now.timestamp()))
        last_modified_day = dt_now.strftime("%Y%m%d")
        partition_suffix = str(random.randint(0, 11))
        item.update(
            {
                "_lm_day": f"{last_modified_day}.{partition_suffix}",
                "_riak_lm": last_modified_timestamp,
            }
        )

    def insert_items(self, internal_id, items, is_update=False, log_item_size=True):
        """
        Perform a put_item or a transact_write_items depending on the number of items.
        """
        for item in items:
            self.add_last_modified_to_item(item)
        try:
            if len(items) == 1:
                return self.put_item(internal_id, items[0], is_update, log_item_size)
            else:
                return self.transact_write_items(internal_id, items, is_update, log_item_size)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                pk = items[0].get(Key.PK.name)
                log_dict = {
                    "internalID": internal_id,
                    "incomingScn": items[0].get("scn", "None"),
                    "pk": pk,
                    "sk": items[0].get(Key.SK.name),
                    "table": self.table_name,
                }
                if is_update:
                    self.log_object.write_log("DDB0022", None, log_dict)
                    raise EpsDataStoreError(
                        self, pk, EpsDataStoreError.CONDITIONAL_UPDATE_FAILURE
                    ) from e
                else:
                    self.log_object.write_log("DDB0021", None, log_dict)
                    raise EpsDataStoreError(self, pk, EpsDataStoreError.DUPLICATE_ERROR) from e
            else:
                raise e

    def get_item(self, internal_id, pk, sk, expect_exists=True, expect_none=False):
        """
        Return an item from the DynamoDB table.

        expect_exists=False will not raise an error if the item does not exist.
        expect_none=True will not raise an error if the item exists but has no data.
        """
        if not pk:
            self.log_object.write_log(
                "DDB0041", None, {"key": pk, "table": self.table_name, "internalID": internal_id}
            )
            raise EpsDataStoreError(self, pk, EpsDataStoreError.ACCESS_ERROR)

        item = self.table.get_item(Key={Key.PK.name: pk, Key.SK.name: sk}).get("Item")

        self._item_checks(item, pk, expect_exists, expect_none)

        return item

    def _item_checks(self, item, key, expect_exists, expect_none):
        """
        Run standard checks on a returned item
        - Does it exist
        - Does it have data
        """
        if not expect_exists:
            return

        if item is None:
            raise EpsDataStoreError(self, key, EpsDataStoreError.MISSING_RECORD)

        if expect_none:
            return

        if item.get(ProjectedAttribute.BODY.name) is None:
            raise EpsDataStoreError(self, key, EpsDataStoreError.EMPTY_RECORD)

    def query_index(self, index_name, key_condition_expression, filter_expression):
        """
        Return the items that match the supplied expressions, for the given index.
        """
        query_args = {"KeyConditionExpression": key_condition_expression}

        if index_name:
            query_args["IndexName"] = index_name

        if filter_expression:
            query_args["FilterExpression"] = filter_expression

        items = []
        while True:
            response = self.table.query(**query_args)
            items.extend(response["Items"])
            if "LastEvaluatedKey" not in response:
                return items
            query_args["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def query_index_with_limit(
        self, index_name, key_condition_expression, filter_expression, limit
    ):
        """
        Return the items that match the supplied expressions, for the given index.
        Will return item count up to the given limit.
        """
        condition_builder = ConditionExpressionBuilder()
        key_condition_expression, condition_attributes, condition_values = (
            condition_builder.build_expression(key_condition_expression, True)
        )
        query_args = {
            "TableName": self.table_name,
            "IndexName": index_name,
            "KeyConditionExpression": key_condition_expression,
            "ExpressionAttributeNames": condition_attributes,
            "ExpressionAttributeValues": self.serialise_for_dynamodb(condition_values),
        }
        if filter_expression:
            query_args["FilterExpression"] = filter_expression
        if limit:
            query_args["Limit"] = limit

        response_iterator = self.client.get_paginator("query").paginate(**query_args)

        items = []
        for response in response_iterator:
            items.extend([self.deserialise_from_dynamodb(item) for item in response["Items"]])
            if limit and len(items) >= limit:
                items = items[:limit]
                break
        return items

    def query_index_yield(self, index_name, key_condition_expression, filter_expression=None):
        """
        Return the items that match the supplied expressions, for the given index.
        Uses yield to allow retrieval of a large number of items.
        """
        query_args = {"IndexName": index_name, "KeyConditionExpression": key_condition_expression}
        if filter_expression:
            query_args["FilterExpression"] = filter_expression

        found = True
        while found:
            response = self.table.query(**query_args)
            yield [item[Key.PK.name] for item in response["Items"]]
            if "LastEvaluatedKey" not in response:
                found = False
            else:
                query_args["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def build_filter_expression(self, filter_dict):
        """
        Build a filter expression for use in the index query.
        """
        filters = []
        for key, value in filter_dict.items():
            filters.append(Attr(key).eq(value))

        filter_expression = None
        for _filter in filters:
            filter_expression = (
                _filter if filter_expression is None else filter_expression & _filter
            )

        return filter_expression

    def delete_item(self, pk, sk):
        """
        Delete an item from the table.
        """
        key = self.serialise_for_dynamodb({Key.PK.name: pk, Key.SK.name: sk})
        self.client.delete_item(TableName=self.table_name, Key=key)


class EpsDataStoreError(Exception):
    """
    Exception to be raised when encountering issues with the DynamoDB datastore.
    """

    ACCESS_ERROR = "accessError"
    CONDITIONAL_UPDATE_FAILURE = "conditionalUpdateFailure"
    DUPLICATE_ERROR = "duplicateError"
    EMPTY_RECORD = "recordRemoved"
    MISSING_RECORD = "missingRecord"

    def __init__(self, client: EpsDynamoDbClient, key: str, error_topic: str):  # noqa: B042
        """
        The error_topic must match a topic defined as an attribute of this class (above).
        The client should have a log_object, a table_name and an aws_endpoint_url.
        """
        super(EpsDataStoreError, self).__init__()
        self.error_topic = error_topic

        log_values = {
            "awsEndpointUrl": client.aws_endpoint_url,
            "errorTopic": self.error_topic,
            "key": key,
            "tableName": client.table_name,
        }

        log_ref = "UTI0213a" if self.error_topic == self.MISSING_RECORD else "UTI0213"

        client.log_object.write_log(log_ref, None, log_values)
