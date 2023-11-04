import pytest
from unittest.mock import patch, MagicMock
from sweepai.core import vector_db
from sweepai.utils.github_utils import ClonedRepo
from sweepai.config.client import SweepConfig

def test_parse_collection_name():
    assert vector_db.parse_collection_name("test_name") == "test_name"
    assert vector_db.parse_collection_name("test/name") == "test--name"
    assert vector_db.parse_collection_name("test_name_with_64_characters_12345678901234567890") == "test_name_with_64_characters_1234567890123456789"

@patch('requests.post')
def test_embed_huggingface(mock_post):
    mock_post.return_value.json.return_value = {"embeddings": "test"}
    assert vector_db.embed_huggingface(["text1", "text2"]) == "test"

@patch('replicate.Client')
def test_embed_replicate(mock_client):
    mock_client.return_value.deployments.get.return_value.predictions.create.return_value.output = [{"embedding": "test"}]
    assert vector_db.embed_replicate(["text1", "text2"]) == ["test"]

def test_embed_texts():
    assert isinstance(vector_db.embed_texts(("text1", "text2")), list)

def test_embedding_function():
    assert isinstance(vector_db.embedding_function(["text1", "text2"]), list)

@patch('sweepai.core.vector_db.get_deeplake_vs_from_repo')
def test_get_deeplake_vs_from_repo(mock_get_deeplake_vs_from_repo):
    mock_get_deeplake_vs_from_repo.return_value = ("deeplake_vs", "index", 2)
    cloned_repo = ClonedRepo("repo_full_name", "installation_id")
    assert vector_db.get_deeplake_vs_from_repo(cloned_repo) == ("deeplake_vs", "index", 2)

def test_prepare_documents_metadata_ids():
    snippets = [MagicMock(), MagicMock()]
    cloned_repo = ClonedRepo("repo_full_name", "installation_id")
    files_to_scores = {"file1": 1, "file2": 2}
    start = 0
    repo_full_name = "repo_full_name"
    assert isinstance(vector_db.prepare_documents_metadata_ids(snippets, cloned_repo, files_to_scores, start, repo_full_name), tuple)

def test_compute_vector_search_scores():
    file_list = ["file1", "file2"]
    cloned_repo = ClonedRepo("repo_full_name", "installation_id")
    repo_full_name = "repo_full_name"
    assert isinstance(vector_db.compute_vector_search_scores(file_list, cloned_repo, repo_full_name), dict)

def test_prepare_lexical_search_index():
    cloned_repo = ClonedRepo("repo_full_name", "installation_id")
    sweep_config = SweepConfig()
    repo_full_name = "repo_full_name"
    assert isinstance(vector_db.prepare_lexical_search_index(cloned_repo, sweep_config, repo_full_name), tuple)

def test_compute_deeplake_vs():
    collection_name = "collection_name"
    documents = ["doc1", "doc2"]
    ids = ["id1", "id2"]
    metadatas = [{"metadata1": "value1"}, {"metadata2": "value2"}]
    sha = "sha"
    assert isinstance(vector_db.compute_deeplake_vs(collection_name, documents, ids, metadatas, sha), vector_db.VectorStore)

def test_compute_embeddings():
    documents = ["doc1", "doc2"]
    assert isinstance(vector_db.compute_embeddings(documents), tuple)

def test_get_relevant_snippets():
    cloned_repo = ClonedRepo("repo_full_name", "installation_id")
    query = "query"
    assert isinstance(vector_db.get_relevant_snippets(cloned_repo, query), list)
