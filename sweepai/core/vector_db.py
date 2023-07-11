import concurrent.futures

class Embedding:
    def __enter__(self):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    @method()
    @method()
    def compute(self, texts: list[str]):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            texts_chunks = [texts[i:i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
            results = list(executor.map(self.model.encode, texts_chunks))
        return [item for sublist in results for item in sublist]

    @method()
    def ping(self):
        return "pong"
