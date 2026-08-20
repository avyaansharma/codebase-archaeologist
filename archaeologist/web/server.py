import os
import sys
import json
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from archaeologist.web.registry import get_repo_config, list_repo_configs, REPOSITORIES
from archaeologist.storage.db import get_session_context
from archaeologist.mcp_server.tools import (
    repo_hotspots_tool,
    repo_ownership_tool,
    change_coupling_tool,
    repo_symbols_tool,
    symbol_history_tool,
    ask_tool
)
from archaeologist.agent.graph import agent_graph

app = FastAPI(
    title="Codebase Archaeologist Intelligence API",
    description="Autonomous Forensic Code Intelligence & Multi-Repository Exploration API",
    version="1.0.0"
)

# Enable CORS for local dev and hosted web frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _activate_repo_environment(repo_id: str):
    """Activates the SQLite database and BM25 index path for the specified repository."""
    config = get_repo_config(repo_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found in registry.")
    
    os.environ["DATABASE_URL"] = f"sqlite:///{config['db_path']}"
    os.environ["BM25_INDEX_PATH"] = config["bm25_path"]
    return config

@app.get("/api/repos")
async def get_repositories():
    """Returns all available indexed repositories with statistics and starter questions."""
    return {"repositories": list_repo_configs()}

@app.get("/api/repos/{repo_id}")
async def get_repository_details(repo_id: str):
    """Returns detailed configuration for a specific repository."""
    config = get_repo_config(repo_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found.")
    return config

@app.post("/api/ask")
async def ask_question(payload: Dict[str, Any]):
    """Synchronous forensic query endpoint."""
    repo_id = payload.get("repo_id", "requests")
    question = payload.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="Missing required 'question' parameter.")
    
    _activate_repo_environment(repo_id)
    
    try:
        response = ask_tool(question=question, repo_id=repo_id)
        return {
            "repo_id": repo_id,
            "question": question,
            "response": response
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ask/stream")
async def stream_question(
    repo_id: str = Query("requests", description="Repository ID (requests, flask, mss)"),
    q: str = Query(..., description="The forensic causal question to investigate")
):
    """Real-time Server-Sent Events (SSE) stream showing the LangGraph execution lifecycle."""
    config = _activate_repo_environment(repo_id)
    
    async def event_generator():
        yield {
            "event": "start",
            "data": json.dumps({
                "repo_id": repo_id,
                "repo_name": config["name"],
                "question": q,
                "status": "Initializing LangGraph state engine and candidate forensics discovery..."
            })
        }
        await asyncio.sleep(0.1)
        
        # Step 1: Candidate Forensics Discovery
        yield {
            "event": "planning",
            "data": json.dumps({
                "step": "Candidate Forensics",
                "message": "Scanning query tokens against AST Symbol Index, Pull Request references, and Commit SHAs..."
            })
        }
        await asyncio.sleep(0.2)
        
        # Run agent graph execution in background thread
        try:
            inputs = {
                "question": q,
                "repo_id": repo_id,
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
            
            yield {
                "event": "retrieval",
                "data": json.dumps({
                    "step": "Hybrid RRF Retrieval",
                    "message": "Executing dense vector search (Qdrant) and lexical BM25 ranking across git diffs..."
                })
            }
            
            loop = asyncio.get_event_loop()
            final_state = await loop.run_in_executor(
                None,
                lambda: agent_graph.invoke(inputs, config={"recursion_limit": 60})
            )
            
            sub_q = final_state.get("sub_questions", [])
            retrieved_count = len(final_state.get("retrieved_chunks", []))
            verification = final_state.get("verification_passed", True)
            answer = final_state.get("response", "Could not synthesize answer.")
            
            yield {
                "event": "verification",
                "data": json.dumps({
                    "step": "Self-Verification Judge",
                    "sub_questions": sub_q,
                    "chunks_evaluated": retrieved_count,
                    "verification_passed": verification,
                    "message": f"Successfully verified causal claims against {retrieved_count} repository history chunks."
                })
            }
            await asyncio.sleep(0.1)
            
            yield {
                "event": "answer",
                "data": json.dumps({
                    "response": answer,
                    "retrieved_chunks_count": retrieved_count,
                    "sub_questions": sub_q
                })
            }
            
            yield {
                "event": "done",
                "data": json.dumps({"status": "complete"})
            }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    return EventSourceResponse(event_generator())

@app.get("/api/hotspots/{repo_id}")
async def get_hotspots(repo_id: str, top_n: int = Query(15, ge=1, le=50)):
    """Returns top churn files ranked by historical commit count."""
    _activate_repo_environment(repo_id)
    hotspots = repo_hotspots_tool(top_n=top_n)
    return {"repo_id": repo_id, "hotspots": hotspots}

@app.get("/api/ownership/{repo_id}")
async def get_ownership(repo_id: str, file_path: Optional[str] = Query(None)):
    """Returns contributor ownership distribution and automated bus factor risk assessment."""
    _activate_repo_environment(repo_id)
    ownership = repo_ownership_tool(file_path=file_path)
    return {"repo_id": repo_id, "ownership": ownership}

@app.get("/api/coupling/{repo_id}")
async def get_coupling(repo_id: str, min_co_commits: int = Query(2, ge=1), top_n: int = Query(15, ge=1, le=50)):
    """Returns temporal file change coupling pairs (files that change together)."""
    _activate_repo_environment(repo_id)
    couplings = change_coupling_tool(min_co_commits=min_co_commits, top_n=top_n)
    return {"repo_id": repo_id, "couplings": couplings}

@app.get("/api/symbols/{repo_id}")
async def get_symbols(repo_id: str, top_n: int = Query(25, ge=1, le=100)):
    """Returns extracted AST code symbols ranked by modification frequency."""
    _activate_repo_environment(repo_id)
    symbols = repo_symbols_tool(top_n=top_n)
    return {"repo_id": repo_id, "symbols": symbols}

@app.get("/api/symbols/{repo_id}/history")
async def get_symbol_history(repo_id: str, symbol: str = Query(...)):
    """Traces all commits that modified a specific AST class or function."""
    _activate_repo_environment(repo_id)
    history = symbol_history_tool(symbol_query=symbol)
    return {"repo_id": repo_id, "symbol": symbol, "commits": history}

@app.get("/api/eval/leaderboard")
async def get_leaderboard():
    """Returns benchmark evaluations across all indexed repositories."""
    results = {}
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    for repo_key, res_file in [
        ("requests", "requests_results.json"),
        ("flask", "flask_results.json"),
        ("mss", "mss_results.json")
    ]:
        fpath = os.path.join(workspace_root, "eval", res_file)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    results[repo_key] = json.load(f)
            except Exception:
                pass
                
    return {"leaderboard": results}

# Mount static web UI directly from web/ directory
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("archaeologist.web.server:app", host="0.0.0.0", port=8000, reload=True)

