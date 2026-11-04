"use strict";
let controlConfig = null, jobsSignature = "", jobsLoading = false;
const jobPending = new Set();
const terminalStates = new Set(["succeeded", "failed", "cancelled", "interrupted", "budget_exceeded"]);
async function missionRequest(path, payload) {
  const response = await fetch(path, payload === undefined ? {cache: "no-store"} : {
    method: "POST", headers: {"content-type": "application/json", "x-swarm-token": controlConfig?.token || ""}, body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : data.detail;
    throw new Error(detail || "Control request failed.");
  }
  return data;
}
function launchOptions() {
  const implement = el("launch-mode").value === "implement";
  el("launch-apply").disabled = !implement;
  if (!implement) el("launch-apply").checked = false;
  el("launch-repairs").disabled = !el("launch-apply").checked;
  if (el("launch-repairs").disabled) el("launch-repairs").value = 0;
  const scenarioAvailable = implement && el("launch-apply").checked && el("launch-provider").value === "demo";
  el("launch-scenario").disabled = !scenarioAvailable;
  if (!scenarioAvailable) el("launch-scenario").value = "standard";
  const guided = el("launch-scenario").value === "repair_demo";
  el("launch-repairs").min = guided ? 1 : 0;
  if (guided && Number(el("launch-repairs").value) < 1) el("launch-repairs").value = 1;
}
async function jobAction(key, path, payload) {
  if (jobPending.has(key)) return;
  jobPending.add(key);
  el("job-status").textContent = "Sending request…";
  try {
    await missionRequest(path, payload);
    el("job-status").textContent = "Request accepted.";
    await loadJobs();
    await loadRuns();
  } catch (error) { el("job-status").textContent = error.message; }
  finally {jobPending.delete(key);}
}
function actionButton(text, key, action, danger = false) {
  const button = node("button", text, danger ? "danger" : "");
  button.type = "button"; button.dataset.jobAction = key;
  button.addEventListener("click", async () => {
    if (jobPending.has(key)) return;
    button.disabled = true;
    try {await action();} finally {if (button.isConnected) button.disabled = false;}
  });
  return button;
}
function renderJobs(jobs) {
  const signature = JSON.stringify(jobs);
  if (signature === jobsSignature) return;
  jobsSignature = signature;
  const focusedAction = document.activeElement?.dataset?.jobAction;
  const openApprovals = new Map([...el("approvals").querySelectorAll("details")].map(item => [item.dataset.ticket, {open: item.open, scroll: item.querySelector("pre")?.scrollTop || 0}]));
  const active = jobs.filter(job => !terminalStates.has(job.state));
  el("queue-count").textContent = active.length;
  el("cancel-all").disabled = !active.length;
  el("jobs").replaceChildren();
  if (!jobs.length) el("jobs").append(node("p", "No jobs yet. Start with a demo plan.", "muted-note"));
  jobs.slice(0, 20).forEach(job => {
    const card = node("div", undefined, "job-card"), title = node("div", undefined, "job-title");
    title.append(node("strong", job.request.task), badge(job.state));
    card.append(title, node("p", `${job.request.mode} · ${job.request.provider} · ${job.request.max_seconds}s · ${job.request.max_model_calls} requests${job.retry_of ? " · retry" : ""}`, "small"));
    if (job.error) card.append(node("p", job.error, "job-error"));
    const actions = node("div", undefined, "job-actions");
    if (job.run_id) actions.append(actionButton("Inspect run", `inspect-${job.id}`, async () => {await selectRun(job.run_id); el("detail").scrollIntoView({block: "start", behavior: "auto"});}));
    if (terminalStates.has(job.state)) actions.append(actionButton("Retry as new run", `retry-${job.id}`, () => jobAction(`retry-${job.id}`, `/jobs/${job.id}/retry`, {})));
    else if (job.state !== "cancelling") actions.append(actionButton("Cancel", `cancel-${job.id}`, () => jobAction(`cancel-${job.id}`, `/jobs/${job.id}/cancel`, {}), true));
    card.append(actions); el("jobs").append(card);
  });
  const approvals = jobs.filter(job => job.state === "awaiting_approval" && job.approval);
  el("approval-section").hidden = !approvals.length;
  el("approvals").replaceChildren();
  approvals.forEach(job => {
    const approval = job.approval, card = node("div", undefined, "approval-card");
    card.append(node("h3", job.request.task), node("p", `${approval.files} file(s)${approval.risky ? " · includes deletion or other risk flags" : ""} · Diff receipt ${approval.digest.slice(0, 16)}`, "small"));
    const diff = node("details"), content = node("pre", approval.diff);
    diff.dataset.ticket = approval.ticket;
    const previous = openApprovals.get(approval.ticket);
    diff.open = previous ? previous.open : true;
    diff.append(node("summary", "Inspect proposed diff"), content);
    card.append(diff);
    const actions = node("div", undefined, "approval-actions");
    const approve = actionButton("Approve this diff", `approve-${approval.ticket}`, () => jobAction(`approve-${approval.ticket}`, `/jobs/${job.id}/approval`, {ticket: approval.ticket, approve: true}));
    approve.classList.add("primary");
    const decline = actionButton("Decline & stop", `decline-${approval.ticket}`, () => jobAction(`decline-${approval.ticket}`, `/jobs/${job.id}/approval`, {ticket: approval.ticket, approve: false}), true);
    approve.disabled = decline.disabled = job.decision_pending;
    actions.append(approve, decline);
    card.append(actions); el("approvals").append(card);
    if (previous) content.scrollTop = previous.scroll;
  });
  if (focusedAction) [...document.querySelectorAll("[data-job-action]")].find(button => button.dataset.jobAction === focusedAction)?.focus({preventScroll: true});
}
async function loadJobs() {
  if (!controlConfig || jobsLoading) return;
  jobsLoading = true;
  try {renderJobs(await missionRequest("/jobs"));}
  catch (error) {el("job-status").textContent = error.message;}
  finally {jobsLoading = false;}
}
async function connectControl() {
  try {
    controlConfig = await missionRequest("/control");
    el("launch-root").textContent = controlConfig.root;
    el("configured-provider").disabled = !controlConfig.live_available;
    el("configured-provider").textContent = controlConfig.live_available ? `Configured · ${controlConfig.provider_mode}` : "NVIDIA endpoint · key required";
    for (const [id, max] of [["launch-seconds", controlConfig.max_seconds], ["launch-calls", controlConfig.max_model_calls], ["launch-tokens", controlConfig.max_total_tokens]]) {
      el(id).max = max; el(id).value = Math.min(Number(el(id).value), max);
    }
    el("launch-submit").disabled = false;
    el("launch-status").textContent = "Ready · demo is selected by default.";
    el("queue-capacity").textContent = `${controlConfig.concurrency} concurrent jobs · active first · up to 20 shown`;
    await loadJobs();
  } catch (error) {el("launch-status").textContent = error.message; el("launch-root").textContent = "Control unavailable";}
}
el("launch-mode").addEventListener("change", launchOptions);
el("launch-apply").addEventListener("change", launchOptions);
el("launch-provider").addEventListener("change", launchOptions);
el("launch-scenario").addEventListener("change", launchOptions);
el("repair-demo").addEventListener("click", () => {
  el("launch-mode").value = "implement"; el("launch-provider").value = "demo";
  el("launch-apply").checked = true; el("launch-scenario").value = "repair_demo";
  el("launch-task").value = "DEMO: approve a proposal, observe a syntax failure, and approve its repair.";
  el("launch-repairs").value = 1; launchOptions();
  el("launch-status").textContent = "Demo preset loaded. Queue to start; each diff requires your approval.";
});
el("launch-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (jobPending.has("launch")) return;
  jobPending.add("launch"); el("launch-submit").disabled = true;
  try {
    const job = await missionRequest("/jobs", {task: el("launch-task").value, mode: el("launch-mode").value,
      provider: el("launch-provider").value, scenario: el("launch-scenario").value, apply_changes: el("launch-apply").checked,
      max_repairs: Number(el("launch-repairs").value), max_seconds: Number(el("launch-seconds").value),
      max_model_calls: Number(el("launch-calls").value), max_total_tokens: Number(el("launch-tokens").value)});
    el("launch-status").textContent = `Queued ${job.id.slice(0, 12)} · follow the job queue.`;
    await loadJobs();
  } catch (error) {el("launch-status").textContent = error.message;}
  finally {jobPending.delete("launch"); el("launch-submit").disabled = false;}
});
el("cancel-all").addEventListener("click", () => jobAction("cancel-all", "/jobs/cancel-all", {}));
el("refresh").addEventListener("click", loadJobs);
setInterval(() => {if (el("live").checked && !document.hidden) loadJobs();}, 2000);
connectControl();
