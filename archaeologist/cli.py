import typer
import os
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(help="Codebase Archaeologist Command Line Interface")

@app.command()
def ingest(
    repo_path: str = typer.Argument(..., help="Path to local repository directory"),
    repo_url: Optional[str] = typer.Option(None, help="GitHub repository URL (e.g. https://github.com/owner/repo)"),
    since: Optional[str] = typer.Option(None, help="Only ingest commits after this date (e.g. YYYY-MM-DD)")
):
    """Ingests commits, PRs, issues, reverts and files of a repository into vector and metadata DBs."""
    from archaeologist.ingestion.pipeline import IngestionPipeline
    
    if not os.path.exists(repo_path):
        typer.echo(f"Error: Repository path '{repo_path}' does not exist.", err=True)
        raise typer.Exit(1)
        
    typer.echo(f"Starting ingestion for repository: {repo_path}...")
    pipeline = IngestionPipeline(repo_path=repo_path, repo_url=repo_url, since_date=since)
    try:
        pipeline.run()
        typer.echo("Ingestion completed successfully!")
    except Exception as e:
        typer.echo(f"Error running ingestion pipeline: {e}", err=True)
        raise typer.Exit(1)

@app.command()
def ask(
    question: str = typer.Argument(..., help="The causal query about the codebase")
):
    """Asks a causal query using the full LangGraph agent loop powered by Gemini."""
    from archaeologist.mcp_server.tools import ask_tool
    typer.echo(f"Query: {question}")
    typer.echo("Running Gemini agent loop...")
    res = ask_tool(question)
    typer.echo("\nResponse:")
    typer.echo(res)

@app.command()
def hotspots(
    top_n: int = typer.Option(15, help="Top N hotspot files to list"),
    db_path: Optional[str] = typer.Option(None, help="Optional SQLite database path (e.g. eval/data/flask.db)")
):
    """Lists repository hotspot files ranked by commit frequency."""
    if db_path:
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    from archaeologist.mcp_server.tools import repo_hotspots_tool
    res = repo_hotspots_tool(top_n=top_n)
    typer.echo(json.dumps(res, indent=2))

@app.command()
def ownership(
    file_path: Optional[str] = typer.Option(None, help="Optional file path to inspect"),
    db_path: Optional[str] = typer.Option(None, help="Optional SQLite database path (e.g. eval/data/flask.db)")
):
    """Analyzes author contribution distribution and bus factor risk."""
    if db_path:
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    from archaeologist.mcp_server.tools import repo_ownership_tool
    res = repo_ownership_tool(file_path=file_path)
    typer.echo(json.dumps(res, indent=2))

@app.command()
def coupling(
    min_co_commits: int = typer.Option(2, help="Minimum co-commits required"),
    top_n: int = typer.Option(15, help="Top N coupled file pairs to list"),
    db_path: Optional[str] = typer.Option(None, help="Optional SQLite database path (e.g. eval/data/flask.db)")
):
    """Identifies pairs of files that frequently change together (temporal coupling)."""
    if db_path:
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    from archaeologist.mcp_server.tools import change_coupling_tool
    res = change_coupling_tool(min_co_commits=min_co_commits, top_n=top_n)
    typer.echo(json.dumps(res, indent=2))

@app.command()
def symbols(
    top_n: int = typer.Option(20, help="Top N AST symbols to list"),
    db_path: Optional[str] = typer.Option(None, help="Optional SQLite database path (e.g. eval/data/flask.db)")
):
    """Lists extracted AST Code Symbols (classes, functions, methods) ranked by commit count."""
    if db_path:
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    from archaeologist.mcp_server.tools import repo_symbols_tool
    res = repo_symbols_tool(top_n=top_n)
    typer.echo(json.dumps(res, indent=2))

@app.command()
def symbol_history(
    symbol_query: str = typer.Argument(..., help="Class or function name to search"),
    db_path: Optional[str] = typer.Option(None, help="Optional SQLite database path (e.g. eval/data/flask.db)")
):
    """Retrieves all commits that modified a specific AST Code Symbol."""
    if db_path:
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    from archaeologist.mcp_server.tools import symbol_history_tool
    res = symbol_history_tool(symbol_query=symbol_query)
    typer.echo(json.dumps(res, indent=2))


@app.command()
def start_server():
    """Starts the Codebase Archaeologist MCP Server on stdio transport."""
    from archaeologist.mcp_server.server import mcp
    typer.echo("Starting stdio MCP server...", err=True)
    mcp.run()

@app.command()
def run_eval(
    dataset: Optional[str] = typer.Option(None, help="Path to QA pairs dataset JSONL file")
):
    """Runs the evaluation harness to measure Grounded Accuracy and Citation Precision."""
    from eval.run_eval import run_evaluation
    typer.echo(f"Starting evaluation suite (dataset: {dataset or 'default'})...")
    run_evaluation(dataset)

if __name__ == "__main__":
    app()
