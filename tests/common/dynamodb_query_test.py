from unittest.mock import Mock

from boto3.dynamodb.conditions import Key as BotoKey

from eps_spine_shared.common.dynamodb_common import GSI, Attribute, Key
from eps_spine_shared.common.dynamodb_query import DynamoDbQuery
from tests.dynamodb_test import DynamoDbTest


class DynamoDbQueryTest(DynamoDbTest):
    """
    Unit tests for the DynamoDbQuery Wrapper
    """

    def test_pagination(self):
        """
        Test that a query which requires pagination works correctly
        """
        get_paginator_mock = Mock()
        paginate_mock = Mock()
        get_paginator_mock.return_value.paginate = paginate_mock
        self.datastore.client.client.get_paginator = get_paginator_mock

        paginate_mock.side_effect = [
            [
                {
                    "Items": [{"PK": {"S": "item1"}}, {"PK": {"S": "item2"}}],
                    "LastEvaluatedKey": {"PK": {"S": "item2"}},
                },
                {"Items": [{"PK": {"S": "item3"}}]},
            ]
        ]

        query = DynamoDbQuery(
            self.datastore.client,
            self.logger,
            self.internal_id,
            GSI.NHS_NUMBER_DATE,
            BotoKey(Attribute.NHS_NUMBER.name).eq("someNhsNumber"),
        )

        items = list(query)
        self.assertTrue(query.complete)
        self.assertEqual(3, len(items))
        ddb0050_logs = self.logger.get_log_occurrences("DDB0050")
        self.assertEqual(2, len(ddb0050_logs))
        self.assertEqual(2, ddb0050_logs[0]["itemCount"])
        self.assertEqual(1, ddb0050_logs[1]["itemCount"])


class DynamoDbQueryIntegrationTest(DynamoDbTest):
    """
    Tests of the DynamoDbQuery Wrapper
    """

    def test_query_single_item(self):
        """
        Test that a single item can be retrieved via a query
        """

        prescription_id, nhs_number = self.get_new_record_keys()
        record = self.get_record(nhs_number)

        self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        query = DynamoDbQuery(
            self.datastore.client,
            self.logger,
            self.internal_id,
            GSI.NHS_NUMBER_DATE,
            BotoKey(Attribute.NHS_NUMBER.name).eq(nhs_number),
        )

        items = list(query)
        self.assertTrue(query.complete)
        self.assertEqual(1, len(items))
        self.assertEqual(prescription_id, items[0][Key.PK.name])

    def test_query_multiple_items(self):
        """
        Test that multiple items can be retrieved via a query
        """
        _, nhs_number = self.get_new_record_keys()
        for _ in range(5):
            prescription_id, _ = self.get_new_record_keys()
            record = self.get_record(nhs_number)
            self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        query = DynamoDbQuery(
            self.datastore.client,
            self.logger,
            self.internal_id,
            GSI.NHS_NUMBER_DATE,
            BotoKey(Attribute.NHS_NUMBER.name).eq(nhs_number),
        )

        items = list(query)
        self.assertTrue(query.complete)
        self.assertEqual(5, len(items))

    def test_query_with_limit(self):
        """
        Test that a query with a limit works correctly
        """
        _, nhs_number = self.get_new_record_keys()
        for _ in range(10):
            prescription_id, _ = self.get_new_record_keys()
            record = self.get_record(nhs_number)
            self.datastore.insert_eps_record_object(self.internal_id, prescription_id, record)

        query = DynamoDbQuery(
            self.datastore.client,
            self.logger,
            self.internal_id,
            GSI.NHS_NUMBER_DATE,
            BotoKey(Attribute.NHS_NUMBER.name).eq(nhs_number),
            limit=5,
        )

        items = list(query)
        self.assertFalse(query.complete)
        self.assertEqual(5, len(items))
