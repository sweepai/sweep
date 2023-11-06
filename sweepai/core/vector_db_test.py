import pytest
from unittest.mock import patch, MagicMock
from sweepai.core import vector_db
from sweepai.utils import github_utils

def test_parse_collection_name():
    assert vector_db.parse_collection_name("test_name") == "test_name"
    assert vector_db.parse_collection_name("test/name") == "test--name"
    assert vector_db.parse_collection_name("test name") == "test--name"
    assert vector_db.parse_collection_name("test_name"*10) == "test_name"*6 + "test_"

@patch("requests.post")
def test_embed_huggingface(mock_post):
    mock_post.return_value.json.return_value = {"embeddings": "test"}
    assert vector_db.embed_huggingface(["text1", "text2"]) == "test"

@patch("replicate.Client")
def test_embed_replicate(mock_client):
    mock_client.return_value.deployments.get.return_value.predictions.create.return_value.output = [{"embedding": "test"}]
    assert vector_db.embed_replicate(["text1", "text2"]) == ["test"]

@patch("sentence_transformers.SentenceTransformer")
def test_embed_texts(mock_transformer):
    mock_transformer.return_value.encode.return_value = "test"
    assert vector_db.embed_texts(("text1", "text2")) == "test"

@patch("sweepai.core.vector_db.embed_texts")
def test_embedding_function(mock_embed_texts):
    mock_embed_texts.return_value = "test"
    assert vector_db.embedding_function(["text1", "text2"]) == "test"

@patch("sweepai.core.vector_db.ClonedRepo")
@patch("sweepai.core.vector_db.prepare_lexical_search_index")
@patch("sweepai.core.vector_db.compute_vector_search_scores")
@patch("sweepai.core.vector_db.prepare_documents_metadata_ids")
@patch("sweepai.core.vector_db.compute_deeplake_vs")
def test_get_deeplake_vs_from_repo(mock_compute_deeplake_vs, mock_prepare_documents_metadata_ids, mock_compute_vector_search_scores, mock_prepare_lexical_search_index, mock_cloned_repo):
    mock_compute_deeplake_vs.return_value = "test"
    assert vector_db.get_deeplake_vs_from_repo(mock_cloned_repo) == ("test", None, None)

def test_prepare_documents_metadata_ids():
    snippets = [github_utils.Snippet("content", 1, 2, "file_path")]
    cloned_repo = github_utils.ClonedRepo("repo_full_name", "installation_id")
    files_to_scores = {"file_path": 1}
    start = 0
    repo_full_name = "repo_full_name"
    assert vector_db.prepare_documents_metadata_ids(snippets, cloned_repo, files_to_scores, start, repo_full_name) == ("repo-full-name", ["content"], ["file_path:1:2"], [{"file_path": "file_path", "start": 1, "end": 2, "score": 1}])

def test_compute_vector_search_scores():
    file_list = ["file1", "file2"]
    cloned_repo = github_utils.ClonedRepo("repo_full_name", "installation_id")
    repo_full_name = "repo_full_name"
    assert vector_db.compute_vector_search_scores(file_list, cloned_repo, repo_full_name) == {"file1": 0, "file2": 0}

def test_prepare_lexical_search_index():
    cloned_repo = github_utils.ClonedRepo("repo_full_name", "installation_id")
    sweep_config = vector_db.SweepConfig()
    repo_full_name = "repo_full_name"
    assert vector_db.prepare_lexical_search_index(cloned_repo, sweep_config, repo_full_name) == ([], [], None)

@patch("sweepai.core.vector_db.redis_client")
@patch("sweepai.core.vector_db.embedding_function")
@patch("sweepai.core.vector_db.init_deeplake_vs")
def test_compute_deeplake_vs(mock_init_deeplake_vs, mock_embedding_function, mock_redis_client):
    mock_embedding_function.return_value = "test"
    mock_init_deeplake_vs.return_value.add.return_value = "test"
    assert vector_db.compute_deeplake_vs("collection_name", ["document"], ["id"], ["metadata"], "sha") == "test"

@patch("sweepai.core.vector_db.redis_client")
@patch("sweepai.core.vector_db.embedding_function")
def test_compute_embeddings(mock_embedding_function, mock_redis_client):
    mock_embedding_function.return_value = "test"
    assert vector_db.compute_embeddings(["document"]) == ("test", [], [], "test")

@patch("sweepai.core.vector_db.ClonedRepo")
@patch("sweepai.core.vector_db.get_query_embedding")
def test_get_relevant_snippets(mock_get_query_embedding, mock_cloned_repo):
    mock_get_query_embedding.return_value = "test"
    assert vector_db.get_relevant_snippets(mock_cloned_repo, "query") == []
