(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const MAX_SOURCE_CHARS = 20000;
  const DEFAULT_CODE = `def clamp(value: float, lower: float, upper: float) -> float:
    """Return value restricted to the inclusive interval [lower, upper]."""
    if lower > upper:
        raise ValueError("lower must not exceed upper")
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value
`;
  const state = { tests: "", result: null, loadingTimer: null, loadingStep: 0, abortController: null };
  const loadingSteps = [
    ["Agents are analyzing your function", "Inspecting branches, parameters, and likely edge cases…"],
    ["Building an adversarial test plan", "Choosing boundary values and behaviors worth challenging…"],
    ["Generating and executing pytest cases", "Checking whether the generated test module runs against your code…"],
    ["Mutation testing in progress", "Trying modified operators to discover tests that are still missing…"],
    ["Reviewing surviving mutants", "The agents are consolidating results and recommendations…"]
  ];

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[char]));
  const pretty = (value) => JSON.stringify(value ?? {}, null, 2);
  const baseUrl = () => $("apiBase").value.trim().replace(/\/+$/, "");

  function setStatus(kind, text) {
    const el = $("runStatus");
    el.className = `status-pill ${kind}`;
    el.innerHTML = `<span></span>${escapeHtml(text)}`;
  }
  function setError(message) {
    const banner = $("errorBanner");
    banner.textContent = message;
    banner.hidden = !message;
  }
  function updateCharCount() {
    const length = $("sourceCode").value.length;
    $("charCount").textContent = `${length.toLocaleString()} / ${MAX_SOURCE_CHARS.toLocaleString()}`;
    $("charCount").classList.toggle("over-limit", length > MAX_SOURCE_CHARS);
  }
  function setConnection(kind, label, message = "") {
    const badge = $("connectionBadge");
    badge.className = `connection-badge ${kind}`;
    badge.textContent = label;
    $("connectionMessage").textContent = message;
  }
  function parseApiError(payload, status) {
    let detail = payload?.detail;
    if (Array.isArray(detail)) detail = detail.map((e) => `${e.loc?.join(".") || "input"}: ${e.msg}`).join("\n");
    return detail ? `Request failed (${status}): ${typeof detail === "string" ? detail : pretty(detail)}` : `Request failed with HTTP ${status}. Check that the backend is running and the URL is correct.`;
  }
  function startLoading() {
    $("loadingOverlay").hidden = false;
    $("generateButton").disabled = true;
    $("generateButton").querySelector(".button-label").textContent = "Generating…";
    state.loadingStep = 0;
    const renderStep = () => {
      const step = loadingSteps[Math.min(state.loadingStep, loadingSteps.length - 1)];
      $("loadingTitle").textContent = step[0];
      $("loadingText").textContent = step[1];
      state.loadingStep = (state.loadingStep + 1) % loadingSteps.length;
    };
    renderStep();
    state.loadingTimer = window.setInterval(renderStep, 7000);
  }
  function stopLoading() {
    $("loadingOverlay").hidden = true;
    $("generateButton").disabled = false;
    $("generateButton").querySelector(".button-label").textContent = "Generate test suite";
    if (state.loadingTimer) window.clearInterval(state.loadingTimer);
    state.loadingTimer = null;
    state.abortController = null;
  }
  function metricText(value, suffix = "") {
    return value === null || value === undefined || value === "" ? "—" : `${value}${suffix}`;
  }
  function listItems(elementId, values, emptyText) {
    const el = $(elementId);
    el.replaceChildren();
    const items = Array.isArray(values) ? values : [];
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "list-item empty";
      empty.textContent = emptyText;
      el.append(empty);
      return;
    }
    items.forEach((value) => {
      const item = document.createElement("div");
      item.className = "list-item";
      item.textContent = typeof value === "string" ? value : pretty(value);
      el.append(item);
    });
  }
  function switchTab(name) {
    document.querySelectorAll(".result-tab").forEach((button) => {
      const active = button.dataset.tab === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll(".tab-pane").forEach((pane) => {
      const active = pane.id === `tab-${name}`;
      pane.classList.toggle("active", active);
      pane.hidden = !active;
    });
  }
  function renderResults(data) {
    state.result = data;
    state.tests = data.generated_tests || "";
    const pytest = data.pytest_result || {};
    const mutation = data.mutation_result || {};
    const report = data.report || {};
    const mutationAnalysis = report.mutation_analysis || {};
    const coverage = pytest.coverage || {};

    $("emptyState").hidden = true;
    $("resultContent").hidden = false;
    $("resultFunction").textContent = data.function_name || $("functionName").value.trim() || "Detected function";
    $("resultRunId").textContent = `RUN ID  ${data.run_id || "unknown"}`;
    $("generatedTests").textContent = state.tests || "No tests were returned by the generator.";
    $("pytestMetric").textContent = (pytest.passed === true || pytest.status === "passed") ? "Passed" : (pytest.status || "Unknown");
    $("pytestMetric").style.color = (pytest.passed === true || pytest.status === "passed") ? "var(--mint)" : ((pytest.status === "failed" || pytest.status === "error" || pytest.status === "timeout") ? "var(--red)" : "var(--text)");
    $("pytestSub").textContent = coverage.status === "collected"
      ? `${pytest.passed === true ? "Tests executed" : "See execution output"} · ${coverage.statement_percent}% stmt · ${coverage.branch_percent ?? "N/A"}% branch`
      : (pytest.passed === true ? "Generated tests executed · coverage unavailable" : "See execution output");
    const score = mutation.score_percent;
    $("mutationMetric").textContent = score === null || score === undefined ? "N/A" : `${score}%`;
    $("mutationSub").textContent = `${metricText(mutation.killed, " killed")} / ${metricText(mutation.total, " total")}`;
    $("revisionMetric").textContent = metricText(report.revision_count ?? report.round_index ?? 0);
    $("reportHeadline").textContent = report.headline || "Run completed";
    $("reportText").textContent = report.summary || "The run finished. Review the tabs for test and mutation details.";
    $("pytestDetailStatus").textContent = pytest.status || "not run";
    $("pytestOutput").textContent = pytest.output || "No pytest output returned.";
    $("mutationEngine").textContent = [mutation.engine, mutation.status].filter(Boolean).join(" · ") || "Not run";
    const scopeItems = [];
    if (mutation.engine === "fallback_token") {
      scopeItems.push("Reduced fallback mutation set only; this is not a full mutmut score.");
      if (mutation.fallback_reason) scopeItems.push(mutation.fallback_reason);
      scopeItems.push("Run under WSL/Linux/Docker to use mutmut on Windows.");
    } else if (mutation.engine === "mutmut") {
      scopeItems.push("mutmut engine used. Review total mutant count and raw output before interpreting the score.");
    }
    if (mutation.evaluation_complete === false) scopeItems.push("The fallback stopped before all generated mutants were evaluated.");
    if (Array.isArray(mutation.inconclusive) && mutation.inconclusive.length) {
      scopeItems.push(`${mutation.inconclusive.length} mutant execution(s) were inconclusive and were not counted as killed.`);
    }
    listItems("mutationScope", scopeItems, "No mutation engine details available.");
    $("mutationOverview").replaceChildren();
    const overview = [
      ["Total mutants", metricText(mutation.total)],
      ["Killed", metricText(mutation.killed)],
      ["Survived", Array.isArray(mutation.survived) ? mutation.survived.length : "—"]
    ];
    overview.forEach(([label, value]) => {
      const card = document.createElement("div"); card.className = "mutation-mini";
      const l = document.createElement("span"); l.textContent = label;
      const v = document.createElement("b"); v.textContent = value;
      card.append(l, v); $("mutationOverview").append(card);
    });
    listItems("survivors", mutation.survived, "No surviving mutants were reported.");
    listItems("recommendations", mutationAnalysis.recommendations, "No recommendations were returned.");
    $("mutationRaw").textContent = pretty(mutation);
    listItems("reportStrengths", report.strengths, "No strengths listed.");
    const coverageGaps = (mutationAnalysis.coverage_gaps || []).concat(
      (coverage.missing_lines || []).map((line) => `Uncovered source line ${line}`),
      (coverage.missing_branches || []).map((branch) => `Uncovered branch ${branch}`)
    );
    listItems("coverageGaps", [...new Set(coverageGaps)], coverage.status === "collected" ? "No uncovered lines or branches reported." : "Coverage was not collected.");
    listItems("reportGaps", report.remaining_gaps, "No remaining gaps listed in the report.");
    listItems("reportSteps", report.next_steps, "No next steps listed.");
    $("reportRounds").textContent = `${metricText(report.round_index ?? 0)} round index`;
    $("reportRaw").textContent = pretty(report);
    $("downloadTests").disabled = !state.tests;
    setStatus("complete", "Run completed");
    switchTab("tests");
  }
  async function readPythonFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".py")) {
      setError("Please choose a Python source file with a .py extension.");
      return;
    }
    if (file.size > MAX_SOURCE_CHARS * 4) {
      setError("That file is too large. The current limit is 20,000 characters of source code.");
      return;
    }
    try {
      const text = await file.text();
      if (text.length > MAX_SOURCE_CHARS) {
        setError(`This file contains ${text.length.toLocaleString()} characters. The API limit is 20,000 characters.`);
        return;
      }
      $("sourceCode").value = text;
      $("editorFilename").textContent = file.name;
      $("sourceHint").textContent = `Loaded ${file.name}. You can edit this content before running.`;
      updateCharCount();
      setError("");
      $("sourceCode").focus();
    } catch (error) {
      setError(`Could not read file: ${error.message || error}`);
    }
  }
  async function checkConnection() {
    const url = baseUrl();
    if (!url) { setConnection("bad", "URL required", "Enter your backend base URL."); return; }
    setConnection("unknown", "Checking…", "Pinging the backend health endpoint…");
    $("checkConnection").disabled = true;
    try {
      const response = await fetch(`${url}/health`, { method: "GET", headers: { Accept: "application/json" } });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.status !== "ok") throw new Error(`Backend responded with HTTP ${response.status}.`);
      setConnection("good", "Connected", `Connected to ${data.service || "FastAPI backend"}.`);
    } catch (error) {
      setConnection("bad", "Unreachable", `${error.message || error}. Check the URL, server state, and CORS settings.`);
    } finally {
      $("checkConnection").disabled = false;
    }
  }
  async function generate() {
    setError("");
    const sourceCode = $("sourceCode").value;
    if (!sourceCode.trim()) { setError("Paste Python code or upload a .py file before generating tests."); $("sourceCode").focus(); return; }
    if (sourceCode.length > MAX_SOURCE_CHARS) { setError("Source code exceeds the API limit of 20,000 characters."); return; }
    const functionName = $("functionName").value.trim();
    if (functionName && !/^[A-Za-z_]\w*$/.test(functionName)) { setError("Target function must be a valid Python identifier, for example calculate_total."); $("functionName").focus(); return; }
    const url = baseUrl();
    if (!url) { setError("Enter your FastAPI base URL in Backend connection settings."); return; }
    startLoading(); setStatus("running", "Agents working");
    state.abortController = new AbortController();
    // Generating tests and running mutation checks may take several minutes.
    const timeout = window.setTimeout(() => state.abortController?.abort(), 10 * 60 * 1000);
    try {
      const response = await fetch(`${url}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          source_code: sourceCode,
          function_name: functionName || null,
          request_notes: $("requestNotes").value.trim(),
          max_rounds: Number($("maxRounds").value)
        }),
        signal: state.abortController.signal
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(parseApiError(data, response.status));
      renderResults(data);
    } catch (error) {
      setStatus("failed", "Run failed");
      const message = error.name === "AbortError"
        ? "The request took longer than 10 minutes and was stopped by the browser. The backend process may need to be checked."
        : `${error.message || error}\n\nIf this is a network error, confirm that the API is running, the URL is correct, and FRONTEND_ORIGINS includes this frontend's origin.`;
      setError(message);
    } finally {
      window.clearTimeout(timeout);
      stopLoading();
    }
  }
  function downloadTests() {
    if (!state.tests) return;
    const blob = new Blob([state.tests.endsWith("\n") ? state.tests : `${state.tests}\n`], { type: "text/x-python;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "generated_tests.py";
    document.body.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
  }
  async function copyTests() {
    if (!state.tests) return;
    const button = $("copyTests");
    try {
      await navigator.clipboard.writeText(state.tests);
      button.textContent = "Copied!";
    } catch {
      const area = document.createElement("textarea"); area.value = state.tests; document.body.append(area); area.select();
      const ok = document.execCommand("copy"); area.remove(); button.textContent = ok ? "Copied!" : "Select code to copy";
    }
    window.setTimeout(() => { button.textContent = "Copy code"; }, 1800);
  }

  $("sourceCode").addEventListener("input", () => {
    updateCharCount();
    if ($("editorFilename").textContent !== "candidate.py") $("editorFilename").textContent = `${$("editorFilename").textContent.replace(" · edited", "")} · edited`;
  });
  $("fileInput").addEventListener("change", (event) => readPythonFile(event.target.files?.[0]));
  $("dropZone").addEventListener("click", () => $("fileInput").click());
  $("dropZone").addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("fileInput").click(); } });
  ["dragenter", "dragover"].forEach((type) => $("dropZone").addEventListener(type, (event) => { event.preventDefault(); $("dropZone").classList.add("dragover"); }));
  ["dragleave", "drop"].forEach((type) => $("dropZone").addEventListener(type, (event) => { event.preventDefault(); $("dropZone").classList.remove("dragover"); }));
  $("dropZone").addEventListener("drop", (event) => readPythonFile(event.dataTransfer?.files?.[0]));
  $("clearCode").addEventListener("click", () => { $("sourceCode").value = ""; $("editorFilename").textContent = "candidate.py"; $("sourceHint").textContent = "Paste your function, or import a Python file below."; updateCharCount(); setError(""); $("sourceCode").focus(); });
  $("generateButton").addEventListener("click", generate);
  $("checkConnection").addEventListener("click", checkConnection);
  $("downloadTests").addEventListener("click", downloadTests);
  $("copyTests").addEventListener("click", copyTests);
  document.querySelectorAll(".result-tab").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  $("sourceCode").value = "";
  updateCharCount();
})();
