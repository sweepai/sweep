import unittest
from unittest.mock import patch, MagicMock
from sweepai.core import vector_db
from sweepai.utils.github_utils import ClonedRepo
from sweepai.config.client import SweepConfig

class TestVectorDB(unittest.TestCase):

    @patch('re.sub')
    def test_parse_collection_name(self, mock_sub):
        mock_sub.return_value = 'test-name'
        result = vector_db.parse_collection_name('test name')
        self.assertEqual(result, 'test-name')

    @patch('requests.post')
    def test_embed_huggingface(self, mock_post):
        mock_post.return_value.json.return_value = {'embeddings': 'test'}
        result = vector_db.embed_huggingface(['test text'])
        self.assertEqual(result, 'test')

    @patch('replicate.Client')
    def test_embed_replicate(self, mock_client):
        mock_client.return_value.deployments.get.return_value.predictions.create.return_value.output = [{'embedding': 'test'}]
        result = vector_db.embed_replicate(['test text'])
        self.assertEqual(result, ['test'])

    @patch('vector_db.SentenceTransformer')
    def test_embed_texts(self, mock_transformer):
        mock_transformer.return_value.encode.return_value = 'test'
        import numpy as np
        result = vector_db.embed_texts(('test text',))
        np.testing.assert_array_equal(result, 'test')

    @patch('vector_db.embed_texts')
    def test_embedding_function(self, mock_embed_texts):
        mock_embed_texts.return_value = 'test'
        import numpy as np
        result = vector_db.embedding_function(['test text'])
        np.testing.assert_array_equal(result, 'test')

    @patch('vector_db.prepare_lexical_search_index')
    @patch('vector_db.compute_vector_search_scores')
    @patch('vector_db.prepare_documents_metadata_ids')
    @patch('vector_db.compute_deeplake_vs')
    def test_get_deeplake_vs_from_repo(self, mock_compute_deeplake_vs, mock_prepare_documents_metadata_ids, mock_compute_vector_search_scores, mock_prepare_lexical_search_index):
        cloned_repo = MagicMock(spec=ClonedRepo)
        cloned_repo.repo = MagicMock()
        cloned_repo.repo_full_name = 'test/repo'
        cloned_repo.repo.get_commits.return_value = [{'sha': 'test'}]
        mock_prepare_lexical_search_index.return_value = ('file_list', 'snippets', 'index')
        mock_compute_vector_search_scores.return_value = 'scores'
        mock_prepare_documents_metadata_ids.return_value = ('collection_name', 'documents', 'ids', 'metadatas')
        mock_compute_deeplake_vs.return_value = 'deeplake_vs'
        result = vector_db.get_deeplake_vs_from_repo(cloned_repo)
        self.assertEqual(result, ('deeplake_vs', 'index', len('documents')))

    # Continue with the rest of the functions...

if __name__ == '__main__':
    unittest.main()
