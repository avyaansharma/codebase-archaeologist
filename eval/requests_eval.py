import json
import os
import re
import sys
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

REQUESTS_QA_PAIRS = [
    {
        "id": 1,
        "question": "How does Session.send() in requests/sessions.py handle request preparation, redirect history tracking, connection pool adapter dispatching, and cookie persistence?",
        "expected_answer": "Session.send() dispatches the prepared request to the registered adapter (HTTPAdapter), manages request redirects using resolve_redirects(), records redirect history in response.history, and merges response cookies back into Session.cookies.",
        "expected_refs": ["sessions.py", "Session", "send", "HTTPAdapter", "resolve_redirects", "cookies"]
    },
    {
        "id": 2,
        "question": "How does HTTPAdapter in requests/adapters.py configure urllib3 connection pooling, max_retries, and SSL verification?",
        "expected_answer": "HTTPAdapter initializes urllib3 PoolManager via init_poolmanager(), sets max_retries on the connection manager, and injects SSL verification context (cert_reqs, ca_certs, ssl_version) into pool connections during request transmission.",
        "expected_refs": ["adapters.py", "HTTPAdapter", "init_poolmanager", "PoolManager", "max_retries", "ssl"]
    },
    {
        "id": 3,
        "question": "How does CaseInsensitiveDict in requests/structures.py enforce lower-case key normalization and preserve original key casing during iteration?",
        "expected_answer": "CaseInsensitiveDict maps lower-cased keys to (original_key, value) tuples inside a private _store dict, ensuring case-insensitive lookups while preserving original key casing when iterating over keys or items.",
        "expected_refs": ["structures.py", "CaseInsensitiveDict", "_store", "lower"]
    },
    {
        "id": 4,
        "question": "How does Response.raise_for_status() in requests/models.py evaluate HTTP status code ranges to raise HTTPError exceptions?",
        "expected_answer": "raise_for_status() checks response.status_code. If 400 <= status_code < 500, it raises a ClientError or HTTPError; if 500 <= status_code < 600, it raises a ServerError or HTTPError, formatted with response URL and reason.",
        "expected_refs": ["models.py", "Response", "raise_for_status", "HTTPError", "status_code"]
    }
]

RESULTS_PATH = os.path.join("eval", "requests_results.json")

def run_requests_eval():
    from archaeologist.mcp_server.tools import ask_tool
    from archaeologist.utils.gemini_client import GeminiClientWrapper
    
    gemini = GeminiClientWrapper()
    scores = []
    precision_scores = []
    detailed_results = []

    print("\n" + "=" * 90, flush=True)
    print("RUNNING BENCHMARK EVALUATION ON FAMOUS OPEN-SOURCE REPO: psf/requests", flush=True)
    print("=" * 90, flush=True)
    print(f"{'Question':<55} | {'Grounded Acc':<12} | {'Citation Prec':<12}", flush=True)
    print("-" * 90, flush=True)

    for item in REQUESTS_QA_PAIRS:
        q = item["question"]
        expected = item["expected_answer"]
        expected_refs = item["expected_refs"]

        # Run multi-hop reasoning agent
        generated = ask_tool(q)

        # Judge Grounded Accuracy using Gemini 3.5 Flash
        prompt = (
            "You are an expert evaluator scoring the accuracy of an agentic code analysis system.\n"
            "Evaluate whether the generated answer accurately conveys the key architectural facts of the expected answer for the psf/requests codebase.\n\n"
            f"Question: {q}\n"
            f"Expected Answer: {expected}\n"
            f"Generated Answer: {generated}\n\n"
            "Score the answer on a scale from 0 to 10 (where 10 is perfectly accurate and 0 is wrong/hallucinated).\n"
            "Respond ONLY with a single JSON object with fields:\n"
            "- score: integer between 0 and 10\n"
            "- reasoning: string explaining your score\n\n"
            "Output ONLY the JSON object. Do not include markdown code block formatting."
        )

        try:
            eval_res = gemini.generate_json(prompt=prompt, model="gemini-3.5-flash")
            acc_score = float(eval_res.get("score", 0)) / 10.0
        except Exception as e:
            print(f"Error in judge evaluation: {e}", flush=True)
            acc_score = 0.0

        scores.append(acc_score)

        # Calculate Citation Precision
        gen_lower = generated.lower()
        matches = sum(1 for ref in expected_refs if ref.lower() in gen_lower)
        prec_score = float(matches) / len(expected_refs) if expected_refs else 0.0
        precision_scores.append(prec_score)

        detailed_results.append({
            "id": item["id"],
            "question": q,
            "expected_answer": expected,
            "generated_answer": generated,
            "grounded_accuracy": acc_score,
            "citation_precision": prec_score
        })

        q_trunc = q[:52] + "..." if len(q) > 55 else q
        print(f"{q_trunc:<55} | {acc_score:<12.2%} | {prec_score:<12.2%}", flush=True)

    avg_acc = sum(scores) / len(scores) if scores else 0.0
    avg_prec = sum(precision_scores) / len(precision_scores) if precision_scores else 0.0

    print("-" * 90, flush=True)
    print(f"{'AVERAGE SUMMARY (psf/requests Benchmark)':<55} | {avg_acc:<12.2%} | {avg_prec:<12.2%}", flush=True)
    print("-" * 90, flush=True)

    summary = {
        "repository": "psf/requests",
        "total_questions": len(REQUESTS_QA_PAIRS),
        "average_grounded_accuracy": avg_acc,
        "average_citation_precision": avg_prec,
        "results": detailed_results
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved evaluation benchmark results to {RESULTS_PATH}", flush=True)

if __name__ == "__main__":
    run_requests_eval()
