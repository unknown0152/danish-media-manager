const state = {
  mediaType: "movie",
  releases: [],
};

const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const queueEl = document.querySelector("#queue");
const grabsEl = document.querySelector("#grabs");
const indexersEl = document.querySelector("#indexers");
const searchForm = document.querySelector("#searchForm");
const queryInput = document.querySelector("#query");

document.querySelectorAll(".segmented button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segmented button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.mediaType = button.dataset.type;
  });
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await search(queryInput.value.trim());
});

document.querySelector("#refreshQueue").addEventListener("click", refreshQueue);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    statusEl.textContent = `Prowlarr ${status.prowlarr_ready ? "ready" : "not ready"} · AltMount ${
      status.altmount_ready ? "ready" : "not ready"
    }`;
  } catch (error) {
    statusEl.textContent = `Status failed: ${error.message}`;
  }
}

async function search(query) {
  if (!query) return;
  resultsEl.innerHTML = "<p>Searching...</p>";
  try {
    const data = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({ query, media_type: state.mediaType, limit: 100 }),
    });
    state.releases = data.releases;
    statusEl.textContent = `${data.total} results · ${data.accepted} accepted · ${data.rejected} rejected`;
    renderResults();
  } catch (error) {
    resultsEl.innerHTML = `<p>Search failed: ${escapeHtml(error.message)}</p>`;
  }
}

function renderResults() {
  if (!state.releases.length) {
    resultsEl.innerHTML = "<p>No results.</p>";
    return;
  }
  resultsEl.innerHTML = "";
  state.releases.forEach((release) => {
    const item = document.createElement("article");
    item.className = "release";
    const size = release.size ? `${(release.size / 1024 / 1024 / 1024).toFixed(2)} GiB` : "unknown size";
    const quality = [
      release.quality?.resolution,
      release.quality?.source,
      release.quality?.codec,
      release.quality?.audio,
    ]
      .filter(Boolean)
      .join(" · ");
    const decision = release.decision || { grab_allowed: false, rejections: [], warnings: [] };
    const notes = [...(decision.rejections || []), ...(decision.warnings || [])];
    item.innerHTML = `
      <div class="score ${release.score.verdict}">
        <span>${release.score.score}</span>
      </div>
      <div>
        <div class="title">${escapeHtml(release.title)}</div>
        <div class="meta">${escapeHtml(release.indexer)} · ${size}</div>
        <div class="meta">${escapeHtml(quality)}</div>
        <div class="reasons">${release.score.reasons.map(escapeHtml).join(" · ")}</div>
        ${
          notes.length
            ? `<div class="decision">${notes.map(escapeHtml).join(" · ")}</div>`
            : `<div class="decision ok">Accepted</div>`
        }
      </div>
      <button type="button" ${decision.grab_allowed ? "" : "disabled"}>Grab</button>
    `;
    const button = item.querySelector("button");
    if (decision.grab_allowed) {
      button.addEventListener("click", () => grab(release));
    }
    resultsEl.appendChild(item);
  });
}

async function grab(release) {
  try {
    await api("/api/grab", {
      method: "POST",
      body: JSON.stringify({
        title: release.title,
        media_type: state.mediaType,
        result_id: release.result_id,
        guid: release.guid,
        indexer_id: release.indexer_id,
      }),
    });
    await Promise.all([refreshQueue(), refreshGrabs()]);
  } catch (error) {
    alert(`Grab failed: ${error.message}`);
  }
}

async function refreshQueue() {
  try {
    const queue = await api("/api/queue");
    queueEl.textContent = JSON.stringify(queue, null, 2);
  } catch (error) {
    queueEl.textContent = `Queue failed: ${error.message}`;
  }
}

async function refreshGrabs() {
  try {
    const grabs = await api("/api/grabs");
    grabsEl.innerHTML = grabs
      .map((grab) => `<div>${escapeHtml(grab.created_at)} · ${escapeHtml(grab.title)}</div>`)
      .join("");
  } catch (error) {
    grabsEl.innerHTML = `<div>History failed: ${escapeHtml(error.message)}</div>`;
  }
}

async function refreshIndexers() {
  try {
    const indexers = await api("/api/indexers");
    indexersEl.innerHTML = indexers
      .map((indexer) => {
        const state = indexer.enable === true ? "enabled" : "disabled";
        return `<div>${escapeHtml(indexer.name)} · ${escapeHtml(indexer.protocol || "")} · ${state}</div>`;
      })
      .join("");
  } catch (error) {
    indexersEl.innerHTML = `<div>Indexers failed: ${escapeHtml(error.message)}</div>`;
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return map[char];
  });
}

loadStatus();
refreshQueue();
refreshGrabs();
refreshIndexers();
