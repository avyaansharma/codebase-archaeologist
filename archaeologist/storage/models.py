from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, JSON, Column, select

class Commit(SQLModel, table=True):
    sha: str = Field(primary_key=True)
    repo_id: Optional[str] = Field(default=None, index=True)
    author_name: str
    author_email: str
    authored_date: datetime
    message: str
    files_changed: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    symbols_modified: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    insertions: int = 0
    deletions: int = 0
    is_revert: bool = False
    reverts_sha: Optional[str] = None          # points to the commit this one reverts
    superseded_by_sha: Optional[str] = None    # set later if this commit is itself reverted
    diff_summary: Optional[str] = None         # LLM-generated, cached
    raw_diff_truncated: Optional[str] = None   # first N chars of diff, for small diffs store full

class PullRequest(SQLModel, table=True):
    number: int = Field(primary_key=True)
    repo_id: Optional[str] = Field(default=None, index=True)
    title: str
    body: Optional[str] = None
    state: str                                  # open|closed|merged
    author: str = "unknown"
    created_at: datetime
    merged_at: Optional[datetime] = None
    merge_commit_sha: Optional[str] = None
    merged_commit_sha: Optional[str] = None
    linked_issue_numbers: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    linked_commit_shas: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    review_comments: List[dict] = Field(default_factory=list, sa_column=Column(JSON))
    comments: List[dict] = Field(default_factory=list, sa_column=Column(JSON))

class Issue(SQLModel, table=True):
    number: int = Field(primary_key=True)
    repo_id: Optional[str] = Field(default=None, index=True)
    title: str
    body: Optional[str] = None
    state: str
    author: Optional[str] = "unknown"
    labels: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = None          # "completed" | "not_planned" | None
    linked_pr_numbers: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    linked_commit_shas: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    comments: List[dict] = Field(default_factory=list, sa_column=Column(JSON))

class Chunk(SQLModel, table=True):
    id: str = Field(primary_key=True)            # deterministic uuid5
    repo_id: Optional[str] = Field(default=None, index=True)
    source_type: str                              # "commit"|"pr"|"issue"|"thread_summary"
    source_id: str                                 # sha, or "pr#123", "issue#45"
    text: str
    timestamp: datetime
    file_paths: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    symbols_modified: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    related_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    is_reverted: bool = False
    token_count: int = 0
    embedded: bool = False                         # ingestion progress flag, for resumability

class SymbolIndex(SQLModel, table=True):
    symbol_id: str = Field(primary_key=True)      # e.g. "src/auth.py::AuthService::login"
    repo_id: Optional[str] = Field(default=None, index=True)
    file_path: str
    symbol_name: str
    kind: str                                     # "class" | "function" | "method"
    commit_count: int = 0

def is_valid_commit_sha(session, sha_str: str) -> bool:
    if not sha_str or len(sha_str) < 7:
        return False
    from archaeologist.utils.security import escape_like
    escaped = escape_like(sha_str)
    stmt = select(Commit.sha).where(Commit.sha.like(f"{escaped}%", escape="\\"))
    result = session.exec(stmt).first()
    return result is not None

def is_valid_pr_or_issue(session, ref_num: int) -> bool:
    pr_stmt = select(PullRequest.number).where(PullRequest.number == ref_num)
    if session.exec(pr_stmt).first() is not None:
        return True
    issue_stmt = select(Issue.number).where(Issue.number == ref_num)
    return session.exec(issue_stmt).first() is not None

def find_candidate_symbols(session, text: str, repo_id: Optional[str] = None, limit: int = 8) -> List[dict]:
    """Finds candidate code symbols matching key tokens in the question text to ground planning."""
    if not text:
        return []
    import re
    from archaeologist.utils.security import escape_like
    
    words = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]{3,}', text))
    stopwords = {"what", "when", "where", "which", "does", "from", "with", "this", "that", "have", "been", "were", "commit", "commits", "pull", "request", "issue", "repository", "history", "code", "file", "method", "function", "class", "architecture", "handle", "using"}
    candidates = [w for w in words if w.lower() not in stopwords]
    
    if not candidates:
        return []
    
    matched = []
    seen = set()
    for word in candidates:
        escaped = escape_like(word)
        stmt = select(SymbolIndex).where(
            (SymbolIndex.symbol_name.like(f"%{escaped}%", escape="\\")) |
            (SymbolIndex.file_path.like(f"%{escaped}%", escape="\\"))
        )
        if repo_id:
            stmt = stmt.where(SymbolIndex.repo_id == repo_id)
        stmt = stmt.limit(limit)
        results = session.exec(stmt).all()
        for r in results:
            if r.symbol_id not in seen:
                matched.append({
                    "symbol_name": r.symbol_name,
                    "file_path": r.file_path,
                    "kind": r.kind
                })
                seen.add(r.symbol_id)
                if len(matched) >= limit:
                    return matched
    return matched

