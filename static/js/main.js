// FraudScope — hero scan animation
// Purely cosmetic demo data for the landing page signature element.
// The real engine (Step 3) will replace this with actual scan results.

const DEMO_ROWS = [
  { id: "TXN-4471", vendor: "Nimbus Logistics",  amt: "48,900",  flag: null   },
  { id: "TXN-4472", vendor: "Aster Supplies",     amt: "12,050",  flag: null   },
  { id: "TXN-4473", vendor: "Aster Supplies",     amt: "12,050",  flag: "med"  }, // duplicate
  { id: "TXN-4474", vendor: "Rehman & Co",        amt: "50,000",  flag: null   },
  { id: "TXN-4475", vendor: "Vellum Traders",     amt: "49,975",  flag: "high" }, // threshold skirt
  { id: "TXN-4476", vendor: "Nimbus Logistics",   amt: "9,400",   flag: null   },
  { id: "TXN-4477", vendor: "Kestrel Freight",    amt: "150,000", flag: "high" }, // outlier
  { id: "TXN-4478", vendor: "Aster Supplies",     amt: "6,200",   flag: null   },
];

function buildTable() {
  const table = document.getElementById("scanTable");
  if (!table) return;

  table.innerHTML = DEMO_ROWS.map((row, i) => `
    <div class="scan-row" data-flag="${row.flag || ''}" style="transition-delay:${i * 60}ms">
      <span class="r-n">${String(i + 1).padStart(2, "0")}</span>
      <span class="r-id">${row.id} · ${row.vendor}</span>
      <span class="r-amt">${row.amt}</span>
      <span class="r-flag">${row.flag === "high" ? "high risk" : row.flag === "med" ? "review" : ""}</span>
    </div>
  `).join("");
}

function runScanCycle() {
  const rows = document.querySelectorAll(".scan-row");
  const status = document.getElementById("scanStatus");

  // reset
  rows.forEach(r => r.classList.remove("flagged-high", "flagged-med"));
  if (status) status.textContent = "scanning…";

  // reveal flags progressively, as if the beam is sweeping over them
  rows.forEach((row, i) => {
    const flag = row.dataset.flag;
    if (!flag) return;
    setTimeout(() => {
      row.classList.add(flag === "high" ? "flagged-high" : "flagged-med");
    }, 400 + i * 260);
  });

  setTimeout(() => {
    if (status) status.textContent = "8 rows · 2 flagged";
  }, 400 + rows.length * 260 + 200);
}

document.addEventListener("DOMContentLoaded", () => {
  buildTable();
  runScanCycle();
  // repeat the reveal in sync with the beam sweep (3.2s animation, add a pause)
  setInterval(runScanCycle, 4200);
});