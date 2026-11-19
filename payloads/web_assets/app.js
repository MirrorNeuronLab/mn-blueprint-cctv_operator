const byId = (id) => document.getElementById(id);
const labels = {starting: "Preparing", ready: "Ready", running: "Running", degraded: "Needs review", stopping: "Stopping", stopped: "Stopped", error: "Needs review"};
let current;
let view = "all";
let selectedCamera = "all";
let stopped = false;
let olderPage = null;
let scope = "";
const cameraTiles = new Map();

function needsReview(camera) {
  return camera.status === "error" || Boolean(camera.error || camera.preview.error);
}

function overview(data) {
  const cameras = data.cameras;
  const attention = cameras.filter(needsReview).length;
  byId("preview-count").textContent = `${cameras.filter(camera => camera.preview.connected).length} / ${cameras.length}`;
  byId("attention-count").textContent = String(attention);
  byId("attention-count").dataset.state = attention ? "error" : "ready";
  byId("observation-count").textContent = String(data.session.total_captions || 0);
  byId("observation-count").title = "Completed observations in this run";
  byId("match-count").textContent = data.has_target ? String(data.match_count || 0) : "—";
  byId("match-count").title = data.has_target ? "Possible matches for the current monitoring goals" : "Set a monitoring goal in Chat";
  const status = byId("monitor-status");
  status.dataset.state = attention ? "degraded" : data.session.status;
  status.textContent = labels[status.dataset.state] || "Preparing";
}

function selectCamera(value) {
  selectedCamera = value;
  if (current) renderCameras(current.cameras);
}

function entry(caption) {
  const item = document.createElement("li");
  item.className = "caption";
  item.dataset.id = caption.id;
  const time = document.createElement("time");
  time.dateTime = caption.start_time;
  time.title = `${caption.start_time} – ${caption.end_time}; received ${caption.received_at}`;
  const start = new Date(caption.start_time);
  const end = new Date(caption.end_time);
  const date = start.toDateString() === new Date().toDateString() ? "" : start.toLocaleDateString() + " · ";
  time.textContent = `${date}${start.toLocaleTimeString()} – ${end.toLocaleTimeString()}`;
  item.dataset.match = caption.goal_match || "uncertain";
  const header = document.createElement("div");
  header.className = "caption-header";
  if (caption.camera) {
    const camera = document.createElement("span");
    camera.className = "caption-camera";
    camera.textContent = caption.camera;
    camera.title = caption.camera;
    header.append(camera);
  }
  header.append(time);
  if (caption.goal_match === "matched") {
    const label = document.createElement("span");
    label.className = "finding-label";
    label.textContent = "Possible match";
    header.append(label);
  }
  const body = document.createElement("div");
  body.className = "caption-body";
  const copy = document.createElement("div");
  copy.className = "caption-copy";
  const content = caption.goal_match ? caption.content : caption.content.split("```", 1)[0].trim() || "No readable window description.";
  const text = document.createElement("p");
  text.className = "caption-excerpt";
  text.textContent = content;
  const details = document.createElement("details");
  details.className = "caption-analysis";
  const summary = document.createElement("summary");
  summary.textContent = "Analysis details";
  const full = document.createElement("p");
  full.textContent = content;
  details.append(summary, full);
  copy.append(text, details);
  const matchedGoals = caption.goal_assessments?.filter((item) => item.verdict === "matched") || [];
  if (matchedGoals.length) {
    const matches = document.createElement("ul");
    matches.setAttribute("aria-label", "Possible goal matches");
    for (const {goal} of matchedGoals) {
      const match = document.createElement("li");
      match.textContent = goal;
      matches.append(match);
    }
    details.append(matches);
  }
  body.append(copy);
  if (caption.snapshot) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "snapshot";
    button.setAttribute("aria-label", `View saved frame at ${start.toLocaleTimeString()}`);
    const image = document.createElement("img");
    image.loading = "lazy";
    image.src = `api/windows/${encodeURIComponent(caption.id)}/snapshot.jpg`;
    image.alt = caption.camera ? `Saved preview from ${caption.camera}` : "Saved camera preview";
    const label = document.createElement("span");
    label.textContent = caption.snapshot.bbox_2d ? "View highlighted frame" : "View frame";
    button.append(image, label);
    button.addEventListener("click", () => {
      byId("evidence-image").src = image.src;
      byId("evidence-image").alt = image.alt;
      const source = caption.camera ? `${caption.camera} · ` : "";
      byId("evidence-caption").textContent = `${source}Preview received ${new Date(caption.snapshot.received_at).toLocaleString()} during this window.${caption.snapshot.bbox_2d ? " Box estimated on this image." : ""}`;
      byId("evidence-description").textContent = content;
      byId("evidence-dialog").showModal();
    });
    body.append(button);
  } else {
    const label = document.createElement("small");
    label.textContent = "No preview frame saved for this window.";
    copy.append(label);
  }
  item.append(header, body);
  return item;
}

