import pickle
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

class BM25Index:
    def __init__(self):
        self.bm25: Optional[BM25Okapi] = None
        self.chunks: List[dict] = []

    def fit(self, chunks: List[dict]):
        """Fits the BM25 model on a list of chunk dictionaries.
        Each chunk dict should contain 'id' and 'text'.
        """
        self.chunks = chunks
        tokenized_corpus = [chunk["text"].lower().split() for chunk in chunks]
        if tokenized_corpus:
            self.bm25 = BM25Okapi(tokenized_corpus)
        else:
            self.bm25 = None

    def search(self, query: str, limit: int = 10) -> List[dict]:
        """Performs a BM25 keyword search and returns ranked chunks with scores."""
        if not self.bm25 or not self.chunks:
            return []

        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)
        
        results = []
        for idx, score in enumerate(scores):
            # Exclude zero or negative relevance hits to keep it clean
            if score > 0:
                results.append({
                    "score": float(score),
                    "chunk": self.chunks[idx]
                })
        
        # Sort desc by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def save(self, file_path: str):
        """Pickles the index to disk."""
        with open(file_path, "wb") as f:
            pickle.dump((self.chunks, self.bm25), f)

    def load(self, file_path: str):
        """Loads a pickled index from disk."""
        try:
            with open(file_path, "rb") as f:
                self.chunks, self.bm25 = pickle.load(f)
        except Exception as e:
            print(f"Error loading BM25 index: {e}")
            self.bm25 = None
            self.chunks = []
