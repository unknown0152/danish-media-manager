const state = {
  mediaType: "movie",
  minResolution: "any",
  releases: [],
  quality: null,
  rejectionSummary: {},
  warningSummary: {},
  currentRequest: null,
  acceptedOnly: false,
  metadata: null,
  targets: { movie: [], tv: [] },
};

const statusEl = document.querySelector("#status");
const sidebarStatusEl = document.querySelector("#sidebarStatus");
const serviceMetricEl = document.querySelector("#serviceMetric");
const serviceMetricCardEl = document.querySelector("#serviceMetricCard");
const requestMetricEl = document.querySelector("#requestMetric");
const requestMetricCardEl = document.querySelector("#requestMetricCard");
const requestMetricSubEl = document.querySelector("#requestMetricSub");
const queueMetricEl = document.querySelector("#queueMetric");
const queueMetricCardEl = document.querySelector("#queueMetricCard");
const queueMetricMiniEl = document.querySelector("#queueMetricMini");
const queueMetricSubEl = document.querySelector("#queueMetricSub");
const indexerMetricEl = document.querySelector("#indexerMetric");
const indexerMetricCardEl = document.querySelector("#indexerMetricCard");
const indexerMetricMiniEl = document.querySelector("#indexerMetricMini");
const indexerMetricSubEl = document.querySelector("#indexerMetricSub");
const serviceStripEl = document.querySelector("#serviceStrip");
const metadataEl = document.querySelector("#metadata");
const searchSummaryEl = document.querySelector("#searchSummary");
const resultsEl = document.querySelector("#results");
const downloadsEl = document.querySelector("#downloads");
const importHealthEl = document.querySelector("#importHealth");
const grabsEl = document.querySelector("#grabs");
const indexersEl = document.querySelector("#indexers");
const prowlarrHealthEl = document.querySelector("#prowlarrHealth");
const requestsEl = document.querySelector("#requests");
const searchForm = document.querySelector("#searchForm");
const queryInput = document.querySelector("#query");
const minResolutionInput = document.querySelector("#minResolution");
const targetPathInput = document.querySelector("#targetPath");
const acceptedOnlyInput = document.querySelector("#acceptedOnly");
const viewTitleEl = document.querySelector("#viewTitle");
const viewSubtitleEl = document.querySelector("#viewSubtitle");
const navWantedBadgeEl = document.querySelector("#navWantedBadge");
const navDownloadBadgeEl = document.querySelector("#navDownloadBadge");
const navIndexerBadgeEl = document.querySelector("#navIndexerBadge");
const dashboardRequestsEl = document.querySelector("#dashboardRequests");
const dashboardDownloadsEl = document.querySelector("#dashboardDownloads");
const dashboardIndexersEl = document.querySelector("#dashboardIndexers");
const dashboardGrabsEl = document.querySelector("#dashboardGrabs");

const viewCopy = {
  dashboard: {
    title: "Dashboard",
    subtitle: "Service state, wanted queue, transfers, and indexer health.",
  },
  wanted: {
    title: "Wanted",
    subtitle: "Requests from Seerr and DMM that still need a matching release.",
  },
  search: {
    title: "Search",
    subtitle: "Ranked release results with Danish/NORDiC scoring and grab controls.",
  },
  downloads: {
    title: "Downloads",
    subtitle: "AltMount queue state, history, and import path checks.",
  },
  indexers: {
    title: "Indexers",
    subtitle: "Enabled Prowlarr sources and current failure state.",
  },
  health: {
    title: "Health",
    subtitle: "Diagnostics from Prowlarr, import paths, and service checks.",
  },
  activity: {
    title: "Activity",
    subtitle: "Recent grabs sent through DMM.",
  },
};

function setActiveView(view) {
  const nextView = viewCopy[view] ? view : "dashboard";
  document.querySelectorAll("[data-view]").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.view === nextView);
  });
  document.querySelectorAll(".nav-item[data-view-target]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.viewTarget === nextView);
  });
  viewTitleEl.textContent = viewCopy[nextView].title;
  viewSubtitleEl.textContent = viewCopy[nextView].subtitle;
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-view-target]");
  if (!target) {
    return;
  }
  event.preventDefault();
  const nextHash = `#${target.dataset.viewTarget}`;
  if (window.location.hash === nextHash) {
    setActiveView(target.dataset.viewTarget);
    return;
  }
  window.location.hash = nextHash;
});

