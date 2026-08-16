# 🏺 Codebase Archaeologist

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Google Gemini API](https://img.shields.io/badge/Google_Gemini-3.5_Flash-4285F4.svg?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic_RAG-FF6F61.svg?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![MCP Server](https://img.shields.io/badge/MCP-Model_Context_Protocol-000000.svg?style=for-the-badge)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

### An Agentic Code Intelligence System for Forensic Causal Investigation (*"Why Code Changed"*)

> **GitHub Copilot and traditional RAG explain *what* code does in its static, current state.**  
> **Codebase Archaeologist is an Autonomous Forensic Investigator that discovers *why* code exists by mining the temporal causal graph — git commit diffs, AST symbol line mappings, PR discussions, linked issues, and revert histories.**

---

```text
$ archaeologist ask "Why was retry logic added to fetchUser?"

[1] Decompose  → Target symbol: `fetchUser` | Goal: Identify motivation for retry loop
[2] AST Lookup → Located `UserService.fetchUser()` in `src/services/user.py`
[3] Git Trace  → Found commit 8f31a2 ("Handle transient upstream 503 failures")
[4] PR Graph   → Traversed linked PR #421 (Author: @tomchristie)
[5] Issue Graph → Traversed linked Issue #389 ("Intermittent gateway timeouts on peak load")
[6] Verifier   → Verified 4/4 claims against codebase diffs & PR notes

Answer:
Retry logic was introduced to `fetchUser()` in commit 8f31a2 (PR #421) by @tomchristie to mitigate 
intermittent 503 upstream gateway timeouts reported in Issue #389.

### Historical PRs & Linked Issues
* PR #421 (Commit 8f31a2 by @tomchristie): Introduced exponential backoff retry loop for transient failures.
* Issue #389 (Reported by @user): Documented intermittent gateway 503 timeouts during peak traffic.
```

---

## 📌 Table of Contents

- [The Problem: Why Static RAG & Copilot Fall Short](#-the-problem-why-static-rag--copilot-fall-short)
- [Why is This System AGENTIC?](#-why-is-this-system-agentic)
- [System Architecture & Data Flow](#-system-architecture--data-flow)
- [Quantitative Evaluation & Ablation Study](#-quantitative-evaluation--ablation-study)
- [🛡️ Anti-Hallucination: Verifiable Citation Engine](#%EF%B8%8F-anti-hallucination-verifiable-citation-engine)
- [Key Design Decisions & Engineering Tradeoffs](#-key-design-decisions--engineering-tradeoffs)
- [🔌 Native MCP Integration (Claude Desktop / Cursor)](#-native-mcp-integration-claude-desktop--cursor)
- [🔥 Structural Intelligence & Features](#-structural-intelligence--features)
- [🚀 Quickstart & Installation](#-quickstart--installation)
- [🛠 CLI Reference](#-cli-reference)

---

## 💥 The Problem: Why Static RAG & Copilot Fall Short

Standard developer tools and code-RAG search engines analyze **static code snapshots**:
- **GitHub Copilot / Cursor**: Inspects current files in your context window to explain *what* a function does today.
- **Naive Vector RAG**: Embeds source code chunks into a vector database to find semantically similar code snippets.

### The Missing Dimension: Temporal Causal Context

Understanding **why** a piece of software exists in its current form cannot be answered by static source code alone. Consider the question:

> *"Why does `fetchUser()` retry 3 times with an exponential backoff?"*

The answer **does not exist** inside `fetchUser()`. The motivation is scattered across a 2-year-old temporal graph:

```text
src/services/user.py (fetchUser)
   │
   ├── Line Diff Mapping ──► Commit 8f31a2 ("Handle transient upstream failures")
   │                            │
   │                            ├── Linked PR #421 ──► Code Review Comments (@tomchristie)
   │                            │                         │
   │                            └── Linked Issue #389 ──► Production Outage Incident Report
   │
   └── AST Symbol Modifications ──► Reverted Commit 4a12c8 ("Initial single-pass request")
```

Codebase Archaeologist treats repository history as a **first-class temporal knowledge graph**, pairing AST code symbol tracking with bidirectional PR/issue linking to provide true causal code intelligence.

---

## 🤖 Why is This System AGENTIC?

Codebase Archaeologist is not a static 1-step retrieval pipeline. It operates as an **autonomous, stateful multi-hop reasoning agent** built on **LangGraph** and **Google Gemini 3.5 Flash**.

### Linear RAG vs. Agentic Forensic Investigation

```text
❌ Traditional Linear RAG (Fixed 1-Pass Execution)
   User Question ──► Vector Search ──► LLM Prompt ──► Output (Misses PRs, Issues, & AST Context)

✅ Codebase Archaeologist (Stateful Multi-Hop Agentic Loop)

                     ┌─────────────────────────┐
                     │      User Question      │
                     └────────────┬────────────┘
                                  │
                       ┌──────────▼──────────┐
                       │   Planner Agent     │
                       └──────────┬──────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              ▼                                       ▼
     ┌─────────────────┐                     ┌─────────────────┐
     │ Hybrid Search   │                     │ AST Symbol Graph│
     │ (Qdrant + BM25) │                     │ Direct Lookup   │
     └────────┬────────┘                     └────────┬────────┘
              │                                       │
              └───────────────────┬───────────────────┘
                                  ▼
                     ┌─────────────────────────┐
                     │  Cross-Link Traversal   │◄──── Dynamic Re-planning
                     │   (Commit ↔ PR ↔ Issue) │      if missing context
                     └────────────┬────────────┘
                                  │
                       ┌──────────▼──────────┐
                       │  Self-Verification  │──► Verification Failed?
                       │      Judge Node     │    (Clear Draft & Loop Back)
                       └──────────┬──────────┘
                                  │ Passed
                       ┌──────────▼──────────┐
                       │ Grounded Synthesis  │
                       │   + PR Citations    │
                       └─────────────────────┘
```

### Key Agent Capabilities

1. **Dynamic Task Decomposition**: Breaks complex user queries into sub-investigations (e.g. *"Identify symbol history for X"*, *"Find PRs referencing issue Y"*).
2. **Autonomous Multi-Hop Navigation**: Discovers cross-linked PR numbers (`pr#421`) or issue references (`issue#389`) during retrieval and automatically executes secondary graph-traversal hops.
3. **Self-Verification & Fact-Checking Loop**: A strict evaluator node judges whether preliminary draft answers are 100% supported by retrieved commit/PR evidence. If claims are unverified, it clears the draft and loops back to re-plan retrieval.
4. **Recursion Safety & Budget Enforcer**: Implements a strict tool budget (`tool_call_count >= 20` or `recursion_limit=25`) to prevent infinite execution loops.

---

## 🏗 System Architecture & Data Flow

Codebase Archaeologist pairs a robust ingestion pipeline with a multi-index storage architecture and an agentic execution graph:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   INGESTION PIPELINE                                   │
│  Git Log Diff Parsing  ──►  AST Symbol Extractor  ──►  SQLite Relational DB (Metadata)   │
│  GitHub REST API       ──►  PR & Issue Linker     ──►  Sparse BM25 Index (Lexical)      │
│  LLM Batch Summarizer  ──►  Gemini / Voyage API   ──►  Qdrant Vector Store (Semantic)    │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              LANGGRAPH REASONING ENGINE                                │
│                                                                                        │
│   [Decompose] ──► [Plan] ──► [Hybrid RRF Search] ──► [Follow Cross-Links]              │
│                                                                 │                      │
│   [Synthesize Response] ◄── [Verify Claims] ◄───────────────────┘                      │
│                                  │ (Failed)                                            │
│                                  └──────► [Re-Plan Retrieval]                          │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                             MODEL CONTEXT PROTOCOL (MCP)                               │
│        Exposes tools over stdio JSON-RPC for Claude Desktop, Cursor, & VS Code          │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🏆 Quantitative Evaluation & Ablation Study

Codebase Archaeologist was quantitatively evaluated using an automated LLM-as-a-Judge test harness across major open-source Python codebases: **`pallets/flask`** (4,774 indexed chunks) and **`encode/httpx`** (4,979 indexed chunks).

### Aggregate Benchmark Summary

| Target Repository | Index Scale | Average Grounded Accuracy | Average Citation Precision | Avg. Inference Latency | Benchmark Suite |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`pallets/flask`** | **4,774 Chunks** | **98.33%** | **72.22%** | **4.2 sec / query** | 6 Core Subsystem Suites (`eval/flask_results.json`) |
| **`encode/httpx`** | **4,979 Chunks** | **92.50%** | **85.00%** | **4.1 sec / query** | Transport Architecture Suite (`eval/httpx_results.json`) |
| **`codebase-archaeologist`** | **520 Chunks** | **90.00%** | **100.00%** | **3.8 sec / query** | 10 Graph Evaluation Pairs (`eval/results.json`) |

---

### 🔬 Component Ablation Study

To evaluate the contribution of each system component, we measured Grounded Accuracy across benchmark repositories as features were incrementally enabled:

| Pipeline Stage / Feature Enabled | `encode/httpx` (4.9k chunks) | `pallets/flask` (4.7k chunks) | `codebase-archaeologist` (520 chunks) | Impact & Rationale |
| :--- | :---: | :---: | :---: | :--- |
| **1. Baseline (Dense Vector Search Only)** | 50.00% | 68.33% | 60.00% | Pure semantic search misses exact code symbol names (`_client.py::Client::send`). |
| **2. + Sparse BM25 Keyword Search & RRF** | 70.00% | 85.00% | 78.00% | Reciprocal Rank Fusion balances exact symbol names with natural language intent. |
| **3. + Bidirectional Cross-Link Traversal** | 80.00% | 93.33% | 85.00% | Graph traversal follows PR review threads, commit SHAs, and issue discussions. |
| **4. + AST Symbol Graph Direct Retrieval & Verification** | **92.50%** | **98.33%** | **90.00%** | Direct symbol graph indexing guarantees code symbol definitions (`create_ssl_context`, `ContextVar`) are retrieved. |

---

## 🛡️ Anti-Hallucination: Verifiable Citation Engine

Unlike standard LLMs that generate answers from static parametric memory (often hallucinating non-existent PR numbers or outdated API signatures), Codebase Archaeologist enforces **ground-truth citation verification**. Every synthesized response explicitly formats real Pull Requests (`PR #3377`, `PR #750`), Issues (`Issue #593`), commit SHAs, and author attributions:

### Verified Sample Output Excerpt (`encode/httpx` - Transport Bridge)

```markdown
In `httpx/_transports/default.py`, `httpx` bridges the synchronization boundary by acting as a clean wrapper 
around `httpcore`, separating sync and async execution paths into `HTTPTransport` and `AsyncHTTPTransport`.

### Historical PRs & Linked Issues
* **PR #3377** (Commit `e9cabc8` by Joe Marshall, co-authored by Tom Christie): Deferred/lazy loading of `httpcore` and `certifi` dependencies until required by transports or exception mappers.
* **PR #3178** (Commit `12be5c4` by Bin Liu, co-authored by Tom Christie): Added `socks5h` proxy scheme support and updated config/transport logic.
* **PR #3175** (Commit `88a81c5` by manav-a, co-authored by Kar Petrosyan): Ensured consistent usage and propagation of `proxy_ssl_context` configurations into underlying transport initializations.
```

> 🎯 **Manual Verification Milestone**: After manually cross-referencing all **13 out of 13** Pull Request and Issue claims generated across the `encode/httpx` benchmark suite (`PR #3377`, `PR #3178`, `PR #3175`, `PR #3571`, `PR #3389`, `PR #3116`, `PR #3245`, `PR #3120`, `PR #3042`, `PR #3123`, `PR #3419`, `PR #3442`, `PR #3418`) against the official `encode/httpx` GitHub repository, **all 13/13 claims stood 100% strong and verified accurate** (0% hallucination rate).

---

## 🧠 Key Design Decisions & Engineering Tradeoffs

| Design Decision | Alternative Considered | Why This Choice Was Made |
| :--- | :--- | :--- |
| **Qdrant + BM25 + RRF** | Dense Vector Search Only | Dense vectors fail on exact identifier queries (`Client.send`, `ContextVar`). BM25 handles exact symbols, while Reciprocal Rank Fusion (RRF) merges candidate ranks without needing score normalization. |
| **AST Symbol Unit Chunking** | Fixed-size Token Windows | Arbitrary 512-token chunks cut functions and classes in half. AST parsing preserves functional code boundaries (`class AuthService`, `def login`). |
| **SQLite + Qdrant Dual Storage** | Vector-Only Payload Storage | Relational SQLite handles complex structured joins (PR ↔ Issue ↔ Commit ↔ Symbol relationships) while Qdrant handles high-dimensional vector search. |
| **LangGraph Stateful Loop** | Linear Chain / Sequential Pipeline | Sequential pipelines cannot recover from missing context. LangGraph enables dynamic re-planning, multi-hop cross-link traversal, and self-correction. |
| **Native MCP Transport** | REST / Custom HTTP API | Model Context Protocol allows external AI assistants (Claude Desktop, Cursor) to invoke repository archaeology tools natively. |

---

## 🔌 Native MCP Integration (Claude Desktop / Cursor)

Codebase Archaeologist exposes a native **Model Context Protocol (MCP)** server over standard `stdio` JSON-RPC transport, allowing AI assistants to query repository history directly.

### Claude Desktop Setup

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "codebase-archaeologist": {
      "command": "uv",
      "args": [
        "--directory",
        "C:/path/to/codebase-archaeologist",
        "run",
        "python",
        "-m",
        "archaeologist.cli",
        "start-server"
      ],
      "env": {
        "GEMINI_API_KEY": "your_gemini_api_key",
        "GITHUB_TOKEN": "your_github_token"
      }
    }
  }
}
```

### Exposed MCP Tools

- `search_history_tool`: Hybrid RRF search over commits, PRs, and issues with file/date filters.
- `find_related_discussion_tool`: Given a commit SHA or PR/issue number, returns all cross-linked items.
- `blame_explain_tool`: Explains the causal origin of specific line ranges in a file.
- `repo_hotspots_tool`: Calculates top churn files ranked by modification frequency.
- `repo_ownership_tool`: Calculates author contribution distribution and flags High Bus Factor Risk.
- `change_coupling_tool`: Discovers file pairs that change together (temporal co-commits).
- `symbol_history_tool`: Retrieves all commits that modified a specific AST Code Symbol.
- `ask_tool`: Executes the full agentic multi-hop retrieval and self-verification graph.

---

## 🔥 Structural Intelligence & Features

- **🛡️ Anti-Hallucination Citation Engine**: Verifiable citations with commit SHAs, PR numbers, and author names.
- **🤖 Multi-Hop Agentic RAG**: LangGraph loop with self-verification and draft regeneration.
- **🔑 Dynamic Multi-Key API Rotation**: Automatically rotates API keys on `429 RESOURCE_EXHAUSTED` rate limits.
- **🌳 AST Symbol Graph Indexing**: Maps commit diffs to Python `ast` nodes and multi-language syntax trees.
- **⚡ Hybrid RRF Retrieval Engine**: Dense embeddings (Qdrant) + Sparse keywords (`rank-bm25`) + RRF fusion.
- **🔗 Cross-Link Graph Traversal**: Automatically traverses `pr#123` and `issue#456` references.
- **📊 Repository Hotspots & Bus Factor Analysis**: Analyzes churn files and contributor dominance.
- **🛡️ Production Hardening**: Stderr logging (protects stdio MCP protocol), bounded concurrency, and model tier fallback (`gemini-3.5-flash` → `gemini-2.5-flash`).

---

## 🚀 Quickstart & Installation

### Prerequisites
- **Python 3.11+**
- **uv** package manager (`pip install uv`)
- **Git**

### 1. Clone the Repository
```bash
git clone https://github.com/avyaansharma/codebase-archaeologist.git
cd codebase-archaeologist
```

### 2. Install Dependencies
```bash
uv sync
```

### 3. Configure Environment Variables
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GITHUB_TOKEN=your_github_token_here
```

### 4. Ingest a Repository
```bash
# Ingest local repository with GitHub PR/Issue fetching
uv run python -m archaeologist.cli ingest . --repo-url https://github.com/owner/repo
```

### 5. Query Causal History
```bash
uv run python -m archaeologist.cli ask "Why was retry logic added to fetchUser?"
```

---

## 🛠 CLI Reference

| Command | Description |
| :--- | :--- |
| `archaeologist ingest <path>` | Ingests commits, PRs, issues, and AST symbols into SQLite & Qdrant. |
| `archaeologist ask "<query>"` | Runs full LangGraph multi-hop agent loop over repository history. |
| `archaeologist hotspots` | Lists top repository hotspot files by commit frequency. |
| `archaeologist ownership` | Calculates author contribution percentages & bus factor risk. |
| `archaeologist coupling` | Finds file pairs that change together (temporal co-commits). |
| `archaeologist symbols` | Lists extracted AST Code Symbols by commit count. |
| `archaeologist symbol-history <name>` | Retrieves all commits modifying a specific class/function. |
| `archaeologist start-server` | Starts stdio MCP Server transport for Claude Desktop / Cursor. |
| `archaeologist run-eval` | Runs Grounded Accuracy evaluation benchmark suite. |

---

## 📜 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.
