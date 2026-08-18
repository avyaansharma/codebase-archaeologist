import sys
from archaeologist.agent.state import AgentState
from archaeologist.utils.gemini_client import GeminiClientWrapper, get_gemini_api_key

PLAN_PROMPT = """You are a codebase archaeologist planner.
Given the current sub-question, generate 2-3 targeted search queries to query the repository commit logs, pull requests, and issues.
MANDATORY: Keep queries concise (2-5 key terms), focusing on exact symbols, PR/Issue numbers, or core architectural concepts (e.g. "strategy pattern", "factory", "deprecated", "refactor") to maximize search recall.

Sub-question: {sub_question}

Return a JSON object with this exact structure:
{{
  "search_queries": [
    "query 1",
    "query 2"
  ]
}}"""

def plan_node(state: AgentState) -> dict:
    idx = state["current_sub_question_index"]
    sub_qs = state["sub_questions"]
    current_sub_q = sub_qs[idx] if idx < len(sub_qs) else state["question"]

    print(f"Agent: Planning retrieval using Gemini 3.5 Flash for sub-question: '{current_sub_q}'...", file=sys.stderr)

    api_key = get_gemini_api_key()
    if not api_key:
        return {"search_queries": [current_sub_q]}

    try:
        client = GeminiClientWrapper(api_key=api_key)
        prompt = PLAN_PROMPT.format(sub_question=current_sub_q)
        result = client.generate_json(
            prompt=prompt,
            model="gemini-3.5-flash",
            temperature=0.0,
            max_output_tokens=2000
        )
        queries = result.get("search_queries", [current_sub_q])
        return {"search_queries": queries if queries else [current_sub_q]}
    except Exception as e:
        print(f"Error in plan_node: {e}", file=sys.stderr)
        return {"search_queries": [current_sub_q]}