window.addEventListener("hashchange", () => {
  setActiveView(window.location.hash.replace("#", "") || "dashboard");
});

window.setActiveView = setActiveView;

document.querySelectorAll(".segmented button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segmented button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.mediaType = button.dataset.type;
    renderTargetOptions();
  });
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await search(queryInput.value.trim());
});

document.querySelector("#refreshQueue").addEventListener("click", refreshQueue);
document.querySelector("#retryWanted").addEventListener("click", retryWanted);
document.querySelector("#requestBest").addEventListener("click", async () => {
  await createRequest(queryInput.value.trim());
});
minResolutionInput.addEventListener("change", () => {
  state.minResolution = minResolutionInput.value;
});
acceptedOnlyInput.addEventListener("change", () => {
  state.acceptedOnly = acceptedOnlyInput.checked;
  renderResults();
});

document.querySelectorAll("[data-set-theme]").forEach((button) => {
  button.addEventListener("click", () => {
    document.documentElement.dataset.theme = button.dataset.setTheme;
    document
      .querySelectorAll("[data-set-theme]")
      .forEach((item) => item.classList.toggle("is-active", item === button));
  });
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
    const readyCount = [status.prowlarr_ready, status.altmount_ready].filter(Boolean).length;
    const statusText = `Prowlarr ${status.prowlarr_ready ? "ready" : "not ready"} · AltMount ${
      status.altmount_ready ? "ready" : "not ready"
    }`;
    serviceMetricEl.textContent = `${readyCount}/2 Ready`;
    serviceMetricCardEl.textContent = `${readyCount} / 2`;
    statusEl.textContent = statusText;
    sidebarStatusEl.textContent = statusText;
    renderServiceStrip(status);
  } catch (error) {
    statusEl.textContent = `Status failed: ${error.message}`;
    sidebarStatusEl.textContent = "Status failed";
    serviceMetricEl.textContent = "Offline";
    serviceMetricCardEl.textContent = "Offline";
    serviceStripEl.innerHTML = "";
  }
}

function renderServiceStrip(status) {
  const cards = [
    {
      label: "Prowlarr",
      state: status.prowlarr_ready ? "Ready" : "Offline",
      ok: status.prowlarr_ready,
      detail: status.prowlarr_url,
    },
    {
      label: "AltMount",
      state: status.altmount_ready ? "Ready" : "Offline",
      ok: status.altmount_ready,
      detail: status.altmount_url,
    },
  ];
  serviceStripEl.innerHTML = cards
    .map(
      (card) => `
        <div class="service-card ${card.ok ? "ok" : "warn"}">
          <div class="service-state">
            <span class="state-dot"></span>
            <span>${escapeHtml(card.label)}</span>
          </div>
          <strong>${escapeHtml(card.state)}</strong>
          <small>${escapeHtml(card.detail)}</small>
        </div>
      `
    )
    .join("");
}

async function search(query) {
  if (!query) return;
  setActiveView("search");
  renderEmptyState("Searching", "DMM is querying Prowlarr and scoring releases against Danish/NORDiC rules.");
  try {
    const data = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        media_type: state.mediaType,
        min_resolution: state.minResolution,
        limit: 100,
      }),
    });
    state.releases = data.releases;
    state.quality = data.quality || null;
    state.metadata = data.metadata || null;
    state.rejectionSummary = data.rejection_summary || {};
    state.warningSummary = data.warning_summary || {};
    state.currentRequest = null;
    statusEl.textContent = `${data.total} results · ${data.accepted} accepted · ${data.rejected} rejected`;
    renderMetadata();
    renderSearchSummary(data.indexers || []);
    renderResults();
  } catch (error) {
    metadataEl.innerHTML = "";
    searchSummaryEl.innerHTML = "";
    renderEmptyState("Search failed", error.message, "bad");
  }
}

