from agents.supervisor import legal_actions


def test_supervisor_starts_with_analyst():
    state = {"source_code": "def f(): return 1"}
    assert legal_actions(state) == ["code_analyst"]


def test_supervisor_sends_survivors_to_mutation_analyst():
    state = {
        "source_code": "def f(): return 1",
        "analysis": {"ast": {"decision_complexity_estimate": 2}},
        "generated_tests": "def test_f(): assert f() == 1",
        "pytest_result": {"passed": True, "status": "passed"},
        "mutation_result": {"status": "completed", "survived": ["line 1 + -> -"]},
        "critic_review": {"approved": True},
        "mutation_analysis": {},
    }
    assert legal_actions(state) == ["mutation_analyst"]


def test_supervisor_sends_real_gaps_to_adversary():
    state = {
        "source_code": "def f(x): return x + 1",
        "analysis": {"ast": {"decision_complexity_estimate": 2}},
        "generated_tests": "def test_f(): assert f(1) == 2",
        "pytest_result": {"passed": True, "status": "passed"},
        "mutation_result": {"status": "completed", "survived": ["line 1 + -> -"]},
        "mutation_analysis": {"genuine_gaps": ["line 1 + -> -"]},
        "round_index": 1, "max_rounds": 3,
    }
    assert legal_actions(state) == ["adversary", "reporter"]


def test_supervisor_can_retry_after_mutmut_failure():
    state = {
        "source_code": "def f(x): return x + 1",
        "analysis": {"ast": {"decision_complexity_estimate": 2}},
        "generated_tests": "def test_f(): assert f(1) == 2",
        "pytest_result": {"passed": True, "status": "passed"},
        "critic_review": {"approved": True},
        "mutation_result": {"status": "error", "engine": "mutmut", "fallback_reason": "timed out"},
        "mutation_attempts": 1,
    }
    assert legal_actions(state) == ["run_mutations", "reporter"]
