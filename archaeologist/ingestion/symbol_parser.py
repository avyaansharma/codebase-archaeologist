import os
import ast
import re
import subprocess
from typing import List, Dict, Any, Optional
from archaeologist.utils.security import validate_repo_path, sanitize_sha, sanitize_file_path

# Require explicit function definition keywords (§4 Fix)
FUNCTION_REGEX = re.compile(
    r'^\s*(?:async\s+)?(?:def|function|fn|func|public|private|protected|static)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
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
    """Parses code text using Python AST if .py, or regex fallback for other languages."""
    symbols = []
    
    if file_path.endswith(".py"):
        try:
            tree = ast.parse(code_text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append({
                        "symbol_id": f"{file_path}:{node.name}",
                        "name": node.name,
                        "kind": "function",
                        "line_number": node.lineno
                    })
                elif isinstance(node, ast.ClassDef):
                    symbols.append({
                        "symbol_id": f"{file_path}:{node.name}",
                        "name": node.name,
                        "kind": "class",
                        "line_number": node.lineno
                    })
            return symbols
        except Exception:
            pass

    # Multi-language Regex Fallback
    for match in FUNCTION_REGEX.finditer(code_text):
        fn_name = match.group(1)
        line_no = code_text[:match.start()].count("\n") + 1
        symbols.append({
            "symbol_id": f"{file_path}:{fn_name}",
            "name": fn_name,
            "kind": "function",
            "line_number": line_no
        })

    for match in CLASS_REGEX.finditer(code_text):
        cls_name = match.group(1)
        line_no = code_text[:match.start()].count("\n") + 1
        symbols.append({
            "symbol_id": f"{file_path}:{cls_name}",
            "name": cls_name,
            "kind": "class",
            "line_number": line_no
        })

    return symbols

def map_lines_to_symbols(symbols: List[Dict[str, Any]], modified_lines: List[int]) -> List[str]:
    """Given a list of symbols and modified lines in a diff, returns symbol_ids that overlap."""
    if not symbols or not modified_lines:
        return []

    lines_set = set(modified_lines)
    touched_symbols = []

    sorted_syms = sorted(symbols, key=lambda s: s.get("line_number") or s.get("start_line", 0))
    for i, sym in enumerate(sorted_syms):
        start_line = sym.get("line_number") or sym.get("start_line", 0)
        end_line = sym.get("end_line") or (
            sorted_syms[i + 1].get("line_number") or sorted_syms[i + 1].get("start_line", start_line + 50) - 1 
            if i + 1 < len(sorted_syms) 
            else start_line + 50
        )
        
        sym_lines = set(range(start_line, end_line + 1))
        if sym_lines.intersection(lines_set):
            touched_symbols.append(sym["symbol_id"])

    return touched_symbols

def extract_modified_line_numbers_from_diff(diff_text: str) -> Dict[str, List[int]]:
    """Parses a unified git diff and returns a dict mapping file paths to modified line numbers."""
    file_lines = {}
    current_file = None
    current_line = 0

    hunk_header = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')

    for line in diff_text.splitlines():
        if line.startswith('+++ '):
            target = line[4:].strip()
            current_file = target[2:] if target.startswith('b/') else None
            if current_file and current_file not in file_lines:
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