async function createRequest(query) {
  if (!query) return;
  setActiveView("search");
  renderEmptyState("Creating request", "DMM is storing the request and checking for an immediate match.");
  try {
    const data = await api("/api/requests", {
      method: "POST",
      body: JSON.stringify({
        query,
        media_type: state.mediaType,
        min_resolution: state.minResolution,
        target_path: targetPathInput.value || null,
        limit: 100,
      }),
    });
    state.releases = data.search.releases;
    state.quality = data.search.quality || null;
    state.metadata = data.search.metadata || null;
    state.rejectionSummary = data.search.rejection_summary || {};
    state.warningSummary = data.search.warning_summary || {};
    state.currentRequest = data.request;
    statusEl.textContent = `Request #${data.request.id} · ${data.search.total} results · ${data.search.accepted} accepted`;
    renderMetadata();
    renderSearchSummary(data.search.indexers || []);
    renderResults();
    await refreshRequests();
  } catch (error) {
    metadataEl.innerHTML = "";
    searchSummaryEl.innerHTML = "";
    renderEmptyState("Request failed", error.message, "bad");
  }
}

async function loadTargets() {
  try {
    state.targets = await api("/api/targets");
    renderTargetOptions();
  } catch (error) {
    targetPathInput.innerHTML = `<option value="">Default folder</option>`;
  }
}

function renderTargetOptions() {
  const targets = state.targets[state.mediaType] || [];
  if (!targets.length) {
    targetPathInput.innerHTML = `<option value="">Default folder</option>`;
    return;
  }
  targetPathInput.innerHTML = targets
    .map((target) => `<option value="${escapeHtml(target.path)}">${escapeHtml(target.label)}</option>`)
    .join("");
}

