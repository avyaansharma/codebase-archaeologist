import json
import os
import re
import sys
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

FLASK_QA_PAIRS = [
    {
        "id": 1,
        "question": "How does Flask handle request context and application context isolation using ContextVar / LocalProxy in src/flask/globals.py and src/flask/ctx.py?",
        "expected_answer": "Flask uses ContextVar inside globals.py (_cv_app and _cv_request) to isolate AppContext and RequestContext instances per thread or async task. Access to current_app, g, request, and session is proxied through LocalProxy instances that dynamically resolve the active context.",
        "expected_refs": ["globals.py", "ctx.py", "LocalProxy", "ContextVar"]
    },
    {
        "id": 2,
        "question": "How does Flask's Blueprint routing defer view function registration until application initialization?",
        "expected_answer": "Blueprint records route definitions and setup callbacks via Blueprint.record() or BlueprintSetupState. When app.register_blueprint() is called, Flask iterates through all recorded state functions and executes them against the application instance.",
        "expected_refs": ["blueprints.py", "register_blueprint", "record", "BlueprintSetupState"]
    },
    {
        "id": 3,
        "question": "How does Flask process error handling hierarchy between app-level error handlers and blueprint-level error handlers in src/flask/app.py?",
        "expected_answer": "Flask maintains app.error_handler_spec dictionary where global errorhandlers use None as key and blueprint errorhandlers use the blueprint name. When handle_user_exception handles an error, it checks blueprint-specific handlers first before falling back to global handlers.",
        "expected_refs": ["app.py", "error_handler_spec", "handle_user_exception", "errorhandler"]
    },
    {
        "id": 4,
        "question": "How does Flask integrate with Click in src/flask/cli.py to create CLI command groups and locate application instances?",
        "expected_answer": "FlaskGroup and AppGroup in src/flask/cli.py extend click.Group. ScriptInfo uses find_best_app() to locate and import the target Flask application instance before executing Click CLI commands.",
        "expected_refs": ["cli.py", "FlaskGroup", "AppGroup", "ScriptInfo", "find_best_app"]
    },
    {
        "id": 5,
        "question": "How does SecureCookieSessionInterface in src/flask/sessions.py sign and validate session cookie data against tampering?",
        "expected_answer": "SecureCookieSessionInterface uses itsdangerous.URLSafeTimedSerializer with the application secret_key and cookie-session salt to serialize, cryptographic sign, and verify session cookie data.",
        "expected_refs": ["sessions.py", "SecureCookieSessionInterface", "URLSafeTimedSerializer", "secret_key"]
    },
    {
        "id": 6,
        "question": "How does full_dispatch_request in src/flask/app.py orchestrate the lifecycle of request hooks, dispatching, and response processing?",
        "expected_answer": "full_dispatch_request runs preprocess_request (before_request hooks) first. If no hook returns a response, it dispatches to dispatch_request (view function), converts the return value via make_response, and passes the response through process_response (after_request hooks).",
        "expected_refs": ["app.py", "full_dispatch_request", "preprocess_request", "dispatch_request", "process_response", "make_response"]
    }
]

RESULTS_PATH = os.path.join("eval", "flask_results.json")

def run_flask_eval():
    from archaeologist.mcp_server.tools import ask_tool
    from archaeologist.utils.gemini_client import GeminiClientWrapper
    
    gemini = GeminiClientWrapper()
    scores = []
    precision_scores = []
    detailed_results = []

    print("\n" + "=" * 90, flush=True)
    print("RUNNING BENCHMARK EVALUATION ON FAMOUS OPEN-SOURCE REPO: pallets/flask", flush=True)
    print("=" * 90, flush=True)
    print(f"{'Question':<55} | {'Grounded Acc':<12} | {'Citation Prec':<12}", flush=True)
    print("-" * 90, flush=True)

    for item in FLASK_QA_PAIRS:
        q = item["question"]
        expected = item["expected_answer"]
        expected_refs = item["expected_refs"]

        # Run multi-hop reasoning agent
        generated = ask_tool(q)

        # Judge Grounded Accuracy using Gemini 3.5 Flash
        prompt = (
            "You are an expert evaluator scoring the accuracy of an agentic code analysis system.\n"
            "Evaluate whether the generated answer accurately conveys the key architectural facts of the expected answer for the Flask codebase.\n\n"
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
    print(f"{'AVERAGE SUMMARY (pallets/flask Benchmark)':<55} | {avg_acc:<12.2%} | {avg_prec:<12.2%}", flush=True)
    print("-" * 90, flush=True)

    summary = {
        "repository": "pallets/flask",
        "total_questions": len(FLASK_QA_PAIRS),
        "average_grounded_accuracy": avg_acc,
        "average_citation_precision": avg_prec,
        "results": detailed_results
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved evaluation benchmark results to {RESULTS_PATH}", flush=True)

if __name__ == "__main__":
    run_flask_eval()