function transcript(data) {
  const goal = view === "goal";
  const nextScope = JSON.stringify([data.run_id, view, goal && data.session.instruction_revision]);
  if (nextScope !== scope) {
    scope = nextScope;
    olderPage = null;
    byId("transcript").scrollTop = 0;
  }
  const rows = olderPage?.observations || (goal ? data.goal_matches : data.captions) || [];
  const list = byId("captions");
  const scroll = byId("transcript");
  const following = scroll.scrollTop < 4;
  const anchor = following ? null : [...list.children].find(el => el.getBoundingClientRect().bottom > scroll.getBoundingClientRect().top);
  const top = anchor?.getBoundingClientRect().top;
  const previous = new Map([...list.children].map(el => [el.dataset.id, el]));
  let cursor = list.firstElementChild;
  for (const caption of rows.slice().reverse()) {
    const element = previous.get(caption.id) || entry(caption);
    previous.delete(caption.id);
    if (element !== cursor) list.insertBefore(element, cursor);
    cursor = element.nextElementSibling;
  }
  for (const obsolete of previous.values()) obsolete.remove();
  if (following) scroll.scrollTop = 0;
  else if (anchor?.isConnected) scroll.scrollTop += anchor.getBoundingClientRect().top - top;
  byId("latest").hidden = !olderPage && scroll.scrollTop < 4;
  byId("earlier").hidden = !(olderPage ? olderPage.omitted_count : (goal ? data.match_count - rows.length : data.omitted_count));
  const total = goal ? data.match_count : data.captions.length + (data.omitted_count || 0);
  byId("caption-count").textContent = String(total || 0);
  byId("window-coverage").textContent = goal
    ? `Showing ${rows.length} of ${total || 0} possible matches for the current goals. Check each capture interval against its source.`
    : `Showing ${rows.length} of ${total || 0} completed windows across cameras, newest first. Activity between samples is unknown.`;
  byId("empty").hidden = rows.length > 0;
  byId("empty").textContent = !goal ? "No completed video observations yet." : data.has_target
    ? "No matches reported for these goals yet." : "Set a monitoring goal in Chat to see matches here.";
  scroll.hidden = !rows.length;
  byId("empty-review").hidden = rows.length > 0;
}

