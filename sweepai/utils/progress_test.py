from unittest.mock import patch

from sweepai.utils.progress import create_index


@patch("sweepai.utils.progress.global_mongo_client")
def test_create_index(mock_mongo_client):
    mock_db = mock_mongo_client.return_value
    mock_collection = mock_db.__getitem__.return_value

    create_index()

    mock_collection.create_index.assert_called_once_with("tracking_id", unique=True)
