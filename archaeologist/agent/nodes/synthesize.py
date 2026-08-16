import sys
from archaeologist.agent.state import AgentState
from archaeologist.utils.gemini_client import GeminiClientWrapper, get_gemini_api_key

SYNTHESIZE_PROMPT = """You are Codebase Archaeologist, an expert AI assistant that mines git commit history, pull requests, issues, and reverts to answer causal questions about code ("why does this exist", "what broke last time this was touched").

Synthesize a clear, accurate, and structured final answer based on the verified draft and historical evidence.

User Question: {question}
Verified Draft Answer: {draft_answer}

Retrieved Evidence Chunks:
{evidence}

Guidelines:
1. Provide a direct, causal answer explaining WHY the code exists or changed in its current form.
2. MANDATORY PR/ISSUE CITATIONS: You MUST explicitly cite all relevant Pull Requests (e.g. PR #123, #456), linked Issues (e.g. Issue #789), commit SHAs, and authors present in the evidence.
3. Dedicated References Section: If linked PRs or Issues are present in the evidence, you MUST include a dedicated section titled "### Historical PRs & Linked Issues" explicitly listing each PR/Issue number, author, and summary.
4. Highlight any revert history, bug fixes, or key discussions discovered in the trace.
5. Keep the tone professional, concise, and technically precise.

Causal Archaeology Answer:"""

def synthesize_node(state: AgentState) -> dict:
    question = state["question"]
    draft = state.get("draft_answer", "")
    retrieved = state.get("retrieved_chunks", [])
    
    print("Agent: Synthesizing final answer using Gemini 3.5 Flash...", file=sys.stderr)

    api_key = get_gemini_api_key()
    if not api_key:
        return {"response": draft or "Gemini API key missing."}

    try:
        client = GeminiClientWrapper(api_key=api_key)
        evidence_lines = []
        for c in retrieved[:20]:
            rel_ids = c.get("related_ids", [])
            rel_str = f" | Linked PRs/Issues: {rel_ids}" if rel_ids else ""
            evidence_lines.append(f"Source: {c.get('source_type', 'commit')} ({c.get('source_id', '')}){rel_str}\nText: {c.get('text', '')}")
        evidence_text = "\n\n".join(evidence_lines)

        prompt = SYNTHESIZE_PROMPT.format(question=question, draft_answer=draft, evidence=evidence_text)
        
        response_text = client.generate_text(
            prompt=prompt,
            model="gemini-3.5-flash",
            temperature=0.0,
            max_output_tokens=3000
        )
        return {"response": response_text or draft}
    except Exception as e:
        print(f"Error in synthesize_node: {e}", file=sys.stderr)
        return {"response": draft or f"Error synthesizing response: {e}"}


