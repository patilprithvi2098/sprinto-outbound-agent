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
      result.innerHTML =
        `<h2>${data.valid.length} of ${data.valid.length + data.rejected.length} accepted</h2>` +
        `<p class="muted">The research pipeline arrives in Phase 1. For now this proves the list is clean.</p>` +
        (ok ? `<ul>${ok}</ul>` : "") +
        (bad ? `<h2>Left out</h2><ul>${bad}</ul>` : "");
    } catch (err) {
      showError("The app is not responding. Check that the server is still running.");
    } finally {
      runBtn.disabled = false;
    }
  });

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
