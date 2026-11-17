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
  let run = null, selected = null, seen = {}, shownDetail = "", mapped = new Set(), fb = null; // fb: the feedback loop's figures
  let openGroups = {}, mapOpen = false, ccPick = {}, reopened = new Set(); // reopened: sent drafts the operator chose to edit again // what the operator opened or ticked survives a redraw

  const shown = s => (s === "Sent to me" ? "Sent" : s); // the operator asked for the words "to me" to go; the note under the draft still says where it went
  const chip = s => `<span class="chip ${TONE[s]}"><svg aria-hidden="true"><use href="#i-${ICON[s]}"/></svg>${esc(shown(s))}</span>`;
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
    count("c-dropped", recs.filter(r => r.status === "Disqualified").length);
  }

  function count(id, to) { // a changed number counts up to its new value, so the eye is drawn to what moved
    const el = $(id), from = +el.textContent || 0;
    if (from === to || !calm.matches) { el.textContent = to; return; }
    const t0 = performance.now();
    const tick = t => { const k = Math.min(1, (t - t0) / 500); el.textContent = Math.round(from + (to - from) * k); if (k < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  // Role groups in priority order (config/icp.json role_priority, tier 1 to 4).
  const LANES = ["Security, compliance or risk", "Engineering leadership", "Operations", "CEO or founder"];
  function renderBoard() {
    const recs = run.records, n = recs.length, done = recs.filter(r => !r.pending);
    const reached = done.filter(r => r.contact && r.draft && r.draft.body);
    renderFlow();
    const fresh = d => (mapped.has(d) ? "" : " arrive");
    // A network map, not a table: the run in the middle, a line to every company, and from each company to the people found there.
    const W = 860, H = 640, cx = W / 2, cy = H / 2 + (n === 1 ? 130 : 0), R1 = 150, rad = d => d * Math.PI / 180; // one company: the hub sits low so its cluster is centred
    const pt = (deg, r) => [(cx + r * Math.cos(rad(deg))).toFixed(1), (cy + r * Math.sin(rad(deg))).toFixed(1)];
    const step = 360 / Math.max(n, 1);
    const kind = r => (r.pending ? "wait" : reached.includes(r) ? "hit" : r.status === "Disqualified" ? "drop" : "flag");
    const short = t => (t.length > 22 ? t.slice(0, 21) + "…" : t);
    const nodes = recs.map((r, i) => {
      const a = -90 + i * step, [x, y] = pt(a, R1), cos = Math.cos(rad(a)), sin = Math.sin(rad(a));
      const open = r.domain === selected && r.contact; // the chosen company opens up: everyone found there, each with a name
      const people = r.contact ? [r.contact, ...(r.others || []).slice(0, open ? 8 : 3)] : [];
      const from = (deg, d) => [(+x + d * Math.cos(rad(deg))).toFixed(1), (+y + d * Math.sin(rad(deg))).toFixed(1)]; // around the company, not the hub
      const side = deg => { const c = Math.cos(rad(deg)), q = Math.sin(rad(deg)); return `dy="${q > .5 ? 11 : q < -.5 ? -3 : 4}" text-anchor="${c > .35 ? "start" : c < -.35 ? "end" : "middle"}"`; };
      const spread = open ? Math.min(34, 170 / Math.max(people.length - 1, 1)) : 32;
      const ppl = people.map((p, j) => { const pa = a + (j - (people.length - 1) / 2) * spread, far = open ? (j % 2 ? 126 : 86) : 50; // two rings keep names apart
        const [px, py] = from(pa, far), [tx, ty] = from(pa, far + 13);
        return `<line class="edge" x1="${x}" y1="${y}" x2="${px}" y2="${py}"/><circle class="pnode${j ? "" : " to"}" cx="${px}" cy="${py}" r="${j ? 6 : 9}"><title>${esc(p.name)}, ${esc(p.position || "no title")}${j ? "" : " (written to)"}</title></circle>` +
          (open ? `<text class="pname${j ? " sub" : ""}" x="${tx}" y="${ty}" ${side(pa)}>${esc(short(p.name))}</text>` : ""); }).join("");
      const la = open ? a + 138 : a, [lx, ly] = open ? from(la, 36) : from(a, (people.length ? 50 : 0) + 22); // an open company is named on its free side
      const label = `<text x="${lx}" y="${ly}" ${side(la)}>${esc(short(r.name || r.domain))}` +
        (r.contact && !open ? ` <tspan class="sub" x="${lx}" dy="15">${esc(short(r.contact.name))}</tspan>` : "") + `</text>`;
      return `<g class="co ${kind(r)}${fresh(r.domain)}" data-domain="${esc(r.domain)}" role="button" tabindex="0" aria-pressed="${r.domain === selected}" ` +
        `aria-description="${esc(shown(r.status))}"><title>${esc(r.name || r.domain)}</title><line class="edge" x1="${cx}" y1="${cy}" x2="${x}" y2="${y}"/>${ppl}` +
        `<circle class="halo" cx="${x}" cy="${y}" r="15"/><circle class="cnode" cx="${x}" cy="${y}" r="${kind(r) === "hit" ? 14 : 10}"/>${label}</g>`;
    }).join("");
    const who = r => `<button type="button" class="who${fresh(r.domain)}" data-domain="${esc(r.domain)}" aria-pressed="${r.domain === selected}">` +
      `<span class="who-name">${esc(r.contact.name)} <span class="mono">${esc(r.contact.position)}</span></span>` +
      `<span class="who-co"><span class="mono">${esc(r.name || r.domain)}</span>${chip(r.status)}</span></button>`;
    const ranked = [...reached].sort((p, q) => (p.contact.role_tier || 9) - (q.contact.role_tier || 9));
    const key = [["hit", "Reached"], ["flag", "Needs you"], ["drop", "Dropped"], ["wait", "Researching"]].filter(k => recs.some(r => kind(r) === k[0]));
    $("reach").innerHTML = `<div class="netwrap"><div><svg class="net" viewBox="0 0 ${W} ${H}" role="group" aria-label="Map of this run: every company, and the people found there">${nodes}` +
      `<circle class="hub" cx="${cx}" cy="${cy}" r="22"/><text class="hubt" x="${cx}" y="${cy + 4}" text-anchor="middle">Run</text></svg>` +
      `<p class="legend">${key.map(k => `<span><svg viewBox="0 0 12 12" aria-hidden="true"><circle class="cnode ${k[0]}" cx="6" cy="6" r="5"/></svg>${k[1]}</span>`).join("")}` +
      `<span><svg viewBox="0 0 12 12" aria-hidden="true"><circle class="pnode to" cx="6" cy="6" r="4"/></svg>Written to</span><span><svg viewBox="0 0 12 12" aria-hidden="true"><circle class="pnode" cx="6" cy="6" r="4"/></svg>Also found</span></p></div>` +
      `<div class="netside"><div id="net-info" aria-live="polite"></div>` +
      (ranked.length ? `<p class="label sub">People reached, by role priority <span class="mono">${ranked.length}</span></p>${ranked.map(who).join("")}` : `<p class="none">No one reached yet in this run.</p>`) + `</div></div>`;
    done.forEach(r => mapped.add(r.domain));
    $("reach").querySelectorAll(".who").forEach(b => b.addEventListener("click", () => go(b.dataset.domain))); // a person opens their company on its people map
    $("reach").querySelectorAll("g.co").forEach(g => { // a node only selects: what it is shows beside the map
      g.addEventListener("click", () => select(g.dataset.domain, false));
      g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(g.dataset.domain, false);
        $("reach").querySelector('g.co[aria-pressed="true"]').focus(); } }); // the map was redrawn: keep the keyboard on the node
    });
    $("net-info").addEventListener("click", e => { if (e.target.closest("[data-open]")) go(selected); if (e.target.closest("[data-more]")) findPeople(e.target.closest("[data-more]")); });
    markReach();
  }

  function go(d) { // open a company below, on its people map
    mapOpen = true; select(d, true);
    $("detail").scrollIntoView({ block: "nearest", behavior: calm.matches ? "smooth" : "auto" });
  }

  // The flow: every stage a company passes, an arrow between stages, who stopped where and why,
  // and the feedback loop: what you change in a draft goes back into how the next drafts are written.
  function renderFlow() {
    const recs = run.records, n = recs.length, done = recs.filter(r => !r.pending);
    const opened = r => !!r.fields || (r.pages_fetched || []).some(pg => pg.ok);
    const read = done.filter(opened), qualified = read.filter(r => r.verdict === "qualified" || r.contact);
    const found = qualified.filter(r => r.contact), drafted = found.filter(ready);
    const rev = r => r.review || {}, sent = drafted.filter(r => rev(r).sent_at), skipped = drafted.filter(r => rev(r).skipped);
    const waiting = drafted.length - sent.length - skipped.length;
    const stages = [
      ["Pasted", n, done.length < n ? `${n - done.length} still being researched` : "domains in this run", []],
      ["Pages read", read.length, "each company's own site", done.filter(r => !opened(r))],
      ["Qualified", qualified.length, "not certified, B2B SaaS, big enough", read.filter(r => !qualified.includes(r))],
      ["Person found", found.length, "the right role, through Hunter", qualified.filter(r => !r.contact)],
      ["Draft ready", drafted.length, "every sentence checked against the site", found.filter(r => !ready(r))],
      ["You reviewed", sent.length + skipped.length, `${sent.length} sent, ${skipped.length} skipped, ${waiting} waiting`, []],
    ];
    const cut = t => (t.length > 70 ? t.slice(0, 69) + "…" : t);
    const stop = r => `<button type="button" class="stop" data-domain="${esc(r.domain)}" title="${esc(r.reason || "")}"><b>${esc(r.name || r.domain)}</b> ${esc(cut(r.reason || ""))}</button>`;
    const used = drafted.filter(r => ((r.feedback_loop || {}).corrections_used || []).length).length;
    const edited = drafted.filter(r => rev(r).rewritten || rev(r).skipped).length;
    const lines = !fb ? ["Reading the loop."] : !fb.ok ? [`Off: ${fb.detail}`] :
      [`${edited} ${edited === 1 ? "draft" : "drafts"} changed by you here`, `${fb.stored} ${fb.stored === 1 ? "correction" : "corrections"} saved`,
       `Used in ${used} of ${drafted.length} drafts here`, ...(fb.avg_disagreement === null ? [] : [`You change ${Math.round(fb.avg_disagreement * 100)}% on average`])];
    $("flow").innerHTML = `<div class="flow">` +
      `<div class="loop${fb && !fb.ok ? " off" : ""}"><svg viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true"><path d="M87.5 40 V9 Q87.5 3 84.5 3 H65.5 Q62.5 3 62.5 9 V38" vector-effect="non-scaling-stroke"/></svg>` +
      `<span class="loop-head" aria-hidden="true"></span><p><b>Feedback loop</b>${lines.map(l => `<span>${esc(l)}</span>`).join("")}</p></div>` +
      stages.map(([label, count, note, stopped], i) => `<div class="stage${i === 4 ? " learns" : ""}" style="--i:${i}"><p class="label">${label}</p><b class="mono count">${count}</b><p class="hint">${esc(note)}</p>` +
        (stopped.length ? `<div class="stops"><p class="label">Stopped here <span class="mono">${stopped.length}</span></p>${stopped.map(stop).join("")}</div>` : "") + `</div>`).join("") +
      `</div>`;
    $("flow").querySelectorAll("[data-domain]").forEach(b => b.addEventListener("click", () => go(b.dataset.domain)));
  }

  function markReach() { // the chosen company is ringed on the map and described beside it
    document.querySelectorAll("#reach [data-domain]").forEach(b => b.setAttribute("aria-pressed", b.dataset.domain === selected));
    const r = run.records.find(x => x.domain === selected), box = $("net-info");
    if (!box || !r) return;
    const c = r.contact, more = (r.others || []).length;
    box.innerHTML = `<h3>${esc(r.name || r.domain)} ${chip(r.status)}</h3><p class="mono muted">${esc(r.domain)}</p>` +
      (c && r.draft && r.draft.body ? `<p><b>${esc(c.name)}</b>, ${esc(c.position)}</p>` + (r.draft.role_measured_on ? `<p>${esc(r.draft.role_measured_on)}</p>` : "") +
        ((r.fields || {}).trigger ? `<p class="muted">Why now: ${esc(r.fields.trigger)}</p>` : "") +
        (more ? `<p class="label sub">Also at ${esc(r.name || r.domain)} <span class="mono">${more}</span></p><ul class="others">${r.others.map(o => `<li><b>${esc(o.name)}</b> <span class="muted">${esc(o.position || "no title")}</span></li>`).join("")}</ul>`
          : `<p class="muted">${r.others_searched ? "Hunter found no one else with a usable address here." : "Only the person written to is on the map so far."}</p>`)
        : `<p>${esc(why(r))}</p>`) +
      `<p class="error" id="more-error" role="alert" hidden></p><div class="row">` +
      (c && !r.others_searched ? `<button type="button" class="btn primary" data-more>Find more people here</button>` : "") +
      `<button type="button" class="btn" data-open>${ready(r) ? "Open the draft" : "Open this company"}</button></div>` +
      (c && !r.others_searched ? `<p class="hint">Finding more people uses 1 Hunter search.</p>` : "");
  }

  function renderList() {
    const detail = $("detail"); // lift the detail out of a phone card before the list is rebuilt
    if (!detail.parentElement.classList.contains("desk")) document.querySelector(".desk").appendChild(detail);
    const html = GROUPS.map(g => {
      const items = run.records.filter(g.test);
      if (!items.length) return "";
      const open = openGroups[g.name] ?? items.some(r => r.domain === selected);
      return `<details class="group" data-group="${esc(g.name)}"${open ? " open" : ""}><summary><span class="label">${esc(g.name)}</span> <span class="mono">${items.length}</span></summary><ul>` + items.map(r => {
        const before = seen[r.domain];
        const cls = [before === undefined && !r.pending ? "arrive" : "", before && before !== r.status ? "changed" : ""].join(" ");
        const src = firstSource(r);
        return `<li class="${cls}" data-domain="${esc(r.domain)}"><button type="button" class="item" aria-pressed="${r.domain === selected}">` +
          `<span class="item-top"><span class="item-name">${esc(r.name || r.domain)}</span>${chip(r.status)}</span>` +
          `<span class="item-why">${esc(why(r))}</span>` +
          (src && !r.pending ? `<span class="item-src mono">${esc(r.domain)}${esc(src)}</span>` : "") + `</button></li>`;
      }).join("") + "</ul></details>";
    }).join("");
    $("list").innerHTML = html;
    run.records.forEach(r => { if (!r.pending) seen[r.domain] = r.status; });
    $("list").querySelectorAll(".item").forEach(b => b.addEventListener("click", () => select(b.parentElement.dataset.domain, true)));
    $("list").querySelectorAll("details.group").forEach(d => d.addEventListener("toggle", () => { openGroups[d.dataset.group] = d.open; }));
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

  const isLocked = r => { const rev = r.review || {}; return !!rev.skipped || (!!rev.sent_at && !reopened.has(r.domain)); };

  function editableDraft(r) {
    const d = r.draft, c = r.contact, rev = r.review || {}, locked = isLocked(r);
    const subject = rev.edited ? rev.edited.subject : d.subject, body = rev.edited ? rev.edited.body : d.body;
    const ro = locked ? "readonly" : "";
    return `<p class="to"><span class="label">To</span> ${esc(c.name)}, ${esc(c.position)} <span class="mono muted">&lt;${esc(c.email)}&gt;</span></p>` +
      `<label class="label" for="ed-subject">Subject</label><input id="ed-subject" class="field subject-field" type="text" maxlength="200" autocomplete="off" value="${esc(subject)}" ${ro}>` +
      `<label class="label" for="ed-body">Email</label><textarea id="ed-body" class="field body-field" maxlength="5000" rows="12" ${ro}>${esc(body)}</textarea>` +
      (locked ? "" : `<p class="hint" id="ed-hint">${rev.sent_at ? "Change it, then send the new version to your inbox. The earlier email stays in your inbox." : "Edit the subject or the email before sending."} Your changes teach the next drafts.</p>` +
        `<label class="label" for="ed-reason">Why did you change it? (optional)</label><input id="ed-reason" class="field" type="text" maxlength="1000" autocomplete="off" placeholder="Too long. Ask about ISO 27001, not SOC 2.">`);
  }

  // The people map of one company: who the email is addressed to, and the others Hunter found there.
  // Each person opens into what we know about them and a notes box; the others can be marked as CC.
  function peopleMap(r) {
    const rev = r.review || {}, locked = isLocked(r), notes = r.notes || {};
    const picks = locked ? new Set(rev.cc || []) : (ccPick[r.domain] = ccPick[r.domain] || new Set());
    const people = [Object.assign({ to: true }, r.contact), ...(r.others || [])];
    const node = (p, i) => `<li class="org-node${p.to ? " to" : ""}"><details class="person"><summary><span class="org-name">${esc(p.name)}</span>` +
      `<span class="mono org-title">${esc(p.position || "No title")}</span></summary><p class="mono src">${esc(p.email)}</p>` +
      (p.to ? `<p>${esc(p.why_this_person)}</p>${r.draft && r.draft.role_measured_on ? `<p class="muted">Measured on: ${esc(r.draft.role_measured_on)}</p>` : ""}`
            : `<p class="muted">Found by Hunter, not picked. ${p.role_tier ? "Role group: " + esc(LANES[p.role_tier - 1].toLowerCase()) + "." : "No role on the priority list."}</p>`) +
      `<label class="label" for="note-${i}">Your notes</label><textarea id="note-${i}" class="field note" data-note="${esc(p.email)}" maxlength="1000" rows="2" placeholder="Anything worth remembering about this person.">${esc(notes[p.email] || "")}</textarea>` +
      `<p class="hint" data-saved="${esc(p.email)}" role="status"></p></details>` +
      (p.to ? `<span class="chip wait">To</span>` : `<label class="cc"><input type="checkbox" data-cc="${esc(p.email)}"${picks.has(p.email) ? " checked" : ""}${locked ? " disabled" : ""}> CC</label>`) + `</li>`;
    return `<details class="orgmap"${mapOpen ? " open" : ""}><summary>People map: ${people.length} ${people.length === 1 ? "person" : "people"} at ${esc(r.name || r.domain)}</summary>` +
      `<div class="org"><div class="org-root"><b>${esc(r.name || r.domain)}</b> <span class="mono muted">${esc(r.domain)}</span></div><ul class="org-row">${people.map(node).join("")}</ul>` +
      `<p class="hint">${r.others ? (r.others.length ? "Tick CC to mark someone. Marked people are named in the email you receive; only addresses you listed in CC_ALLOWED are really emailed." : "Hunter found no one else with a usable address here.")
        : "Other people at this company are saved from the next run on."}</p></div></details>`;
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
      const ccNote = (rev.cc || []).length ? ` CC marked: ${rev.cc.length}; ${(rev.cc_delivered || []).length ? "emailed: " + rev.cc_delivered.join(", ") : "none of them were emailed"}.` : "";
      const used = ((r.feedback_loop || {}).corrections_used || []).length;
      const loopLine = used ? `<p>Written with ${used} of your earlier ${used === 1 ? "correction" : "corrections"} in mind.${r.feedback_loop.pattern ? " " + esc(r.feedback_loop.pattern) : ""}</p>` : "";
      return head + peopleMap(r) + `<div class="draft">${editableDraft(r)}` +
        `<div class="row actions">` + (sent && !skipped && !reopened.has(r.domain)
          ? `<button class="btn primary" type="button" data-reopen>Edit and send again</button>`
          : `<button class="btn primary" type="button" data-act="send" ${skipped ? "disabled" : ""}>${sent ? "Send the new version" : "Send to my inbox"}</button>`) +
        (sent ? "" : `<button class="btn" type="button" data-act="rewrote" ${rev.rewritten || skipped ? "disabled" : ""}>I rewrote it</button>` +
          `<button class="btn" type="button" data-act="skip" ${skipped ? "disabled" : ""}>Skip</button>`) + `</div>` +
        `<p class="error" id="act-error" role="alert" hidden></p><p class="muted" id="act-note">${esc(note + (sent ? ccNote : ""))}</p></div>` +
        `<div class="reasons">${company}<h3>Why this person</h3><p>${esc(r.contact.why_this_person)} Hunter confidence <span class="mono">${esc(r.contact.confidence)}</span>, email ${esc(r.contact.verification_status || "unverified")}.</p>` +
        `<h3>Two pains</h3><ol class="pains">${d.pains.map(p => `<li>${esc(p.pain)} <span class="mono src">${esc(p.evidence_field)}</span></li>`).join("")}</ol>` +
        `<h3>What this role is measured on</h3><p>${esc(d.role_measured_on)}</p>${loopLine ? "<h3>What it learned from you</h3>" + loopLine : ""}${traceBlock(d)}</div>`;
    }
    if (r.status === "Disqualified") return head + `<div class="reasons"><h3>Why it was dropped</h3><p>${esc(r.reason)}</p>${evidenceList(r)}</div>`;
    const held = r.draft && r.draft.body && r.contact ? `<details class="held"><summary>See the held-back draft</summary>${draftBlock(r)}${traceBlock(r.draft)}</details>` : "";
    return head + (r.contact ? peopleMap(r) : "") + `<div class="draft nodraft"><h3>No draft</h3><p>${esc(r.reason)}</p>` +
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
      detail.querySelectorAll("[data-reopen]").forEach(b => b.addEventListener("click", () => {
        reopened.add(r.domain); ccPick[r.domain] = new Set((r.review || {}).cc || []);
        renderDetail(true); $("ed-body").focus();
      }));
      detail.querySelectorAll(".orgmap").forEach(d => d.addEventListener("toggle", () => { mapOpen = d.open; }));
      detail.querySelectorAll("[data-cc]").forEach(c => c.addEventListener("change", () => ccPick[r.domain][c.checked ? "add" : "delete"](c.dataset.cc)));
      detail.querySelectorAll("[data-note]").forEach(t => t.addEventListener("change", () => saveNote(r, t)));
    }
    place();
  }

  async function findPeople(btn) { // one more Hunter search, on the operator's click: everyone Hunter knows at this company
    if (btn.disabled) return;
    btn.disabled = true; btn.textContent = "Searching";
    const domain = selected;
    try {
      const res = signInIfNeeded(await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: run.id, domain, action: "people" }) }));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "The search did not work. Try again.");
      run.records[run.records.findIndex(x => x.domain === domain)] = data.record;
      renderBoard(); renderDetail(true); quota();
    } catch (e) {
      if (e.message === "Signing in") return;
      const err = $("more-error");
      err.textContent = e.message.startsWith("Failed") ? "The app is not responding. Check that the server is still running." : e.message;
      err.hidden = false; btn.disabled = false; btn.textContent = "Find more people here";
    }
  }

  async function saveNote(r, box) {
    const said = $("detail").querySelector(`[data-saved="${CSS.escape(box.dataset.note)}"]`);
    try {
      const res = signInIfNeeded(await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: run.id, domain: r.domain, action: "note", person: box.dataset.note, note: box.value }) }));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "The note was not saved.");
      run.records[run.records.findIndex(x => x.domain === r.domain)] = data.record;
      said.textContent = "Saved.";
    } catch (e) {
      if (e.message !== "Signing in") said.textContent = e.message.startsWith("Failed") ? "Not saved: the app is not responding." : e.message;
    }
  }

  function select(domain, user) {
    selected = domain;
    renderBoard(); // the chosen company opens up on the map
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
    const err = $("act-error");
    const payload = { run_id: run.id, domain: r.domain, action };
    if (action !== "rewrote" && $("ed-reason")) payload.reason = $("ed-reason").value;
    if (action === "send" && ccPick[r.domain]) payload.cc = [...ccPick[r.domain]];
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
      if (action === "send") reopened.delete(r.domain);
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
      b.disabled = (b.dataset.act !== "rewrote" && isLocked(r)) || (b.dataset.act === "rewrote" && (rev.rewritten || rev.skipped));
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
      fb = f;
      if (run) renderFlow();
    } catch (e) { /* the figure stays "-" */ }
  }

  narrow.addEventListener("change", place);
  load();
  quota();
  loop();
})();
