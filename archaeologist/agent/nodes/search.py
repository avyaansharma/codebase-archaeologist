import os
import sys
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
    """Strips GitHub search qualifiers and git CLI flags to prevent BM25 string matching pollution."""
    cleaned = re.sub(r'(?:repo|is|owner|org|site|author|label):\S+', '', query, flags=re.IGNORECASE)
    cleaned = re.sub(r'git\s+log|--(?:grep|oneline|author|since|until|path|name-only|stat)\S*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'["\'\-\-]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else query

def search_node(state: AgentState) -> dict:
    raw_queries = state.get("search_queries", [])
    queries_to_run = raw_queries if raw_queries else [state["question"]]

    plan = state.get("_current_plan", {})
    file_path = plan.get("file_path")
    source_types = plan.get("source_types")
    date_from = plan.get("date_from")
    date_to = plan.get("date_to")

    bm25 = BM25Index()
    has_bm25 = os.path.exists("bm25_index.bin")
    if has_bm25:
        bm25.load("bm25_index.bin")

    embedder = Embedder()
    vector_store = VectorStore(vector_size=embedder.dimension)
    vector_store.init_collection()

    all_sparse_hits = []
    all_dense_hits = []
    seen_sparse_ids = set()
    seen_dense_ids = set()

    for raw_q in queries_to_run:
        query = sanitize_search_query(raw_q)
        print(f"Agent: Executing search for query: '{query}'...", file=sys.stderr)

        # 1. Sparse BM25 Search
        if has_bm25:
            s_hits = bm25.search(
                query=query,
                limit=30,
                file_path=file_path,
                source_types=source_types
            )
            for hit in s_hits:
                cid = hit["chunk"]["id"]
                if cid not in seen_sparse_ids:
                    seen_sparse_ids.add(cid)
                    all_sparse_hits.append(hit)

        # 2. Dense Vector Search
        try:
            query_vectors = embedder.embed_texts([query])
            if query_vectors:
                d_hits = vector_store.search_chunks(
                    query_vector=query_vectors[0],
                    limit=30,
                    file_path=file_path,
                    date_from=date_from,
                    date_to=date_to,
                    source_types=source_types
                )
                for hit in d_hits:
                    cid = hit["id"]
                    if cid not in seen_dense_ids:
                        seen_dense_ids.add(cid)
                        all_dense_hits.append(hit)
        except Exception as e:
            print(f"Error in dense search: {e}", file=sys.stderr)

        # 3. AST Symbol Graph Direct Retrieval
        symbol_matches = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]{3,})\b', query)
        if symbol_matches:
            from archaeologist.utils.security import escape_like
            with get_session_context() as session:
                for sym in symbol_matches:
                    if sym.lower() in ("http", "httpx", "python", "code", "file", "path", "test", "class", "func", "defs", "does", "how", "what", "where", "when", "why"):
                        continue
                    stmt = select(Chunk).where(Chunk.symbols_modified.like(f"%{escaped_sym}%", escape="\\"))

                    raw_chunks = session.exec(stmt).all()
                    sym_chunks = [
                        c for c in raw_chunks 
                        if any(sym.lower() in str(s).lower() for s in (c.symbols_modified or []))
                    ]
                    for c in sym_chunks:
                        if c.id not in seen_dense_ids:
                            seen_dense_ids.add(c.id)
                            all_dense_hits.append({
                                "id": c.id,
                                "score": 1.5,
                                "payload": {
                                    "id": c.id,
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


    vector_store.close()

    # SQLite direct text fallback if dense vector hits are empty
    if not all_dense_hits:
        with get_session_context() as session:
            stmt = select(Chunk)
            all_chunks = session.exec(stmt).all()
            for raw_q in queries_to_run:
                query_words = [w.lower() for w in sanitize_search_query(raw_q).split() if len(w) > 2]
                for c in all_chunks:
                    text_lower = c.text.lower()
                    if c.id not in seen_dense_ids and any(w in text_lower for w in query_words):
                        seen_dense_ids.add(c.id)
                        all_dense_hits.append({
                            "id": c.id,
                            "score": 1.0,
                            "payload": {
                                "id": c.id,
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

    # 3. Hybrid Fusion across all accumulated query hits
    fused_results = reciprocal_rank_fusion(all_dense_hits, all_sparse_hits, limit=10)
    print(f"Found {len(fused_results)} relevant history chunks across {len(queries_to_run)} search queries.", file=sys.stderr)

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

