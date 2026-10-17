from pr_time_machine.ast_analyzer import analyze_repository

FILES = {
    "app/__init__.py": "",
    "app/util.py": "RATE = 2\n\ndef helper(x):\n    return x * RATE\n\nclass Base:\n    def run(self):\n        return self.step()\n    def step(self):\n        return 1\n",
    "app/core.py": (
        "from . import util\nfrom .util import helper as h, Base\nimport app.util\n\n"
        "class Job(Base):\n    pass\n\n"
        "def a():\n    return h(1)\n\ndef b():\n    return util.helper(2)\n\n"
        "def c():\n    return app.util.helper(3)\n\ndef d():\n    return Job()\n\n"
        "def e(name):\n    return getattr(util, name)()\n\ndef f(obj):\n    return obj.helper(4)\n"
    ),
    "app/broken.py": "def oops(:\n",
}


def edges(analysis, kind=None):
    return {(e.source, e.target) for e in analysis.edges if kind is None or e.kind == kind}


def test_resolves_imports_aliases_and_relative_modules():
    calls = edges(analyze_repository(FILES), "call")
    for caller in ("app.core.a", "app.core.b", "app.core.c"):
        assert (caller, "app.util.helper") in calls


def test_self_method_instantiation_inheritance_and_variable_reference():
    analysis = analyze_repository(FILES)
    assert ("app.util.Base.run", "app.util.Base.step") in edges(analysis, "call")
    assert ("app.core.d", "app.core.Job") in edges(analysis, "instantiation")
    assert ("app.core.Job", "app.util.Base") in edges(analysis, "inheritance")
    assert ("app.util.helper", "app.util.RATE") in edges(analysis, "reference")


def test_dynamic_and_untyped_calls_are_recorded_as_unresolved_not_guessed():
    analysis = analyze_repository(FILES)
    reasons = {(u.caller, u.reason.split(";")[0]) for u in analysis.unresolved}
    assert any(c == "app.core.e" for c, _ in reasons)
    assert any(c == "app.core.f" for c, _ in reasons)
    assert ("app.core.f", "app.util.helper") not in edges(analysis)


def test_syntax_errors_are_reported_and_do_not_stop_analysis():
    analysis = analyze_repository(FILES)
    assert "app/broken.py" in analysis.parse_errors
    assert "app.util.helper" in analysis.index
