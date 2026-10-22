"""Protect existing retrieval collections unless a rebuild is explicit."""
from scripts.embed_and_index import parse_args


def test_indexing_preserves_collections_by_default():
    assert parse_args([]).reseting is False
    assert parse_args(["--no-reseting"]).reseting is False


def test_rebuild_requires_explicit_option():
    assert parse_args(["--reseting"]).reseting is True


def test_existing_collection_is_never_deleted_during_upsert():
    from unittest.mock import Mock
    from scripts.embed_and_index import recreate_collection
    client = Mock()
    client.collection_exists.return_value = True
    recreate_collection(client, "fitness_programs", reset=False)
    client.delete_collection.assert_not_called()
    client.create_collection.assert_not_called()


def test_first_upsert_creates_missing_collection():
    from unittest.mock import Mock
    from scripts.embed_and_index import recreate_collection
    client = Mock()
    client.collection_exists.return_value = False
    recreate_collection(client, "fitness_programs", reset=False)
    client.delete_collection.assert_not_called()
    assert client.create_collection.call_args.kwargs["collection_name"] == "fitness_programs"
