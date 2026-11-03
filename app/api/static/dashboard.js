"use strict";
const el = id => document.getElementById(id);
let runs = [], selected = null, artifacts = {}, requestNumber = 0, loading = false;
const labels = {not_run: "Not run", approved: "Approved", changes_requested: "Changes requested", invalid: "Invalid review", passed: "Passed", failed: "Failed", running: "Running", succeeded: "Succeeded", unknown: "Unknown"};
const label = value => labels[value] || value || "Not recorded";
function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function badge(status, prefix = "") {
  const item = node("span", prefix + label(status), "badge");
  item.dataset.status = status;
  return item;
}
function date(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? "Time unavailable" : parsed.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"});
}
function renderRuns() {
  const focusedRun = document.activeElement?.dataset?.runId;
  const query = el("search").value.toLowerCase(), status = el("status-filter").value;
  const visible = runs.filter(run => (!status || run.status === status) &&
    [run.task, run.mode, run.run_id, run.status].join(" ").toLowerCase().includes(query));
  el("visible-count").textContent = visible.length;
  el("runs").replaceChildren();
  if (!visible.length) el("runs").append(node("li", runs.length ? "No matching runs. Try another filter." : "No runs yet. Start with swarm demo.", "empty"));
  visible.forEach(run => {
    const item = node("li"), button = node("button");
    button.type = "button";
    button.dataset.runId = run.run_id;
    button.setAttribute("aria-current", String(run.run_id === selected));
    const meta = node("span", undefined, "run-row-meta");
    meta.append(node("span", `${run.mode || "unknown"} · ${run.provider || "legacy"}`), badge(run.status));
    button.append(node("span", run.task || run.run_id, "run-title"), meta);
    button.addEventListener("click", () => selectRun(run.run_id));
    item.append(button); el("runs").append(item);
    if (focusedRun === run.run_id) button.focus({preventScroll: true});
  });
}
function showArtifact() {
  const value = artifacts[el("artifact-select").value];
  el("artifact-content").textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2) || "No readable artifacts.";
}
function renderOverview(data) {
  const summary = data.summary, result = data.artifacts["result.json"] || {};
  const review = data.artifacts["review.json"] || result.review;
  const attempts = Array.isArray(data.artifacts["attempts.json"]) ? data.artifacts["attempts.json"] : [];
  for (const [id, value] of [["validation-state", summary.validation_status], ["review-state", summary.review_status]]) {
    el(id).textContent = label(value); el(id).dataset.status = value || "unknown";
  }
  el("attempt-count").textContent = summary.attempt_count ?? attempts.length;
  el("workspace-info").hidden = !summary.workspace_path;
  el("workspace-branch").textContent = summary.workspace_branch || "";
  el("workspace-path").textContent = summary.workspace_path || "";
  el("attempt-section").hidden = !attempts.length;
  el("attempts").replaceChildren();
  attempts.forEach(attempt => {
    const row = node("div", undefined, "attempt"), statuses = node("div", undefined, "attempt-badges");
    statuses.append(badge(attempt.validation_status, "Tests: "), badge(attempt.review_status, "Review: "));
    row.append(node("strong", `Attempt ${attempt.number}`), statuses); el("attempts").append(row);
  });
  el("findings").replaceChildren();
  const findings = Array.isArray(review?.findings) ? review.findings : [];
  el("finding-count").textContent = `${findings.length} finding${findings.length === 1 ? "" : "s"}`;
  if (review?.summary) el("findings").append(node("p", review.summary, "risk-note"));
  if (!findings.length) {
    const text = summary.review_status === "approved" ? "No blocking findings reported. Model review remains advisory evidence; inspect validation separately." :
      summary.review_status === "invalid" ? "Review output did not match the required schema. Approval is blocked." :
      summary.review_status === "changes_requested" ? "The reviewer requested changes. Inspect the review artifact for the decision." : "No structured review recorded for this run.";
    el("findings").append(node("div", text, "muted-note"));
  }
  findings.forEach(finding => {
    const card = node("div", undefined, "finding"), head = node("div", undefined, "finding-head");
    const severity = badge(["critical", "high"].includes(finding.severity) ? "failed" : "unknown");
    severity.textContent = finding.severity;
    head.append(node("strong", finding.title), severity);
    card.append(head, node("p", finding.detail));
    if (finding.path) card.append(node("small", finding.path + (finding.line ? `:${finding.line}` : "")));
    el("findings").append(card);
  });
  if (Array.isArray(review?.residual_risks)) review.residual_risks.forEach(risk => el("findings").append(node("p", `Residual risk: ${risk}`, "risk-note")));
  el("validation").replaceChildren();
  const commands = Array.isArray(data.artifacts["validation.json"]) ? data.artifacts["validation.json"] : [];
  if (!commands.length) el("validation").append(node("div", "No commands recorded. Previews and declined applications do not execute validation.", "muted-note"));
  commands.forEach(command => {
    const card = node("div", undefined, "command"), head = node("div", undefined, "command-head");
    head.append(node("code", command.command), badge(command.exit_code === 0 ? "passed" : "failed"));
    card.append(head, node("p", `Exit ${command.exit_code} · ${command.duration_seconds || 0}s`, "small"));
    if (command.stdout || command.stderr) {
      const details = node("details"); details.append(node("summary", "Command output"), node("pre", [command.stdout, command.stderr].filter(Boolean).join("\n"))); card.append(details);
    }
    el("validation").append(card);
  });
  const events = Array.isArray(data.artifacts["events.jsonl"]) ? data.artifacts["events.jsonl"] : [];
  el("event-count").textContent = `${events.length} events${events.length > 50 ? " · latest 50 shown" : ""}`;
  el("timeline").replaceChildren();
  if (!events.length) el("timeline").append(node("li", "No execution events recorded.", "muted-note"));
  events.slice(-50).forEach(event => {
    const row = node("li"), dot = node("span", undefined, "dot"), text = node("span", `${event.agent} · ${label(event.status)}`, "event-label");
    dot.dataset.status = event.status;
    const extra = [event.attempt ? `Attempt ${event.attempt}` : "", event.model || "", event.command || "", event.duration_seconds != null ? `${event.duration_seconds}s` : "", event.error || ""].filter(Boolean).join(" · ");
    if (extra) text.append(node("small", extra));
    row.append(dot, text, node("time", date(event.at))); el("timeline").append(row);
  });
}
async function selectRun(id, refresh = false) {
  const request = ++requestNumber, previousArtifact = refresh ? el("artifact-select").value : null;
  selected = id; renderRuns(); el("empty-detail").hidden = true; el("detail").hidden = false;
  if (!refresh) {
    el("detail-title").textContent = "Loading run…"; el("overview").hidden = true;
    el("artifact-panel").hidden = true; document.querySelector(".tabs").hidden = true;
  }
  try {
    const response = await fetch(`/runs/${encodeURIComponent(id)}`, {cache: "no-store"});
    if (!response.ok) throw new Error("Run is unavailable. Refresh the list and try again.");
    const data = await response.json();
    if (request !== requestNumber) return;
    const summary = data.summary;
    el("detail-title").textContent = summary.task || id;
    el("detail-id").textContent = `${summary.mode || "unknown"} / ${id}`;
    el("detail-badge").textContent = label(summary.status); el("detail-badge").dataset.status = summary.status;
    el("detail-status").textContent = `${summary.provider || "legacy run"} · ${summary.model_calls || 0} model calls · ${(summary.total_tokens || 0).toLocaleString()} tokens · Application: ${label(summary.application_status)}${summary.started_at ? " · " + new Date(summary.started_at).toLocaleString() : ""}`;
    artifacts = data.artifacts;
    const options = Object.keys(artifacts);
    el("artifact-select").replaceChildren(...options.map(name => {const option = node("option", name); option.value = name; return option;}));
    if (previousArtifact && options.includes(previousArtifact)) el("artifact-select").value = previousArtifact;
    else if (options.includes("result.json")) el("artifact-select").value = "result.json";
    el("artifact-count").textContent = options.length;
    const errors = Object.keys(data.artifact_errors || {}).length;
    el("artifact-warning").textContent = errors ? `${errors} artifact(s) could not be read. Other artifacts remain available.` : "Artifacts are displayed as plain text.";
    const expanded = [...el("validation").querySelectorAll("details")].map(item => item.open);
    renderOverview(data);
    if (refresh) [...el("validation").querySelectorAll("details")].forEach((item, index) => {item.open = !!expanded[index];});
    document.querySelector(".tabs").hidden = false;
    showArtifact(); activateTab(el("artifacts-tab").getAttribute("aria-selected") === "true" ? "artifacts" : "overview");
  } catch (error) {
    if (request !== requestNumber) return;
    el("detail-title").textContent = "Unable to read run"; el("detail-status").textContent = error.message;
    el("detail-badge").textContent = "Unavailable"; el("detail-badge").dataset.status = "failed";
    el("overview").hidden = true; el("artifact-panel").hidden = true;
    document.querySelector(".tabs").hidden = true;
  }
}
async function loadRuns() {
  if (loading) return;
  loading = true; el("refresh").disabled = true; el("refresh-status").textContent = "Refreshing…";
  try {
    const response = await fetch("/runs?details=true&limit=100", {cache: "no-store"});
    if (!response.ok) throw new Error("Unable to load runs. Check the local server.");
    runs = await response.json(); renderRuns();
    el("run-count").textContent = runs.length;
    el("active-count").textContent = runs.filter(run => run.status === "running").length;
    el("failed-count").textContent = runs.filter(run => run.status === "failed").length;
    el("token-count").textContent = runs.reduce((sum, run) => sum + (run.total_tokens || 0), 0).toLocaleString();
    el("refresh-status").textContent = `Updated ${new Date().toLocaleTimeString()} · ${el("live").checked ? "Live every 5s" : "Manual refresh"}`;
    if (selected && !document.activeElement?.closest("#overview")) await selectRun(selected, true);
  } catch (error) { el("refresh-status").textContent = error.message; }
  finally {loading = false; el("refresh").disabled = false;}
}
function activateTab(name) {
  for (const tab of ["overview", "artifacts"]) {
    const button = el(`${tab}-tab`), active = tab === name;
    button.setAttribute("aria-selected", String(active)); button.tabIndex = active ? 0 : -1;
  }
  el("overview").hidden = name !== "overview"; el("artifact-panel").hidden = name !== "artifacts";
}
for (const name of ["overview", "artifacts"]) {
  el(`${name}-tab`).addEventListener("click", () => activateTab(name));
  el(`${name}-tab`).addEventListener("keydown", event => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault(); const target = event.key === "Home" ? "overview" : event.key === "End" ? "artifacts" : name === "overview" ? "artifacts" : "overview";
      activateTab(target); el(`${target}-tab`).focus();
    }
  });
}
el("search").addEventListener("input", renderRuns);
el("status-filter").addEventListener("change", renderRuns);
el("refresh").addEventListener("click", loadRuns);
el("live").addEventListener("change", loadRuns);
el("artifact-select").addEventListener("change", showArtifact);
setInterval(() => {if (el("live").checked && !document.hidden) loadRuns();}, 5000);
loadRuns();
