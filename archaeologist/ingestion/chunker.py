import tiktoken
import uuid
from datetime import datetime
from typing import List, Dict, Any

enc = tiktoken.get_encoding("cl100k_base")

def token_count(text: str) -> int:
    if not text:
        return 0
    return len(enc.encode(text))

def make_deterministic_chunk_id(source_type: str, source_id: str, index: int = 0, text_snippet: str = "") -> str:
    """Generates a deterministic UUID5 chunk ID based on source metadata and content snippet."""
    key = f"{source_type}:{source_id}:{index}:{text_snippet[:60]}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))

def chunk_commit(commit: dict, diff_summary: str | None) -> dict:
    body = diff_summary or ""
    symbols_str = ", ".join(commit.get("symbols_modified", []))
    sym_header = f"\nSymbols Modified: {symbols_str}" if symbols_str else ""
    
    text = f"Commit {commit['sha']} by {commit['author_name']}\nMessage: {commit['message']}{sym_header}\n\nDiff Summary:\n{body}".strip()
    if token_count(text) > 500:
        msg_text = f"Commit {commit['sha']} by {commit['author_name']}\nMessage: {commit['message']}{sym_header}\n\nDiff Summary:\n"
        msg_tokens = token_count(msg_text)
        budget = max(500 - msg_tokens, 50)
        body_tokens = enc.encode(body)[:budget]
        body = enc.decode(body_tokens)
        text = f"{msg_text}{body}".strip()
        
    chunk_id = make_deterministic_chunk_id("commit", commit["sha"], 0, text)

    return {
        "id": chunk_id,
        "source_type": "commit",
        "source_id": commit["sha"],
        "text": text,
        "timestamp": commit["authored_date"],
        "file_paths": commit.get("files_changed", []),
        "symbols_modified": commit.get("symbols_modified", []),
        "is_reverted": commit.get("is_revert", False),
        "token_count": token_count(text),
        "related_ids": commit.get("related_ids", [])
    }

def chunk_issue(issue: dict) -> List[dict]:
    chunks = []
    source_id = f"issue#{issue['number']}"
    author_name = issue.get("author") or "unknown"
    
    body_text = issue.get("body") or ""
    issue_start = f"[Issue #{issue['number']} - '{issue['title']}' created by {author_name}]\n{body_text}"
    if token_count(issue_start) > 400:
        truncated_body = enc.decode(enc.encode(body_text)[:300])
        issue_start = f"[Issue #{issue['number']} - '{issue['title']}' created by {author_name}]\n{truncated_body}..."

    created_at = issue.get("created_at") or datetime.utcnow()
    
    chunk_id_head = make_deterministic_chunk_id("issue", source_id, 0, issue_start)
    chunks.append({
        "id": chunk_id_head,
        "source_type": "issue",
        "source_id": source_id,
        "text": issue_start,
        "timestamp": created_at,
        "file_paths": [],
        "symbols_modified": [],
        "is_reverted": False,
        "token_count": token_count(issue_start),
        "related_ids": [f"pr#{num}" for num in issue.get("linked_pr_numbers", [])]
    })

    for idx, c in enumerate(issue.get("comments", []), start=1):
        c_author = c.get("author") or "unknown"
        c_body = c.get("body") or ""
        comment_text = f"[Issue #{issue['number']} comment by {c_author}]: {c_body}"
        if token_count(comment_text) > 400:
            truncated = enc.decode(enc.encode(c_body)[:350])
            comment_text = f"[Issue #{issue['number']} comment by {c_author}]: {truncated}..."
        
        c_time = c.get("created_at")
        if isinstance(c_time, str):
            try:
                c_time = datetime.fromisoformat(c_time)
            except Exception:
                c_time = created_at
        else:
            c_time = c_time or created_at
            
        chunk_id_comm = make_deterministic_chunk_id("issue", source_id, idx, comment_text)
        chunks.append({
            "id": chunk_id_comm,
            "source_type": "issue",
            "source_id": source_id,
            "text": comment_text,
            "timestamp": c_time,
            "file_paths": [],
            "symbols_modified": [],
            "is_reverted": False,
            "token_count": token_count(comment_text),
            "related_ids": [f"pr#{num}" for num in issue.get("linked_pr_numbers", [])]
        })

    return chunks

