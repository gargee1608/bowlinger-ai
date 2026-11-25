const uploadForm = document.querySelector("#upload-form");
const uploadError = document.querySelector("#upload-error");
const uploadButton = document.querySelector("#upload-button");
const statusPanel = document.querySelector("#status-panel");
const statusPill = document.querySelector("#status-pill");
const sessionIdEl = document.querySelector("#session-id");
const jobError = document.querySelector("#job-error");
const resultEl = document.querySelector("#result");
const userKeyInput = document.querySelector("#user-key");

const storedKey = localStorage.getItem("bowlinger_user_key");
if (storedKey) userKeyInput.value = storedKey;

let pollTimer = null;

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
    if (payload.user_key) {
      localStorage.setItem("bowlinger_user_key", payload.user_key);
      userKeyInput.value = payload.user_key;
    }
    showSession(payload);
    poll(payload.session_id);
  } catch (error) {
    uploadError.hidden = false;
    uploadError.textContent = error.message;
  } finally {
    uploadButton.disabled = false;
  }
});

function showSession(payload) {
  statusPanel.hidden = false;
  sessionIdEl.textContent = payload.session_id;
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
  const head = document.createElement("tr");
  for (const label of ["#", "Release", "Contact", "Audio check", "Shot", "Runs"]) {
    const th = document.createElement("th");
    th.textContent = label;
    head.append(th);
  }
  table.append(head);
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
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = String(value);
      tr.append(td);
    }
    table.append(tr);
  }
  resultEl.append(table);
}
