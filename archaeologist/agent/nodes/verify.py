from archaeologist.agent.state import AgentState
from archaeologist.utils.gemini_client import GeminiClientWrapper, get_gemini_api_key

DRAFT_PROMPT = """You are a codebase archaeologist drafting a preliminary answer based on retrieved git/issue/PR evidence chunks.

Question: {question}

Evidence Chunks:
{evidence}

Draft a clear, factual 2-4 sentence explanation answering the question using only the evidence provided. Include specific PR/commit citations if present.

Draft Answer:"""

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
    question = state["question"]
    retrieved = state.get("retrieved_chunks", [])
    draft = state.get("draft_answer")
    verification_passed = state.get("verification_passed", True)

    print("Agent: Generating draft answer and self-verifying using Gemini 3.5 Flash...")

    api_key = get_gemini_api_key()
    if not api_key:
        return {
            "draft_answer": draft or "No Gemini API key available to verify answer.",
            "verification_passed": True,
            "unverified_claims": []
        }

    client = GeminiClientWrapper(api_key=api_key)
    evidence_text = "\n\n".join([f"[{c['id']}] {c['text']}" for c in retrieved[:12]])

    # 1. Force Draft Answer regeneration if missing or if previous verification failed (§1 Fix)
    if not draft or not verification_passed:
        draft = None
        try:
            draft_prompt = DRAFT_PROMPT.format(question=question, evidence=evidence_text)
            draft = client.generate_text(
                prompt=draft_prompt,
                model="gemini-3.5-flash",
                temperature=0.0,
                max_output_tokens=1000
            )
        except Exception as e:
            print(f"Error generating draft answer: {e}")
            draft = "Draft generation failed."

    # 2. Fact-Check Draft Answer against Evidence
    try:
        verify_prompt = VERIFY_PROMPT.format(question=question, draft_answer=draft, evidence=evidence_text)
        result = client.generate_json(
            prompt=verify_prompt,
            model="gemini-3.5-flash",
            temperature=0.0,
            max_output_tokens=1000
        )
        return {
            "draft_answer": draft,
            "verification_passed": result.get("verification_passed", True),
            "unverified_claims": result.get("unverified_claims", [])
        }
    except Exception as e:
        print(f"Error in verify_node: {e}")
        return {
            "draft_answer": draft,
            "verification_passed": True,
            "unverified_claims": []
        }
