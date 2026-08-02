// FraudScope — scan page interactions
// Flow: Upload -> Confirm Columns -> Analyzing -> Report
// /api/detect-columns, /api/scan, /api/narrative, /api/export, /api/chat are all real Flask endpoints.

const uploadState = document.getElementById("uploadState");
const confirmState = document.getElementById("confirmState");
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

const confirmFileName = document.getElementById("confirmFileName");
const columnConfirmList = document.getElementById("columnConfirmList");
const thresholdInput = document.getElementById("thresholdInput");
const backToUploadBtn = document.getElementById("backToUploadBtn");
const continueScanBtn = document.getElementById("continueScanBtn");

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

// Fields shown on the Confirm Columns screen, in display order.
const CONFIRM_FIELDS = [
  { key: "amount", label: "Amount", hint: "Required — the transaction value", required: true },
  { key: "date",   label: "Date",   hint: "Optional — used for weekend / off-hours checks", required: false },
  { key: "id",     label: "ID",     hint: "Optional — falls back to row number if left blank", required: false },
  { key: "vendor", label: "Vendor / Party", hint: "Optional — groups duplicate & concentration checks", required: false },
];

const CONFIDENCE_META = {
  detected: { text: "Detected", badge: "badge-detected" },
  guessed:  { text: "Best guess — check this", badge: "badge-guessed" },
  none:     { text: "Not found — please select", badge: "badge-none" },
};

let currentFile = null;
let allColumnsCache = [];
let currentReportData = null;

// Chat state — reset on every new report, since it's tied to that scan's data.
let chatHistory = [];
let chatConsent = false;

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
  currentFile = file;
  fileNameEl.textContent = file.name;
  setTimeout(() => detectColumnsStep(file), 300);
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
  [uploadState, confirmState, analyzingState, reportState].forEach(s => s.hidden = true);
  state.hidden = false;
}

// =========================================================
// STEP 1: detect columns (quick server round-trip)
// =========================================================
async function detectColumnsStep(file) {
  showState(analyzingState);
  analyzingTitle.textContent = "Reading column headers…";
  analyzingSub.textContent = file.name;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/detect-columns", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Couldn't read this file's columns.");
    }

    buildConfirmState(file, data);
    showState(confirmState);
  } catch (err) {
    alert(err.message || "Couldn't reach the server. Please try again.");
    resetToUpload();
  }
}

function buildConfirmState(file, data) {
  confirmFileName.textContent = file.name;
  allColumnsCache = data.all_columns || [];

  columnConfirmList.innerHTML = CONFIRM_FIELDS.map(field => {
    const detectedCol = data.columns_detected?.[field.key] || "";
    const confidenceKey = data.confidence?.[field.key] || "none";
    const conf = CONFIDENCE_META[confidenceKey] || CONFIDENCE_META.none;

    const optionsHtml = buildOptionsHtml(detectedCol, field.required);

    return `
      <div class="confirm-row">
        <div class="confirm-row-label">
          <span class="confirm-field-name">${field.label}</span>
          <span class="confirm-field-hint">${field.hint}</span>
        </div>
        <select class="confirm-select" data-field="${field.key}">
          ${optionsHtml}
        </select>
        <span class="confidence-badge ${conf.badge}">${conf.text}</span>
      </div>
    `;
  }).join("");
}

function buildOptionsHtml(selectedCol, required) {
  const opts = [];
  if (!required) {
    opts.push(`<option value=""${selectedCol ? "" : " selected"}>— none —</option>`);
  }
  allColumnsCache.forEach(col => {
    const selected = col.name === selectedCol ? " selected" : "";
    const safeName = escapeHtml(col.name);
    opts.push(`<option value="${safeName}"${selected}>${safeName} (${col.dtype})</option>`);
  });
  return opts.join("");
}

backToUploadBtn.addEventListener("click", () => {
  resetToUpload();
});

continueScanBtn.addEventListener("click", () => {
  const mapping = {};
  document.querySelectorAll(".confirm-select").forEach(sel => {
    mapping[sel.dataset.field] = sel.value;
  });

  if (!mapping.amount) {
    alert("Please choose which column holds the transaction amount.");
    return;
  }

  const thresholdRaw = thresholdInput.value.trim();
  if (thresholdRaw && (isNaN(thresholdRaw) || Number(thresholdRaw) <= 0)) {
    alert("Approval limit must be a positive number, or leave it blank.");
    return;
  }
  mapping.customThreshold = thresholdRaw || null;

  startAnalysis(currentFile, mapping);
});

function resetToUpload() {
  currentFile = null;
  fileNameEl.textContent = "";
  fileInput.value = "";
  thresholdInput.value = "";
  showState(uploadState);
}

// =========================================================
// STEP 2: real scan, using the confirmed column mapping
// =========================================================
let stepInterval = null;

const SCAN_STEPS = [
  "Running statistical checks…",
  "Scanning for duplicates…",
  "Checking approval thresholds…",
  "Compiling report…",
];

function startAnalysis(file, mapping) {
  if (stepInterval) clearInterval(stepInterval);

  showState(analyzingState);
  analyzingSub.textContent = file.name;

  let i = 0;
  analyzingTitle.textContent = SCAN_STEPS[0];
  // Cycle through step labels while the real request is in flight.
  // We stop one step short of the end and hold there until the
  // response actually comes back, so it never claims to be "done"
  // before the backend really is.
  stepInterval = setInterval(() => {
    if (i < SCAN_STEPS.length - 1) {
      i++;
      analyzingTitle.textContent = SCAN_STEPS[i];
    }
  }, 420);

  runScan(file, mapping);
}

