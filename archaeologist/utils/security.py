import os
import re
from typing import Optional

def validate_repo_path(repo_path: str) -> str:
    """Validates that a repo path exists and is a valid directory."""
    abs_path = os.path.abspath(repo_path)
    if not os.path.exists(abs_path):
        raise ValueError(f"Repository path '{repo_path}' does not exist.")
    if not os.path.isdir(abs_path):
        raise ValueError(f"Repository path '{repo_path}' is not a directory.")
    return abs_path

def sanitize_file_path(base_repo_path: str, target_file_path: str) -> str:
    """Sanitizes and prevents path traversal outside base repository path."""
    abs_base = os.path.abspath(base_repo_path)
    # Resolve relative target file path against abs_base
    joined = os.path.abspath(os.path.join(abs_base, target_file_path))
    
    # Check that joined path stays within abs_base directory
    if not joined.startswith(abs_base):
        raise ValueError(f"Path traversal detected: '{target_file_path}' is outside repository root.")
        
    # Return path relative to base_repo_path for git commands
    rel_path = os.path.relpath(joined, abs_base)
    return rel_path

def sanitize_sha(sha: str) -> str:
    """Sanitizes git commit SHA to contain only alphanumeric characters."""
    cleaned = sha.strip()
    if not re.match(r'^[a-fA-F0-9]{4,40}$', cleaned):
        raise ValueError(f"Invalid Git commit SHA format: '{sha}'")
    return cleaned
