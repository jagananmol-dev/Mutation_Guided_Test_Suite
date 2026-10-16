from __future__ import annotations
from typing import Any
from core.llm import ask_json
from agents.util import traced, error_update


def adversary(state: dict[str, Any]) -> dict[str, Any]:
    try:
        mutation_analysis = state.get("mutation_analysis") or {}
        prompt = f"""Choose high-value inputs and edge cases for pytest tests for the function below.
Prioritize uncovered branches and any surviving mutants classified as genuine gaps. Avoid duplicate cases.
Return JSON: {{"edge_cases":[{{"id":"EC-1","category":"boundary|type|exception|branch|mutation_gap|other",
"description":"...","input_idea":"...","expected_behavior":"...","priority":"high|medium|low",
"targets_mutants":["..." ]}}],"reasoning":"..."}}. Keep the list to 3-8 cases and do not fabricate exact expected outputs when behavior is unclear.

AST/behavior analysis: {state.get('analysis', {})}
Prior cases: {state.get('edge_cases', [])}
Mutation analysis: {mutation_analysis}
Measured coverage: {(state.get('pytest_result') or {}).get('coverage', {})}
Prioritize concrete uncovered line/branch targets and survivor-triggering inputs.
Mutation survivors: {(state.get('mutation_result') or {}).get('survived', [])}
Source:
```python
{state['source_code']}
```"""
        result = ask_json("You are the Adversary agent: actively search for inputs that expose plausible faults.", prompt)
        if result and result.get("_llm_error"):
            return {**error_update(state, "adversary", result["_llm_error"]),
                    **traced(state, "adversary", "edge_case_fallback", {"reason": "LLM request failed"},
                             {"edge_cases": state.get("edge_cases", [])})}
        proposed = result.get("edge_cases", []) if result else []
        if not proposed:
            ast_info = (state.get("analysis") or {}).get("ast", {})
            params = ast_info.get("parameters", [])
            proposed = [
                {"id": "EC-boundary-1", "category": "boundary", "description": "Exercise boundary values around each comparison.",
                 "input_idea": f"Try boundary inputs for parameters {params}.", "expected_behavior": "Follow the implemented comparison and return path.", "priority": "high", "targets_mutants": []},
                {"id": "EC-empty-1", "category": "type", "description": "Check empty strings or collections where applicable.",
                 "input_idea": "Try an empty string/list/dict for compatible parameters.", "expected_behavior": "Return the function's documented or implied result, or raise the intended exception.", "priority": "medium", "targets_mutants": []},
            ]
            # The local fallback is a smoke-test aid, not an LLM-generated decision.
        existing = state.get("edge_cases", [])
        seen = {item.get("description") for item in existing}
        additions = [item for item in proposed if item.get("description") not in seen]
        combined = existing + additions
        return traced(state, "adversary", "edge_cases_proposed",
                      {"added": len(additions), "total": len(combined), "llm_used": result is not None,
                       "targeted_survivors": len((mutation_analysis.get("genuine_gaps") or []))},
                      {"edge_cases": combined, "needs_regeneration": bool(state.get("mutation_analysis"))})
    except Exception as exc:
        return {**error_update(state, "adversary", f"{type(exc).__name__}: {exc}"), "edge_cases": state.get("edge_cases", [])}
