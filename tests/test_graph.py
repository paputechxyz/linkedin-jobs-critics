"""Topology smoke test for the LangGraph judge→fix→re-judge loop.

Locks in the expected node set + terminal routing so refactors that break the
control flow fail fast. Behavior coverage lives in test_cli.py.
"""

from critics import graph


def test_graph_has_all_nodes():
    g = graph.build_graph()
    nodes = set(g.get_graph().nodes.keys())
    expected = {
        "__start__",
        "load_job",
        "judge",
        "gate",
        "pre_check",
        "run_agent",
        "post_check",
        "rescore",
    }
    assert expected.issubset(nodes), f"missing nodes: {expected - nodes}"


def test_graph_node_signatures():
    """Every node is a callable taking LoopState and returning a dict patch."""
    for name in ("load_job", "judge", "gate", "pre_check", "run_agent", "post_check", "rescore"):
        assert hasattr(graph, name), f"missing node fn: {name}"
        assert callable(getattr(graph, name))


def test_route_by_rc():
    assert graph._route_by_rc({"rc": 0}, "gate") == "__end__"
    assert graph._route_by_rc({"rc": 1}, "gate") == "__end__"
    assert graph._route_by_rc({}, "gate") == "gate"
    assert graph._route_by_rc({"report": object()}, "pre_check") == "pre_check"
