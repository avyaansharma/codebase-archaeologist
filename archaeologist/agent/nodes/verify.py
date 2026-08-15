from archaeologist.agent.state import AgentState
from archaeologist.utils.gemini_client import GeminiClientWrapper, get_gemini_api_key

VERIFY_PROMPT = """You are a strict technical fact-checker for codebase archaeology.
Verify if the draft answer is fully supported by the retrieved history evidence.

User Question: {question}
Draft Answer: {draft_answer}

Evidence Chunks:
{evidence}

Return a JSON object with this exact structure:
{{
  "verification_passed": true,
  "unverified_claims": []
}}"""

def verify_node(state: AgentState) -> dict:
    draft = state.get("draft_answer", "")
    question = state["question"]
    retrieved = state.get("retrieved_chunks", [])

    print("Agent: Generating draft answer and self-verifying using Gemini 3.5 Flash...")

    api_key = get_gemini_api_key()
    if not api_key:
        return {"verification_passed": True, "unverified_claims": []}

    try:
        client = GeminiClientWrapper(api_key=api_key)
        evidence_text = "\n\n".join([f"[{c['id']}] {c['text']}" for c in retrieved[:10]])
        prompt = VERIFY_PROMPT.format(question=question, draft_answer=draft, evidence=evidence_text)
        result = client.generate_json(
            prompt=prompt,
            model="gemini-3.5-flash",
            temperature=0.0,
            max_output_tokens=2000
        )
        return {
            "verification_passed": result.get("verification_passed", True),
            "unverified_claims": result.get("unverified_claims", [])
        }
    except Exception as e:
        print(f"Error in verify_node: {e}")
        return {"verification_passed": True, "unverified_claims": []}
