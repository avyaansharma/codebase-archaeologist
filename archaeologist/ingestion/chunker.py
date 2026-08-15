import tiktoken
from datetime import datetime
from typing import List, Dict, Any
import uuid

enc = tiktoken.get_encoding("cl100k_base")

def token_count(text: str) -> int:
    if not text:
        return 0
    return len(enc.encode(text))

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
        
    return {
        "id": str(uuid.uuid4()),
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
    
    body_text = issue.get("body") or ""
    issue_start = f"[Issue #{issue['number']} - '{issue['title']}' created by ghost]\n{body_text}"
    if token_count(issue_start) > 400:
        truncated_body = enc.decode(enc.encode(body_text)[:300])
        issue_start = f"[Issue #{issue['number']} - '{issue['title']}' created by ghost]\n{truncated_body}..."

    created_at = issue.get("created_at") or datetime.utcnow()
    
    chunks.append({
        "id": str(uuid.uuid4()),
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

    for idx, c in enumerate(issue.get("comments", [])):
        comment_text = f"[Issue #{issue['number']} comment by {c['author']}]: {c['body']}"
        if token_count(comment_text) > 400:
            truncated = enc.decode(enc.encode(c['body'])[:350])
            comment_text = f"[Issue #{issue['number']} comment by {c['author']}]: {truncated}..."
        
        c_time = c.get("created_at")
        if isinstance(c_time, str):
            try:
                c_time = datetime.fromisoformat(c_time)
            except Exception:
                c_time = created_at
        else:
            c_time = c_time or created_at
            
        chunks.append({
            "id": str(uuid.uuid4()),
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
    
    body_text = pr.get("body") or ""
    pr_start = f"[PR #{pr['number']} - '{pr['title']}' created by {pr['author']}]\n{body_text}"
    if token_count(pr_start) > 400:
        truncated_body = enc.decode(enc.encode(body_text)[:300])
        pr_start = f"[PR #{pr['number']} - '{pr['title']}' created by {pr['author']}]\n{truncated_body}..."

    created_at = pr.get("created_at") or datetime.utcnow()
    
    chunks.append({
        "id": str(uuid.uuid4()),
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

    comments_to_process = []
    for c in pr.get("review_comments", []):
        comments_to_process.append({
            "author": c.get("author", "unknown"),
            "body": f"Review comment on file '{c.get('path', '')}' line {c.get('line', '')}: {c.get('body', '')}",
            "created_at": c.get("created_at")
        })
    for c in pr.get("comments", []):
        comments_to_process.append(c)

    for c in comments_to_process:
        comment_text = f"[PR #{pr['number']} comment by {c.get('author', 'unknown')}]: {c.get('body', '')}"
        if token_count(comment_text) > 400:
            truncated = enc.decode(enc.encode(c.get('body', ''))[:350])
            comment_text = f"[PR #{pr['number']} comment by {c.get('author', 'unknown')}]: {truncated}..."
            
        c_time = c.get("created_at")
        if isinstance(c_time, str):
            try:
                c_time = datetime.fromisoformat(c_time)
            except Exception:
                c_time = created_at
        else:
            c_time = c_time or created_at

        chunks.append({
            "id": str(uuid.uuid4()),
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

    return chunks
