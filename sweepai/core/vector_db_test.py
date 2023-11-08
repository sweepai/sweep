import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from sweepai.core import vector_db

def test_compute_embeddings():
    documents = ["doc1", "doc2", "doc3"]
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), np.array([7, 8, 9])]

    with patch("sweepai.core.vector_db.redis_client", new_callable=MagicMock) as mock_redis_client, \
         patch("sweepai.core.vector_db.SentenceTransformer", new_callable=MagicMock) as mock_sentence_transformer, \
         patch("sweepai.core.vector_db.openai.Embedding.create", new_callable=MagicMock) as mock_openai_embedding, \
         patch("sweepai.core.vector_db.embed_huggingface", new_callable=MagicMock) as mock_embed_huggingface, \
         patch("sweepai.core.vector_db.embed_replicate", new_callable=MagicMock) as mock_embed_replicate:

        mock_redis_client.mget.return_value = [json.dumps(embedding.tolist()) for embedding in embeddings]
        mock_sentence_transformer.return_value.encode.return_value = embeddings
        mock_openai_embedding.return_value = {"data": [{"embedding": embedding.tolist()} for embedding in embeddings]}
        mock_embed_huggingface.return_value = embeddings
        mock_embed_replicate.return_value = embeddings

        vector_db.VECTOR_EMBEDDING_SOURCE = "sentence-transformers"
        assert vector_db.compute_embeddings(documents) == (embeddings, [], [], embeddings[-1])

        vector_db.VECTOR_EMBEDDING_SOURCE = "openai"
        assert vector_db.compute_embeddings(documents) == (embeddings, [], [], embeddings[-1])

        vector_db.VECTOR_EMBEDDING_SOURCE = "huggingface"
        assert vector_db.compute_embeddings(documents) == (embeddings, [], [], embeddings[-1])

        vector_db.VECTOR_EMBEDDING_SOURCE = "replicate"
        assert vector_db.compute_embeddings(documents) == (embeddings, [], [], embeddings[-1])

        vector_db.VECTOR_EMBEDDING_SOURCE = "invalid"
        with pytest.raises(Exception):
            vector_db.compute_embeddings(documents)

def test_compute_deeplake_vs():
    collection_name = "collection"
    documents = ["doc1", "doc2", "doc3"]
    ids = ["id1", "id2", "id3"]
    metadatas = [{"metadata1": "value1"}, {"metadata2": "value2"}, {"metadata3": "value3"}]
    sha = "sha"
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), np.array([7, 8, 9])]

    with patch("sweepai.core.vector_db.redis_client", new_callable=MagicMock) as mock_redis_client, \
         patch("sweepai.core.vector_db.embedding_function", new_callable=MagicMock) as mock_embedding_function, \
         patch("sweepai.core.vector_db.init_deeplake_vs", new_callable=MagicMock) as mock_init_deeplake_vs:

        mock_redis_client.mget.return_value = [json.dumps(embedding.tolist()) for embedding in embeddings]
        mock_embedding_function.return_value = embeddings
        mock_init_deeplake_vs.return_value = MagicMock()

        vector_db.compute_deeplake_vs(collection_name, documents, ids, metadatas, sha)

        mock_embedding_function.assert_called_once_with(documents)
        mock_init_deeplake_vs.assert_called_once_with(collection_name)
        mock_init_deeplake_vs.return_value.add.assert_called_once_with(text=ids, embedding=embeddings, metadata=metadatas)