function renderCameras(cameras) {
  const grid = byId("camera-grid");
  const selector = byId("camera-select");
  if (!cameras.some(camera => String(camera.slot) === selectedCamera)) selectedCamera = "all";
  grid.classList.toggle("multiple", selectedCamera === "all" && cameras.length > 1);
  const slots = new Set(cameras.map(camera => camera.slot));
  for (const option of [...selector.options].slice(1)) {
    if (!slots.has(Number(option.value))) option.remove();
  }
  for (const [slot, tile] of cameraTiles) {
    if (!slots.has(slot)) {
      tile.querySelector(".camera-image").removeAttribute("src");
      tile.remove();
      cameraTiles.delete(slot);
    }
  }
  for (const camera of cameras) {
    let tile = cameraTiles.get(camera.slot);
    if (!tile) {
      tile = byId("camera-tile").content.firstElementChild.cloneNode(true);
      tile.querySelector(".camera-image").src = `api/preview.mjpeg?camera=${camera.slot}`;
      grid.append(tile);
      cameraTiles.set(camera.slot, tile);
      tile.querySelector(".focus-camera").addEventListener("click", () => {
        selectCamera(selectedCamera === "all" ? String(camera.slot) : "all");
      });
    }
    let option = [...selector.options].find(option => option.value === String(camera.slot));
    if (!option) {
      option = document.createElement("option");
      option.value = String(camera.slot);
      selector.append(option);
    }
    if (option.textContent !== camera.camera) option.textContent = camera.camera;
    tile.hidden = selectedCamera !== "all" && selectedCamera !== String(camera.slot);
    tile.dataset.attention = String(needsReview(camera));
    tile.setAttribute("aria-label", `Live video · ${camera.camera}`);
    tile.title = camera.camera;
    tile.querySelector(".camera-image").alt = `Current camera preview · ${camera.camera}`;
    const name = tile.querySelector(".camera-name");
    if (name.textContent !== camera.camera) name.textContent = camera.camera;
    name.title = camera.camera;
    const status = tile.querySelector(".camera-status");
    const label = labels[camera.status] || "Preparing";
    if (status.textContent !== label) status.textContent = label;
    status.dataset.state = camera.status;
    status.title = `Analysis: ${label}`;
    const badge = tile.querySelector(".preview-badge");
    const previewLabel = camera.preview.connected ? "Live preview" : camera.preview.error ? "Preview unavailable" : "Connecting";
    if (badge.textContent !== previewLabel) badge.textContent = previewLabel;
    badge.title = previewLabel;
    const focus = tile.querySelector(".focus-camera");
    const action = selectedCamera === "all" ? `Focus preview · ${camera.camera}` : "Show all cameras";
    focus.setAttribute("aria-label", action);
    focus.title = action;
    focus.hidden = cameras.length < 2;
    const preview = tile.querySelector(".preview-state");
    const message = camera.error || (camera.preview.connected ? "" : camera.preview.error || "Connecting to live video…");
    preview.hidden = !message;
    preview.title = message;
    if (preview.textContent !== message) preview.textContent = message;
  }
  selector.value = selectedCamera;
  selector.title = selector.selectedOptions[0].textContent;
  selector.disabled = cameras.length < 2;
}

function render(data) {
  current = data;
  const session = data.session;
  overview(data);
  renderCameras(data.cameras);
  const goal = byId("goal");
  const instruction = data.has_target ? session.instruction : "Monitoring general activity.";
  if (goal.textContent !== instruction) goal.textContent = instruction;
  byId("error").hidden = !(data.error || session.error);
  byId("error").textContent = data.error || session.error || "";
  transcript(data);
}

byId("camera-select").addEventListener("change", (event) => selectCamera(event.target.value));

byId("close-evidence").addEventListener("click", () => byId("evidence-dialog").close());
byId("evidence-dialog").addEventListener("close", () => byId("evidence-image").removeAttribute("src"));

byId("filters").addEventListener("change", (event) => {
  view = event.target.value;
  byId("captions").replaceChildren();
  byId("transcript").scrollTop = 0;
  if (current) transcript(current);
});
byId("earlier").addEventListener("click", async () => {
  const key = scope;
  const button = byId("earlier");
  button.disabled = true;
  try {
    const before = byId("captions").lastElementChild.dataset.id;
    const params = new URLSearchParams({view, before_id: before, revision: current.session.instruction_revision || 0});
    const response = await fetch("api/observations?" + params, {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error("Unavailable");
    const page = await response.json();
    if (scope === key) {
      olderPage = page;
      byId("transcript").scrollTop = 0;
      transcript(current);
      byId("transcript").focus();
    }
  } catch {
    byId("error").hidden = false;
    byId("error").textContent = "Couldn't load earlier observations. Try again.";
  } finally {
    button.disabled = false;
  }
});
byId("transcript").addEventListener("scroll", () => { byId("latest").hidden = !olderPage && byId("transcript").scrollTop < 4; });
byId("latest").addEventListener("click", () => {
  olderPage = null;
  byId("transcript").scrollTop = 0;
  transcript(current);
  byId("transcript").focus();
});

async function refresh() {
  try {
    const response = await fetch("api/status", {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error("Unavailable");
    render(await response.json());
  } catch {
    byId("monitor-status").textContent = "Reconnecting";
    byId("monitor-status").dataset.state = "error";
    byId("error").hidden = false;
    byId("error").textContent = "Couldn't refresh camera status. Reconnecting…";
  } finally {
    if (!stopped) setTimeout(refresh, 2000);
  }
}
window.addEventListener("pagehide", () => {stopped = true;});
window.addEventListener("pageshow", (event) => {if (event.persisted) {stopped = false; refresh();}});
refresh();