function renderMetadata() {
  const metadata = state.metadata;
  if (!metadata) {
    metadataEl.innerHTML = "";
    return;
  }
  const year = metadata.year ? ` (${metadata.year})` : "";
  const source = metadata.source ? ` · ${metadata.source}` : "";
  const poster = metadata.poster_url
    ? `<img src="${escapeHtml(metadata.poster_url)}" alt="" loading="lazy" />`
    : "";
  metadataEl.innerHTML = `
    ${poster}
    <div>
      <div class="title">${escapeHtml(metadata.title)}${escapeHtml(year)}</div>
      <div class="meta">Exact year ${escapeHtml(metadata.year || "unknown")}${escapeHtml(source)}</div>
      ${
        metadata.overview
          ? `<div class="meta metadata-overview">${escapeHtml(metadata.overview)}</div>`
          : ""
      }
    </div>
  `;
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
          <span>${escapeHtml(indexer.name)}</span>
          <strong>${indexer.accepted}/${indexer.total}</strong>
          <small>${escapeHtml(`accepted${score}`)}</small>
        </div>
      `;
    })
    .join("");
  if (state.quality) {
    searchSummaryEl.innerHTML += renderQualitySummary(state.quality);
  }
  searchSummaryEl.innerHTML += renderReasonSummary("Rejected", state.rejectionSummary);
  searchSummaryEl.innerHTML += renderReasonSummary("Warnings", state.warningSummary);
}

function renderQualitySummary(quality) {
  const resolutions = formatCountMap(quality.resolutions);
  const accepted = formatCountMap(quality.accepted_by_resolution);
  const best = [quality.best_resolution, quality.best_source, quality.best_score ? `score ${quality.best_score}` : ""]
    .filter(Boolean)
    .join(" · ");
  return `
    <div class="summary-chip quality-chip">
      <span>Quality</span>
      <strong>${escapeHtml(best || "no best")}</strong>
      <small>${escapeHtml(resolutions || "no resolutions")}</small>
      <small>${escapeHtml(accepted ? `accepted ${accepted}` : "none accepted")}</small>
    </div>
  `;
}

function formatCountMap(values) {
  return Object.entries(values || {})
    .map(([key, count]) => `${key} ${count}`)
    .join(" · ");
}

function renderReasonSummary(label, values) {
  const formatted = formatCountMap(values);
  if (!formatted) {
    return "";
  }
  return `
    <div class="summary-chip reason-chip">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(formatted)}</strong>
    </div>
  `;
}

function renderIndexerAttrs(release) {
  const attrs = release.indexer_attrs || {};
  const preferred = ["files", "grabs", "genre", "category", "comments"];
  const chips = preferred
    .filter((name) => attrs[name] && attrs[name].length)
    .slice(0, 5)
    .map((name) => {
      const value = attrs[name].slice(0, 3).join(", ");
      return `<span><strong>${escapeHtml(name)}</strong> ${escapeHtml(value)}</span>`;
    });
  if (!chips.length) {
    return "";
  }
  return `<div class="indexer-attrs">${chips.join("")}</div>`;
}

function renderResults() {
  if (!state.releases.length) {
    renderEmptyState("No releases found", "No matching releases came back from the enabled indexers.");
    return;
  }
  const visibleReleases = state.acceptedOnly
    ? state.releases.filter((release) => release.decision?.grab_allowed === true)
    : state.releases;
  if (!visibleReleases.length) {
    renderEmptyState("No accepted releases", "The current filter is hiding rejected results.");
    return;
  }
  resultsEl.innerHTML = "";
  visibleReleases.forEach((release) => {
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
    const verdict = release.score?.verdict || "weak";
    const qualityLabel = quality || "unknown quality";
    const releaseIndexer = release.indexer || "unknown indexer";
    const bestBadge =
      state.currentRequest?.best_result_id === release.result_id
        ? `<span class="best-tag">BEST</span>`
        : "";
    item.innerHTML = `
      <div class="score ${verdict}">
        <small>Score</small>
        <span>${release.score.score}</span>
      </div>
      <div class="release-main">
        ${
          state.currentRequest?.best_result_id === release.result_id
            ? `<div class="badge">Best pick</div>`
            : ""
        }
        <div class="title">${bestBadge}${escapeHtml(release.title)}</div>
        <div class="release-meta">
          <span>${escapeHtml(releaseIndexer)}</span>
          <span>${escapeHtml(year)}</span>
          <span>${escapeHtml(overlap)}</span>
        </div>
        ${renderIndexerAttrs(release)}
        <div class="reasons">${release.score.reasons.map(escapeHtml).join(" · ")}</div>
        ${
          notes.length
            ? `<div class="decision">${notes.map(escapeHtml).join(" · ")}</div>`
            : `<div class="decision ok">Accepted</div>`
        }
      </div>
      <div class="release-quality">
        <strong>${escapeHtml(qualityLabel)}</strong>
        <span>${size}</span>
        <span>${escapeHtml(releaseIndexer)}</span>
      </div>
      <button class="grab-action" type="button" ${decision.grab_allowed ? "" : "disabled"}>Grab</button>
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
    await refreshImportHealth();
  } catch (error) {
    downloadsEl.innerHTML = `<div>Downloads failed: ${escapeHtml(error.message)}</div>`;
  }
}

function renderDownloads(downloads) {
  const header = `
    <div class="download-summary">
      <div>
        <span>State</span>
        <strong>${escapeHtml(downloads.status || "unknown")}</strong>
      </div>
      <div>
        <span>Speed</span>
        <strong>${escapeHtml(downloads.speed || "0 B/s")}</strong>
      </div>
      ${
        downloads.size_left_mb === null || downloads.size_left_mb === undefined
          ? ""
          : `<div><span>Remaining</span><strong>${Number(downloads.size_left_mb).toFixed(1)} MB</strong></div>`
      }
    </div>
  `;
  const queue = renderDownloadGroup("Queue", downloads.queue || []);
  const history = renderDownloadGroup("History", downloads.history || []);
  const queueCount = (downloads.queue || []).length;
  const historyCount = (downloads.history || []).length;
  queueMetricEl.textContent = downloads.status || "Unknown";
  queueMetricCardEl.textContent = downloads.status || "Unknown";
  queueMetricMiniEl.textContent = downloads.status || "Unknown";
  navDownloadBadgeEl.textContent = downloads.status || "Unknown";
  queueMetricSubEl.textContent = `${queueCount} queued · ${historyCount} history · ${downloads.speed || "0 B/s"}`;
  downloadsEl.innerHTML = `${header}${queue}${history}`;
  dashboardDownloadsEl.innerHTML = `
    <div class="dashboard-row">
      <strong>${escapeHtml(downloads.status || "Unknown")}</strong>
      <span>${queueCount} queued · ${historyCount} history</span>
    </div>
    <div class="dashboard-row">
      <strong>${escapeHtml(downloads.speed || "0")}</strong>
      <span>Current AltMount speed</span>
    </div>
  `;
}

