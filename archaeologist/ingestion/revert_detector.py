import re
from typing import Optional
from sqlmodel import Session, select
from archaeologist.storage.models import Commit

REVERT_MSG_PATTERN = re.compile(r'^Revert\s+"(.+)"', re.IGNORECASE)

def _escape_like(s: str) -> str:
    """Escapes SQL LIKE wildcard characters (%, _, \\)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def detect_revert_from_message(message: str) -> Optional[str]:
    """Returns the subject line of the reverted commit if this looks like a git-generated revert."""
    m = REVERT_MSG_PATTERN.match(message)
    return m.group(1) if m else None

def find_reverted_commit(db_session: Session, reverted_subject: str, before_date) -> Optional[Commit]:
    """git revert messages embed the ORIGINAL subject line, not its sha. Look it up by matching
    subject text among commits before this one. If multiple matches, take the most recent."""
    escaped_subject = _escape_like(reverted_subject)
    stmt = (select(Commit)
            .where(Commit.message.like(f"{escaped_subject}%", escape="\\"))
            .where(Commit.authored_date < before_date)
            .order_by(Commit.authored_date.desc()))
    return db_session.exec(stmt).first()
