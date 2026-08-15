import os
import ast
import re
import subprocess
from typing import List, Dict, Any, Optional
from archaeologist.utils.security import validate_repo_path, sanitize_sha, sanitize_file_path

FUNCTION_REGEX = re.compile(
    r'^\s*(?:async\s+)?(?:def|function|fn|func|public|private|protected|static|\s)*\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
    re.MULTILINE
)
CLASS_REGEX = re.compile(
    r'^\s*(?:class|struct|interface|trait|enum)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
    re.MULTILINE
)

def resolve_file_path(repo_path: str, fpath: str) -> Optional[str]:
    """Resolves relative git diff path against local repo root directory."""
    p1 = os.path.join(repo_path, fpath)
    if os.path.exists(p1) and os.path.isfile(p1):
        return p1
    parts = fpath.replace("\\", "/").split("/")
    for i in range(len(parts)):
        sub_path = os.path.join(repo_path, *parts[i:])
        if os.path.exists(sub_path) and os.path.isfile(sub_path):
            return sub_path
    return None

def get_git_file_content(repo_path: str, sha: str, file_path: str) -> Optional[str]:
    """Retrieves file content at a specific historical git commit SHA using `git show sha:file_path`."""
    try:
        validated_repo = validate_repo_path(repo_path)
        clean_sha = sanitize_sha(sha)
        clean_path = sanitize_file_path(validated_repo, file_path)
        cmd = ["git", "-C", validated_repo, "show", f"{clean_sha}:{clean_path}"]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return None

def extract_symbols_from_code(code_text: str, file_path: str) -> List[Dict[str, Any]]:
    """Parses source code into Abstract Syntax Trees (AST) or regex symbols with line boundaries."""
    symbols = []
    if not code_text or not code_text.strip():
        return symbols

    # Python AST parsing
    if file_path.endswith(".py"):
        try:
            tree = ast.parse(code_text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start_line = getattr(node, "lineno", 1)
                    end_line = getattr(node, "end_lineno", start_line + 10)
                    symbols.append({
                        "name": node.name,
                        "kind": "function",
                        "start_line": start_line,
                        "end_line": end_line,
                        "symbol_id": f"{file_path}::{node.name}"
                    })
                elif isinstance(node, ast.ClassDef):
                    start_line = getattr(node, "lineno", 1)
                    end_line = getattr(node, "end_lineno", start_line + 20)
                    symbols.append({
                        "name": node.name,
                        "kind": "class",
                        "start_line": start_line,
                        "end_line": end_line,
                        "symbol_id": f"{file_path}::{node.name}"
                    })
            return symbols
        except Exception:
            pass

    # Generic Multi-language Regex Fallback
    lines = code_text.splitlines()
    for idx, line in enumerate(lines, start=1):
        c_match = CLASS_REGEX.match(line)
        if c_match:
            symbols.append({
                "name": c_match.group(1),
                "kind": "class",
                "start_line": idx,
                "end_line": idx + 30,
                "symbol_id": f"{file_path}::{c_match.group(1)}"
            })
            continue

        f_match = FUNCTION_REGEX.match(line)
        if f_match:
            symbols.append({
                "name": f_match.group(1),
                "kind": "function",
                "start_line": idx,
                "end_line": idx + 15,
                "symbol_id": f"{file_path}::{f_match.group(1)}"
            })

    return symbols

def map_lines_to_symbols(symbols: List[Dict[str, Any]], modified_lines: List[int]) -> List[str]:
    """Finds which AST symbols intersect with modified line numbers from a git diff."""
    matched_symbol_ids = set()
    if not symbols or not modified_lines:
        return []

    for sym in symbols:
        s_start = sym["start_line"]
        s_end = sym["end_line"]
        for line in modified_lines:
            if s_start <= line <= s_end:
                matched_symbol_ids.add(sym["symbol_id"])
                break

    return sorted(list(matched_symbol_ids))

def extract_modified_line_numbers_from_diff(diff_text: str) -> Dict[str, List[int]]:
    """Parses a unified git diff and returns a dict mapping file paths to modified line numbers."""
    file_lines = {}
    current_file = None
    current_line = 0

    hunk_header = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')

    for line in diff_text.splitlines():
        if line.startswith('+++ b/'):
            current_file = line[6:].strip()
            if current_file not in file_lines:
                file_lines[current_file] = []
        elif line.startswith('@@'):
            m = hunk_header.match(line)
            if m:
                current_line = int(m.group(1))
        elif current_file and (line.startswith('+') and not line.startswith('+++')):
            file_lines[current_file].append(current_line)
            current_line += 1
        elif current_file and not line.startswith('-'):
            current_line += 1

    return file_lines
