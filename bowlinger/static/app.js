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

const youtubeButton = document.querySelector("#youtube-button");
const youtubeUrl = document.querySelector("#youtube-url");
const youtubeError = document.querySelector("#youtube-error");

youtubeButton.addEventListener("click", async () => {
  youtubeError.hidden = true;
  youtubeButton.disabled = true;
  const body = new FormData();
  body.set("url", youtubeUrl.value.trim());
  if (userKeyInput.value.trim()) body.set("user_key", userKeyInput.value.trim());
  try {
    const response = await fetch("/api/sessions/youtube", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "YouTube download failed");
    remember(payload);
    showSession(payload);
    poll(payload.session_id);
  } catch (error) {
    youtubeError.hidden = false;
    youtubeError.textContent = error.message;
  } finally {
    youtubeButton.disabled = false;
  }
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
  if (!result) {
    const panel = document.querySelector("#draw-panel");
    if (panel) panel.hidden = true;
    return;
  }
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
    const geometry = result.geometry;
    if (geometry && geometry.stumps) {
      const stumps = geometry.stumps;
      rows.push(["Stump box", stumps.locked ? `${stumps.source}, fixed` : "not locked — draw one"]);
      if (stumps.manual_required) {
        rows.push(["Next step", "Analysis finished. Draw the stump box on the first frame. Nothing is waiting in the queue."]);
      }
      const roles = geometry.roles || {};
      rows.push(
        ["Batsman label", roles.batsman ? "yes" : "no"],
        ["Bowler label", roles.bowler ? "yes" : "no"],
        ["Wicketkeeper", roles.wicketkeeper ? "yes" : "no"],
        ["Fielders", String((roles.fielder || []).length)],
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
  for (const label of ["#", "Release", "Ball release", "Contact", "Audio check", "Shot", "Runs", "Outcome"]) {
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
    const ballRelease = delivery.ball_release || {};
    const cells = [
      delivery.index,
      delivery.release_time_s == null ? "—" : `${delivery.release_time_s}s`,
      ballRelease.accepted ? ballRelease.source : "not accepted",
      contact.video_detected ? `${contact.time_s}s` : "none",
      contact.audio_confirmation || "—",
      delivery.shot || "—",
      delivery.virtual_runs == null ? "—" : String(delivery.virtual_runs),
      delivery.outcome ? `${delivery.outcome} (${delivery.outcome_runs})` : "—",
    ];
    const labels = ["#", "Release", "Ball release", "Contact", "Audio check", "Shot", "Runs", "Outcome"];
    cells.forEach((value, index) => {
      const td = document.createElement("td");
      td.dataset.label = labels[index];
      td.textContent = String(value);
      tr.append(td);
    });
    body.append(tr);
  }
  resultEl.append(table);
  setupDrawing(result);
}

const drawPanel = document.querySelector("#draw-panel");
const drawNote = document.querySelector("#draw-note");
const drawCanvas = document.querySelector("#draw-canvas");
const drawError = document.querySelector("#draw-error");
let drawMode = "stumps";
let drawStart = null;
let stumpBox = null;
let frameImage = null;
const pitchEditor = createPitchEditor();
let pitchSessionId = "";

document.querySelector("#draw-stumps").addEventListener("click", () => { drawMode = "stumps"; });
document.querySelector("#draw-pitch").addEventListener("click", () => { drawMode = "pitch"; });
document.querySelector("#complete-area").addEventListener("click", () => { pitchEditor.complete(); paintDraw(); });
document.querySelector("#clear-pitch").addEventListener("click", () => { pitchEditor.clear(); paintDraw(); });
document.querySelector("#delete-point").addEventListener("click", () => { pitchEditor.removeSelected(); paintDraw(); });
document.querySelector("#save-marks").addEventListener("click", () => saveMarks(false));
document.querySelector("#analyse-marks").addEventListener("click", () => saveMarks(true));

function setupDrawing(result) {
  const stumps = result && result.geometry && result.geometry.stumps;
  if (!stumps || !sessionIdEl.textContent) {
    drawPanel.hidden = true;
    return;
  }
  drawPanel.hidden = false;
  drawNote.textContent = stumps.manual_required
    ? "The stumps were not locked in the first five frames. Draw a box on this first frame. It stays fixed for the whole clip. Click to place the pitch polygon. Complete Area closes it. A ball outside that shape is a dead ball."
    : "The stump box is fixed. Draw only if you want to replace it. Click to place pitch points, drag a point to move it, and right-click a point to remove it.";
  if (pitchSessionId !== sessionIdEl.textContent) {
    pitchSessionId = sessionIdEl.textContent;
    const saved = result.geometry && result.geometry.pitch && result.geometry.pitch.polygon;
    pitchEditor.load(saved);
  }
  const image = new Image();
  image.onload = () => {
    frameImage = image;
    drawCanvas.width = image.naturalWidth;
    drawCanvas.height = image.naturalHeight;
    paintDraw();
  };
  image.src = `/api/sessions/${encodeURIComponent(sessionIdEl.textContent)}/frames/0`;
}

function canvasPoint(event) {
  const rect = drawCanvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * (drawCanvas.width / rect.width),
    y: (event.clientY - rect.top) * (drawCanvas.height / rect.height),
  };
}

drawCanvas.addEventListener("pointerdown", (event) => {
  const point = canvasPoint(event);
  if (drawMode === "pitch") {
    pitchEditor.pointerDown(point);
    paintDraw();
    return;
  }
  drawStart = point;
});
drawCanvas.addEventListener("pointermove", (event) => {
  if (drawMode !== "pitch" || !pitchEditor.dragging) return;
  pitchEditor.pointerMove(canvasPoint(event));
  paintDraw();
});
drawCanvas.addEventListener("pointerup", (event) => {
  if (drawMode === "pitch") {
    pitchEditor.pointerUp();
    return;
  }
  if (!drawStart) return;
  const end = canvasPoint(event);
  stumpBox = [drawStart.x, drawStart.y, end.x, end.y];
  drawStart = null;
  paintDraw();
});
drawCanvas.addEventListener("contextmenu", (event) => {
  if (drawMode !== "pitch") return;
  event.preventDefault();
  const index = pitchEditor.hit(canvasPoint(event));
  if (index >= 0) {
    pitchEditor.removeAt(index);
    paintDraw();
  }
});

function paintDraw() {
  const context = drawCanvas.getContext("2d");
  context.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
  if (frameImage) context.drawImage(frameImage, 0, 0, drawCanvas.width, drawCanvas.height);
  pitchEditor.paint(context);
  strokeBox(context, stumpBox, "#e0b15c");
}

function strokeBox(context, box, color) {
  if (!box) return;
  context.strokeStyle = color;
  context.lineWidth = 3;
  context.strokeRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
}

async function saveMarks(rerun) {
  drawError.hidden = true;
  const body = {};
  if (stumpBox) body.stumps = stumpBox;
  if (pitchEditor.points.length >= 3) {
    pitchEditor.complete();
    body.pitch_polygon = pitchEditor.coordinates();
    paintDraw();
  } else if (pitchEditor.points.length) {
    drawError.hidden = false;
    drawError.textContent = "The pitch needs at least three points before it can close.";
    return;
  }
  const path = rerun ? "analyse" : "marks";
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionIdEl.textContent)}/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Could not save the pitch");
    showSession(payload);
    if (rerun && (payload.status === "queued" || payload.status === "running")) poll(payload.session_id);
  } catch (error) {
    drawError.hidden = false;
    drawError.textContent = error.message;
  }
}
