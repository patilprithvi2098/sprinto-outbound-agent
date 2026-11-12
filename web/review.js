(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ICON = { Qualified: "check", "Sent to me": "send", Rewritten: "pencil", Disqualified: "x", Flagged: "flag", Researching: "clock" };
  const TONE = { Qualified: "wait", "Sent to me": "ok", Rewritten: "ok", Disqualified: "bad", Flagged: "warn", Researching: "wait" };
  const GROUPS = [
    { name: "Needs you", test: r => r.status === "Flagged" },
    { name: "Drafts to review", test: r => ["Qualified", "Sent to me", "Rewritten"].includes(r.status) },
    { name: "Researching", test: r => r.status === "Researching" },
    { name: "Dropped with reason", test: r => r.status === "Disqualified" },
  ];
  const narrow = window.matchMedia("(max-width: 820px)");
  let run = null, selected = null, seen = {}, shownDetail = "";

  const chip = s => `<span class="chip ${TONE[s]}"><svg aria-hidden="true"><use href="#i-${ICON[s]}"/></svg>${esc(s)}</span>`;
  const path = url => { try { return new URL(url).pathname; } catch (e) { return ""; } };
  const firstSource = r => path((r.evidence || [])[0]?.page_url || (r.pages_fetched || [])[0]?.url || "");
  const ready = r => r.verdict === "qualified" && r.draft && r.draft.grader_verdict === "ready";
  const traceLine = c => `${c.from_pack} of ${c.from_pack + c.generic + c.made_up + c.banned} sentences from the pack, ${c.generic} generic, ${c.made_up} made up, ${c.banned} banned`;

  function why(r) {
    if (r.pending) return run.finished_at || run.interrupted ? "Not researched: the run stopped before this company." : "Researching this company now.";
    if (ready(r)) return `${r.contact.position}: ${r.draft.subject}`;
    return r.reason || "";
  }

  function renderHeader() {
    const recs = run.records, n = recs.length;
    $("title").textContent = `Run of ${n} ${n === 1 ? "domain" : "domains"}`;
    const done = recs.filter(r => !r.pending).length;
    const start = new Date(run.started_at);
    let when = `Started ${start.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}`;
    if (run.finished_at) {
      const secs = Math.round((new Date(run.finished_at) - start) / 1000);
      when += `, took ${secs >= 60 ? Math.floor(secs / 60) + " min " : ""}${secs % 60} s`;
    } else if (run.interrupted) when += ". The run stopped when the server stopped";
    else when += `. Researching: ${done} of ${n} done`;
    $("run-meta").textContent = `${when}. Hunter searches used: ${run.hunter_searches_used}.`;
    $("c-need").textContent = recs.filter(r => r.status === "Flagged").length;
    $("c-ready").textContent = recs.filter(r => ["Qualified", "Sent to me", "Rewritten"].includes(r.status)).length;
    $("c-dropped").textContent = recs.filter(r => r.status === "Disqualified").length;
  }

  function renderList() {
    const detail = $("detail"); // lift the detail out of a phone card before the list is rebuilt
    if (!detail.parentElement.classList.contains("desk")) document.querySelector(".desk").appendChild(detail);
    const html = GROUPS.map(g => {
      const items = run.records.filter(g.test);
      if (!items.length) return "";
      return `<h2 class="group label">${esc(g.name)} <span class="mono">${items.length}</span></h2><ul>` + items.map(r => {
        const before = seen[r.domain];
        const cls = [before === undefined && !r.pending ? "arrive" : "", before && before !== r.status ? "changed" : ""].join(" ");
        const src = firstSource(r);
        return `<li class="${cls}" data-domain="${esc(r.domain)}"><button type="button" class="item" aria-pressed="${r.domain === selected}">` +
          `<span class="item-top"><span class="item-name">${esc(r.name || r.domain)}</span>${chip(r.status)}</span>` +
          `<span class="item-why">${esc(why(r))}</span>` +
          (src && !r.pending ? `<span class="item-src mono">${esc(r.domain)}${esc(src)}</span>` : "") + `</button></li>`;
      }).join("") + "</ul>";
    }).join("");
    $("list").innerHTML = html;
    run.records.forEach(r => { if (!r.pending) seen[r.domain] = r.status; });
    $("list").querySelectorAll(".item").forEach(b => b.addEventListener("click", () => select(b.parentElement.dataset.domain, true)));
  }

  function evidenceList(r) {
    const ev = r.evidence || [];
    if (!ev.length) return "";
    return `<ul class="evidence">` + ev.map(e => `<li><span class="label">${esc(e.field.replace("_", " "))}</span> “${esc(e.quote)}” <span class="mono src">${esc(path(e.page_url))}</span></li>`).join("") + `</ul>`;
  }

  function traceBlock(d) {
    if (!d.trace) return "";
    return `<details class="trace"><summary>Trace: ${esc(traceLine(d.counts))}</summary><ol>` +
      d.trace.map(t => `<li><span class="label">${esc(t.label)}${t.pack_field ? " · " + esc(t.pack_field) : ""}</span> ${esc(t.sentence)}${t.note ? `<span class="muted"> (${esc(t.note)})</span>` : ""}</li>`).join("") + `</ol></details>`;
  }

  function draftBlock(r) {
    const d = r.draft, c = r.contact;
    return `<p class="to"><span class="label">To</span> ${esc(c.name)}, ${esc(c.position)} <span class="mono muted">&lt;${esc(c.email)}&gt;</span></p>` +
      `<p class="subject"><span class="label">Subject</span> ${esc(d.subject)}</p><div class="body">${esc(d.body)}</div>`;
  }

  function detailHtml(r) {
    const head = `<div class="detail-head"><h2>${esc(r.name || r.domain)}</h2>${chip(r.status)}</div><p class="mono muted">${esc(r.domain)}</p>`;
    if (r.pending) return head + `<p class="muted">${esc(why(r))}</p>`;
    const flags = (r.flags || []).length ? `<ul class="flags">${r.flags.map(f => `<li><svg aria-hidden="true"><use href="#i-flag"/></svg>${esc(f)}</li>`).join("")}</ul>` : "";
    const companyWhy = r.qualify_reason || (ready(r) ? r.reason : ""); // a flagged record's reason is already shown under No draft
    const company = `<h3>Why this company</h3>${companyWhy ? `<p>${esc(companyWhy)}</p>` : ""}${evidenceList(r)}${flags}`;
    if (ready(r)) {
      const d = r.draft, rev = r.review || {}, sent = !!rev.sent_at, skipped = !!rev.skipped;
      const note = sent ? `Sent to your inbox ${new Date(rev.sent_at).toLocaleString([], { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })}.` : skipped ? "Skipped. Nothing will be sent." : "";
      return head + `<div class="draft">${draftBlock(r)}` +
        `<div class="row actions"><button class="btn primary" type="button" data-act="send" ${sent || skipped ? "disabled" : ""}>Send to my inbox</button>` +
        `<button class="btn" type="button" data-act="rewrote" ${rev.rewritten || skipped ? "disabled" : ""}>I rewrote it</button>` +
        `<button class="btn" type="button" data-act="skip" ${sent || skipped ? "disabled" : ""}>Skip</button></div>` +
        `<p class="error" id="act-error" role="alert" hidden></p><p class="muted" id="act-note">${esc(note)}</p></div>` +
        `<div class="reasons">${company}<h3>Why this person</h3><p>${esc(r.contact.why_this_person)} Hunter confidence <span class="mono">${esc(r.contact.confidence)}</span>, email ${esc(r.contact.verification_status || "unverified")}.</p>` +
        `<h3>Two pains</h3><ol class="pains">${d.pains.map(p => `<li>${esc(p.pain)} <span class="mono src">${esc(p.evidence_field)}</span></li>`).join("")}</ol>` +
        `<h3>What this role is measured on</h3><p>${esc(d.role_measured_on)}</p>${traceBlock(d)}</div>`;
    }
    if (r.status === "Disqualified") return head + `<div class="reasons"><h3>Why it was dropped</h3><p>${esc(r.reason)}</p>${evidenceList(r)}</div>`;
    const held = r.draft && r.draft.body && r.contact ? `<details class="held"><summary>See the held-back draft</summary>${draftBlock(r)}${traceBlock(r.draft)}</details>` : "";
    return head + `<div class="draft nodraft"><h3>No draft</h3><p>${esc(r.reason)}</p>` +
      `<div class="row actions"><a class="btn primary" href="https://${esc(r.domain)}/" target="_blank" rel="noopener noreferrer">Open for manual review</a></div>${held}</div>` +
      `<div class="reasons">${r.fields ? company : ""}</div>`;
  }

  function place() {
    const detail = $("detail");
    const li = selected && document.querySelector(`#list li[data-domain="${CSS.escape(selected)}"]`);
    if (narrow.matches && li) li.appendChild(detail); // phone: the selected card expands in place, email first
    else if (!detail.parentElement.classList.contains("desk")) document.querySelector(".desk").appendChild(detail);
  }

  function renderDetail(force) {
    const r = run.records.find(x => x.domain === selected);
    const html = r ? detailHtml(r) : "";
    if (force || html !== shownDetail) {
      const detail = $("detail");
      detail.innerHTML = html;
      detail.classList.remove("open"); void detail.offsetWidth; detail.classList.add("open");
      shownDetail = html;
      detail.querySelectorAll("[data-act]").forEach(b => b.addEventListener("click", () => act(r, b.dataset.act, b)));
    }
    place();
  }

  function select(domain, user) {
    selected = domain;
    renderList();
    renderDetail(true);
    if (user && narrow.matches) $("detail").scrollIntoView({ block: "nearest" });
  }

  function defaultSelection() {
    for (const g of GROUPS) { const r = run.records.find(g.test); if (r) return r.domain; }
    return null;
  }

  async function act(r, action, btn) {
    const buttons = [...$("detail").querySelectorAll("[data-act]")];
    if (btn.disabled) return; // double clicks send one email
    buttons.forEach(b => (b.disabled = true));
    const err = $("act-error");
    try {
      const res = await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: run.id, domain: r.domain, action }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "That did not work. Try again.");
      run.records[run.records.findIndex(x => x.domain === r.domain)] = data.record;
      renderHeader(); renderList(); renderDetail(true);
    } catch (e) {
      err.textContent = e.message.startsWith("Failed") ? "The app is not responding. Check that the server is still running." : e.message;
      err.hidden = false;
      renderDetailButtons(r);
    }
  }

  function renderDetailButtons(r) { // re-enable what the record allows after a failed action
    const rev = r.review || {};
    $("detail").querySelectorAll("[data-act]").forEach(b => {
      b.disabled = (b.dataset.act !== "rewrote" && (rev.sent_at || rev.skipped)) || (b.dataset.act === "rewrote" && (rev.rewritten || rev.skipped));
    });
  }

  async function load() {
    try {
      const data = await (await fetch("/api/runs/latest")).json();
      $("loading").hidden = true;
      $("load-error").hidden = true;
      if (!data.run) { $("empty").hidden = false; return; }
      run = data.run;
      $("run").hidden = false;
      if (!selected || !run.records.some(r => r.domain === selected)) selected = defaultSelection();
      renderHeader(); renderList(); renderDetail(false);
      if (!run.finished_at && !run.interrupted) setTimeout(load, 2000);
    } catch (e) {
      $("loading").hidden = true;
      $("load-error").textContent = "The app is not responding. Check that the server is still running, then reload.";
      $("load-error").hidden = false;
      if (run) setTimeout(load, 5000);
    }
  }

  async function quota() {
    try {
      const q = await (await fetch("/api/quota")).json();
      if (q.ok) $("c-hunter").textContent = `${q.searches_left} of ${q.searches_total}`;
    } catch (e) { /* the count stays "-" */ }
  }

  narrow.addEventListener("change", place);
  load();
  quota();
})();
