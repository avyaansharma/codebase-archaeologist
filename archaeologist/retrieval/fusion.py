from typing import List, Dict, Any

def reciprocal_rank_fusion(
    dense_hits: List[Dict[str, Any]], 
    sparse_hits: List[Dict[str, Any]], 
    k: int = 60,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Applies Reciprocal Rank Fusion (RRF) to merge vector and keyword search results.
    
    dense_hits: List of hits from Qdrant search. Format:
      {"id": "...", "score": 0.85, "payload": {...}}
    sparse_hits: List of hits from BM25. Format:
      {"score": 12.5, "chunk": {"id": "...", "text": "...", ...}}
      
    Returns a list of chunks ranked by RRF score.
    """
    rrf_scores: Dict[str, float] = {}
    chunk_payloads: Dict[str, Dict[str, Any]] = {}

    # Helper to clean/standardize payload representation
    def add_hit(chunk_id: str, rank: int, payload: Dict[str, Any]):
        if chunk_id not in rrf_scores:
            rrf_scores[chunk_id] = 0.0
            chunk_payloads[chunk_id] = payload
        rrf_scores[chunk_id] += 1.0 / (k + rank)

    # Process dense (vector) hits
    for rank, hit in enumerate(dense_hits, start=1):
        chunk_id = hit["id"]
        # payload directly maps to the chunk schema
        payload = hit["payload"]
        # Make sure 'id' is in payload
        if "id" not in payload:
            payload["id"] = chunk_id
        add_hit(chunk_id, rank, payload)

    # Process sparse (BM25) hits
    for rank, hit in enumerate(sparse_hits, start=1):
        chunk_data = hit["chunk"]
        chunk_id = chunk_data["id"]
        
        # Format matching the vector store payload format
        ts = chunk_data.get("timestamp")
        ts_iso = ts.isoformat() if (ts and hasattr(ts, "isoformat")) else ts
        
        payload = {
            "id": chunk_id,
            "source_type": chunk_data["source_type"],
            "source_id": chunk_data["source_id"],
            "text": chunk_data["text"],
            "timestamp": ts_iso,
            "file_paths": chunk_data["file_paths"],
            "related_ids": chunk_data["related_ids"],
            "is_reverted": chunk_data["is_reverted"]
        }
        add_hit(chunk_id, rank, payload)

    # Sort candidates desc by RRF score
    sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

    fused_results = []
    for cid in sorted_ids[:limit]:
        fused_results.append({
            "id": cid,
            "rrf_score": rrf_scores[cid],
            "payload": chunk_payloads[cid]
        })

    return fused_results
