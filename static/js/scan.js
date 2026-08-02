// FraudScope — scan page interactions
// Step 4: wired to the real /api/scan Flask endpoint. No more dummy data.

const uploadState = document.getElementById("uploadState");
const analyzingState = document.getElementById("analyzingState");
const reportState = document.getElementById("reportState");

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const browseBtn = document.getElementById("browseBtn");
const fileNameEl = document.getElementById("fileName");
const analyzingTitle = document.getElementById("analyzingTitle");
const analyzingSub = document.getElementById("analyzingSub");
const newScanBtn = document.getElementById("newScanBtn");
const downloadBtn = document.getElementById("downloadBtn");

// Human-readable labels + risk-dot color for each detection method.
// Backend may send any subset of these keys in method_counts.
const METHOD_META = {
  outlier:              { label: "Statistical outlier",   dot: "dot-red"   },
  threshold_skirt:      { label: "Threshold-skirting",    dot: "dot-red"   },
  duplicate:            { label: "Duplicate detection",   dot: "dot-amber" },
  round_number:         { label: "Round-number bias",     dot: "dot-amber" },
  time_anomaly:         { label: "Time-based anomaly",    dot: "dot-amber" },
  vendor_concentration: { label: "Vendor concentration",  dot: "dot-amber" },
};

// ---------- dropzone interactions ----------
browseBtn.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("click", (e) => {
  if (e.target !== browseBtn) fileInput.click();
});

["dragover", "dragenter"].forEach(evt =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach(evt =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});
fileInput.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) handleFile(file);
});

function handleFile(file) {
  fileNameEl.textContent = file.name;
  setTimeout(() => startAnalysis(file), 350);
}

// ---------- toggles ----------
// AI Narrative and Offline Mode are mutually exclusive: offline mode means
// zero external calls, so it forces AI summaries off and locks the toggle.
const aiToggle = document.getElementById("aiToggle");
const offlineToggle = document.getElementById("offlineToggle");

offlineToggle.addEventListener("click", () => {
  const goingOffline = !offlineToggle.classList.contains("toggle-on");
  offlineToggle.classList.toggle("toggle-on", goingOffline);

  if (goingOffline) {
    aiToggle.classList.remove("toggle-on");
    aiToggle.classList.add("toggle-disabled");
  } else {
    aiToggle.classList.remove("toggle-disabled");
  }
});

aiToggle.addEventListener("click", () => {
  if (aiToggle.classList.contains("toggle-disabled")) return; // locked while offline
  aiToggle.classList.toggle("toggle-on");
});

// ---------- state transitions ----------
function showState(state) {
  [uploadState, analyzingState, reportState].forEach(s => s.hidden = true);
  state.hidden = false;
}

let stepInterval = null;

const ANALYZING_STEPS = [
  "Reading file…",
  "Detecting columns…",
  "Running statistical checks…",
  "Scanning for duplicates…",
  "Checking approval thresholds…",
  "Compiling report…",
];

function startAnalysis(file) {
  if (stepInterval) clearInterval(stepInterval);

  showState(analyzingState);
  analyzingSub.textContent = file.name;

  let i = 0;
  analyzingTitle.textContent = ANALYZING_STEPS[0];
  // Cycle through step labels while the real request is in flight.
  // We stop one step short of the end and hold there until the
  // response actually comes back, so it never claims to be "done"
  // before the backend really is.
  stepInterval = setInterval(() => {
    if (i < ANALYZING_STEPS.length - 1) {
      i++;
      analyzingTitle.textContent = ANALYZING_STEPS[i];
    }
  }, 420);

  runScan(file);
}

async function runScan(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/scan", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Something went wrong while scanning this file.");
    }

    if (stepInterval) {
      clearInterval(stepInterval);
      stepInterval = null;
    }
    analyzingTitle.textContent = "Compiling report…";

    renderReport(data);
    showState(reportState);
  } catch (err) {
    if (stepInterval) {
      clearInterval(stepInterval);
      stepInterval = null;
    }
    alert(err.message || "Couldn't reach the server. Please try again.");
    fileNameEl.textContent = "";
    fileInput.value = "";
    showState(uploadState);
  }
}

// ---------- report rendering ----------
function renderReport(data) {
  document.getElementById("reportFileName").textContent = data.filename || "Report";

  renderSummaryCards(data);
  renderTable(data.rows || []);
  renderFilterTabs(data);
  renderMethodList(data.method_counts || {});
  renderAiSummary(data);

  applyFilter("all");
}

function renderSummaryCards(data) {
  const cards = document.querySelectorAll(".summary-card .summary-num");
  // Order in the DOM: total, high, medium, clear
  cards[0].textContent = data.total_rows ?? 0;
  cards[1].textContent = data.high_risk ?? 0;
  cards[2].textContent = data.medium_risk ?? 0;
  cards[3].textContent = data.clear ?? 0;
}

