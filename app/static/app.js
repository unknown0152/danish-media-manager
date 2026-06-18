const state = {
  mediaType: "movie",
  releases: [],
  currentRequest: null,
};

const statusEl = document.querySelector("#status");
const searchSummaryEl = document.querySelector("#searchSummary");
const resultsEl = document.querySelector("#results");
const downloadsEl = document.querySelector("#downloads");
const grabsEl = document.querySelector("#grabs");
const indexersEl = document.querySelector("#indexers");
const requestsEl = document.querySelector("#requests");
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
document.querySelector("#requestBest").addEventListener("click", async () => {
  await createRequest(queryInput.value.trim());
});

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
    state.currentRequest = null;
    statusEl.textContent = `${data.total} results · ${data.accepted} accepted · ${data.rejected} rejected`;
    renderSearchSummary(data.indexers || []);
    renderResults();
  } catch (error) {
    searchSummaryEl.innerHTML = "";
    resultsEl.innerHTML = `<p>Search failed: ${escapeHtml(error.message)}</p>`;
  }
}

async function createRequest(query) {
  if (!query) return;
  resultsEl.innerHTML = "<p>Creating request...</p>";
  try {
    const data = await api("/api/requests", {
      method: "POST",
      body: JSON.stringify({ query, media_type: state.mediaType, limit: 100 }),
    });
    state.releases = data.search.releases;
    state.currentRequest = data.request;
    statusEl.textContent = `Request #${data.request.id} · ${data.search.total} results · ${data.search.accepted} accepted`;
    renderSearchSummary(data.search.indexers || []);
    renderResults();
    await refreshRequests();
  } catch (error) {
    searchSummaryEl.innerHTML = "";
    resultsEl.innerHTML = `<p>Request failed: ${escapeHtml(error.message)}</p>`;
  }
}

function renderSearchSummary(indexers) {
  if (!indexers.length) {
    searchSummaryEl.innerHTML = "";
    return;
  }
  searchSummaryEl.innerHTML = indexers
    .map((indexer) => {
      const score =
        indexer.best_score === null || indexer.best_score === undefined ? "" : ` · best ${indexer.best_score}`;
      return `
        <div class="summary-chip">
          <strong>${escapeHtml(indexer.name)}</strong>
          <span>${indexer.accepted}/${indexer.total} accepted${score}</span>
        </div>
      `;
    })
    .join("");
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
    if (state.currentRequest?.best_result_id === release.result_id) {
      item.classList.add("best");
    }
    const size = release.size ? `${(release.size / 1024 / 1024 / 1024).toFixed(2)} GiB` : "unknown size";
    const quality = [
      release.quality?.resolution,
      release.quality?.source,
      release.quality?.codec,
      release.quality?.audio,
      ...(release.quality?.hdr || []),
    ]
      .filter(Boolean)
      .join(" · ");
    const decision = release.decision || { grab_allowed: false, rejections: [], warnings: [] };
    const notes = [...(decision.rejections || []), ...(decision.warnings || [])];
    const year =
      release.title_match?.release_year === null || release.title_match?.release_year === undefined
        ? "unknown year"
        : release.title_match.release_year;
    const overlap =
      release.title_match?.token_overlap === null || release.title_match?.token_overlap === undefined
        ? "unknown match"
        : `${Math.round(release.title_match.token_overlap * 100)}% title match`;
    item.innerHTML = `
      <div class="score ${release.score.verdict}">
        <span>${release.score.score}</span>
      </div>
      <div>
        ${
          state.currentRequest?.best_result_id === release.result_id
            ? `<div class="badge">Best pick</div>`
            : ""
        }
        <div class="title">${escapeHtml(release.title)}</div>
        <div class="meta">${escapeHtml(release.indexer)} · ${size}</div>
        <div class="meta">${escapeHtml(quality)}</div>
        <div class="meta">${escapeHtml(year)} · ${escapeHtml(overlap)}</div>
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
    const downloads = await api("/api/downloads");
    renderDownloads(downloads);
  } catch (error) {
    downloadsEl.innerHTML = `<div>Downloads failed: ${escapeHtml(error.message)}</div>`;
  }
}

function renderDownloads(downloads) {
  const header = `
    <div class="download-summary">
      <strong>${escapeHtml(downloads.status || "unknown")}</strong>
      <span>${escapeHtml(downloads.speed || "0 B/s")}</span>
      ${
        downloads.size_left_mb === null || downloads.size_left_mb === undefined
          ? ""
          : `<span>${Number(downloads.size_left_mb).toFixed(1)} MB left</span>`
      }
    </div>
  `;
  const queue = renderDownloadGroup("Queue", downloads.queue || []);
  const history = renderDownloadGroup("History", downloads.history || []);
  downloadsEl.innerHTML = `${header}${queue}${history}`;
}

function renderDownloadGroup(label, items) {
  if (!items.length) {
    return `<div class="download-group"><div class="meta">${label}: empty</div></div>`;
  }
  return `
    <div class="download-group">
      <div class="meta">${label}</div>
      ${items.map(renderDownloadItem).join("")}
    </div>
  `;
}

function renderDownloadItem(item) {
  const size =
    item.size_mb === null || item.size_mb === undefined ? "" : `${Number(item.size_mb).toFixed(1)} MB`;
  const progress =
    item.progress_percent === null || item.progress_percent === undefined
      ? ""
      : `${Number(item.progress_percent).toFixed(0)}%`;
  const meta = [item.status, item.category, size, progress, item.time_left].filter(Boolean).join(" · ");
  return `
    <div class="download-item">
      <div>${escapeHtml(item.name)}</div>
      <div class="meta">${escapeHtml(meta)}</div>
    </div>
  `;
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

async function refreshRequests() {
  try {
    const requests = await api("/api/requests");
    requestsEl.innerHTML = requests
      .map((request) => {
        const best = request.best_title ? `<div class="meta">${escapeHtml(request.best_title)}</div>` : "";
        const score =
          request.best_score === null || request.best_score === undefined ? "" : ` · ${request.best_score}`;
        return `
          <div class="request">
            <div><strong>#${request.id}</strong> ${escapeHtml(request.query)}${score}</div>
            <div class="meta">${escapeHtml(request.media_type)} · ${escapeHtml(request.status)} · ${
              request.accepted
            }/${request.total} accepted</div>
            ${best}
            <button type="button" data-request-id="${request.id}" ${
              request.best_result_id ? "" : "disabled"
            }>Grab best</button>
          </div>
        `;
      })
      .join("");
    requestsEl.querySelectorAll("button[data-request-id]").forEach((button) => {
      button.addEventListener("click", () => grabBest(button.dataset.requestId));
    });
  } catch (error) {
    requestsEl.innerHTML = `<div>Requests failed: ${escapeHtml(error.message)}</div>`;
  }
}

async function grabBest(requestId) {
  try {
    await api(`/api/requests/${requestId}/grab-best`, { method: "POST" });
    await Promise.all([refreshQueue(), refreshGrabs(), refreshRequests()]);
  } catch (error) {
    alert(`Grab best failed: ${error.message}`);
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
refreshRequests();
