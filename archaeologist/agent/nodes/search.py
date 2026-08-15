import os
import re
from sqlmodel import select
from archaeologist.agent.state import AgentState
from archaeologist.retrieval.embedder import Embedder
from archaeologist.retrieval.vector_store import VectorStore
from archaeologist.retrieval.bm25_index import BM25Index
from archaeologist.retrieval.fusion import reciprocal_rank_fusion
from archaeologist.storage.db import get_session_context
from archaeologist.storage.models import Chunk

def sanitize_search_query(query: str) -> str:
    """Strips GitHub search qualifiers (repo:..., is:pr, is:issue, site:...) to prevent BM25 string matching pollution."""
    cleaned = re.sub(r'(?:repo|is|owner|org|site|author|label):\S+', '', query, flags=re.IGNORECASE)
    cleaned = re.sub(r'["\']', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else query

def search_node(state: AgentState) -> dict:
    raw_queries = state.get("search_queries", [])
    if not raw_queries:
        raw_query = state["question"]
    else:
        raw_query = raw_queries[0]

    query = sanitize_search_query(raw_query)

    plan = state.get("_current_plan", {})
    file_path = plan.get("file_path")
    source_types = plan.get("source_types")
    date_from = plan.get("date_from")
    date_to = plan.get("date_to")

    print(f"Agent: Executing search for query: '{query}'...")

    # 1. Sparse BM25 Search
    bm25 = BM25Index()
    sparse_hits = []
    if os.path.exists("bm25_index.bin"):
        bm25.load("bm25_index.bin")
        sparse_hits = bm25.search(query, limit=30)

    # 2. Dense Vector Search
    embedder = Embedder()
    vector_store = VectorStore(vector_size=embedder.dimension)
    vector_store.init_collection()
    
    dense_hits = []
    try:
        query_vectors = embedder.embed_texts([query])
        if query_vectors:
            dense_hits = vector_store.search_chunks(
                query_vector=query_vectors[0],
                limit=30,
                file_path=file_path,
                date_from=date_from,
                date_to=date_to,
                source_types=source_types
            )
    except Exception as e:
        print(f"Error in dense search: {e}")
    finally:
        vector_store.close()

    # SQLite direct text fallback if vector hits are empty (e.g. in-memory or mock mode)
    if not dense_hits:
        with get_session_context() as session:
            stmt = select(Chunk)
            all_chunks = session.exec(stmt).all()
            query_words = [w.lower() for w in query.split() if len(w) > 2]
            for c in all_chunks:
                text_lower = c.text.lower()
                if any(w in text_lower for w in query_words):
                    dense_hits.append({
                        "id": c.id,
                        "score": 1.0,
                        "payload": {
                            "source_type": c.source_type,
                            "source_id": c.source_id,
                            "text": c.text,
                            "timestamp": c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else c.timestamp,
                            "file_paths": c.file_paths,
                            "symbols_modified": c.symbols_modified,
                            "related_ids": c.related_ids,
                            "is_reverted": c.is_reverted
                        }
                    })

    # 3. Hybrid Fusion
    fused_results = reciprocal_rank_fusion(dense_hits, sparse_hits, limit=10)
    print(f"Found {len(fused_results)} relevant history chunks.")

    retrieved = state.get("retrieved_chunks", [])
    evidence_map = state.get("evidence_by_chunk_id", {})

    new_chunks = []
    for hit in fused_results:
        cid = hit["id"]
        if cid not in evidence_map:
            chunk_data = hit["payload"]
            chunk_data["id"] = cid
            chunk_data["rrf_score"] = hit["rrf_score"]
            new_chunks.append(chunk_data)
            evidence_map[cid] = chunk_data

    return {
        "retrieved_chunks": retrieved + new_chunks,
        "evidence_by_chunk_id": evidence_map
    }