function renderDownloadGroup(label, items) {
  if (!items.length) {
    return `<div class="download-group"><div class="meta">${label}: empty</div></div>`;
  }
  return `
    <div class="download-group">
      <div class="group-label">${label}</div>
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
      <strong>${escapeHtml(item.name)}</strong>
      <div class="meta">${escapeHtml(meta)}</div>
    </div>
  `;
}

async function refreshImportHealth() {
  try {
    const health = await api("/api/import-health");
    renderImportHealth(health);
  } catch (error) {
    importHealthEl.innerHTML = `<div>Import health failed: ${escapeHtml(error.message)}</div>`;
  }
}

function renderImportHealth(health) {
  const warnings = health.warnings || [];
  const probes = [health.import_dir, health.mount_path, health.media_root]
    .map((probe) => {
      const state = probe.exists && probe.is_dir && probe.readable ? "ok" : "warn";
      return `<div class="probe ${state}"><strong>${escapeHtml(probe.path)}</strong><span>${probe.readable ? "ready" : "not ready"}</span></div>`;
    })
    .join("");
  const samples = (health.sample_symlinks || [])
    .slice(0, 3)
    .map((item) => {
      const state = item.target_under_mount && item.target_exists ? "ok" : "warn";
      return `<div class="probe ${state}"><strong>${escapeHtml(item.path)}</strong><span>${escapeHtml(item.target || "missing")}</span></div>`;
    })
    .join("");
  importHealthEl.innerHTML = `
    ${probes}
    <div class="meta">${health.symlink_count} symlinks · ${health.regular_file_count} regular files</div>
    ${warnings.map((warning) => `<div class="probe warn">${escapeHtml(warning)}</div>`).join("")}
    ${samples}
  `;
}

