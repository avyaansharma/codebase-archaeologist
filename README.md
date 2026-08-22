# 🏛️ Codebase History Analyzer

> Autonomous Forensic Code Intelligence & Temporal Causal Graph Analysis powered by LangGraph, Google Gemini, BM25, Qdrant, and SQLite.

---

## Features
- **Temporal Causal Knowledge Graph**: 4-lane stratified interactive graph connecting Issues, PRs, Commits, Reverts, and AST Symbols.
- **Client-Provided Gemini Key Architecture**: Zero-server storage privacy model.
- **Forensic Query Console**: Multi-hop RAG execution lifecycle with verified causal claim badges.
- **Hotspots, Contributor Ownership & Coupling**: Automated bus factor risk assessments.

---

## Local Quickstart
```bash
# 1. Install dependencies
pip install -e .

# 2. Start web application
python -m uvicorn archaeologist.web.server:app --host 127.0.0.1 --port 8000
```
