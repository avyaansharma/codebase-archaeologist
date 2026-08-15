import os
import re
from datetime import datetime
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlmodel import select

from archaeologist.storage.db import init_db, get_session_context
from archaeologist.storage.models import Commit, PullRequest, Issue, Chunk, SymbolIndex
from archaeologist.ingestion.git_parser import iter_commits, get_commit_diff, is_merge_commit
from archaeologist.ingestion.revert_detector import detect_revert_from_message, find_reverted_commit
from archaeologist.ingestion.github_client import GitHubIngestionClient
from archaeologist.ingestion.link_resolver import update_cross_links
from archaeologist.ingestion.chunker import chunk_commit, chunk_issue, chunk_pr, make_deterministic_chunk_id, token_count
from archaeologist.ingestion.diff_summarizer import LLMSummarizer
from archaeologist.ingestion.symbol_parser import (
    extract_symbols_from_code,
    map_lines_to_symbols,
    extract_modified_line_numbers_from_diff,
    resolve_file_path,
    get_git_file_content
)
from archaeologist.retrieval.embedder import Embedder
from archaeologist.retrieval.vector_store import VectorStore
from archaeologist.retrieval.bm25_index import BM25Index

class IngestionPipeline:
    def __init__(self, repo_path: str, repo_url: Optional[str] = None, since_date: Optional[str] = None, github_limit: int = 500):
        self.repo_path = repo_path
        self.repo_url = repo_url
        self.since_date = since_date
        self.github_limit = github_limit

    def run(self):
        print("Initializing metadata database...")
        init_db()

        print("Initializing vector store collection...")
        embedder = Embedder()
        vector_store = VectorStore(vector_size=embedder.dimension)
        vector_store.init_collection()
        vector_store.close()

        # Step 1: Walk git log & Extract AST Symbol Graph at historical commit SHAs
        print(f"Walking git log and extracting AST code symbols from {self.repo_path}...")
        new_commits_count = 0
        
        with get_session_context() as session:
            existing_shas = set(session.exec(select(Commit.sha)).all())
            
            for c_data in iter_commits(self.repo_path, since=self.since_date):
                if c_data["sha"] in existing_shas:
                    continue
                    
                reverted_subject = detect_revert_from_message(c_data["message"])
                is_revert = bool(reverted_subject)
                
                # AST Symbol Extraction Pass at Historical Commit SHA
                symbols_modified = []
                diff_text = get_commit_diff(self.repo_path, c_data["sha"])
                if diff_text:
                    modified_lines_map = extract_modified_line_numbers_from_diff(diff_text)
                    for fpath, lines in modified_lines_map.items():
                        code_text = get_git_file_content(self.repo_path, c_data["sha"], fpath)
                        if not code_text:
                            resolved_path = resolve_file_path(self.repo_path, fpath)
                            if resolved_path:
                                try:
                                    with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
                                        code_text = f.read()
                                except Exception:
                                    code_text = None

                        if code_text:
                            file_symbols = extract_symbols_from_code(code_text, fpath)
                            touched_syms = map_lines_to_symbols(file_symbols, lines)
                            symbols_modified.extend(touched_syms)

                            for sym in file_symbols:
                                sym_obj = session.get(SymbolIndex, sym["symbol_id"])
                                if not sym_obj:
                                    sym_obj = SymbolIndex(
                                        symbol_id=sym["symbol_id"],
                                        file_path=fpath,
                                        symbol_name=sym["name"],
                                        kind=sym["kind"],
                                        commit_count=1 if sym["symbol_id"] in touched_syms else 0
                                    )
                                    session.add(sym_obj)
                                elif sym["symbol_id"] in touched_syms:
                                    sym_obj.commit_count += 1
                                    session.add(sym_obj)

                commit_obj = Commit(
                    sha=c_data["sha"],
                    author_name=c_data["author_name"],
                    author_email=c_data["author_email"],
                    authored_date=c_data["authored_date"],
                    message=c_data["message"],
                    files_changed=c_data["files_changed"],
                    symbols_modified=sorted(list(set(symbols_modified))),
                    insertions=c_data["insertions"],
                    deletions=c_data["deletions"],
                    is_revert=is_revert,
                    reverts_sha=None
                )
                session.add(commit_obj)
                existing_shas.add(c_data["sha"])
                new_commits_count += 1
                
        print(f"Added {new_commits_count} new commits to SQLite.")

        # Step 1b: Codebase File Ingestion Pass
        print("Chunking codebase source files...")
        with get_session_context() as session:
            for root, dirs, files in os.walk(self.repo_path):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "__pycache__", "node_modules", "site-packages", "dist", "build")]
                for fname in files:
                    if fname.endswith((".py", ".md", ".json", ".ts", ".js", ".yml", ".yaml", ".jsonl")):
                        abs_fpath = os.path.join(root, fname)
                        rel_fpath = os.path.relpath(abs_fpath, self.repo_path).replace("\\", "/")
                        try:
                            with open(abs_fpath, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                            if content.strip():
                                chunk_id = make_deterministic_chunk_id("file", rel_fpath, 0, content)
                                c_obj = session.get(Chunk, chunk_id)
                                if not c_obj:
                                    chunk_text = f"File {rel_fpath}:\n{content[:3000]}"
                                    session.add(Chunk(
                                        id=chunk_id,
                                        source_type="file",
                                        source_id=rel_fpath,
                                        text=chunk_text,
                                        timestamp=datetime.utcnow(),
                                        file_paths=[rel_fpath],
                                        symbols_modified=[],
                                        is_reverted=False,
                                        token_count=token_count(chunk_text)
                                    ))
                        except Exception:
                            pass

        # Step 2: Revert Detection Resolution Pass
        print("Running revert detection pass...")
        with get_session_context() as session:
            revert_commits = session.exec(select(Commit).where(Commit.is_revert == True)).all()
            reverts_resolved = 0
            for r_commit in revert_commits:
                if not r_commit.reverts_sha:
                    reverted_subject = detect_revert_from_message(r_commit.message)
                    if reverted_subject:
                        orig_commit = find_reverted_commit(session, reverted_subject, r_commit.authored_date)
                        if orig_commit:
                            r_commit.reverts_sha = orig_commit.sha
                            session.add(r_commit)
                            orig_commit.superseded_by_sha = r_commit.sha
                            session.add(orig_commit)
                            reverts_resolved += 1
        print(f"Resolved {reverts_resolved} reverts.")

        # Step 3: Fetch GitHub Issues and PRs (Historical order: direction='asc')
        if self.repo_url:
            try:
                print(f"Fetching GitHub Issues and PRs for {self.repo_url} (limit={self.github_limit}, direction=asc)...")
                gh_client = GitHubIngestionClient(self.repo_url)
                prs = gh_client.fetch_pull_requests(limit=self.github_limit, direction="asc")
                issues = gh_client.fetch_issues(limit=self.github_limit, direction="asc")
                
                with get_session_context() as session:
                    for pr_data in prs:
                        pr_obj = session.get(PullRequest, pr_data["number"])
                        if not pr_obj:
                            pr_obj = PullRequest(
                                number=pr_data["number"],
                                title=pr_data["title"],
                                body=pr_data["body"],
                                state=pr_data["state"],
                                author=pr_data.get("author", "unknown"),
                                created_at=pr_data["created_at"],
                                merged_at=pr_data["merged_at"],
                                merge_commit_sha=pr_data.get("merged_commit_sha"),
                                merged_commit_sha=pr_data.get("merged_commit_sha"),
                                comments=pr_data.get("comments", []),
                                review_comments=pr_data.get("review_comments", []),
                                linked_issue_numbers=pr_data.get("linked_issue_numbers", [])
                            )
                            session.add(pr_obj)

                    for issue_data in issues:
                        issue_obj = session.get(Issue, issue_data["number"])
                        if not issue_obj:
                            issue_obj = Issue(
                                number=issue_data["number"],
                                title=issue_data["title"],
                                body=issue_data["body"],
                                state=issue_data["state"],
                                author=issue_data.get("author", "unknown"),
                                created_at=issue_data["created_at"],
                                closed_at=issue_data.get("closed_at"),
                                labels=issue_data.get("labels", []),
                                comments=issue_data.get("comments", []),
                                linked_pr_numbers=issue_data.get("linked_pr_numbers", [])
                            )
                            session.add(issue_obj)
            except Exception as e:
                print(f"Notice: Skipping GitHub API ingestion ({e})")
        else:
            print("No GitHub URL/remote origin provided. Skipping GitHub REST API ingestion.")

        # Step 4: Cross-Link Resolution Pass (§2 Fix: Copy linked_commit_shas back to ORM objects)
        with get_session_context() as session:
            prs = session.exec(select(PullRequest)).all()
            issues = session.exec(select(Issue)).all()
            pr_dicts = [p.model_dump() for p in prs]
            issue_dicts = [i.model_dump() for i in issues]
            
            update_cross_links(pr_dicts, issue_dicts)
            
            for p_dict in pr_dicts:
                p_obj = session.get(PullRequest, p_dict["number"])
                if p_obj:
                    p_obj.linked_issue_numbers = p_dict.get("linked_issue_numbers", [])
                    p_obj.linked_commit_shas = p_dict.get("linked_commit_shas", [])
                    session.add(p_obj)
            for i_dict in issue_dicts:
                i_obj = session.get(Issue, i_dict["number"])
                if i_obj:
                    i_obj.linked_pr_numbers = i_dict.get("linked_pr_numbers", [])
                    i_obj.linked_commit_shas = i_dict.get("linked_commit_shas", [])
                    session.add(i_obj)

        # Step 5: Batched Chunking & Summarization Pass (§3 Fix: populate commit_dict["related_ids"])
        print("Processing chunking rules & generating summaries with API request batching...")
        summarizer = LLMSummarizer()
        
        with get_session_context() as session:
            all_commits = session.exec(select(Commit)).all()
            all_prs = session.exec(select(PullRequest)).all()
            
            # Map commit SHAs to merging PRs
            pr_by_commit = {}
            for p in all_prs:
                if p.merged_commit_sha:
                    pr_by_commit[p.merged_commit_sha] = p.number
                for sha in p.linked_commit_shas:
                    pr_by_commit[sha] = p.number

            eligible_diffs = []
            for c in all_commits:
                if 0 < len(c.files_changed) <= 20:
                    d_text = get_commit_diff(self.repo_path, c.sha)
                    if d_text:
                        eligible_diffs.append({"sha": c.sha, "diff_text": d_text})

            diff_summaries = {}
            batch_size = 5
            for i in range(0, len(eligible_diffs), batch_size):
                batch = eligible_diffs[i:i + batch_size]
                batch_res = summarizer.summarize_diff_batch(batch)
                diff_summaries.update(batch_res)

            for c in all_commits:
                summary = diff_summaries.get(c.sha)
                commit_dict = c.model_dump()
                
                # Populate commit_dict["related_ids"] (§3 Fix)
                related = []
                if c.sha in pr_by_commit:
                    related.append(f"pr#{pr_by_commit[c.sha]}")
                commit_dict["related_ids"] = related

                chunk_info = chunk_commit(commit=commit_dict, diff_summary=summary)
                c_obj = session.get(Chunk, chunk_info["id"])
                if not c_obj:
                    session.add(Chunk(**chunk_info))

            # PR Chunks
            for pr in all_prs:
                pr_dict = pr.model_dump()
                pr_chunks = chunk_pr(pr=pr_dict)
                for chunk_info in pr_chunks:
                    c_obj = session.get(Chunk, chunk_info["id"])
                    if not c_obj:
                        session.add(Chunk(**chunk_info))

            # Issue Chunks
            all_issues = session.exec(select(Issue)).all()
            for i in all_issues:
                issue_dict = i.model_dump()
                issue_chunks = chunk_issue(issue=issue_dict)
                for chunk_info in issue_chunks:
                    c_obj = session.get(Chunk, chunk_info["id"])
                    if not c_obj:
                        session.add(Chunk(**chunk_info))

        # Step 6: Indexing (BM25 + Qdrant)
        print("Fetching chunks for indexing...")
        with get_session_context() as session:
            all_chunks_db = session.exec(select(Chunk)).all()
            all_chunk_dicts = [
                {
                    "id": c.id,
                    "source_type": c.source_type,
                    "source_id": c.source_id,
                    "text": c.text,
                    "timestamp": c.timestamp,
                    "file_paths": c.file_paths,
                    "symbols_modified": c.symbols_modified,
                    "related_ids": c.related_ids,
                    "is_reverted": c.is_reverted
                }
                for c in all_chunks_db
            ]

        # 6a. BM25 Sparse Index
        if all_chunk_dicts:
            print(f"Fitting BM25 index on {len(all_chunk_dicts)} chunks...")
            bm25 = BM25Index()
            bm25.fit(all_chunk_dicts)
            bm25.save("bm25_index.bin")

        # 6b. Qdrant Dense Index (filter Chunk.embedded == False for incremental resumability)
        with get_session_context() as session:
            unembedded_chunks = session.exec(select(Chunk).where(Chunk.embedded == False)).all()
            unembedded_dicts = [
                {
                    "id": c.id,
                    "source_type": c.source_type,
                    "source_id": c.source_id,
                    "text": c.text,
                    "timestamp": c.timestamp,
                    "file_paths": c.file_paths,
                    "symbols_modified": c.symbols_modified,
                    "related_ids": c.related_ids,
                    "is_reverted": c.is_reverted
                }
                for c in unembedded_chunks
            ]

        if unembedded_dicts:
            vector_store = VectorStore(vector_size=embedder.dimension)
            vector_store.init_collection()
            
            print(f"Generating embeddings for {len(unembedded_dicts)} un-embedded chunks...")
            texts = [c["text"] for c in unembedded_dicts]
            embeddings = embedder.embed_texts(texts)
            
            if embeddings:
                vector_store.upsert_chunks(unembedded_dicts, embeddings)
                with get_session_context() as session:
                    for c_dict in unembedded_dicts:
                        c_db = session.get(Chunk, c_dict["id"])
                        if c_db:
                            c_db.embedded = True
                            session.add(c_db)
                print("Incremental dense vector indexing complete!")
            vector_store.close()
        else:
            print("All chunks already embedded. Skipping dense vector re-embedding.")

        print("Ingestion pipeline completed successfully!")
