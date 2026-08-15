from langgraph.graph import StateGraph, END
from archaeologist.agent.state import AgentState
from archaeologist.agent.nodes.decompose import decompose_node
from archaeologist.agent.nodes.plan import plan_node
from archaeologist.agent.nodes.search import search_node
from archaeologist.agent.nodes.follow_links import follow_links_node
from archaeologist.agent.nodes.verify import verify_node
from archaeologist.agent.nodes.synthesize import synthesize_node

def increment_retry_node(state: AgentState) -> dict:
    retries = state.get("retry_count", 0)
    print(f"Agent: Verification failed. Incrementing retry count to {retries + 1}...")
    return {"retry_count": retries + 1}

# Create the graph workflow
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("decompose", decompose_node)
workflow.add_node("plan", plan_node)
workflow.add_node("search", search_node)
workflow.add_node("follow_links", follow_links_node)
workflow.add_node("verify", verify_node)
workflow.add_node("increment_retry", increment_retry_node)
workflow.add_node("synthesize", synthesize_node)

# Set entry point
workflow.set_entry_point("decompose")

# Standard transitions
workflow.add_edge("decompose", "plan")
workflow.add_edge("plan", "search")
workflow.add_edge("search", "follow_links")
workflow.add_edge("follow_links", "verify")

# Conditional transitions from verification check
def verification_router(state: AgentState):
    if state.get("verification_passed", True):
        return "synthesize"
    
    retries = state.get("retry_count", 0)
    if retries >= 2:
        print("Agent: Verification failed after maximum retries. Proceeding to synthesis.")
        return "synthesize"
        
    return "retry"

workflow.add_conditional_edges(
    "verify",
    verification_router,
    {
        "synthesize": "synthesize",
        "retry": "increment_retry"
    }
)

workflow.add_edge("increment_retry", "plan")
workflow.add_edge("synthesize", END)

# Compile workflow
agent_graph = workflow.compile()
