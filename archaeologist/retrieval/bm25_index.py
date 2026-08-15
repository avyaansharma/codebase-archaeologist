import os
import pickle
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

_BM25_CACHE = {}

class BM25Index:
    def __init__(self):
        self.bm25: Optional[BM25Okapi] = None
        self.chunks: List[dict] = []

    def fit(self, chunks: List[dict]):
        """Fits the BM25 model on a list of chunk dictionaries."""
        self.chunks = chunks
        tokenized_corpus = [chunk["text"].lower().split() for chunk in chunks]
        if tokenized_corpus:
            self.bm25 = BM25Okapi(tokenized_corpus)
        else:
            self.bm25 = None

    def search(
        self,
        query: str,
        limit: int = 10,
        file_path: Optional[str] = None,
        source_types: Optional[List[str]] = None,
        is_reverted: Optional[bool] = None
    ) -> List[dict]:
        """Performs a BM25 keyword search with metadata filters and returns ranked chunks."""
        if not self.bm25 or not self.chunks:
            return []

        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)
        
        results = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
                
            chunk = self.chunks[idx]
            
            # Apply metadata filters (§2.2 Fix)
            if file_path and file_path not in chunk.get("file_paths", []):
                continue
            if is_reverted is not None and chunk.get("is_reverted") != is_reverted:
                continue
            if source_types and chunk.get("source_type") not in source_types:
                continue

            results.append({
                "score": float(score),
                "chunk": chunk
            })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def save(self, file_path: str):
        """Pickles the index to disk and updates the in-memory cache."""
        with open(file_path, "wb") as f:
            pickle.dump((self.chunks, self.bm25), f)
        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
        _BM25_CACHE[file_path] = (mtime, self.chunks, self.bm25)

    def load(self, file_path: str):
        """Loads a pickled index from memory cache or disk (§2.3 Fix)."""
        if not os.path.exists(file_path):
            self.bm25 = None
            self.chunks = []
            return

        mtime = os.path.getmtime(file_path)
        if file_path in _BM25_CACHE and _BM25_CACHE[file_path][0] == mtime:
            _, self.chunks, self.bm25 = _BM25_CACHE[file_path]
            return

        try:
            with open(file_path, "rb") as f:
                self.chunks, self.bm25 = pickle.load(f)
            _BM25_CACHE[file_path] = (mtime, self.chunks, self.bm25)
        except Exception as e:
            print(f"Error loading BM25 index: {e}")
            self.bm25 = None
            self.chunks = []