async function runScan(file, mapping) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("amount_col", mapping.amount || "");
  formData.append("date_col", mapping.date || "");
  formData.append("id_col", mapping.id || "");
  formData.append("vendor_col", mapping.vendor || "");
  formData.append("custom_threshold", mapping.customThreshold || "");

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
    resetToUpload();
  }
}

// ---------- report rendering ----------
function renderReport(data) {
  currentReportData = data;
  chatHistory = [];
  chatConsent = false;
  resetChatUI();

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

// =========================================================
// AI Narrative summary — real /api/narrative call.
// Only ever sends aggregated stats (never raw rows), and is skipped
// entirely if Offline Mode is on, matching the backend's own guardrail.
// =========================================================
async function renderAiSummary(data) {
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

  el.textContent = "Generating summary…";

  const summary = {
    total_rows: data.total_rows ?? 0,
    high_risk: data.high_risk ?? 0,
    medium_risk: data.medium_risk ?? 0,
    clear: data.clear ?? 0,
    method_counts: data.method_counts ?? {},
  };

  try {
    const response = await fetch("/api/narrative", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ offline_mode: false, summary }),
    });
    const result = await response.json();

    if (result.narrative) {
      el.textContent = result.narrative;
    } else {
      el.textContent = result.error || "AI summary is currently unavailable.";
    }
  } catch (err) {
    el.textContent = "Couldn't reach the AI summary service. Please try again.";
  }
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
  resetToUpload();
});

downloadBtn.addEventListener("click", async () => {
  if (!currentReportData) {
    alert("No report to export yet — scan a file first.");
    return;
  }

  const originalText = downloadBtn.textContent;
  downloadBtn.disabled = true;
  downloadBtn.textContent = "Generating PDF…";

  try {
    const response = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentReportData),
    });

    if (!response.ok) {
      throw new Error("Couldn't generate the PDF. Please try again.");
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "fraudscope_report.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    alert(err.message || "Couldn't reach the server. Please try again.");
  } finally {
    downloadBtn.disabled = false;
    downloadBtn.textContent = originalText;
  }
});

// =========================================================
// Chat widget — consent-aware, wired to /api/chat
// =========================================================
const chatMessages = document.getElementById("chatMessages");
const chatInput = document.getElementById("chatInput");
const chatSendBtn = document.getElementById("chatSendBtn");

function resetChatUI() {
  if (!chatMessages) return;
  chatMessages.innerHTML = `
    <div class="chat-msg chat-msg-bot">
      Ask me anything about this scan — I can answer from the summary stats.
      For row-level detail (specific vendors, amounts, IDs) I'll ask your
      permission first.
    </div>
  `;
}

function appendChatMsg(text, cls) {
  const div = document.createElement("div");
  div.className = `chat-msg ${cls}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function appendConsentPrompt(pendingQuestion) {
  const wrap = document.createElement("div");
  wrap.className = "chat-msg chat-msg-bot";
  wrap.textContent = "";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "chat-consent-btn";
  btn.textContent = "Allow access to answer this";
  btn.addEventListener("click", () => {
    chatConsent = true;
    btn.disabled = true;
    btn.textContent = "Access allowed ✓";
    sendChatMessage(pendingQuestion, true);
  });

  wrap.appendChild(document.createTextNode("I don't have access to your transaction data for that. "));
  wrap.appendChild(document.createElement("br"));
  wrap.appendChild(btn);
  chatMessages.appendChild(wrap);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatMessage(message, isRetry = false) {
  if (!currentReportData) return;

  const offline = offlineToggle.classList.contains("toggle-on");
  if (offline) {
    appendChatMsg("Offline mode is on — the chatbot is disabled while it's active.", "chat-msg-error");
    return;
  }

  if (!isRetry) {
    appendChatMsg(message, "chat-msg-user");
  }

  chatInput.disabled = true;
  chatSendBtn.disabled = true;
  const typingEl = appendChatMsg("Thinking…", "chat-msg-typing");

  const summary = {
    total_rows: currentReportData.total_rows ?? 0,
    high_risk: currentReportData.high_risk ?? 0,
    medium_risk: currentReportData.medium_risk ?? 0,
    clear: currentReportData.clear ?? 0,
    method_counts: currentReportData.method_counts ?? {},
  };

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: chatHistory,
        summary,
        rows: chatConsent ? (currentReportData.rows ?? []) : [],
        consent: chatConsent,
        offline_mode: false,
      }),
    });
    const result = await response.json();
    typingEl.remove();

    if (result.error) {
      appendChatMsg(result.error, "chat-msg-error");
      return;
    }

    if (result.needs_data_access) {
      appendConsentPrompt(message);
      // Don't add this exchange to history — we're about to retry it with consent.
      return;
    }

    appendChatMsg(result.answer, "chat-msg-bot");
    chatHistory.push({ role: "user", content: message });
    chatHistory.push({ role: "assistant", content: result.answer });
  } catch (err) {
    typingEl.remove();
    appendChatMsg("Couldn't reach the chat service. Please try again.", "chat-msg-error");
  } finally {
    chatInput.disabled = false;
    chatSendBtn.disabled = false;
    chatInput.focus();
  }
}

chatSendBtn.addEventListener("click", () => {
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  sendChatMessage(message);
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    chatSendBtn.click();
  }
});