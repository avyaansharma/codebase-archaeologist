import sys
from sqlmodel import select
from archaeologist.agent.state import AgentState
from archaeologist.storage.db import get_session
from archaeologist.storage.models import Chunk

def follow_links_node(state: AgentState) -> dict:
    print("Agent: Checking cross-linked references...", file=sys.stderr)
    current_chunks = state.get("retrieved_chunks", [])
    seen_ids = {c["id"] for c in current_chunks}
    seen_source_ids = {c["source_id"] for c in current_chunks}

    # Collect related IDs from retrieved chunks
    related_ids_to_fetch = set()
    for chunk in current_chunks:
        for ref in chunk.get("related_ids", []):
            if ref not in seen_source_ids:
                related_ids_to_fetch.add(ref)

    if not related_ids_to_fetch:
        print("No new cross-linked references to follow.", file=sys.stderr)
        return {}

    print(f"Fetching linked items: {related_ids_to_fetch}", file=sys.stderr)
    db_session = get_session()
    new_chunks = []
    try:
        for ref in related_ids_to_fetch:
            # Query local metadata DB for chunk by source_id
            stmt = select(Chunk).where(Chunk.source_id == ref)
            results = db_session.exec(stmt).all()
            for c in results:
                if c.id not in seen_ids:
                    # Format matching AgentState retrieved_chunks
                    new_chunks.append({
                        "id": c.id,
                        "source_type": c.source_type,
                        "source_id": c.source_id,
                        "text": c.text,
                        "timestamp": c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else c.timestamp,
                        "file_paths": c.file_paths,
                        "related_ids": c.related_ids,
                        "is_reverted": c.is_reverted,
                        "rrf_score": 0.0  # reference hit has no initial search score
                    })
                    seen_ids.add(c.id)
    finally:
        db_session.close()

    if new_chunks:
        print(f"Added {len(new_chunks)} linked chunks to retrieval pool.", file=sys.stderr)
        return {"retrieved_chunks": current_chunks + new_chunks}
    
    return {}

