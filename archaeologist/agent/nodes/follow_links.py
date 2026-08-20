import sys
from sqlmodel import select
from archaeologist.agent.state import AgentState
from archaeologist.storage.db import get_session_context
from archaeologist.storage.models import Chunk
from archaeologist.utils.security import escape_like

def follow_links_node(state: AgentState) -> dict:
    print("Agent: Checking cross-linked references...", file=sys.stderr)
    current_chunks = state.get("retrieved_chunks", [])
    seen_ids = {c["id"] for c in current_chunks}
    seen_source_ids = {c["source_id"] for c in current_chunks}
    repo_id = state.get("repo_id")

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
    new_chunks = []
    with get_session_context() as session:
        for ref in related_ids_to_fetch:
            clean_ref = ref.split("#")[-1].split(":")[-1] if ("#" in ref or ":" in ref) else ref
            escaped = escape_like(clean_ref)
            is_sha = len(clean_ref) >= 7 and all(c in "0123456789abcdefABCDEF" for c in clean_ref)
            
            if is_sha:
                stmt = select(Chunk).where(
                    (Chunk.source_id == ref) |
                    (Chunk.source_id == clean_ref) |
                    (Chunk.source_id.like(f"{escaped}%", escape="\\"))
                )
            else:
                stmt = select(Chunk).where(
                    (Chunk.source_id == ref) |
                    (Chunk.source_id == clean_ref) |
                    (Chunk.source_id == f"pr#{clean_ref}") |
                    (Chunk.source_id == f"issue#{clean_ref}")
                )

            if repo_id:
                stmt = stmt.where(Chunk.repo_id == repo_id)
            stmt = stmt.limit(5)
            
            results = session.exec(stmt).all()
            for c in results:
                if c.id not in seen_ids:
                    new_chunks.append({
                        "id": c.id,
                        "source_type": c.source_type,
                        "source_id": c.source_id,
                        "text": c.text,
                        "timestamp": c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else c.timestamp,
                        "file_paths": c.file_paths,
                        "related_ids": c.related_ids,
                        "is_reverted": c.is_reverted,
                        "rrf_score": 0.0
                    })
                    seen_ids.add(c.id)

    if new_chunks:
        print(f"Added {len(new_chunks)} linked chunks to retrieval pool.", file=sys.stderr)
        return {"retrieved_chunks": current_chunks + new_chunks}
    
    return {}
