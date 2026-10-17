from pr_time_machine.ast_analyzer import Edge
from pr_time_machine.dependency_graph import DependencyGraph


def e(src, dst, kind="call"):
    return Edge(src, dst, kind, "f.py", 1, "resolved", "test")


def test_shortest_paths_and_depths():
    g = DependencyGraph([e("b", "a"), e("c", "b"), e("c", "a"), e("d", "c")])
    reached, truncated = g.reverse_reachable(["a"], max_depth=5, max_nodes=50)
    assert not truncated
    assert reached["c"].depth == 1 and reached["d"].depth == 2
    assert [x.source for x in reached["d"].path] == ["c", "d"]


def test_cycles_terminate():
    g = DependencyGraph([e("a", "b"), e("b", "a"), e("c", "a")])
    reached, _ = g.reverse_reachable(["a"], max_depth=10, max_nodes=50)
    assert set(reached) == {"a", "b", "c"}


def test_limits_and_import_edges_are_not_traversed():
    g = DependencyGraph([e("b", "a"), e("c", "b"), e("x", "a", kind="import")])
    reached, truncated = g.reverse_reachable(["a"], max_depth=1, max_nodes=50)
    assert set(reached) == {"a", "b"} and truncated
    _, truncated_nodes = g.reverse_reachable(["a"], max_depth=5, max_nodes=2)
    assert truncated_nodes
