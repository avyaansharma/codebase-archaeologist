import os
import re
import json
import subprocess
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional
from sqlmodel import select

from archaeologist.storage.db import get_session_context
from archaeologist.storage.models import Commit, PullRequest, Issue, Chunk, SymbolIndex
from archaeologist.retrieval.embedder import Embedder
from archaeologist.retrieval.vector_store import VectorStore
from archaeologist.retrieval.bm25_index import BM25Index
from archaeologist.retrieval.fusion import reciprocal_rank_fusion
from archaeologist.agent.graph import agent_graph
from archaeologist.utils.gemini_client import GeminiClientWrapper, get_gemini_api_key
from archaeologist.utils.security import validate_repo_path, sanitize_file_path

def _get_json_list(value: Any) -> List[str]:
    """Safely deseralizes JSON list fields stored in SQLite."""
    if not value:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return value

def search_history_tool(
    query: str,
    file_path: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source_types: Optional[List[str]] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Hybrid search over commit/PR/issue history for a repo."""
    bm25 = BM25Index()
    sparse_hits = []
    if os.path.exists("bm25_index.bin"):
        bm25.load("bm25_index.bin")
        sparse_hits = bm25.search(query, limit=30)

    embedder = Embedder()
    vector_store = VectorStore(vector_size=embedder.dimension)
    dense_hits = []
    try:
        query_vectors = embedder.embed_texts([query])
        if query_vectors:
            dense_hits = vector_store.search_chunks(
                query_vector=query_vectors[0],
                limit=30,
                file_path=file_path,
                date_from=date_from,
                date_to=date_to,
                source_types=source_types
            )
    except Exception as e:
        print(f"Error in vector search: {e}")
    finally:
        vector_store.close()

    fused_results = reciprocal_rank_fusion(dense_hits, sparse_hits, limit=limit)
    
    formatted = []
    for hit in fused_results:
        formatted.append({
            "id": hit["id"],
            "rrf_score": hit["rrf_score"],
            "payload": hit["payload"]
        })
    return formatted

def find_related_discussion_tool(ref: str) -> Dict[str, Any]:
    """Given a commit SHA or PR/issue number, return linked issues, PRs, and commits."""
    result = {"commits": [], "pull_requests": [], "issues": []}
    
    with get_session_context() as session:
        ref_cleaned = ref.strip().lower()
        
        if len(ref_cleaned) >= 7 and not ref_cleaned.startswith("#") and ref_cleaned.isalnum():
            stmt = select(Commit).where(Commit.sha.like(f"{ref_cleaned}%"))
            commit = session.exec(stmt).first()
            if commit:
                result["commits"].append({
                    "sha": commit.sha,
                    "author": commit.author_name,
                    "date": commit.authored_date.isoformat(),
                    "message": commit.message,
                    "is_revert": commit.is_revert,
                    "reverts_sha": commit.reverts_sha,
                    "superseded_by_sha": commit.superseded_by_sha
                })
                
                stmt_chunk = select(Chunk).where(Chunk.source_type == "commit", Chunk.source_id == commit.sha)
                chunks = session.exec(stmt_chunk).all()
                related_refs = set()
                for c in chunks:
                    related_refs.update(c.related_ids)
                
                for r in related_refs:
                    if r.startswith("pr#"):
                        pr_num = int(r.split("#")[-1])
                        pr = session.get(PullRequest, pr_num)
                        if pr:
                            result["pull_requests"].append({"number": pr.number, "title": pr.title, "state": pr.state})
                    elif r.startswith("issue#"):
                        issue_num = int(r.split("#")[-1])
                        issue = session.get(Issue, issue_num)
                        if issue:
                            result["issues"].append({"number": issue.number, "title": issue.title, "state": issue.state})

        else:
            num_match = re.search(r'\d+', ref_cleaned)
            if num_match:
                num = int(num_match.group(0))
                
                pr = session.get(PullRequest, num)
                if pr:
                    result["pull_requests"].append({
                        "number": pr.number,
                        "title": pr.title,
                        "state": pr.state,
                        "author": pr.author,
                        "linked_issues": pr.linked_issue_numbers
                    })
                    for i_num in pr.linked_issue_numbers:
                        i = session.get(Issue, i_num)
                        if i:
                            result["issues"].append({"number": i.number, "title": i.title, "state": i.state})
                            
                    stmt_commits = select(Commit).where(Commit.message.like(f"%#{pr.number}%"))
                    linked_commits = session.exec(stmt_commits).all()
                    for c in linked_commits:
                        result["commits"].append({"sha": c.sha, "message": c.message, "author": c.author_name})
                
                issue = session.get(Issue, num)
                if issue:
                    result["issues"].append({
                        "number": issue.number,
                        "title": issue.title,
                        "state": issue.state,
                        "labels": issue.labels,
                        "linked_prs": issue.linked_pr_numbers
                    })
                    for p_num in issue.linked_pr_numbers:
                        p = session.get(PullRequest, p_num)
                        if p:
                            result["pull_requests"].append({"number": p.number, "title": p.title, "state": p.state})

    return result

def blame_explain_tool(
    repo_path: str,
    file_path: str,
    line_start: int,
    line_end: int
) -> Dict[str, Any]:
    """Given a file and line range, return the commit history and causal explanation for why that code exists."""
    validated_repo = validate_repo_path(repo_path)
    clean_file_path = sanitize_file_path(validated_repo, file_path)

    cmd = [
        "git", "-C", validated_repo, "blame", 
        "-L", f"{line_start},{line_end}", 
        "--porcelain", clean_file_path
    ]
    
    shas = set()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                parts = line.split()
                if parts and len(parts[0]) == 40:
                    shas.add(parts[0])
    except Exception as e:
        print(f"Error running git blame: {e}")
        
    if not shas:
        return {"explanation": "No commit history found for specified lines.", "commits": []}

    commits_metadata = []
    chunk_evidence = []
    
    with get_session_context() as session:
        for sha in shas:
            commit = session.get(Commit, sha)
            if commit:
                commits_metadata.append({
                    "sha": commit.sha,
                    "author": commit.author_name,
                    "date": commit.authored_date.isoformat(),
                    "message": commit.message,
                    "symbols_modified": _get_json_list(commit.symbols_modified),
                    "is_revert": commit.is_revert,
                })
                stmt = select(Chunk).where(Chunk.source_id == commit.sha)
                chunks = session.exec(stmt).all()
                for c in chunks:
                    chunk_evidence.append(c.text)

    api_key = get_gemini_api_key()
    explanation = "Gemini API key missing. Commits returned without explanation."
    
    if api_key and chunk_evidence:
        client = GeminiClientWrapper(api_key=api_key)
        evidence_str = "\n\n".join(chunk_evidence)
        prompt = (
            "You are a codebase archaeologist. Analyze the commits that modified the specified lines of code.\n"
            "Using the commit messages, explain the causal history of why these lines exist in their current form.\n"
            "Identify the authors, when it was changed, and the context (e.g. bug fixes, refactoring, feature additions).\n\n"
            f"Commit Data:\n{evidence_str}\n\n"
            "Causal Explanation:"
        )
        try:
            explanation = client.generate_text(
                prompt=prompt,
                model="gemini-2.5-flash",
                temperature=0.0,
                max_output_tokens=500
            )
        except Exception as e:
            explanation = f"Error generating explanation: {e}"

    return {
        "explanation": explanation,
        "commits": commits_metadata
    }

def repo_hotspots_tool(top_n: int = 15) -> List[Dict[str, Any]]:
    """Ranks files by commit frequency (most frequently modified files / hotspots)."""
    counter = Counter()
    with get_session_context() as session:
        commits = session.exec(select(Commit)).all()
        for c in commits:
            for path in _get_json_list(c.files_changed):
                counter[path] += 1

    hotspots = []
    for path, count in counter.most_common(top_n):
        hotspots.append({"file_path": path, "commit_count": count})
    return hotspots

def repo_ownership_tool(file_path: Optional[str] = None) -> Dict[str, Any]:
    """Analyzes author contribution distribution per file or across the repository to determine bus factor."""
    author_counts = defaultdict(Counter)
    total_commits_per_file = Counter()

    with get_session_context() as session:
        commits = session.exec(select(Commit)).all()
        for c in commits:
            author = c.author_name
            for path in _get_json_list(c.files_changed):
                if file_path and path != file_path:
                    continue
                author_counts[path][author] += 1
                total_commits_per_file[path] += 1

    results = {}
    for path, authors in author_counts.items():
        total = total_commits_per_file[path]
        distribution = []
        for author, count in authors.most_common():
            percentage = round((count / total) * 100, 2)
            distribution.append({"author": author, "commits": count, "percentage": percentage})
        
        main_author = distribution[0] if distribution else None
        bus_factor_risk = "HIGH" if (main_author and main_author["percentage"] > 70 and total > 5) else "NORMAL"
        
        results[path] = {
            "total_commits": total,
            "main_owner": main_author["author"] if main_author else "unknown",
            "bus_factor_risk": bus_factor_risk,
            "authors": distribution
        }

    return results

def change_coupling_tool(min_co_commits: int = 2, top_n: int = 15) -> List[Dict[str, Any]]:
    """Finds pairs of files that frequently change together in the same commit (temporal coupling)."""
    co_commit_counts = Counter()

    with get_session_context() as session:
        commits = session.exec(select(Commit)).all()
        for c in commits:
            files = sorted(list(set(_get_json_list(c.files_changed))))
            for i in range(len(files)):
                for j in range(i + 1, len(files)):
                    pair = (files[i], files[j])
                    co_commit_counts[pair] += 1

    couplings = []
    for (f1, f2), count in co_commit_counts.most_common(top_n):
        if count >= min_co_commits:
            couplings.append({
                "file_a": f1,
                "file_b": f2,
                "co_commit_count": count
            })
    return couplings

def repo_symbols_tool(top_n: int = 20) -> List[Dict[str, Any]]:
    """Lists extracted AST code symbols (classes, functions, methods) ranked by modification frequency."""
    with get_session_context() as session:
        symbols = session.exec(select(SymbolIndex).order_by(SymbolIndex.commit_count.desc()).limit(top_n)).all()
        return [
            {
                "symbol_id": s.symbol_id,
                "file_path": s.file_path,
                "symbol_name": s.symbol_name,
                "kind": s.kind,
                "commit_count": s.commit_count
            }
            for s in symbols
        ]

def symbol_history_tool(symbol_query: str) -> List[Dict[str, Any]]:
    """Retrieves all commits that modified a specific AST Code Symbol (e.g. 'AuthService' or 'login')."""
    matching_commits = []
    with get_session_context() as session:
        commits = session.exec(select(Commit)).all()
        for c in commits:
            syms = _get_json_list(c.symbols_modified)
            if any(symbol_query.lower() in s.lower() for s in syms):
                matching_commits.append({
                    "sha": c.sha,
                    "author": c.author_name,
                    "date": c.authored_date.isoformat(),
                    "message": c.message,
                    "symbols_modified": syms,
                    "files_changed": _get_json_list(c.files_changed)
                })
    return matching_commits

def ask_tool(question: str) -> str:
    """Answers a causal 'why' question about the codebase using full agentic multi-hop retrieval."""
    inputs = {
        "question": question,
        "sub_questions": [],
        "current_sub_question_index": 0,
        "search_queries": [],
        "retrieved_chunks": [],
        "evidence_by_chunk_id": {},
        "draft_answer": None,
        "verification_passed": False,
        "unverified_claims": [],
        "retry_count": 0,
        "response": None
    }
    
    try:
        final_state = agent_graph.invoke(inputs)
        return final_state.get("response", "Could not synthesize response.")
    except Exception as e:
        return f"Error executing agent loop: {e}"