def chunk_pr(pr: dict) -> List[dict]:
    chunks = []
    source_id = f"pr#{pr['number']}"
    author_name = pr.get("author") or "unknown"
    
    body_text = pr.get("body") or ""
    pr_start = f"[PR #{pr['number']} - '{pr['title']}' created by {author_name}]\n{body_text}"
    if token_count(pr_start) > 400:
        truncated_body = enc.decode(enc.encode(body_text)[:300])
        pr_start = f"[PR #{pr['number']} - '{pr['title']}' created by {author_name}]\n{truncated_body}..."

    created_at = pr.get("created_at") or datetime.utcnow()
    
    chunk_id_head = make_deterministic_chunk_id("pr", source_id, 0, pr_start)
    chunks.append({
        "id": chunk_id_head,
        "source_type": "pr",
        "source_id": source_id,
        "text": pr_start,
        "timestamp": created_at,
        "file_paths": [],
        "symbols_modified": [],
        "is_reverted": False,
        "token_count": token_count(pr_start),
        "related_ids": [f"issue#{num}" for num in pr.get("linked_issue_numbers", [])]
    })

    # Process genuine inline review comments on diff lines
    idx_count = 1
    for c in pr.get("review_comments", []):
        c_author = c.get("author") or "unknown"
        c_body = c.get("body") or ""
        f_path = c.get("path", "")
        line_num = c.get("line", "")
        path_info = f" on file '{f_path}' line {line_num}" if f_path else ""
        comment_text = f"[PR #{pr['number']} inline review comment by {c_author}{path_info}]: {c_body}"
        if token_count(comment_text) > 400:
            truncated = enc.decode(enc.encode(c_body)[:350])
            comment_text = f"[PR #{pr['number']} inline review comment by {c_author}{path_info}]: {truncated}..."
            
        c_time = c.get("created_at")
        if isinstance(c_time, str):
            try:
                c_time = datetime.fromisoformat(c_time)
            except Exception:
                c_time = created_at
        else:
            c_time = c_time or created_at

        chunk_id_comm = make_deterministic_chunk_id("pr", source_id, idx_count, comment_text)
        chunks.append({
            "id": chunk_id_comm,
            "source_type": "pr",
            "source_id": source_id,
            "text": comment_text,
            "timestamp": c_time,
            "file_paths": [f_path] if f_path else [],
            "symbols_modified": [],
            "is_reverted": False,
            "token_count": token_count(comment_text),
            "related_ids": [f"issue#{num}" for num in pr.get("linked_issue_numbers", [])]
        })
        idx_count += 1

    # Process general PR discussion comments
    for c in pr.get("comments", []):
        c_author = c.get("author") or "unknown"
        c_body = c.get("body") or ""
        comment_text = f"[PR #{pr['number']} comment by {c_author}]: {c_body}"
        if token_count(comment_text) > 400:
            truncated = enc.decode(enc.encode(c_body)[:350])
            comment_text = f"[PR #{pr['number']} comment by {c_author}]: {truncated}..."
            
        c_time = c.get("created_at")
        if isinstance(c_time, str):
            try:
                c_time = datetime.fromisoformat(c_time)
            except Exception:
                c_time = created_at
        else:
            c_time = c_time or created_at

        chunk_id_comm = make_deterministic_chunk_id("pr", source_id, idx_count, comment_text)
        chunks.append({
            "id": chunk_id_comm,
            "source_type": "pr",
            "source_id": source_id,
            "text": comment_text,
            "timestamp": c_time,
            "file_paths": [],
            "symbols_modified": [],
            "is_reverted": False,
            "token_count": token_count(comment_text),
            "related_ids": [f"issue#{num}" for num in pr.get("linked_issue_numbers", [])]
        })
        idx_count += 1

    return chunks
