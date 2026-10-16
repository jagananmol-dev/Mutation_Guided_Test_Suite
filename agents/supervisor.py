"""LLM-led supervisor. Code defines legal destinations; the LLM chooses among them."""
from __future__ import annotations
from core.llm import ask_json
from agents.util import traced, error_update


def legal_actions(state: dict) -> list[str]:
    """Return actions that are valid at the current state, not the next action itself."""
    if not state.get("source_code") or (state.get("analysis") or {}).get("error"):
        return ["reporter"]
    if not state.get("analysis"):
        return ["code_analyst"]
    if not state.get("edge_cases") and not state.get("generated_tests"):
        return ["adversary", "test_writer"]
    if not state.get("generated_tests"):
        return ["test_writer"]
    pytest_result = state.get("pytest_result") or {}
    max_rounds = int(state.get("max_rounds", 3))
    revisions = int(state.get("revision_count", 0))
    if not pytest_result.get("passed"):
        return ["test_writer", "reporter"] if revisions < max_rounds else ["reporter"]
    mutation = state.get("mutation_result") or {}
    if mutation:
        if mutation.get("status") in ("error", "timeout", "baseline_failed"):
            return ["run_mutations", "reporter"] if int(state.get("mutation_attempts", 0)) < 2 else ["reporter"]
        if not state.get("mutation_analysis"):
            return ["mutation_analyst"]
        gaps = state.get("mutation_analysis", {}).get("genuine_gaps", [])
        if gaps and int(state.get("round_index", 0)) < max_rounds and not state.get("needs_regeneration"):
            return ["adversary", "reporter"]
        if state.get("needs_regeneration"):
            return ["test_writer"]
        return ["reporter"]
    critic = state.get("critic_review") or {}
    complexity = (state.get("analysis") or {}).get("ast", {}).get("decision_complexity_estimate", 99)
    if not critic:
        # On trivial functions the supervisor may elect to skip the critic and test mutants directly.
        return ["test_critic", "run_mutations"] if complexity <= 2 else ["test_critic"]
    if not critic.get("approved"):
        return ["test_writer", "reporter"] if revisions < max_rounds else ["run_mutations", "reporter"]
    return ["run_mutations", "reporter"]


def _offline_choice(state: dict, actions: list[str]) -> tuple[str, str]:
    # Explicit offline behavior for tests without an API key; live demos should use LLM decisions.
    preference = ["code_analyst", "adversary", "test_writer", "test_critic", "run_mutations",
                  "mutation_analyst", "reporter"]
    choice = next((name for name in preference if name in actions), actions[0])
    return choice, "Offline fallback selected the first safe action in its priority order; configure OPENAI_API_KEY for agentic routing."


def supervisor(state: dict) -> dict:
    actions = legal_actions(state)
    prompt = f"""You are the Supervisor agent coordinating specialized test-generation agents.
Select the best NEXT action from the allowed list. You are allowed to choose a non-obvious action if it is valid.
Use the shared blackboard to adapt, ask the critic for revisions when useful, send survivors to the adversary,
and stop through `reporter` when additional work has low value or round limits are reached.
Return JSON keys: next_action (must exactly match one allowed action), rationale (specific evidence from state),
replan (boolean).
Allowed actions: {actions}
Current state summary: { {
  'analysis_ready': bool(state.get('analysis')),
  'edge_case_count': len(state.get('edge_cases', [])),
  'tests_ready': bool(state.get('generated_tests')),
  'pytest': (state.get('pytest_result') or {}).get('status'),
  'critic': (state.get('critic_review') or {}).get('approved'),
  'mutations': (state.get('mutation_result') or {}).get('status'),
  'survivors': (state.get('mutation_result') or {}).get('survived', []),
  'mutation_analysis': state.get('mutation_analysis', {}),
  'round': state.get('round_index', 0), 'max_rounds': state.get('max_rounds', 3),
  'errors': state.get('errors', [])[-3:],
} }
"""
    response = ask_json("You are a genuinely decision-making supervisor, not a fixed workflow router.", prompt, max_tokens=900)
    llm_used = response is not None and not response.get("_llm_error")
    if llm_used and response.get("next_action") in actions:
        choice = response["next_action"]
        reason = str(response.get("rationale", "No rationale returned."))
    else:
        choice, reason = _offline_choice(state, actions)
        if response and response.get("_llm_error"):
            # Keep the failure visible in both the real trace and shared state.
            updates = error_update(state, "supervisor", response["_llm_error"])
        else:
            updates = {}
        event_updates = traced(state, "supervisor", "routing_decision",
                               {"allowed_actions": actions, "selected_action": choice, "rationale": reason,
                                "llm_used": False, "replan": True})
        merged = {**updates, **event_updates, "allowed_actions": actions,
                  "next_action": choice, "decision_reason": reason}
        merged["trace_events"] = updates.get("trace_events", []) + event_updates.get("trace_events", [])
        merged["errors"] = updates.get("errors", [])
        return merged
    return traced(state, "supervisor", "routing_decision",
                  {"allowed_actions": actions, "selected_action": choice, "rationale": reason,
                   "llm_used": True, "replan": bool(response.get("replan", False))},
                  {"allowed_actions": actions, "next_action": choice, "decision_reason": reason})
