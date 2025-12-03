import zlib
from uuid import uuid4

import simplejson

from eps_spine_shared.common.dynamodb_client import EpsDataStoreError
from eps_spine_shared.common.dynamodb_common import Key, ProjectedAttribute, SortKey
from tests.dynamodb_test import DynamoDbTest


class DynamoDbClientTest(DynamoDbTest):
    """
    Tests relating to DynamoDbClient.
    """

    def test_log_item_size_default(self):
        """
        Test logging size of items using default size fn.
        """
        key = str(uuid4())
        item = {
            Key.PK.name: key,
            Key.SK.name: "DEF",
            ProjectedAttribute.BODY.name: {"a": 1, "b": True},
        }
        serialised_item = self.datastore.client.serialise_for_dynamodb(item)
        internal_id = self.internal_id
        self.datastore.client._log_item_size(internal_id, serialised_item)

        expected = {
            "itemType": "DEF",
            "key": key,
            "size": 169,
            "table": self.datastore.client.table_name,
            "internalID": internal_id,
        }

        logs = self.logger.get_log_occurrences("DDB0011")
        self.assertEqual(logs[0], expected)

    def test_log_item_size_record(self):
        """
        Test logging size of record items.
        """
        key = str(uuid4())
        body = zlib.compress(simplejson.dumps({"a": 1, "b": True}).encode("utf-8"))
        item = {
            Key.PK.name: key,
            Key.SK.name: SortKey.RECORD.value,
            ProjectedAttribute.BODY.name: body,
        }
        serialised_item = self.datastore.client.serialise_for_dynamodb(item)
        internal_id = self.internal_id
        self.datastore.client._log_item_size(internal_id, serialised_item)

        expected = {
            "itemType": SortKey.RECORD.value,
            "key": key,
            "size": 184,
            "table": self.datastore.client.table_name,
            "internalID": internal_id,
        }

        logs = self.logger.get_log_occurrences("DDB0011")
        self.assertEqual(logs[0], expected)

    def test_log_item_size_document(self):
        """
        Test logging size of document items.
        """
        key = str(uuid4())
        content = self.get_document_content()
        internal_id = self.internal_id
        document = self.datastore.buildDocument(internal_id, {"content": content}, None)
        document[Key.PK.name] = key
        serialised_item = self.datastore.client.serialise_for_dynamodb(document)
        self.datastore.client._log_item_size(internal_id, serialised_item)

        expected = {
            "itemType": SortKey.DOCUMENT.value,
            "key": key,
            "size": 264,
            "table": self.datastore.client.table_name,
            "internalID": internal_id,
        }

        logs = self.logger.get_log_occurrences("DDB0011")
        self.assertEqual(logs[0], expected)

    def test_log_item_size_document_no_content(self):
        """
        Test logging size of document items when no content is present.
        """
        key = str(uuid4())
        internal_id = self.internal_id
        document = self.datastore.buildDocument(internal_id, {}, None)
        document[Key.PK.name] = key
        serialised_item = self.datastore.client.serialise_for_dynamodb(document)
        self.datastore.client._log_item_size(internal_id, serialised_item)

        expected = {
            "itemType": SortKey.DOCUMENT.value,
            "key": key,
            "size": 193,
            "table": self.datastore.client.table_name,
            "internalID": internal_id,
        }

        logs = self.logger.get_log_occurrences("DDB0011")
        self.assertEqual(logs[0], expected)

    def test_log_item_size_claim(self):
        """
        Test logging size of items using bespoke claim fn.
        """
        key = str(uuid4())
        item = {
            Key.PK.name: key,
            Key.SK.name: SortKey.CLAIM.value,
            ProjectedAttribute.BODY.name: {"a": 1, "b": True, "Batch XML": b"<xml />"},
        }
        serialised_item = self.datastore.client.serialise_for_dynamodb(item)
        internal_id = self.internal_id
        self.datastore.client._log_item_size(internal_id, serialised_item)

        expected = {
            "itemType": SortKey.CLAIM.value,
            "key": key,
            "size": 226,
            "table": self.datastore.client.table_name,
            "internalID": internal_id,
        }

        logs = self.logger.get_log_occurrences("DDB0011")
        self.assertEqual(logs[0], expected)

    def test_log_item_size_work_list(self):
        """
        Test logging size of items using bespoke workList fn.
        WorkList may or may not have responseDetails containing compressed xml.
        """
        key = str(uuid4())
        bodies = [
            ({"a": 1, "b": True}, 169),
            ({"a": 1, "b": True, "responseDetails": {"XML": b"<xml />"}}, 40),
        ]

        for i, (body, size) in enumerate(bodies):
            item = {
                Key.PK.name: key,
                Key.SK.name: SortKey.WORK_LIST.value,
                ProjectedAttribute.BODY.name: body,
            }
            serialised_item = self.datastore.client.serialise_for_dynamodb(item)
            internal_id = self.internal_id
            self.datastore.client._log_item_size(internal_id, serialised_item)

            expected = {
                "itemType": SortKey.WORK_LIST.value,
                "key": key,
                "size": size,
                "table": self.datastore.client.table_name,
                "internalID": internal_id,
            }

            logs = self.logger.get_log_occurrences("DDB0011")
            self.assertEqual(logs[i], expected)

    def test_get_item_raises_data_store_error_when_pk_is_falsy(self):
        """
        Test that the get_item method throws an EpsDataStoreError matching that thrown by the original datastore,
        when the given key is falsy.
        """
        keys = [False, "", [], {}]
        for key in keys:
            with self.assertRaises(EpsDataStoreError):
                self.datastore.client.get_item(self.internal_id, key, "SK")
