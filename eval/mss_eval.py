import json
import os
import sys
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# Ground-truth causal ("why") eval set for BoboTiG/python-mss
#
# Repo chosen deliberately: cross-platform screenshot capture library,
# ~1,050 commits, real PR/issue culture, MIT licensed, and — critically —
# niche/specific enough a domain that it should NOT be heavily represented
# in an LLM's pretrained knowledge the way Flask/httpx are. Every fact below
# was pulled directly from `git log`/`git show` against a real clone of the
# repo and cross-checked; nothing here is invented or paraphrased from
# general software-engineering intuition.
#
# BEFORE running this against the real agent: run each question through a
# tool-less/search-less LLM call cold (no repo access) and compare the blind
# answer to `expected_answer`. If the blind answer gets close, the question
# is contaminated (too guessable) and should be dropped or sharpened before
# it's trusted as a real test. A `blind_test_notes` field is included per
# question with my own read on guessability — treat it as a starting
# hypothesis to verify, not a substitute for actually running the check.
# ============================================================================

MSS_QA_PAIRS = [
    {
        "id": 1,
        "question": (
            "The Windows capture backend once cached the region being grabbed for performance. "
            "A fix was written to correct a bug where two same-size regions at different screen "
            "positions could return a wrong/stale screenshot. That fix was reverted just days "
            "later. Why was it reverted, and what happened to the test that was added alongside it?"
        ),
        "expected_answer": (
            "The original bug (commit 5e5f3ee) was that the Windows GDI backend's region cache "
            "compared only (height, width) when deciding whether to reallocate the cached bitmap, "
            "so two regions of the same size but different (top, left) position incorrectly reused "
            "a stale bitmap sized correctly but positioned wrong. The fix changed the check to "
            "compare the full region dict instead of just height/width, and added a regression "
            "test (test_region_caching) asserting the cache updates when position changes. Three "
            "days later this fix was reverted (commit 2d24115) with the message 'The patch was "
            "indeed a bad idea and fixed nothing' — the author reverted the actual code change but "
            "explicitly kept the added test in place rather than removing it."
        ),
        "expected_evidence": [
            "5e5f3eecc87660b73d11c4c964571f1515c09531",
            "2d24115320534460c9f5f510c429dd36f838d457",
        ],
        "difficulty": "hard",
        "blind_test_notes": (
            "High confidence this is not guessable: requires knowing the exact revert happened, "
            "that it was 3 days after the original fix, that the fix looked correct (passing test) "
            "but 'fixed nothing', and the specific detail that the test was kept despite the code "
            "being reverted. No general GDI/screenshot-caching knowledge would produce this."
        ),
    },
    {
        "id": 2,
        "question": (
            "This library moved from a single global thread lock protecting all internal state to "
            "per-object locking. What was the stated reason for the change, and which specific "
            "backend still needed to keep a global (not per-object) lock, and why?"
        ),
        "expected_answer": (
            "PR #452 (commit 06dc845) replaced a single global lock with per-object locks, stating "
            "the global lock 'provides too much of a surface for contention and deadlocks.' The "
            "Xlib backend specifically was called out as still needing global locking, because "
            "Xlib itself is not thread-safe and the library wasn't enabling the (partial) "
            "thread-safety features Xlib offers, so Xlib kept its own dedicated lock object "
            "separate from the new per-object scheme used elsewhere."
        ),
        "expected_evidence": ["06dc84550512de2edef633019c849ea48b11b39a"],
        "difficulty": "medium",
        "blind_test_notes": (
            "Medium-high confidence: a model might guess 'global locks cause contention, so they "
            "moved to finer-grained locking' as a generic pattern, but the specific carve-out for "
            "Xlib being non-thread-safe and needing to retain a global lock is a repo-specific "
            "detail unlikely to be guessed correctly."
        ),
    },
    {
        "id": 3,
        "question": (
            "A fix for a KeyboardInterrupt-related bug during buffer copying in one of the Linux "
            "capture backends was itself reworked shortly after being merged. What was the original "
            "bug, and what specifically changed in the follow-up?"
        ),
        "expected_answer": (
            "In the XShmGetImage backend, there was a window during buffer copying where a "
            "KeyboardInterrupt (or other async exception) hitting mid-copy would cause cleanup to "
            "raise a different, confusing exception instead of letting the original KeyboardInterrupt "
            "propagate to the user (PR #467, commit 0822b33). The stated goal was not full "
            "correctness under async exceptions, just avoiding a misleading secondary exception. "
            "The follow-up (PR #468, commit 9637209) reworked the fix after the author 'just learned "
            "that memoryviews can be used as context managers' and release their buffers automatically "
            "at the end of a `with` block, replacing the original approach with this simpler pattern."
        ),
        "expected_evidence": ["0822b334a90193a297f8b31158df061ba16acb11", "9637209"],
        "difficulty": "hard",
        "blind_test_notes": (
            "High confidence: the specific detail that the second PR's motivation was the author "
            "personally learning about memoryview context-manager semantics, rather than a bug in "
            "the first fix, is a very specific, personal, undocumented-elsewhere detail that general "
            "knowledge of Python or screenshot libraries would not produce."
        ),
    },
    {
        "id": 4,
        "question": (
            "The library's internal architecture was reworked so users always interact with a single "
            "top-level class regardless of platform, hiding the previous per-platform class "
            "hierarchy. What issue motivated this, and what specifically got deprecated as a result?"
        ),
        "expected_answer": (
            "PR #494 (commit 8a7bbc2) moved the library to a strategy-pattern design, citing issue "
            "#486 as the motivation. The change hides platform/capture-strategy differences behind "
            "a single mss.MSS class rather than exposing different implementation classes per "
            "platform, so internal class hierarchies could change freely without breaking user code. "
            "This deprecated both the existing `mss` factory function and the per-platform "
            "`mss.{platform}.MSS` types, with a stated plan to keep the factory function available "
            "for a transition period while deprecated functionality emits DeprecationWarnings."
        ),
        "expected_evidence": ["8a7bbc238c09b52ca1091915293099afeceea7d6", "issue#486"],
        "difficulty": "medium",
        "blind_test_notes": (
            "Medium confidence: 'moved to strategy pattern for extensibility' is a somewhat guessable "
            "generic architecture narrative, but the specific linked issue number and the precise "
            "two things deprecated (the factory function AND the per-platform types) are specific "
            "enough that a blind guess is unlikely to get both right."
        ),
    },
    {
        "id": 5,
        "question": (
            "There are two different low-level backends for capturing screenshots on Linux via X11 "
            "— one based on XCB and one using the MIT-SHM shared-memory extension. Why does the "
            "second one exist given the first one already worked, and what performance difference "
            "was reported at the time it was introduced?"
        ),
        "expected_answer": (
            "PR #426 (commit 8575606) first added an XCB-based backend named 'getimage' as a "
            "replacement path for the older Xlib implementation, which was explicitly designated "
            "'legacy' status per issue #425 (new functionality like XShmGetImage would not be "
            "added to the Xlib backend going forward). PR #431 (commit 712503a) then added the "
            "XShmGetImage-based backend using the X MIT-SHM extension for shared-memory transfer. "
            "The PR description reports a concrete benchmark from the author's own machine: the new "
            "shared-memory backend achieved 30-34 fps capturing 4k screenshots, versus 11-14 fps for "
            "the existing XGetImage-based approach — roughly a 3x throughput improvement."
        ),
        "expected_evidence": [
            "8575606",
            "712503a",
            "issue#425",
        ],
        "difficulty": "hard",
        "blind_test_notes": (
            "High confidence: the specific FPS numbers (30-34 vs 11-14) and the framing that Xlib "
            "was designated legacy 'per issue #425' are precise, sourced facts that general "
            "knowledge of X11/screenshot libraries would not reproduce, even though 'shared memory "
            "is faster than round-tripping image data' is a guessable general principle on its own."
        ),
    },
]

