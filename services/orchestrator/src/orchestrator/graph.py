from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.nodes import (
    WorkflowNodes,
    route_after_analyst,
    route_after_join,
    route_after_writer,
)
from orchestrator.state import WorkflowState


def build_workflow_graph(
    nodes: WorkflowNodes,
    checkpointer: BaseCheckpointSaver | None = None,
):
    builder = StateGraph(WorkflowState)
    builder.add_node("call_researcher", nodes.call_researcher)
    builder.add_node("call_market", nodes.call_market)
    builder.add_node("join_research", nodes.join_research)
    builder.add_node("call_analyst", nodes.call_analyst)
    builder.add_node("call_writer", nodes.call_writer)
    builder.add_node("finalize_success", nodes.finalize_success)
    builder.add_node("finalize_failure", nodes.finalize_failure)

    builder.add_edge(START, "call_researcher")
    builder.add_edge(START, "call_market")
    builder.add_edge(["call_researcher", "call_market"], "join_research")
    builder.add_conditional_edges(
        "join_research",
        route_after_join,
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
