from __future__ import annotations
from core.llm import ask_json
from agents.util import traced


def reporter(state: dict) -> dict:
    analysis = state.get("analysis") or {}
    ast_info = analysis.get("ast", {})
    pytest_result = state.get("pytest_result") or {}
    mutation = state.get("mutation_result") or {}
    mutation_analysis = state.get("mutation_analysis") or {}
    prompt = f"""Write a concise final report for a developer reviewing generated tests.
Be factual. Mention uncertainty or fallback behavior; do not claim a mutation score if unavailable.
Return JSON keys: headline, summary, strengths (list), remaining_gaps (list), next_steps (list).
Function: {ast_info.get('function_name')}
Pytest result: {pytest_result}
Critic review: {state.get('critic_review', {})}
Mutation result: {mutation}
Mutation analysis: {mutation_analysis}
Measured coverage: {(state.get('pytest_result') or {}).get('coverage', {})}
IMPORTANT: if engine is fallback_token, state that the score applies only to a reduced fallback mutation set, not full mutmut coverage. If mutmut was unsupported on Windows, explain WSL/Linux/Docker is needed for a full mutmut run.
Run errors: {state.get('errors', [])}
"""
    llm_report = ask_json("You are the Reporter agent. Summarize the run accurately and make uncertainty explicit.", prompt)
    if llm_report and llm_report.get("_llm_error"):
        llm_report = None
    if llm_report is None:
        coverage = pytest_result.get("coverage", {})
        coverage_gaps = list(mutation_analysis.get("coverage_gaps", []))
        remaining = (list(mutation_analysis.get("uncertain", [])) +
                     list(mutation_analysis.get("genuine_gaps", [])) + coverage_gaps)
        if coverage.get("status") == "collected":
            coverage_summary = (f" Statement coverage: {coverage.get('statement_percent')}%; "
                                f"branch coverage: {coverage.get('branch_percent')}%.")
        else:
            coverage_summary = " Coverage was unavailable or not collected."
        mutation_summary = (f"Mutation engine: {mutation.get('engine', 'not run')} ({mutation.get('status', 'not run')}).")
        if mutation.get("engine") == "fallback_token":
            mutation_summary += " The score covers only a reduced fallback mutation set, not full mutmut coverage."
        llm_report = {
            "headline": "Test generation run completed with caveats",
            "summary": (f"Function `{ast_info.get('function_name', 'unknown')}`: pytest status is "
                        f"{pytest_result.get('status', 'not run')}." + coverage_summary + " " + mutation_summary),
            "strengths": (["Generated tests executed in a subprocess."] if pytest_result.get("status") else []),
            "remaining_gaps": list(dict.fromkeys(remaining)),
            "next_steps": ["Review uncovered lines/branches and add targeted tests.",
                           "Run full mutmut under WSL/Linux/Docker for broader mutation coverage." if mutation.get("engine") == "fallback_token" else "Review generated tests and mutation output manually.",
                           "Configure the LLM API key for agent-driven reasoning and critic review."],
        }
    # Enforce objective caveats even if the language model omits them.
    coverage = pytest_result.get("coverage", {})
    deterministic_gaps = list(mutation_analysis.get("coverage_gaps", []))
    if isinstance(coverage, dict) and coverage.get("status") == "collected":
        deterministic_gaps.extend(f"uncovered source line {line}" for line in coverage.get("missing_lines", []))
        deterministic_gaps.extend(f"uncovered branch {branch}" for branch in coverage.get("missing_branches", []))
    if deterministic_gaps:
        llm_report["remaining_gaps"] = list(dict.fromkeys(list(llm_report.get("remaining_gaps", [])) + deterministic_gaps))
    if mutation.get("engine") == "fallback_token":
        caveat = "Mutation score applies only to the reduced fallback mutation set; it is not a full mutmut score."
        summary = str(llm_report.get("summary", ""))
        if caveat not in summary:
            llm_report["summary"] = (summary + " " + caveat).strip()
        next_steps = llm_report.get("next_steps", [])
        if not isinstance(next_steps, list):
            next_steps = []
        recommendation = "Run full mutmut under WSL/Linux/Docker for broader mutation coverage."
        if recommendation not in next_steps:
            next_steps.append(recommendation)
        llm_report["next_steps"] = next_steps
    if coverage.get("status") == "collected":
        coverage_note = (f"Measured coverage: {coverage.get('statement_percent')}% statements, "
                         f"{coverage.get('branch_percent')}% branches.")
        summary = str(llm_report.get("summary", ""))
        if coverage_note not in summary:
            llm_report["summary"] = (summary + " " + coverage_note).strip()
    report = {
        **llm_report,
        "run_id": state.get("run_id"),
        "function_name": ast_info.get("function_name", state.get("function_name")),
        "pytest": pytest_result,
        "critic": state.get("critic_review", {}),
        "mutation": mutation,
        "mutation_analysis": mutation_analysis,
        "revision_count": state.get("revision_count", 0),
        "round_index": state.get("round_index", 0),
        "errors": state.get("errors", []),
        "trace_path": state.get("trace_path", "trace.jsonl"),
    }
    return traced(state, "reporter", "final_report_created",
                  {"pytest_status": pytest_result.get("status"), "mutation_status": mutation.get("status"),
                   "rounds": state.get("round_index", 0)}, {"report": report})
