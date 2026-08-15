import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, MatchAny, Range
from dotenv import load_dotenv

load_dotenv()

class VectorStore:
    def __init__(self, collection_name: str = "repo_history", vector_size: int = 1024):
        self.collection_name = collection_name
        self.vector_size = vector_size
        
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
        
        self.client = self._init_client(qdrant_url, qdrant_api_key)

    def _init_client(self, qdrant_url: str, qdrant_api_key: str) -> QdrantClient:
        """Connects to server Qdrant if available, otherwise uses pure in-memory Qdrant (zero-ops, lock-free)."""
        try:
            if qdrant_api_key:
                client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=1.0)
            else:
                client = QdrantClient(url=qdrant_url, timeout=1.0)
            client.get_collections()
            print(f"Connected to Qdrant server at {qdrant_url}")
            return client
        except Exception:
            print(f"Qdrant server at {qdrant_url} unavailable. Initializing lock-free in-memory Qdrant instance.")

        return QdrantClient(":memory:")

    def init_collection(self):
        """Creates the collection and payload indexes if they do not exist."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
        except Exception:
            exists = False
        
        if not exists:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    def upsert_chunks(self, chunks: List[dict], embeddings: List[List[float]], batch_size: int = 100):
        """Upserts chunks and their embeddings to Qdrant in batches of batch_size."""
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            points.append(PointStruct(
                id=chunk["id"],
                vector=embedding,
                payload={
                    "source_type": chunk["source_type"],
                    "source_id": chunk["source_id"],
                    "text": chunk["text"],
                    "timestamp": chunk["timestamp"].isoformat() if hasattr(chunk["timestamp"], "isoformat") else chunk["timestamp"],
                    "timestamp_unix": int(chunk["timestamp"].timestamp()) if hasattr(chunk["timestamp"], "timestamp") else 0,
                    "file_paths": chunk.get("file_paths", []),
                    "symbols_modified": chunk.get("symbols_modified", []),
                    "related_ids": chunk.get("related_ids", []),
                    "is_reverted": chunk.get("is_reverted", False),
                }
            ))
        
        if points:
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )

    def search_chunks(
        self, 
        query_vector: List[float], 
        limit: int = 10,
        file_path: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        source_types: Optional[List[str]] = None,
        is_reverted: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Searches collection with vector similarity and payload metadata filters."""
        must_filters = []
        
        if file_path:
            must_filters.append(FieldCondition(key="file_paths", match=MatchValue(value=file_path)))
            
        if is_reverted is not None:
            must_filters.append(FieldCondition(key="is_reverted", match=MatchValue(value=is_reverted)))
            
        if source_types:
            must_filters.append(FieldCondition(key="source_type", match=MatchAny(any=source_types)))
            
        if date_from or date_to:
            range_filter = {}
            if date_from:
                dt_from = datetime.fromisoformat(date_from) if isinstance(date_from, str) else date_from
                range_filter["gte"] = int(dt_from.timestamp())
            if date_to:
                dt_to = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                range_filter["lte"] = int(dt_to.timestamp())
            must_filters.append(FieldCondition(key="timestamp_unix", range=Range(**range_filter)))
            
        query_filter = Filter(must=must_filters) if must_filters else None
        
        try:
            if hasattr(self.client, "query_points"):
                res = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit
                )
                results = res.points
            elif hasattr(self.client, "search"):
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit
                )
            else:
                results = []
        except Exception as e:
            print(f"Error executing Qdrant search: {e}")
            results = []
        
        hits = []
        for hit in results:
            hits.append({
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload
            })
        return hits

    def close(self):
        """Closes the underlying client connection."""
        try:
            if hasattr(self.client, "close"):
                self.client.close()
        except Exception:
            pass
