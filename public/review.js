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
  const calm = window.matchMedia("(prefers-reduced-motion: no-preference)");
  let run = null, selected = null, seen = {}, shownDetail = "", bars = [], mapped = new Set();

  const chip = s => `<span class="chip ${TONE[s]}"><svg aria-hidden="true"><use href="#i-${ICON[s]}"/></svg>${esc(s)}</span>`;
  const path = url => { try { return new URL(url).pathname; } catch (e) { return ""; } };
  const firstSource = r => path((r.evidence || [])[0]?.page_url || (r.pages_fetched || [])[0]?.url || "");
  const ready = r => r.verdict === "qualified" && r.draft && r.draft.grader_verdict === "ready";
  const traceLine = c => `${c.from_pack} of ${c.from_pack + c.generic + c.made_up + c.banned} sentences from the pack, ${c.generic} generic, ${c.made_up} made up, ${c.banned} banned`;

  function why(r) {
    if (r.pending) return "Researching this company now.";
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
    } else when += `. Researching: ${done} of ${n} done`;
    $("run-meta").textContent = `${when}. Hunter searches used: ${run.hunter_searches_used}.` +
      (run.corrections_paused ? " Your corrections were not applied to this run: more than half of the last run's drafts were skipped." : "");
    count("c-need", recs.filter(r => r.status === "Flagged").length);
    count("c-ready", recs.filter(r => ["Qualified", "Sent to me", "Rewritten"].includes(r.status)).length);
    count("c-sent", recs.filter(r => (r.review || {}).sent_at).length);
    count("c-dropped", recs.filter(r => r.status === "Disqualified").length);
  }

  function count(id, to) { // a changed number counts up to its new value, so the eye is drawn to what moved
    const el = $(id), from = +el.textContent || 0;
    if (from === to || !calm.matches) { el.textContent = to; return; }
    const t0 = performance.now();
    const tick = t => { const k = Math.min(1, (t - t0) / 500); el.textContent = Math.round(from + (to - from) * k); if (k < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  // The reach map: each person we wrote to sits in the lane of their role (config/icp.json role_priority, tier 1 to 4).
  const LANES = ["Security, compliance or risk", "Engineering leadership", "Operations", "CEO or founder"];
  function renderBoard() {
    const recs = run.records, n = recs.length, done = recs.filter(r => !r.pending);
    const reached = done.filter(r => r.contact && r.draft && r.draft.body);
    const steps = [["Pasted", n], ["Researched", done.length], ["Qualified", done.filter(r => r.verdict === "qualified" || r.contact).length],
      ["Contact found", done.filter(r => r.contact).length], ["Drafted", reached.length], ["Sent to me", done.filter(r => (r.review || {}).sent_at).length]];
    $("funnel").innerHTML = steps.map(([label, v], i) => `<div><span>${label}</span><i class="${bars[i] === v ? "" : "grow"}" style="--w:${n ? v / n * 100 : 0}"></i><b class="mono">${v}</b></div>`).join("");
    bars = steps.map(x => x[1]);
    const fresh = d => (mapped.has(d) ? "" : " arrive");
    const who = r => `<button type="button" class="who${fresh(r.domain)}" data-domain="${esc(r.domain)}" aria-pressed="${r.domain === selected}">` +
      `<span class="who-co mono">${esc(r.name || r.domain)} · ${esc(r.domain)}</span>` +
      `<span class="who-name">${esc(r.contact.name)} <span class="mono">${esc(r.contact.position)}</span>${chip(r.status)}</span>` +
      (r.draft.role_measured_on ? `<span class="who-about">${esc(r.draft.role_measured_on)}</span>` : "") +
      ((r.fields || {}).trigger ? `<span class="who-why">Why now: ${esc(r.fields.trigger)}</span>` : "") + `</button>`;
    const lane = r => Math.min(Math.max(r.contact.role_tier || 4, 1), 4) - 1;
    const missed = done.filter(r => !reached.includes(r));
    $("reach").innerHTML = `<div class="lanes">` + LANES.map((label, i) => {
      const people = reached.filter(r => lane(r) === i);
      return `<div class="lane"><p class="label">Priority ${i + 1} · <b>${label}</b></p>${people.map(who).join("") || `<p class="none">No one reached in this role.</p>`}</div>`;
    }).join("") + `</div>` + (missed.length ? `<p class="label sub">Not reached, and why <span class="mono">${missed.length}</span></p><div class="missed">` +
      missed.map(r => `<button type="button" class="miss${fresh(r.domain)}" data-domain="${esc(r.domain)}" aria-pressed="${r.domain === selected}" title="${esc(r.reason || "")}"><b>${esc(r.name || r.domain)}</b> ${esc(r.reason || "")}</button>`).join("") + `</div>` : "");
    done.forEach(r => mapped.add(r.domain));
    $("reach").querySelectorAll("[data-domain]").forEach(b => b.addEventListener("click", () => {
      select(b.dataset.domain, true);
      $("detail").scrollIntoView({ block: "nearest", behavior: calm.matches ? "smooth" : "auto" });
    }));
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

  function editableDraft(r) {
    const d = r.draft, c = r.contact, rev = r.review || {}, locked = !!(rev.sent_at || rev.skipped);
    const subject = rev.edited ? rev.edited.subject : d.subject, body = rev.edited ? rev.edited.body : d.body;
    const ro = locked ? "readonly" : "";
    return `<p class="to"><span class="label">To</span> ${esc(c.name)}, ${esc(c.position)} <span class="mono muted">&lt;${esc(c.email)}&gt;</span></p>` +
      `<label class="label" for="ed-subject">Subject</label><input id="ed-subject" class="field subject-field" type="text" maxlength="200" autocomplete="off" value="${esc(subject)}" ${ro}>` +
      `<label class="label" for="ed-body">Email</label><textarea id="ed-body" class="field body-field" maxlength="5000" rows="12" ${ro}>${esc(body)}</textarea>` +
      (locked ? "" : `<p class="hint" id="ed-hint">Edit the subject or the email before sending. Your changes teach the next drafts.</p>` +
        `<label class="label" for="ed-reason">Why did you change it? (optional)</label><input id="ed-reason" class="field" type="text" maxlength="1000" autocomplete="off" placeholder="Too long. Ask about ISO 27001, not SOC 2.">`);
  }

  function detailHtml(r) {
    const head = `<div class="detail-head"><h2>${esc(r.name || r.domain)}</h2>${chip(r.status)}</div><p class="mono muted">${esc(r.domain)}</p>`;
    if (r.pending) return head + `<p class="muted">${esc(why(r))}</p>`;
    const flags = (r.flags || []).length ? `<ul class="flags">${r.flags.map(f => `<li><svg aria-hidden="true"><use href="#i-flag"/></svg>${esc(f)}</li>`).join("")}</ul>` : "";
    // a flagged record's reason is already shown under No draft, so it is not repeated here
    const companyWhy = ready(r) ? (r.qualify_reason || r.reason) : (r.qualify_reason !== r.reason ? r.qualify_reason || "" : "");
    const companyBody = `${companyWhy ? `<p>${esc(companyWhy)}</p>` : ""}${evidenceList(r)}${flags}`;
    const company = companyBody ? `<h3>Why this company</h3>${companyBody}` : "";
    if (ready(r)) {
      const d = r.draft, rev = r.review || {}, sent = !!rev.sent_at, skipped = !!rev.skipped;
      const learned = rev.correction ? (rev.correction.saved ? " Saved to the feedback loop." : ` Not saved to the feedback loop: ${rev.correction.note}.`) : "";
      const parts = (rev.changed_parts || []).length ? ` You changed: ${rev.changed_parts.join(", ")}.` : "";
      const note = (sent ? `Sent to your inbox ${new Date(rev.sent_at).toLocaleString([], { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })}.${parts || (rev.disagreement === 0 && !rev.rewritten ? " Sent as written, so nothing was stored for the feedback loop." : "")}` : skipped ? "Skipped. Nothing will be sent." : "") + learned;
      const used = ((r.feedback_loop || {}).corrections_used || []).length;
      const loopLine = used ? `<p>Written with ${used} of your earlier ${used === 1 ? "correction" : "corrections"} in mind.${r.feedback_loop.pattern ? " " + esc(r.feedback_loop.pattern) : ""}</p>` : "";
      return head + `<div class="draft">${editableDraft(r)}` +
        `<div class="row actions"><button class="btn primary" type="button" data-act="send" ${sent || skipped ? "disabled" : ""}>Send to my inbox</button>` +
        `<button class="btn" type="button" data-act="rewrote" ${rev.rewritten || skipped ? "disabled" : ""}>I rewrote it</button>` +
        `<button class="btn" type="button" data-act="skip" ${sent || skipped ? "disabled" : ""}>Skip</button></div>` +
        `<p class="error" id="act-error" role="alert" hidden></p><p class="muted" id="act-note">${esc(note)}</p></div>` +
        `<div class="reasons">${company}<h3>Why this person</h3><p>${esc(r.contact.why_this_person)} Hunter confidence <span class="mono">${esc(r.contact.confidence)}</span>, email ${esc(r.contact.verification_status || "unverified")}.</p>` +
        `<h3>Two pains</h3><ol class="pains">${d.pains.map(p => `<li>${esc(p.pain)} <span class="mono src">${esc(p.evidence_field)}</span></li>`).join("")}</ol>` +
        `<h3>What this role is measured on</h3><p>${esc(d.role_measured_on)}</p>${loopLine ? "<h3>What it learned from you</h3>" + loopLine : ""}${traceBlock(d)}</div>`;
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
    const typing = !force && $("detail").contains(document.activeElement) && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
    if (!typing && (force || html !== shownDetail)) {
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
    document.querySelectorAll("#reach [data-domain]").forEach(b => b.setAttribute("aria-pressed", b.dataset.domain === selected));
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
    const err = $("act-error");
    const payload = { run_id: run.id, domain: r.domain, action };
    if (action !== "rewrote" && $("ed-reason")) payload.reason = $("ed-reason").value;
    if (action === "send" && $("ed-body")) {
      payload.subject = $("ed-subject").value; payload.body = $("ed-body").value;
      if (!payload.subject.trim() || !payload.body.trim()) {
        err.textContent = "The email needs a subject and a body."; err.hidden = false;
        (payload.subject.trim() ? $("ed-body") : $("ed-subject")).focus();
        return;
      }
    }
    buttons.forEach(b => (b.disabled = true));
    try {
      const res = signInIfNeeded(await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "That did not work. Try again.");
      run.records[run.records.findIndex(x => x.domain === r.domain)] = data.record;
      renderHeader(); renderBoard(); renderList(); renderDetail(true); loop();
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

  function show(newRun) {
    run = newRun;
    $("run").hidden = false;
    if (!selected || !run.records.some(r => r.domain === selected)) selected = defaultSelection();
    renderHeader(); renderBoard(); renderList(); renderDetail(false);
  }

  async function load() {
    try {
      const data = await signInIfNeeded(await fetch("/api/runs/latest")).json();
      $("loading").hidden = true;
      $("load-error").hidden = true;
      if (!data.run) { $("empty").hidden = false; return; }
      show(data.run);
      if (!run.finished_at) research();
    } catch (e) {
      if (e.message === "Signing in") return;
      $("loading").hidden = true;
      $("load-error").textContent = "The app is not responding. Check that the server is still running, then reload.";
      $("load-error").hidden = false;
      if (run) setTimeout(load, 5000);
    }
  }

  // The server researches one company per request (serverless functions stop when they answer), so this
  // page keeps asking until every company is done. Closing the page pauses the run; opening it resumes.
  async function research() {
    while (run && !run.finished_at) {
      try {
        const res = signInIfNeeded(await fetch("/api/step", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: run.id }) }));
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "step failed");
        show(data.run);
        quota();
      } catch (e) {
        if (e.message === "Signing in") return;
        $("load-error").textContent = "Research paused: the app did not answer. It will try again in a few seconds.";
        $("load-error").hidden = false;
        await new Promise(r => setTimeout(r, 5000));
        $("load-error").hidden = true;
      }
    }
  }

  async function quota() {
    try {
      const q = await signInIfNeeded(await fetch("/api/quota")).json();
      if (q.ok) $("c-hunter").textContent = `${q.searches_left} of ${q.searches_total}`;
    } catch (e) { /* the count stays "-" */ }
  }

  async function loop() {
    try {
      const f = await signInIfNeeded(await fetch("/api/feedback")).json();
      $("c-disagree").textContent = f.avg_disagreement === null ? "-" : Math.round(f.avg_disagreement * 100) + "%";
      $("c-disagree-note").textContent = f.drafts_counted ? `last ${f.drafts_counted} ${f.drafts_counted === 1 ? "draft" : "drafts"}` : "no drafts acted on yet";
      $("loop-off").textContent = f.ok ? "" : f.detail;
      $("loop-off").hidden = f.ok;
    } catch (e) { /* the figure stays "-" */ }
  }

  narrow.addEventListener("change", place);
  load();
  quota();
  loop();
})();
