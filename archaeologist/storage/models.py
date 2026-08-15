from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, JSON, Column

class Commit(SQLModel, table=True):
    sha: str = Field(primary_key=True)
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
    title: str
    body: Optional[str] = None
    state: str                                  # open|closed|merged
    author: str
    created_at: datetime
    merged_at: Optional[datetime] = None
    merge_commit_sha: Optional[str] = None
    linked_issue_numbers: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    review_comments: List[dict] = Field(default_factory=list, sa_column=Column(JSON))

class Issue(SQLModel, table=True):
    number: int = Field(primary_key=True)
    title: str
    body: Optional[str] = None
    state: str
    labels: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = None          # "completed" | "not_planned" | None
    linked_pr_numbers: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    comments: List[dict] = Field(default_factory=list, sa_column=Column(JSON))

class Chunk(SQLModel, table=True):
    id: str = Field(primary_key=True)            # uuid4
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
    file_path: str
    symbol_name: str
    kind: str                                     # "class" | "function" | "method"
    commit_count: int = 0
