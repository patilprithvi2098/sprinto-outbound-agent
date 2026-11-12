(() => {
  const $ = id => document.getElementById(id);
  const form = $("run-form"), box = $("domains"), count = $("domains-count"), error = $("form-error"),
    result = $("result"), runBtn = $("run-btn"), recheck = $("recheck-btn");

  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const entries = () => box.value.split(/[\s,;]+/).filter(Boolean);
  const showCount = () => { const n = entries().length; count.textContent = n + (n === 1 ? " domain" : " domains"); };
  const showError = msg => { error.textContent = msg; error.hidden = !msg; };

  box.addEventListener("input", () => { showCount(); showError(""); });
  $("clear-btn").addEventListener("click", () => { box.value = ""; result.innerHTML = ""; showCount(); showError(""); box.focus(); });

  form.addEventListener("submit", async e => {
    e.preventDefault();
    if (runBtn.disabled) return; // a second click while the first is in flight does nothing
    if (!entries().length) { showError("Paste at least one domain."); box.focus(); return; }
    showError("");
    runBtn.disabled = true;
    try {
      const res = await fetch("/api/domains", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: box.value }) });
      const data = await res.json();
      if (!res.ok) { showError(data.error || "The list could not be checked."); return; }
      const ok = data.valid.map(d => `<li><span class="mono">${esc(d)}</span><span class="muted">ready</span></li>`).join("");
      const bad = data.rejected.map(r => `<li><span class="mono rejected-input">${esc(r.input)}</span><span class="reason">${esc(r.reason)}</span></li>`).join("");
      const n = data.valid.length, word = n === 1 ? "domain" : "domains";
      result.innerHTML =
        `<h2>${n} of ${n + data.rejected.length} accepted</h2>` +
        (n ? `<p class="muted">Up to <span class="mono">${n}</span> Hunter ${n === 1 ? "search" : "searches"} (only companies that qualify use one) and about <span class="mono">$${(n * COST_PER_COMPANY).toFixed(2)}</span> of Claude usage.</p>` +
             `<div class="row"><button class="btn primary" type="button" id="start-btn">Run ${n} ${word}</button></div>` +
             `<p class="error" id="start-error" role="alert" hidden></p>` : "") +
        (ok ? `<ul>${ok}</ul>` : "") +
        (bad ? `<h2>Left out</h2><ul>${bad}</ul>` : "");
      if (n) $("start-btn").addEventListener("click", () => startRun(data.valid));
    } catch (err) {
      showError("The app is not responding. Check that the server is still running.");
    } finally {
      runBtn.disabled = false;
    }
  });

  const COST_PER_COMPANY = 0.05; // shortcut: rough Claude cost per company from the Phase 1-2 runs, replace with logged usage in Phase 5
  const startRun = async domains => {
    const btn = $("start-btn"), err = $("start-error"), label = btn.textContent;
    if (btn.disabled) return; // a double click starts one run
    btn.disabled = true;
    btn.textContent = "Starting";
    try {
      const res = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: domains.join("\n") }) });
      const data = await res.json();
      if (res.ok) { location.href = "review.html"; return; }
      err.textContent = data.error || "The run could not start.";
    } catch (e) {
      err.textContent = "The app is not responding. Check that the server is still running.";
    }
    err.hidden = false;
    btn.disabled = false;
    btn.textContent = label;
  };

  const setChip = (name, state, label) => {
    const chip = document.querySelector(`[data-check="${name}"]`);
    const icon = { ok: "check", bad: "x", wait: "clock" }[state];
    chip.className = "chip " + state;
    chip.innerHTML = `<svg><use href="#i-${icon}"/></svg>${label}`;
  };
  const setupCheck = async () => {
    recheck.disabled = true;
    ["claude", "hunter", "gmail"].forEach(n => setChip(n, "wait", "Checking"));
    try {
      const data = await (await fetch("/api/setup-check")).json();
      for (const name of ["claude", "hunter", "gmail"]) {
        setChip(name, data[name].ok ? "ok" : "bad", data[name].ok ? "Working" : "Needs you");
        document.querySelector(`[data-detail="${name}"]`).textContent = data[name].detail;
      }
      $("quota").textContent = data.hunter.ok ? `${data.hunter.searches_left} of ${data.hunter.searches_total}` : "-";
    } catch (err) {
      ["claude", "hunter", "gmail"].forEach(n => {
        setChip(n, "bad", "Needs you");
        document.querySelector(`[data-detail="${n}"]`).textContent = "The app is not responding.";
      });
    } finally {
      recheck.disabled = false;
    }
  };
  recheck.addEventListener("click", setupCheck);
  showCount();
  setupCheck();
})();
