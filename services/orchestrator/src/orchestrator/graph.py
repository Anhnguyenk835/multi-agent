from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.nodes import (
    WorkflowNodes,
    route_after_analyst,
    route_after_market_intelligence,
    route_after_writer,
)
from orchestrator.state import WorkflowState


def build_workflow_graph(
    nodes: WorkflowNodes,
    checkpointer: BaseCheckpointSaver | None = None,
):
    builder = StateGraph(WorkflowState)
    builder.add_node("call_market_analyst", nodes.call_market_analyst)
    builder.add_node("call_competitor_analyst", nodes.call_competitor_analyst)
    builder.add_node("join_market_intelligence", nodes.join_market_intelligence)
    builder.add_node("call_analyst", nodes.call_analyst)
    builder.add_node("call_writer", nodes.call_writer)
    builder.add_node("finalize_success", nodes.finalize_success)
    builder.add_node("finalize_failure", nodes.finalize_failure)

    builder.add_edge(START, "call_market_analyst")
    builder.add_edge(START, "call_competitor_analyst")
    builder.add_edge(
        ["call_market_analyst", "call_competitor_analyst"],
        "join_market_intelligence",
    )
    builder.add_conditional_edges(
        "join_market_intelligence",
        route_after_market_intelligence,
        {"analyst": "call_analyst", "failure": "finalize_failure"},
    )
    builder.add_conditional_edges(
        "call_analyst",
        route_after_analyst,
        {"writer": "call_writer", "failure": "finalize_failure"},
    )
    builder.add_conditional_edges(
        "call_writer",
        route_after_writer,
        {"success": "finalize_success", "failure": "finalize_failure"},
    )
    builder.add_edge("finalize_success", END)
    builder.add_edge("finalize_failure", END)
    return builder.compile(checkpointer=checkpointer)