RESULTS_PATH = os.path.join("eval", "mss_results.json")


def run_mss_eval():
    from archaeologist.mcp_server.tools import ask_tool
    from archaeologist.utils.gemini_client import GeminiClientWrapper

    gemini = GeminiClientWrapper()
    scores = []
    precision_scores = []
    detailed_results = []

    print("\n" + "=" * 90, flush=True)
    print("RUNNING GROUND-TRUTH CAUSAL ('WHY') BENCHMARK ON: BoboTiG/python-mss", flush=True)
    print("=" * 90, flush=True)
    print(f"{'Question':<55} | {'Grounded Acc':<12} | {'Citation Prec':<12}", flush=True)
    print("-" * 90, flush=True)

    for item in MSS_QA_PAIRS:
        q = item["question"]
        expected = item["expected_answer"]
        expected_refs = item["expected_evidence"]

        generated = ask_tool(q)

        # NOTE: unlike the httpx/flask eval scripts, judge with a DIFFERENT
        # model family than the one the agent itself runs on, to avoid the
        # same-family self-judging bias flagged in review. Swap this for a
        # Claude or GPT call if available; using Gemini here only as a
        # placeholder if no other judge is configured.
        prompt = (
            "You are an expert evaluator scoring whether a generated answer about a specific "
            "open-source repository's git/PR/issue history matches the verified ground truth. "
            "Score strictly: generic, plausible-sounding reasoning that doesn't match the SPECIFIC "
            "facts in the expected answer (exact PR/issue numbers, specific reverts, specific "
            "quoted reasoning, specific benchmark numbers) should NOT score highly, even if it "
            "sounds reasonable.\n\n"
            f"Question: {q}\n"
            f"Expected Answer (verified ground truth): {expected}\n"
            f"Generated Answer: {generated}\n\n"
            "Score 0-10. Respond ONLY with JSON: {\"score\": int, \"reasoning\": str}"
        )

        acc_score = 0.0
        for attempt in range(3):
            try:
                eval_res = gemini.generate_json(prompt=prompt, model="gemini-3.5-flash")
                acc_score = float(eval_res.get("score", 0)) / 10.0
                break
            except Exception as e:
                print(f"Error in judge evaluation (attempt {attempt + 1}/3): {e}", flush=True)
                import time
                time.sleep(3.0)

        scores.append(acc_score)

        # Citation precision against REAL evidence IDs (commit SHAs / issue
        # numbers), not filenames or terms already present in the question.
        gen_lower = generated.lower()
        matches = sum(1 for ref in expected_refs if ref.lower()[:10] in gen_lower)
        prec_score = float(matches) / len(expected_refs) if expected_refs else 0.0
        precision_scores.append(prec_score)

        detailed_results.append({
            "id": item["id"],
            "question": q,
            "expected_answer": expected,
            "generated_answer": generated,
            "expected_evidence": expected_refs,
            "difficulty": item["difficulty"],
            "blind_test_notes": item["blind_test_notes"],
            "grounded_accuracy": acc_score,
            "citation_precision": prec_score,
        })

        q_trunc = q[:52] + "..." if len(q) > 55 else q
        print(f"{q_trunc:<55} | {acc_score:<12.2%} | {prec_score:<12.2%}", flush=True)

    avg_acc = sum(scores) / len(scores) if scores else 0.0
    avg_prec = sum(precision_scores) / len(precision_scores) if precision_scores else 0.0

    print("-" * 90, flush=True)
    print(f"{'AVERAGE SUMMARY (python-mss Ground-Truth Benchmark)':<55} | {avg_acc:<12.2%} | {avg_prec:<12.2%}", flush=True)
    print("-" * 90, flush=True)

    summary = {
        "repository": "BoboTiG/python-mss",
        "eval_type": "ground_truth_causal_why",
        "total_questions": len(MSS_QA_PAIRS),
        "average_grounded_accuracy": avg_acc,
        "average_citation_precision": avg_prec,
        "results": detailed_results,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved evaluation benchmark results to {RESULTS_PATH}", flush=True)


if __name__ == "__main__":
    run_mss_eval()
