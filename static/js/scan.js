// FraudScope — scan page interactions
// Currently simulates the pipeline with dummy data.
// Step 3 will swap simulateAnalysis() for a real fetch() to the Flask backend.

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

const DEMO_REPORT_ROWS = [
  { id: "TXN-4471", vendor: "Nimbus Logistics", amt: "48,900",  risk: "clear", reason: "—" },
  { id: "TXN-4472", vendor: "Aster Supplies",    amt: "12,050",  risk: "med",   reason: "Duplicate of TXN-4473, same vendor within 3 days" },
  { id: "TXN-4473", vendor: "Aster Supplies",    amt: "12,050",  risk: "med",   reason: "Duplicate of TXN-4472, same vendor within 3 days" },
  { id: "TXN-4474", vendor: "Rehman & Co",       amt: "50,000",  risk: "clear", reason: "—" },
  { id: "TXN-4475", vendor: "Vellum Traders",    amt: "49,975",  risk: "high",  reason: "Sits $25 under the 50,000 approval threshold" },
  { id: "TXN-4476", vendor: "Nimbus Logistics",  amt: "9,400",   risk: "clear", reason: "—" },
  { id: "TXN-4477", vendor: "Kestrel Freight",   amt: "150,000", risk: "high",  reason: "4.2x above account's typical transaction size" },
  { id: "TXN-4478", vendor: "Aster Supplies",    amt: "49,988",  risk: "high",  reason: "Sits $12 under the 50,000 approval threshold" },
];

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
  setTimeout(() => startAnalysis(file.name), 350);
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

let analysisInterval = null;

function startAnalysis(filename) {
  if (analysisInterval) clearInterval(analysisInterval);

  showState(analyzingState);
  analyzingSub.textContent = filename;

  const steps = [
    "Reading file…",
    "Detecting columns…",
    "Running Benford's Law check…",
    "Scanning for duplicates…",
    "Checking approval thresholds…",
    "Compiling report…",
  ];
  let i = 0;
  analyzingTitle.textContent = steps[0];
  analysisInterval = setInterval(() => {
    i++;
    if (i < steps.length) {
      analyzingTitle.textContent = steps[i];
    } else {
      clearInterval(analysisInterval);
      analysisInterval = null;
      renderReport(filename);
      showState(reportState);
    }
  }, 480);
}

// ---------- report rendering ----------
function renderReport(filename) {
  document.getElementById("reportFileName").textContent = filename;
  const table = document.getElementById("reportTable");

  const rowsHtml = DEMO_REPORT_ROWS.map(r => `
    <div class="report-row" data-risk="${r.risk}">
      <span class="c-id">${r.id}</span>
      <span class="c-vendor">${r.vendor}</span>
      <span class="c-amt">${r.amt}</span>
      <span class="risk-pill risk-${r.risk}">${r.risk === "clear" ? "clear" : r.risk === "med" ? "medium" : "high"}</span>
      <span class="c-reason">${r.reason}</span>
    </div>
  `).join("");

  table.innerHTML = `
    <div class="report-table-head">
      <span>ID</span><span>Vendor</span><span>Amount</span><span>Risk</span><span>Why it's flagged</span>
    </div>
    ${rowsHtml}
  `;
  applyFilter("all");
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
  alert("Report export will be wired up once the real detection engine is connected (Step 4).");
});