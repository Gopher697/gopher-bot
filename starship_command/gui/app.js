const state = {
  snapshot: null,
  selected: { type: "division", id: "first_officer" },
};

const missionInput = document.querySelector("#missionInput");
const outputPanel = document.querySelector("#outputPanel");
const divisionRoster = document.querySelector("#divisionRoster");
const missionBoard = document.querySelector("#missionBoard");
const detailsPanel = document.querySelector("#detailsPanel");
const selectionType = document.querySelector("#selectionType");
const handoffPanel = document.querySelector("#handoffPanel");
const readinessButton = document.querySelector("#runLocalModelReadiness");

async function api(path, body = null) {
  const options = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

async function loadState() {
  state.snapshot = await api("/api/state");
  if (state.snapshot.selected) {
    state.selected = state.snapshot.selected;
  }
  render();
}

function statusLabel(status) {
  return `<span class="status ${escapeHtml(status)}">${escapeHtml(status)}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortText(value, fallback = "No current assignment") {
  const text = String(value || fallback);
  return text.length > 96 ? `${text.slice(0, 93)}...` : text;
}

function render() {
  if (!state.snapshot) return;
  outputPanel.textContent = state.snapshot.output || "Awaiting mission orders.";
  renderRoster();
  renderMissionBoard();
  renderDetails();
}

function renderRoster() {
  const { divisions, division_order } = state.snapshot;
  divisionRoster.innerHTML = division_order
    .map((key) => {
      const division = divisions[key];
      const selected = state.selected.type === "division" && state.selected.id === key ? " selected" : "";
      return `
        <article class="division-card${selected}" data-type="division" data-id="${escapeHtml(key)}">
          <h3>${escapeHtml(division.name)}</h3>
          <p><strong>Standing officer:</strong> ${escapeHtml(division.standing_officer)}</p>
          <p>${statusLabel(division.status)}</p>
          <p><strong>Assignment:</strong> ${escapeHtml(shortText(division.current_assignment))}</p>
          <p><strong>Specialists:</strong> ${division.specialists.length}</p>
        </article>
      `;
    })
    .join("");
}

function renderMissionBoard() {
  const assignments = state.snapshot.assignments || [];
  if (!assignments.length) {
    missionBoard.innerHTML = `<p>No active assignments in this session.</p>`;
    return;
  }
  missionBoard.innerHTML = assignments
    .map((assignment) => {
      const selected = state.selected.type === "assignment" && state.selected.id === assignment.id ? " selected" : "";
      return `
        <article class="assignment-card${selected}" data-type="assignment" data-id="${escapeHtml(assignment.id)}">
          <strong>${escapeHtml(assignment.id)} ${escapeHtml(assignment.kind.replaceAll("_", " "))}</strong>
          <p>${escapeHtml(shortText(assignment.mission, "Bridge log / handoff"))}</p>
          <p>${escapeHtml(assignment.primary_division || "Unassigned")} ${statusLabel(assignment.status)}</p>
        </article>
      `;
    })
    .join("");
}

function findSelected() {
  if (!state.snapshot) return null;
  if (state.selected.type === "division") {
    return state.snapshot.divisions[state.selected.id] || null;
  }
  if (state.selected.type === "assignment") {
    return state.snapshot.assignments.find((item) => item.id === state.selected.id) || null;
  }
  if (state.selected.type === "specialist") {
    for (const division of Object.values(state.snapshot.divisions)) {
      const specialist = division.specialists.find((item) => item.id === state.selected.id);
      if (specialist) return specialist;
    }
  }
  return null;
}

function renderDetails() {
  const selected = findSelected();
  selectionType.textContent = state.selected.type;
  if (!selected) {
    detailsPanel.innerHTML = `<p>No selection.</p>`;
    return;
  }
  if (state.selected.type === "division") {
    detailsPanel.innerHTML = `
      <h2>${escapeHtml(selected.name)}</h2>
      <p><strong>Standing officer:</strong> ${escapeHtml(selected.standing_officer)}</p>
      <p><strong>Authority:</strong> ${escapeHtml(selected.authority)}</p>
      <p>${statusLabel(selected.status)}</p>
      <p><strong>Mission:</strong> ${escapeHtml(selected.mission)}</p>
      <p><strong>Current assignment:</strong> ${escapeHtml(selected.current_assignment || "None")}</p>
      <p><strong>Specialists currently assigned:</strong> ${selected.specialists.length}</p>
      <ul>${selected.responsibilities.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      ${selected.specialists.map(renderSpecialistLine).join("")}
    `;
    return;
  }
  if (state.selected.type === "specialist") {
    detailsPanel.innerHTML = `
      <h2>${escapeHtml(selected.name)}</h2>
      <p><strong>Division:</strong> ${escapeHtml(selected.division)}</p>
      <p><strong>Role:</strong> specialist</p>
      <p><strong>Authority:</strong> ${escapeHtml(selected.authority)}</p>
      <p>${statusLabel(selected.status)}</p>
      <p><strong>Mission:</strong> ${escapeHtml(selected.mission)}</p>
      <p><strong>Current assignment:</strong> ${escapeHtml(selected.current_assignment)}</p>
      <p><strong>Required context:</strong></p>
      <ul>${selected.required_context.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      <p><strong>Retirement condition:</strong> ${escapeHtml(selected.retirement_condition)}</p>
      <p><strong>Latest output:</strong></p>
      <pre>${escapeHtml(selected.latest_output)}</pre>
    `;
    return;
  }
  detailsPanel.innerHTML = `
    <h2>${escapeHtml(selected.id)} ${escapeHtml(selected.kind.replaceAll("_", " "))}</h2>
    <p><strong>Division:</strong> ${escapeHtml(selected.primary_division)}</p>
    <p><strong>Mission:</strong> ${escapeHtml(selected.mission)}</p>
    <p>${statusLabel(selected.status)}</p>
    <p><strong>Supporting divisions:</strong> ${escapeHtml((selected.supporting_divisions || []).join(", ") || "None")}</p>
    <p><strong>Latest output:</strong></p>
    <pre>${escapeHtml(selected.output)}</pre>
  `;
}

function renderSpecialistLine(specialist) {
  return `
    <button class="ghost-button specialist-select" data-type="specialist" data-id="${escapeHtml(specialist.id)}">
      ${escapeHtml(specialist.name)}
    </button>
  `;
}

async function performAction(action) {
  const mission = missionInput.value.trim();
  if (!mission && action !== "handoff") {
    outputPanel.textContent = "Enter mission orders before routing.";
    return;
  }
  let response;
  if (action === "route") response = await api("/api/route", { mission });
  if (action === "deploy") response = await api("/api/deploy-specialist", { mission });
  if (action === "codex") response = await api("/api/codex-order", { mission });
  if (action === "handoff") {
    handoffPanel.hidden = false;
    response = await api("/api/handoff", {
      Project: document.querySelector("#handoffProject").value || mission,
      Mission: mission,
      "Stardate/Date": document.querySelector("#handoffDate").value,
      "Current State": document.querySelector("#handoffState").value,
      "Open Threads": document.querySelector("#handoffThreads").value,
      "Next Action": document.querySelector("#handoffNext").value,
      "Suggested Next Station": document.querySelector("#handoffStation").value,
    });
  }
  state.snapshot = response.state;
  state.selected = state.snapshot.selected;
  render();
}

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await performAction(button.dataset.action);
    } catch (error) {
      outputPanel.textContent = error.message;
    }
  });
});

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-type][data-id]");
  if (!target) return;
  state.selected = { type: target.dataset.type, id: target.dataset.id };
  render();
});

document.querySelector("#copyOutput").addEventListener("click", async () => {
  await navigator.clipboard.writeText(outputPanel.textContent);
});

readinessButton.addEventListener("click", async () => {
  readinessButton.disabled = true;
  readinessButton.classList.add("busy");
  outputPanel.textContent = "Running local model readiness check... slower local models may take 20+ seconds.";
  try {
    const response = await api("/api/local-model-readiness", {});
    state.snapshot = response.state;
    state.selected = state.snapshot.selected;
    render();
  } catch (error) {
    outputPanel.textContent = error.message;
  } finally {
    readinessButton.disabled = false;
    readinessButton.classList.remove("busy");
  }
});

document.querySelector("#resetSession").addEventListener("click", async () => {
  const response = await api("/api/reset", {});
  state.snapshot = response.state;
  state.selected = state.snapshot.selected;
  render();
});

loadState().catch((error) => {
  outputPanel.textContent = error.message;
});
