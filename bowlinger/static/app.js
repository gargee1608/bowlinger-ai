const uploadForm = document.querySelector("#upload-form");
const uploadError = document.querySelector("#upload-error");
const uploadButton = document.querySelector("#upload-button");
const statusPanel = document.querySelector("#status-panel");
const statusPill = document.querySelector("#status-pill");
const sessionIdEl = document.querySelector("#session-id");
const jobError = document.querySelector("#job-error");
const resultEl = document.querySelector("#result");
const userKeyInput = document.querySelector("#user-key");

const storageLine = document.querySelector("#storage-line");
const storedKey = localStorage.getItem("bowlinger_user_key");
if (storedKey) {
  userKeyInput.value = storedKey;
  refreshStorage();
}

const demoButton = document.querySelector("#demo-button");
const demoError = document.querySelector("#demo-error");
const lookupForm = document.querySelector("#lookup-form");
const lookupId = document.querySelector("#lookup-id");
const lookupError = document.querySelector("#lookup-error");

let pollTimer = null;

function sessionFromLocation() {
  const query = new URLSearchParams(location.search).get("session");
  if (query) return query;
  const match = location.pathname.match(/^\/s\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

demoButton.addEventListener("click", async () => {
  demoError.hidden = true;
  demoButton.disabled = true;
  const body = new FormData();
  if (userKeyInput.value.trim()) body.set("user_key", userKeyInput.value.trim());
  try {
    const response = await fetch("/api/demo", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Demo failed");
    remember(payload);
    showSession(payload);
    poll(payload.session_id);
  } catch (error) {
    demoError.hidden = false;
    demoError.textContent = error.message;
  } finally {
    demoButton.disabled = false;
  }
});

lookupForm.addEventListener("submit", (event) => {
  event.preventDefault();
  lookupError.hidden = true;
  openSession(lookupId.value.trim());
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  uploadError.hidden = true;
  uploadButton.disabled = true;
  const body = new FormData(uploadForm);
  if (!userKeyInput.value.trim()) body.delete("user_key");
  try {
    const response = await fetch("/api/sessions", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Upload failed");
    remember(payload);
    showSession(payload);
    poll(payload.session_id);
  } catch (error) {
    uploadError.hidden = false;
    uploadError.textContent = error.message;
  } finally {
    uploadButton.disabled = false;
  }
});

function formatBytes(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

async function refreshStorage() {
  const key = userKeyInput.value.trim();
  if (!key) return;
  const response = await fetch(`/api/users/${encodeURIComponent(key)}`);
  if (!response.ok) return;
  const usage = await response.json();
  storageLine.hidden = false;
  storageLine.textContent = `${formatBytes(usage.used_bytes)} of ${formatBytes(usage.quota_bytes)} used. The oldest session is removed first when a new video does not fit.`;
}

function remember(payload) {
  if (!payload.user_key) return;
  localStorage.setItem("bowlinger_user_key", payload.user_key);
  userKeyInput.value = payload.user_key;
  refreshStorage();
}

async function openSession(sessionId) {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    lookupError.hidden = false;
    lookupError.textContent = payload.detail || "Session not found";
    return;
  }
  showSession(payload);
  if (payload.status === "queued" || payload.status === "running") poll(payload.session_id);
}

function showSession(payload) {
  statusPanel.hidden = false;
  sessionIdEl.textContent = payload.session_id;
  lookupId.value = payload.session_id;
  const next = `/s/${payload.session_id}`;
  if (location.pathname !== next) history.replaceState(null, "", next);
  setStatus(payload.status);
  jobError.hidden = !payload.error;
  jobError.textContent = payload.error || "";
  renderResult(payload.result);
}

function setStatus(status) {
  statusPill.textContent = status;
  statusPill.className = `pill ${status}`;
}

function poll(sessionId) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const response = await fetch(`/api/sessions/${sessionId}`);
    if (!response.ok) return;
    const payload = await response.json();
    showSession(payload);
    if (payload.status === "completed" || payload.status === "failed") {
      clearInterval(pollTimer);
    }
  }, 800);
}

const initial = sessionFromLocation();
if (initial) openSession(initial);

function renderResult(result) {
  resultEl.replaceChildren();
  if (!result) return;
  const video = result.video;
  if (video) {
    const table = document.createElement("table");
    table.className = "facts";
    const rows = [
      ["Frame rate", `${Number(video.fps).toFixed(2)} FPS`],
      ["Resolution", `${video.width}×${video.height}`],
      ["Frames", String(video.frame_count)],
      ["Duration", `${video.duration_s} s`],
      ["Audio stream", video.has_audio_stream ? "yes" : "no"],
    ];
    const pre = result.preanalysis;
    if (pre) {
      rows.push(
        ["Stumps", pre.stumps_detected ? `${pre.stump_count} uprights` : "not seen"],
        ["Ball", pre.ball_type],
        ["Batsman on crease", pre.batsman_on_crease ? "yes" : "no"],
        ["Audio present", pre.audio_present ? "yes" : "no"],
      );
    }
    for (const [label, value] of rows) {
      const tr = document.createElement("tr");
      const th = document.createElement("td");
      const td = document.createElement("td");
      th.textContent = label;
      td.textContent = value;
      tr.append(th, td);
      table.append(tr);
    }
    resultEl.append(table);
  }
  for (const warning of (result.quality && result.quality.warnings) || []) {
    const note = document.createElement("p");
    note.className = "warn";
    note.textContent = warning;
    resultEl.append(note);
  }
  const deliveries = result.deliveries || [];
  if (!deliveries.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "No deliveries were found in this clip.";
    resultEl.append(empty);
    return;
  }
  const table = document.createElement("table");
  table.className = "deliveries";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const label of ["#", "Release", "Contact", "Audio check", "Shot", "Runs"]) {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.append(th);
  }
  head.append(headRow);
  const body = document.createElement("tbody");
  table.append(head, body);
  for (const delivery of deliveries) {
    const tr = document.createElement("tr");
    const contact = delivery.contact || {};
    const cells = [
      delivery.index,
      delivery.release_time_s == null ? "—" : `${delivery.release_time_s}s`,
      contact.video_detected ? `${contact.time_s}s` : "none",
      contact.audio_confirmation || "—",
      delivery.shot || "—",
      delivery.virtual_runs == null ? "—" : String(delivery.virtual_runs),
    ];
    const labels = ["#", "Release", "Contact", "Audio check", "Shot", "Runs"];
    cells.forEach((value, index) => {
      const td = document.createElement("td");
      td.dataset.label = labels[index];
      td.textContent = String(value);
      tr.append(td);
    });
    body.append(tr);
  }
  resultEl.append(table);
}
