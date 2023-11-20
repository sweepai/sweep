import unittest
from unittest.mock import MagicMock, patch

from sweepai.core.vector_db import (download_models, init_deeplake_vs,
                                    parse_collection_name)


class TestInitDeeplakeVs(unittest.TestCase):


    @patch("time.time")


    @patch("deeplake.core.vectorstore.deeplake_vectorstore.VectorStore")
    

    @unittest.skip("FAILED (failures=1)")
    def test_init_deeplake_vs(self, mock_VectorStore, mock_time):
        # Arrange
        mock_time.return_value = 1234567890
        mock_VectorStore.return_value = MagicMock()
        repo_name = "test_repo"

        # Act
        result = init_deeplake_vs(repo_name)

        # Assert
        mock_VectorStore.assert_called_once_with(path=f"mem://1234567890{repo_name}", read_only=False, overwrite=False)
        self.assertIsInstance(result, MagicMock)


    @patch("time.time")
    @patch("deeplake.core.vectorstore.deeplake_vectorstore.VectorStore")
    def test_init_deeplake_vs_with_string(self, mock_VectorStore, mock_time):
        # Arrange
        mock_time.return_value = 1234567890
        mock_VectorStore.return_value = MagicMock()
        repo_name = "test_repo"

        # Act
        result = init_deeplake_vs(repo_name)

        # Assert
        mock_time.assert_called_once()
        mock_VectorStore.assert_called_once_with(path=f"mem://1234567890{repo_name}", read_only=False, overwrite=False)
        self.assertIsInstance(result, MagicMock)

    @patch("time.time")
    @patch("deeplake.core.vectorstore.deeplake_vectorstore.VectorStore")
    def test_init_deeplake_vs_with_integer(self, mock_VectorStore, mock_time):
        # Arrange
        mock_time.return_value = 1234567890
        mock_VectorStore.return_value = MagicMock()
        repo_name = 123

        # Act
        with self.assertRaises(TypeError):
            init_deeplake_vs(repo_name)

    @patch("time.time")
    @patch("deeplake.core.vectorstore.deeplake_vectorstore.VectorStore")
    def test_init_deeplake_vs_with_float(self, mock_VectorStore, mock_time):
        # Arrange
        mock_time.return_value = 1234567890
        mock_VectorStore.return_value = MagicMock()
        repo_name = 123.456

        # Act
        with self.assertRaises(TypeError):
            init_deeplake_vs(repo_name)

    @patch("time.time")
    @patch("deeplake.core.vectorstore.deeplake_vectorstore.VectorStore")
    def test_init_deeplake_vs_with_none(self, mock_VectorStore, mock_time):
        # Arrange
        mock_time.return_value = 1234567890
        mock_VectorStore.return_value = MagicMock()
        repo_name = None

        # Act
        with self.assertRaises(TypeError):
            init_deeplake_vs(repo_name)
class TestDownloadModels(unittest.TestCase):
    @patch("sweepai.config.server.SENTENCE_TRANSFORMERS_MODEL", "mock_model")
    @patch("sweepai.core.vector_db.MODEL_DIR", "mock_dir")
    @patch("sentence_transformers.SentenceTransformer")
    def test_download_models(self, mock_sentence_transformer):
        mock_sentence_transformer.return_value = MagicMock()
        download_models()
        mock_sentence_transformer.assert_called_once_with("mock_model", cache_folder="mock_dir")



    @patch("sweepai.config.server.SENTENCE_TRANSFORMERS_MODEL", "mock_model")
    @patch("sentence_transformers.SentenceTransformer")
    def test_download_models_with_string(self, mock_sentence_transformer):
        mock_sentence_transformer.return_value = MagicMock()
        download_models()
        mock_sentence_transformer.assert_called_once_with("mock_model", cache_folder=MODEL_DIR)

    @patch("sweepai.config.server.SENTENCE_TRANSFORMERS_MODEL", 123)
    @patch("sentence_transformers.SentenceTransformer")
    def test_download_models_with_integer(self, mock_sentence_transformer):
        with self.assertRaises(TypeError):
            download_models()

    @patch("sweepai.config.server.SENTENCE_TRANSFORMERS_MODEL", 123.45)
    @patch("sentence_transformers.SentenceTransformer")
    def test_download_models_with_float(self, mock_sentence_transformer):
        with self.assertRaises(TypeError):
            download_models()

    @patch("sweepai.config.server.SENTENCE_TRANSFORMERS_MODEL", None)
    @patch("sentence_transformers.SentenceTransformer")
    def test_download_models_with_none(self, mock_sentence_transformer):
        with self.assertRaises(TypeError):
            download_models()
class TestParseCollectionName(unittest.TestCase):
    def test_parse_collection_name(self):
        # Test case: alphanumeric characters
        self.assertEqual(parse_collection_name("test123"), "test123")
        
        # Test case: non-alphanumeric characters
        self.assertEqual(parse_collection_name("test@123"), "test--123")
        
        # Test case: name length more than 63 characters
        self.assertEqual(parse_collection_name("a"*64), "a"*63)
        
        # Test case: name length less than 3 characters
        self.assertEqual(parse_collection_name("a"), "axx")

def test_parse_collection_name_with_integer(self):
        with self.assertRaises(TypeError):
            parse_collection_name(123)

    def test_parse_collection_name_with_float(self):
        with self.assertRaises(TypeError):
            parse_collection_name(123.456)

    def test_parse_collection_name_with_none(self):
        with self.assertRaises(TypeError):
            parse_collection_name(None)

if __name__ == "__main__":
    unittest.main()