function renderFilterTabs(data) {
  const total = data.total_rows ?? 0;
  const high = data.high_risk ?? 0;
  const med = data.medium_risk ?? 0;

  const tabs = document.querySelectorAll(".filter-tab");
  tabs.forEach(tab => {
    const countEl = tab.querySelector("span");
    if (tab.dataset.filter === "all") countEl.textContent = total;
    if (tab.dataset.filter === "high") countEl.textContent = high;
    if (tab.dataset.filter === "med") countEl.textContent = med;
  });
}

function riskLabel(risk) {
  if (risk === "high") return "high";
  if (risk === "med") return "medium";
  return "clear";
}

function renderTable(rows) {
  const table = document.getElementById("reportTable");

  const rowsHtml = rows.map(r => `
    <div class="report-row" data-risk="${r.risk}">
      <span class="c-id">${escapeHtml(r.id)}</span>
      <span class="c-vendor">${escapeHtml(r.vendor)}</span>
      <span class="c-amt">${escapeHtml(String(r.amount))}</span>
      <span class="risk-pill risk-${r.risk}">${riskLabel(r.risk)}</span>
      <span class="c-reason">${escapeHtml(r.reason || "—")}</span>
    </div>
  `).join("");

  table.innerHTML = `
    <div class="report-table-head">
      <span>ID</span><span>Vendor</span><span>Amount</span><span>Risk</span><span>Why it's flagged</span>
    </div>
    ${rowsHtml || `<div class="report-row"><span class="c-reason">No rows to show.</span></div>`}
  `;
}

function renderMethodList(methodCounts) {
  const list = document.querySelector(".method-list");
  if (!list) return;

  const entries = Object.entries(methodCounts)
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a);

  if (entries.length === 0) {
    list.innerHTML = `<li><span class="method-count">No anomaly methods fired on this file.</span></li>`;
    return;
  }

  list.innerHTML = entries.map(([key, count]) => {
    const meta = METHOD_META[key] || { label: prettifyKey(key), dot: "dot-amber" };
    return `
      <li><span class="${meta.dot}"></span> ${meta.label} <span class="method-count">${count}</span></li>
    `;
  }).join("");
}

function renderAiSummary(data) {
  const el = document.getElementById("aiSummaryText");
  if (!el) return;

  const offline = offlineToggle.classList.contains("toggle-on");
  const aiOn = aiToggle.classList.contains("toggle-on");

  if (offline) {
    el.textContent = "Offline mode is on — no summary was generated, not even locally.";
    return;
  }
  if (!aiOn) {
    el.textContent = "AI narrative summary is turned off for this scan.";
    return;
  }

  el.textContent = buildLocalSummary(data);
}

// Placeholder local summary generator. Real Groq-based narrative comes
// in a later step — this stays honest about that instead of pretending
// to be an AI summary.
function buildLocalSummary(data) {
  const high = data.high_risk ?? 0;
  const med = data.medium_risk ?? 0;
  const total = data.total_rows ?? 0;

  if (high === 0 && med === 0) {
    return `All ${total} rows came back clear — no anomalies detected in this file.`;
  }

  const topMethod = Object.entries(data.method_counts || {})
    .sort(([, a], [, b]) => b - a)[0];

  let sentence = `${high} of ${total} transactions were flagged high risk`;
  if (med > 0) sentence += ` and ${med} medium risk`;
  sentence += ".";

  if (topMethod) {
    const meta = METHOD_META[topMethod[0]] || { label: prettifyKey(topMethod[0]) };
    sentence += ` The most common signal was ${meta.label.toLowerCase()} (${topMethod[1]} rows).`;
  }

  sentence += " (Local summary — AI-generated narrative is coming in a later step.)";
  return sentence;
}

function prettifyKey(key) {
  return key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function applyFilter(filter) {
  document.querySelectorAll(".report-row").forEach(row => {
    const risk = row.dataset.risk;
    const show = filter === "all" || risk === filter;
    row.style.display = show ? "grid" : "none";
  });
}

document.addEventListener("click", (e) => {
  if (e.target.closest(".filter-tab")) {
    const tab = e.target.closest(".filter-tab");
    document.querySelectorAll(".filter-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    applyFilter(tab.dataset.filter);
  }
});

// ---------- reset / download ----------
newScanBtn.addEventListener("click", () => {
  fileNameEl.textContent = "";
  fileInput.value = "";
  showState(uploadState);
});

downloadBtn.addEventListener("click", () => {
  alert("Report export will be wired up in a later step (PDF/report export).");
});