async function refreshGrabs() {
  try {
    const grabs = await api("/api/grabs");
    grabsEl.innerHTML = grabs
      .map(
        (grab) => `
          <div class="mini-row">
            <strong>${escapeHtml(grab.title)}</strong>
            <span>${escapeHtml(grab.created_at)}</span>
          </div>
        `
      )
      .join("");
    dashboardGrabsEl.innerHTML = grabs.length
      ? grabs
          .slice(0, 5)
          .map(
            (grab) => `
              <button class="dashboard-row text-row" type="button" data-view-target="activity">
                <strong>${escapeHtml(grab.title)}</strong>
                <span>${escapeHtml(grab.created_at)}</span>
              </button>
            `
          )
          .join("")
      : `<div class="dashboard-row"><strong>No grabs yet</strong><span>Recent grab history will appear here.</span></div>`;
  } catch (error) {
    grabsEl.innerHTML = `<div>History failed: ${escapeHtml(error.message)}</div>`;
    dashboardGrabsEl.innerHTML = `<div class="dashboard-row"><strong>History failed</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

async function refreshIndexers() {
  try {
    const [indexers, diagnostics] = await Promise.all([
      api("/api/indexers"),
      api("/api/prowlarr-diagnostics"),
    ]);
    const enabledCount = indexers.filter((indexer) => indexer.enable === true).length;
    const failureCount = (diagnostics.indexer_failures || []).length;
    indexerMetricEl.textContent = `${enabledCount}/${indexers.length}`;
    indexerMetricCardEl.textContent = `${enabledCount} / ${indexers.length}`;
    indexerMetricMiniEl.textContent = `${enabledCount} / ${indexers.length}`;
    navIndexerBadgeEl.textContent = `${enabledCount}/${indexers.length}`;
    indexerMetricSubEl.textContent =
      failureCount > 0 ? `${failureCount} failing in Prowlarr` : "No active failures";
    indexersEl.innerHTML = indexers
      .map((indexer) => {
        const state = indexer.enable === true ? "enabled" : "disabled";
        return `
          <div class="mini-row">
            <strong>${escapeHtml(indexer.name)}</strong>
            <span>${escapeHtml(indexer.protocol || "")} · ${state}</span>
          </div>
        `;
      })
      .join("");
    dashboardIndexersEl.innerHTML = `
      <button class="dashboard-row" type="button" data-view-target="indexers">
        <strong>${enabledCount} enabled</strong>
        <span>${indexers.length} total indexers</span>
      </button>
      <button class="dashboard-row ${failureCount > 0 ? "bad" : "ok"}" type="button" data-view-target="health">
        <strong>${failureCount > 0 ? `${failureCount} failing` : "No failures"}</strong>
        <span>Prowlarr diagnostics</span>
      </button>
    `;
    renderProwlarrDiagnostics(diagnostics);
  } catch (error) {
    indexersEl.innerHTML = `<div>Indexers failed: ${escapeHtml(error.message)}</div>`;
    prowlarrHealthEl.innerHTML = "";
    dashboardIndexersEl.innerHTML = `<div class="dashboard-row bad"><strong>Indexers failed</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

function renderProwlarrDiagnostics(diagnostics) {
  const failures = diagnostics.indexer_failures || [];
  const health = diagnostics.health || [];
  const hints = diagnostics.hints || [];
  if (!failures.length && !health.length && !hints.length) {
    prowlarrHealthEl.innerHTML = `<div class="probe ok">No active Prowlarr health issues</div>`;
    return;
  }
  const hintHtml = hints
    .map((item) => {
      const state = item.level === "error" ? "bad" : "warn";
      return `<div class="probe ${state}"><strong>Hint</strong><span>${escapeHtml(item.message)}</span></div>`;
    })
    .join("");
  const failureHtml = failures
    .map((item) => {
      const meta = [item.disabled_till, item.most_recent_failure, item.level].filter(Boolean).join(" · ");
      return `<div class="probe bad"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(meta || "Indexer failure")}</span></div>`;
    })
    .join("");
  const healthHtml = health
    .map((item) => {
      const label = [item.source, item.type].filter(Boolean).join(" · ");
      const state = item.type === "error" ? "bad" : "warn";
      return `<div class="probe ${state}"><strong>${escapeHtml(label || "Health")}</strong><span>${escapeHtml(item.message)}</span></div>`;
    })
    .join("");
  prowlarrHealthEl.innerHTML = `${hintHtml}${failureHtml}${healthHtml}`;
}

async function refreshRequests() {
  try {
    const requests = await api("/api/requests");
    const wantedCount = requests.filter((request) =>
      ["no_results", "search_failed", "grab_failed"].includes(request.status)
    ).length;
    const grabbedCount = requests.filter((request) => request.status === "grabbed").length;
    requestMetricEl.textContent = String(requests.length);
    requestMetricCardEl.textContent = String(requests.length);
    navWantedBadgeEl.textContent = String(wantedCount);
    requestMetricSubEl.textContent = `${wantedCount} wanted · ${grabbedCount} grabbed`;
    requestsEl.innerHTML = requests
      .map((request) => {
        const best = request.best_title ? `<div class="meta">${escapeHtml(request.best_title)}</div>` : "";
        const target = request.target_label || request.target_path || "default folder";
        const metadata = [request.metadata_title, request.metadata_year ? `(${request.metadata_year})` : ""]
          .filter(Boolean)
          .join(" ");
        const score =
          request.best_score === null || request.best_score === undefined ? "" : ` · ${request.best_score}`;
        const wanted = ["no_results", "search_failed", "grab_failed"].includes(request.status)
          ? `<span class="request-badge wanted">Wanted</span>`
          : "";
        const statusClass = request.status === "grabbed" ? "done" : wanted ? "wanted" : "neutral";
        const poster = request.metadata_poster_url
          ? `<img class="request-poster" src="${escapeHtml(request.metadata_poster_url)}" alt="" loading="lazy" />`
          : `<div class="request-poster fallback">${escapeHtml(request.media_type.slice(0, 2).toUpperCase())}</div>`;
        return `
          <div class="request ${statusClass}">
            ${poster}
            <div class="request-body">
              <div class="request-top">
                <strong>#${request.id} ${escapeHtml(request.query)}</strong>
                ${wanted}
              </div>
              <div class="request-stats">
                <span>${escapeHtml(request.media_type)}</span>
                <span>${escapeHtml(request.status)}${score}</span>
                <span>${request.accepted}/${request.total} accepted</span>
              </div>
              <div class="meta">${escapeHtml(target)}${metadata ? ` · ${escapeHtml(metadata)}` : ""}</div>
              ${best ? `<div class="request-best">${best}</div>` : ""}
              <div class="request-actions">
                <button type="button" data-search-request-id="${request.id}">Search</button>
                <button type="button" data-request-id="${request.id}" ${
                  request.best_result_id ? "" : "disabled"
                }>Grab best</button>
              </div>
            </div>
          </div>
        `;
      })
      .join("");
    requestsEl.querySelectorAll("button[data-search-request-id]").forEach((button) => {
      button.addEventListener("click", () => rerunRequestSearch(button.dataset.searchRequestId));
    });
    requestsEl.querySelectorAll("button[data-request-id]").forEach((button) => {
      button.addEventListener("click", () => grabBest(button.dataset.requestId));
    });
    dashboardRequestsEl.innerHTML = requests.length
      ? requests
          .slice(0, 5)
          .map((request) => {
            const score =
              request.best_score === null || request.best_score === undefined ? "" : ` · ${request.best_score}`;
            return `
              <button class="dashboard-row" type="button" data-view-target="wanted">
                <strong>${escapeHtml(request.query)}</strong>
                <span>${escapeHtml(request.status)}${score} · ${request.accepted}/${request.total} accepted</span>
              </button>
            `;
          })
          .join("")
      : `<div class="dashboard-row"><strong>No requests</strong><span>Seerr and DMM requests will appear here.</span></div>`;
  } catch (error) {
    requestsEl.innerHTML = `<div>Requests failed: ${escapeHtml(error.message)}</div>`;
    dashboardRequestsEl.innerHTML = `<div class="dashboard-row bad"><strong>Requests failed</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

async function rerunRequestSearch(requestId) {
  try {
    setActiveView("search");
    renderEmptyState("Searching request", "DMM is rerunning the stored request against current indexer results.");
    const data = await api(`/api/requests/${requestId}/search`, { method: "POST" });
    state.mediaType = data.request.media_type;
    state.releases = data.search.releases;
    state.quality = data.search.quality || null;
    state.metadata = data.search.metadata || null;
    state.rejectionSummary = data.search.rejection_summary || {};
    state.warningSummary = data.search.warning_summary || {};
    state.currentRequest = data.request;
    statusEl.textContent = `Request #${data.request.id} · ${data.search.total} results · ${data.search.accepted} accepted`;
    renderMetadata();
    renderSearchSummary(data.search.indexers || []);
    renderResults();
    await refreshRequests();
  } catch (error) {
    renderEmptyState("Stored request search failed", error.message, "bad");
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

async function retryWanted() {
  try {
    const result = await api("/api/wanted/retry", { method: "POST" });
    statusEl.textContent = `Wanted retry · ${result.grabbed} grabbed · ${result.skipped} still waiting · ${result.failed} failed`;
    await Promise.all([refreshRequests(), refreshQueue(), refreshGrabs()]);
  } catch (error) {
    alert(`Retry wanted failed: ${error.message}`);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return map[char];
  });
}

function renderEmptyState(title, message, tone = "neutral") {
  const className = tone === "bad" ? "empty-state bad" : "empty-state";
  resultsEl.innerHTML = `
    <div class="${className}">
      <div>
        <div class="empty-mark">DM</div>
        <strong>${escapeHtml(title)}</strong>
        <p class="muted">${escapeHtml(message)}</p>
      </div>
    </div>
  `;
}

setActiveView(window.location.hash.replace("#", "") || "dashboard");
loadStatus();
loadTargets();
refreshQueue();
refreshImportHealth();
refreshGrabs();
refreshIndexers();
refreshRequests();
