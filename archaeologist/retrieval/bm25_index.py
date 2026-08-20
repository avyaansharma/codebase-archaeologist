import os
import re
import pickle
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

_BM25_CACHE = {}

def tokenize_text(text: str) -> List[str]:
    """Tokenizes text into alphanumeric and underscore words for robust BM25 matching."""
    return re.findall(r'[a-zA-Z0-9_]+', text.lower())

class BM25Index:
    def __init__(self):
        self.bm25: Optional[BM25Okapi] = None
        self.chunks: List[dict] = []

    def fit(self, chunks: List[dict]):
        """Fits the BM25 model on a list of chunk dictionaries."""
        self.chunks = chunks
        tokenized_corpus = [tokenize_text(chunk["text"]) for chunk in chunks]
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
        is_reverted: Optional[bool] = None,
        repo_id: Optional[str] = None
    ) -> List[dict]:
        """Performs a BM25 keyword search with flexible metadata filters and returns ranked chunks."""
        if not self.bm25 or not self.chunks:
            return []

        tokenized_query = tokenize_text(query)
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)
        
        results = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
                
            chunk = self.chunks[idx]

            # Structural repo_id filter
            if repo_id:
                c_repo = chunk.get("repo_id")
                if c_repo and c_repo.lower() != repo_id.lower() and repo_id.lower() not in c_repo.lower():
                    continue
            
            # Structural file_path filter matching against chunk.file_paths
            if file_path:
                fp_lower = file_path.lower()
                c_paths = [p.lower() for p in chunk.get("file_paths", [])]
                if not any(fp_lower in p or p.endswith(fp_lower) or fp_lower.endswith(p) for p in c_paths):
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
        """Saves the fitted BM25 model and chunks to disk."""
        data = {
            "bm25": self.bm25,
            "chunks": self.chunks
        }
        with open(file_path, "wb") as f:
            pickle.dump(data, f)
        _BM25_CACHE[file_path] = data

    def load(self, file_path: str):
        """Loads a fitted BM25 model and chunks from disk with in-memory caching."""
        if file_path in _BM25_CACHE:
            data = _BM25_CACHE[file_path]
            self.bm25 = data["bm25"]
            self.chunks = data["chunks"]
            return

        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                data = pickle.load(f)
                self.bm25 = data["bm25"]
                self.chunks = data["chunks"]
                _BM25_CACHE[file_path] = data
