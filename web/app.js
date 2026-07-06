// app.js — Lighthouse dashboard. Centered composer → results, with a lively
// progress state, cancel, recent audits, head-to-head, and RAG Ask.

const $ = (s) => document.querySelector(s);
const composer = $("#composer");
const panel = $("#panel");
let activeId = null;
let pollTimer = null;
let phraseTimer = null;
let currentData = null;
let currentTab = "overview";

const pct = (x) => (x == null ? "--" : Math.round(x * 1000) / 10 + "%");
const num = (x) => (x == null ? "--" : x);

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Minimal, safe markdown -> HTML (escape first, then format) so answers render
// like a proper chat reply instead of raw asterisks and hashes.
function mdToHtml(src) {
  const lines = escapeHtml(src || "").split(/\r?\n/);
  const inline = (t) => t
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  let html = "", list = null;
  const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if (/^#{1,6}\s/.test(line)) { closeList(); html += `<h4 class="md-h">${inline(line.replace(/^#{1,6}\s/, ""))}</h4>`; }
    else if ((m = line.match(/^\s*[-*]\s+(.*)/))) { if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = line.match(/^\s*\d+\.\s+(.*)/))) { if (list !== "ol") { closeList(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
    else if (line.trim() === "") { closeList(); }
    else { closeList(); html += `<p>${inline(line)}</p>`; }
  }
  closeList();
  return html;
}

// per-brand caches so switching tabs doesn't wipe an answer or a generated fix
const askCache = {};     // brand_id -> { q, html }
const actionCache = {};  // brand_id -> { competitor -> plan }
const buildCache = {};   // brand_id -> { mode -> build result } (landing / gtm)
const retrievalCache = {}; // brand_id -> retrieval reconstruction result

// --- view toggle ------------------------------------------------------------

function showComposer() {
  clearInterval(pollTimer); clearInterval(phraseTimer);
  activeId = null;
  panel.hidden = true;
  composer.hidden = false;
  loadRecent();
}
function showPanel() {
  composer.hidden = true;
  panel.hidden = false;
}

// --- recent audits ----------------------------------------------------------

async function loadRecent() {
  let brands = [];
  try { brands = await api("/api/brands"); } catch { /* ignore */ }
  const el = $("#recent-list");
  if (!brands.length) { el.innerHTML = `<span class="recent-empty">No audits yet.</span>`; return; }
  el.innerHTML = brands.slice(0, 12).map((b) => {
    const right = b.status === "done" ? pct(b.mention_rate)
      : `<span class="dot-run"></span>${escapeHtml(b.status || "pending")}`;
    return `<button class="recent-chip" data-id="${b.id}">
      <span class="rc-name">${escapeHtml(b.name)}</span>
      <span class="rc-cat">${escapeHtml(b.category)}</span>
      <span class="rc-rate">${right}</span></button>`;
  }).join("");
  el.querySelectorAll(".recent-chip").forEach((c) =>
    (c.onclick = () => selectBrand(Number(c.dataset.id))));
}

// --- selection + polling ----------------------------------------------------

async function selectBrand(id) {
  activeId = id; currentTab = "overview";
  clearInterval(pollTimer);
  showPanel();
  await refreshPanel();
}

async function refreshPanel() {
  if (activeId == null) return;
  let data;
  try { data = await api(`/api/brands/${activeId}`); }
  catch (e) { panel.innerHTML = `<div class="err-box">Could not load: ${escapeHtml(e.message)}</div>`; return; }

  if (data.status === "error") {
    clearInterval(pollTimer); clearInterval(phraseTimer);
    panel.innerHTML = `<div class="err-box"><b>Audit failed.</b><br>
      ${escapeHtml(data.error_message || "Unknown error.")}<br><br>
      Usually a transient API hiccup — run it again.</div>
      <div style="margin-top:14px"><button class="btn btn-ghost btn-sm" onclick="window.__newAudit()">Back</button></div>`;
    return;
  }
  if (data.status && data.status !== "done") {
    renderProgress(data.status, data.name, data.progress);
    clearInterval(pollTimer);
    const tick = async () => {
      const s = await api(`/api/brands/${activeId}/status`).catch(() => null);
      if (!s) return;
      if (s.status === "done" || s.status === "error") {
        clearInterval(pollTimer); clearInterval(phraseTimer);
        await loadRecent(); await refreshPanel();
      } else {
        updateProgress(s.status, s.progress);
      }
    };
    tick();                                  // fill real counts immediately
    pollTimer = setInterval(tick, 2000);
    return;
  }
  clearInterval(phraseTimer);
  currentData = data;
  render();
}

// --- lively progress --------------------------------------------------------

const STAGE_TEXT = {
  pending: "Spinning up your audit",
  generating: "Designing your question panel",
  probing: "Interrogating the AI engines",
  parsing: "Reading the answers",
};
// The real pipeline, as ordered steps. `key` maps to the backend status that
// makes this step "active"; everything before it is "done".
const STEPS = [
  { key: "generating", tt: "Build a panel of real buyer questions",
    sub: p => p && p.queries ? `${p.queries} questions generated` : "" },
  { key: "probing",    tt: "Ask GPT-5, Claude & Perplexity",
    sub: p => p ? `${p.responses || 0} / ${p.responses_total || 0} answers collected` : "" },
  { key: "parsing",    tt: "Read every answer for brand mentions",
    sub: p => p ? `${p.parsed || 0} / ${p.responses || 0} answers analyzed` : "" },
  { key: "finishing",  tt: "Map cited sources & score the vibes",
    sub: () => "" },
];
const STAGE_ORDER = { pending: 0, generating: 0, probing: 1, parsing: 2, finishing: 3 };

function pctFor(status, p) {
  if (!p) return status === "generating" ? 6 : 2;
  if (status === "probing")
    return 8 + Math.round((p.responses_total ? (p.responses || 0) / p.responses_total : 0) * 62);
  if (status === "parsing")
    return 72 + Math.round((p.responses ? (p.parsed || 0) / p.responses : 0) * 24);
  if (status === "generating") return 6;
  return 2;
}

function renderProgress(status, name, progress) {
  const steps = STEPS.map((s, i) =>
    `<div class="run-step" id="rs-${i}"><span class="ic"></span>
       <div class="tx"><div class="tt">${s.tt}</div><div class="sub" id="rsub-${i}"></div></div></div>`
  ).join("");
  panel.innerHTML = `
    <div class="run-card">
      <div class="run-orbit"><span></span><span></span><span></span></div>
      <div class="run-stage" id="run-stage">${escapeHtml(STAGE_TEXT[status] || "Working")}</div>
      <div class="run-for">${name ? "for " + escapeHtml(name) : ""}</div>
      <div class="run-bar"><i id="run-fill"></i></div>
      <div class="run-pct" id="run-pct"></div>
      <div class="run-steps">${steps}</div>
      <button class="btn btn-ghost btn-sm run-cancel" id="cancel-btn">Cancel</button>
    </div>`;
  $("#cancel-btn").onclick = cancelActive;
  clearInterval(phraseTimer);
  updateProgress(status, progress);
}

function updateProgress(status, progress) {
  const stage = $("#run-stage"); if (stage) stage.textContent = STAGE_TEXT[status] || "Working";
  const cur = STAGE_ORDER[status] != null ? STAGE_ORDER[status] : 0;
  STEPS.forEach((s, i) => {
    const el = $(`#rs-${i}`), sub = $(`#rsub-${i}`);
    if (!el) return;
    el.className = "run-step" + (i < cur ? " done" : i === cur ? " active" : "");
    if (sub) {
      const txt = i < cur ? (s.sub(progress) || "Done")
                : i === cur ? s.sub(progress)
                : "";
      sub.textContent = txt;
    }
  });
  const fill = $("#run-fill"), pe = $("#run-pct");
  const v = pctFor(status, progress);
  if (fill) fill.style.width = v + "%";
  if (pe) pe.textContent = v >= 2 ? v + "%" : "";
}
async function cancelActive() {
  if (activeId == null) return;
  const btn = $("#cancel-btn"); if (btn) { btn.disabled = true; btn.textContent = "Cancelling…"; }
  try { await api(`/api/brands/${activeId}/cancel`, { method: "POST" }); } catch { /* ignore */ }
  showComposer();
}

// --- render shell + tabs ----------------------------------------------------

function bar(name, value, max, meta, focal) {
  const w = max > 0 ? Math.round((value / max) * 100) : 0;
  return `<div class="barrow"><span class="nm ${focal ? "focal-row" : ""}">${escapeHtml(name)}</span>
    <div class="bar ${focal ? "focal" : ""}"><span style="width:${w}%"></span></div>
    <span class="meta">${meta}</span></div>`;
}

function render() {
  const d = currentData;
  panel.innerHTML = `
    <div class="dash-head">
      <div><h1 class="dash-title">${escapeHtml(d.name)}</h1><div class="dash-cat">${escapeHtml(d.category)}</div></div>
      <div class="focal">canonical: <b>${escapeHtml(d.focal_canonical)}</b><br>${d.total_responses} responses analyzed
        <br><button class="btn btn-ghost btn-sm" style="margin-top:8px" onclick="window.__newAudit()">New audit</button></div>
    </div>
    <div class="tabs">
      <div class="tab ${currentTab === "overview" ? "active" : ""}" data-tab="overview">Overview</div>
      <div class="tab ${currentTab === "vibes" ? "active" : ""}" data-tab="vibes">Vibes</div>
      <div class="tab ${currentTab === "action" ? "active" : ""}" data-tab="action">Action</div>
      <div class="tab ${currentTab === "retrieval" ? "active" : ""}" data-tab="retrieval">Why you lose</div>
      <div class="tab ${currentTab === "ask" ? "active" : ""}" data-tab="ask">Ask</div>
    </div>
    <div id="tabbody"></div>`;
  panel.querySelectorAll(".tab").forEach((t) =>
    (t.onclick = () => { currentTab = t.dataset.tab; render(); }));
  if (currentTab === "overview") renderOverview();
  else if (currentTab === "vibes") renderVibes();
  else if (currentTab === "action") renderAction();
  else if (currentTab === "retrieval") renderRetrieval();
  else renderAsk();
}

function renderOverview() {
  const d = currentData;
  const compMax = Math.max(1, ...(d.competitors || []).map((c) => c.mentions), d.mentions || 0);
  const modelMax = Math.max(1, ...(d.by_model || []).map((m) => m.responses));
  const competitors = (d.competitors || [])
    .map((c) => bar(c.brand, c.mentions, compMax,
      `${pct(c.rate)}${c.avg_position != null ? " &middot; pos " + c.avg_position : ""}`, false)).join("");
  const focalBar = bar(d.focal_canonical + " (you)", d.mentions, compMax, pct(d.mention_rate), true);
  const models = (d.by_model || [])
    .map((m) => bar(m.model, m.mentions, modelMax, `${pct(m.rate)} of ${m.responses}`, false)).join("");
  const n = d.normalization || {};
  const prov = d.provenance || {};
  const provSources = (prov.top_sources || [])
    .map((s) => `<div class="provrow"><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.domain)}</a><span class="meta">${s.count}</span></div>`).join("");
  const provCard = (prov.top_sources && prov.top_sources.length)
    ? `<div class="card prov-card"><h4>Sources the AI cites</h4>
        <p class="muted" style="margin:-4px 0 12px;font-size:13px">From ${prov.responses_with_sources} retrieval answers via ${escapeHtml((prov.engines || []).join(", ") || "Perplexity")}. Where you're absent from the top sources is where you lose.</p>
        <div class="provrows">${provSources}</div></div>`
    : "";

  // head-to-head vs a chosen competitor
  const kc = d.key_competitor;
  const h2h = kc ? `<div class="card h2h">
      <h4>Head to head</h4>
      <div class="h2h-row"><span class="h2h-name focal-row">${escapeHtml(d.focal_canonical)} (you)</span>
        <div class="bar focal"><span style="width:${Math.round((kc.you_rate||0)*100)}%"></span></div><span class="meta">${pct(kc.you_rate)}</span></div>
      <div class="h2h-row"><span class="h2h-name">${escapeHtml(kc.brand)}</span>
        <div class="bar"><span style="width:${Math.round((kc.rate||0)*100)}%"></span></div><span class="meta">${pct(kc.rate)}</span></div>
    </div>` : "";

  $("#tabbody").innerHTML = `
    ${h2h}
    <div class="kpis">
      <div class="kpi"><div class="label">Mention rate</div><div class="val accent">${pct(d.mention_rate)}</div></div>
      <div class="kpi"><div class="label">Avg position</div><div class="val">${num(d.avg_position)}</div></div>
      <div class="kpi"><div class="label">Share of voice</div><div class="val">${pct(d.share_of_voice)}</div></div>
      <div class="kpi"><div class="label">Responses</div><div class="val">${d.total_responses}</div></div>
    </div>
    <div class="norm"><div class="big">${n.merged ?? 0}</div>
      <div class="txt">raw variants merged by <b>brand-identity normalization</b>.<br>
        ${n.raw_variants ?? 0} raw mentions resolved to <b>${n.canonical_brands ?? 0}</b> real brands.</div></div>
    <div class="cards2">
      <div class="card"><h4>You vs competitors (mentions)</h4>${focalBar}${competitors || '<div class="bi-cat">No competitors found.</div>'}</div>
      <div class="card"><h4>By model</h4>${models || '<div class="bi-cat">No model data.</div>'}</div>
    </div>
    ${provCard}`;
}

function renderVibes() {
  const d = currentData;
  const lex = d.lexical || {};
  const top = lex.focal_top || [];
  const maxC = lex.max_count || 1;
  const cloud = top.length
    ? top.map((x) => {
        const size = 13 + Math.round((x.count / maxC) * 13);
        const op = 0.55 + 0.45 * (x.count / maxC);
        return `<span class="vibe" style="font-size:${size}px;opacity:${op}" title="${x.count} mentions">${escapeHtml(x.term)}</span>`;
      }).join("")
    : `<div class="bi-cat">No descriptors captured yet for ${escapeHtml(d.name)}.</div>`;
  const ownChips = (arr, withSrc) => (arr && arr.length)
    ? arr.map((x) => {
        const src = withSrc && x.sources && x.sources.length
          ? `<span class="vibe-src">${x.sources.map(escapeHtml).join(" · ")}</span>` : "";
        return `<span class="vibe-pill">${escapeHtml(x.term)}<span class="vc">${x.count}</span>${src}</span>`;
      }).join("")
    : `<div class="bi-cat">Nothing distinctive yet.</div>`;
  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 16px">The words AI assistants use to describe ${escapeHtml(d.name)} and rivals, and the source sites that drive them. Lean into the vibes you already own.</p>
    <div class="card"><h4>How AI describes ${escapeHtml(d.name)}</h4><div class="vibe-cloud">${cloud}</div></div>
    <div class="cards2">
      <div class="card vibe-own"><h4>Vibes you own <span class="muted" style="text-transform:none;font-weight:400">· with the sites driving them</span></h4><div class="vibe-pills col">${ownChips(lex.you_own, true)}</div></div>
      <div class="card vibe-them"><h4>Vibes competitors own</h4><div class="vibe-pills">${ownChips(lex.they_own, false)}</div></div>
    </div>`;
}

function renderAction() {
  const d = currentData;
  const comps = (d.competitors || []).slice(0, 4);
  const lex = d.lexical || {};
  const srcs = ((d.provenance || {}).top_sources || []).slice(0, 6);
  const theyOwn = (lex.they_own || []).slice(0, 8);

  // 1) Honest gap diagnosis — drawn straight from the real audit, no projection.
  const gapSrc = srcs.length
    ? `<div class="gap-row"><span class="gap-k">Sources AI cites here</span><div class="gap-tags">${srcs.map(s => `<span class="gap-tag">${escapeHtml(s.domain)}</span>`).join("")}</div></div>` : "";
  const gapVibe = theyOwn.length
    ? `<div class="gap-row"><span class="gap-k">Language rivals own, you don't</span><div class="gap-tags">${theyOwn.map(t => `<span class="gap-tag warn">${escapeHtml(t.term)}</span>`).join("")}</div></div>` : "";
  const gapComp = comps.length
    ? `<div class="gap-row"><span class="gap-k">Who AI recommends instead</span><div class="gap-tags">${comps.map(c => `<span class="gap-tag">${escapeHtml(c.brand)} · ${pct(c.rate)}</span>`).join("")}</div></div>` : "";
  const gap = (gapSrc || gapVibe || gapComp)
    ? `<div class="gap-card"><div class="gap-hd">Where you're losing — measured</div>${gapComp}${gapSrc}${gapVibe}</div>` : "";

  const compCards = comps.map((c) => `
    <div class="rec" data-comp="${escapeHtml(c.brand)}">
      <div class="rec-top"><span class="who">${escapeHtml(c.brand)} is winning here</span>
        <span class="meta muted">${pct(c.rate)} of answers</span></div>
      <p>${escapeHtml(c.brand)} is recommended in ${pct(c.rate)} of responses while ${escapeHtml(d.focal_canonical)} sits at ${pct(d.mention_rate)}. Generate the website change that targets this gap.</p>
      <div class="rec-actions"><button class="btn btn-primary btn-sm gen" data-comp="${escapeHtml(c.brand)}">Generate positioning + schema</button></div>
      <div class="gen-out"></div>
    </div>`).join("");

  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 16px">Build the fix from the evidence: every asset below is grounded in the sources AI cites and the language it rewards in <b>your</b> category. Ship it, then re-run the audit to see the real movement.</p>
    ${gap}
    <div class="build-card">
      <div class="build-hd">Build a full asset</div>
      <p class="muted" style="font-size:13px;margin:2px 0 12px">Two agents work from your audit: a strategist shapes the play, a designer ships the page.</p>
      <div class="build-btns">
        <button class="btn btn-primary btn-sm build" data-mode="landing">Generate a landing page</button>
        <button class="btn btn-ghost btn-sm build" data-mode="gtm">Build a GTM strategy</button>
      </div>
      <div class="build-out" id="build-out"></div>
    </div>
    <div class="sec-sub">Per-competitor change</div>
    ${compCards || '<div class="card">Run an audit with competitors to see per-competitor changes.</div>'}
    <div class="remeasure">Shipped a change? <b>Re-run this audit in 2–3 weeks</b> to measure the real movement in mention rate and share of voice. That before/after is the proof — not a projection.</div>`;

  const copyBtn = (label) => `<button class="btn btn-ghost btn-sm copy">${label}</button>`;
  const wireCopy = (el, getText, note) => el.onclick = async () => {
    try { await navigator.clipboard.writeText(getText()); note.textContent = "Copied."; note.className = "push-note show ok"; }
    catch { note.textContent = "Select and copy manually."; note.className = "push-note show ok"; }
  };

  // render a positioning+schema plan into a competitor card's output area
  function renderPlan(out, p) {
    const notes = (p.verify_notes || []).length
      ? `<div class="verify"><b>Verify before publishing:</b><ul>${p.verify_notes.map((v) => `<li>${escapeHtml(v)}</li>`).join("")}</ul></div>` : "";
    out.classList.add("show");
    out.innerHTML = `
      ${p.angle ? `<div class="angle"><b>Angle:</b> ${escapeHtml(p.angle)}</div>` : ""}
      <div class="act-block">
        <div class="act-hd"><span>Positioning content</span><span class="copy-slot" data-k="content"></span></div>
        <div class="act-body md">${mdToHtml(p.positioning_md || "")}</div>
      </div>
      <div class="act-block">
        <div class="act-hd"><span>Schema markup (JSON-LD)</span><span class="copy-slot" data-k="schema"></span></div>
        <pre class="act-code">${escapeHtml(p.schema_jsonld || "")}</pre>
      </div>
      ${notes}
      <div class="push-note"></div>`;
    const note = out.querySelector(".push-note");
    const cSlot = out.querySelector('.copy-slot[data-k="content"]');
    const sSlot = out.querySelector('.copy-slot[data-k="schema"]');
    cSlot.innerHTML = copyBtn("Copy content"); sSlot.innerHTML = copyBtn("Copy schema");
    wireCopy(cSlot.querySelector(".copy"), () => p.positioning_md || "", note);
    wireCopy(sSlot.querySelector(".copy"), () => p.schema_jsonld || "", note);
  }

  // render a grounded GTM plan (strategist agent output)
  function gtmCards(p) {
    const pillars = (p.messaging_pillars || []).map(x => `<span class="pill">${escapeHtml(x)}</span>`).join("");
    const chans = (p.channels || []).map(c => `<div class="chan"><b>${escapeHtml(c.name)}</b><div class="why muted">${escapeHtml(c.why)}</div><div class="mv"><span>First move:</span> ${escapeHtml(c.first_move)}</div></div>`).join("");
    const card = (h, b) => `<div class="gcard"><h4>${h}</h4>${b}</div>`;
    return `<div class="gone">${escapeHtml(p.one_liner || p.name || "")}</div>
      <div class="ggrid">
        ${card("Beachhead ICP", `<p>${escapeHtml(p.icp || "")}</p>`)}
        ${card("The problem", `<p>${escapeHtml(p.problem || "")}</p>`)}
        ${card("Value proposition", `<p>${escapeHtml(p.value_prop || "")}</p>`)}
        ${card("The wedge", `<p>${escapeHtml(p.wedge || "")}</p>`)}
        ${card("Message pillars", `<div class="pillars">${pillars}</div>`)}
        ${card("Launch channels", chans)}
        ${card("Week-one campaign", `<p>${escapeHtml(p.first_campaign || "")}</p>`)}
        ${card("North-star metric", `<p>${escapeHtml(p.north_star || "")}</p>`)}
      </div>`;
  }

  // brand-level build: landing page or GTM strategy, grounded in the audit
  const bout = $("#build-out");
  function renderBuild(res) {
    if (res.mode === "gtm") {
      bout.innerHTML = `<div class="agent-pill done"><span class="dot"></span>Strategist · grounded in your audit</div>${gtmCards(res.plan)}`;
    } else {
      const f = document.createElement("iframe"); f.className = "land-frame"; f.title = "Generated landing page";
      bout.innerHTML = `<div class="agent-pill done"><span class="dot"></span>Strategist + designer · grounded in your audit</div>
        ${gtmCards(res.plan)}
        <div class="land-hd">Generated landing page</div><div class="land-wrap"></div>`;
      bout.querySelector(".land-wrap").appendChild(f);
      f.srcdoc = res.html;
    }
  }
  const cachedBuild = (buildCache[d.brand_id] || {});
  $("#tabbody").querySelectorAll(".build").forEach((btn) => {
    const mode = btn.dataset.mode;
    if (cachedBuild[mode] && Object.keys(cachedBuild).length) { /* show last build below */ }
    btn.onclick = async () => {
      $("#tabbody").querySelectorAll(".build").forEach(b => b.disabled = true);
      bout.innerHTML = `<div class="agent-pill run"><span class="dot"></span>${mode === "gtm" ? "Strategist is building your play…" : "Strategist + designer are building your page…"}</div><div class="loading"><span class="spin"></span> Working from your audit evidence…</div>`;
      try {
        const res = await api(`/api/brands/${d.brand_id}/build`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode }) });
        (buildCache[d.brand_id] = buildCache[d.brand_id] || {})[mode] = res;
        renderBuild(res);
      } catch (err) {
        bout.innerHTML = `<div class="err-box">Could not build: ${escapeHtml(err.message)}</div>`;
      } finally { $("#tabbody").querySelectorAll(".build").forEach(b => b.disabled = false); }
    };
  });
  // restore last build across tab switches
  const lastMode = Object.keys(cachedBuild)[0];
  if (lastMode) renderBuild(cachedBuild[lastMode]);

  $("#tabbody").querySelectorAll(".rec").forEach((card) => {
    const out = card.querySelector(".gen-out");
    const comp = card.dataset.comp;
    const cached = (actionCache[d.brand_id] || {})[comp];
    if (cached) renderPlan(out, cached);   // restore across tab switches
    card.querySelector(".gen").onclick = async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true; btn.textContent = "Generating…";
      out.classList.add("show");
      out.innerHTML = `<div class="loading"><span class="spin"></span> Writing positioning content + schema markup…</div>`;
      try {
        const p = await api("/api/recommendations/generate", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ brand_id: d.brand_id, competitor: comp }),
        });
        (actionCache[d.brand_id] = actionCache[d.brand_id] || {})[comp] = p;
        renderPlan(out, p);
      } catch (err) {
        out.innerHTML = `<div class="err-box">Could not generate: ${escapeHtml(err.message)}</div>`;
      } finally { btn.disabled = false; btn.textContent = "Generate positioning + schema"; }
    };
  });
}

function renderRetrieval() {
  const d = currentData;
  const cached = retrievalCache[d.brand_id];
  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 14px">We reconstruct the retrieval step behind the AI's answer — which pages it pulls for your queries — and show where <b>your</b> page ranks vs the ones it actually cites. This is our reconstruction (validated ~7.8x better than chance), not the engine's internal rank.</p>
    <div class="rx-bar">
      <input id="rx-site" class="rx-input" type="text" placeholder="Your page URL (e.g. gradewiz.ai)" value="${cached ? escapeHtml(cached._site || "") : ""}" />
      <button id="rx-go" class="btn btn-primary btn-sm">Reconstruct</button>
    </div>
    <div id="rx-out"></div>`;
  const out = $("#rx-out");
  const run = async () => {
    const site = $("#rx-site").value.trim();
    $("#rx-go").disabled = true;
    out.innerHTML = `<div class="loading"><span class="spin"></span> Rebuilding the retrieval set and ranking your page…</div>`;
    try {
      const r = await api(`/api/brands/${d.brand_id}/retrieval`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ site: site || null }) });
      r._site = site;
      retrievalCache[d.brand_id] = r;
      renderRxResult(out, r);
    } catch (e) {
      out.innerHTML = `<div class="err-box">Could not reconstruct: ${escapeHtml(e.message)}</div>`;
    } finally { const b = $("#rx-go"); if (b) b.disabled = false; }
  };
  $("#rx-go").onclick = run;
  if (cached) renderRxResult(out, cached);
}

function renderRxResult(out, r) {
  if (!r.queries || !r.queries.length) {
    out.innerHTML = `<div class="card">${escapeHtml(r.note || "Nothing to reconstruct yet.")}</div>`;
    return;
  }
  const fid = r.fidelity;
  const head = `<div class="rx-head">
    ${r.site ? `<div class="rx-you">Your page ranks <b>#${Math.round(r.your_avg_rank)}</b> on average across these queries</div>` : `<div class="rx-you muted">Add your page URL above to see where you rank.</div>`}
    ${fid ? `<div class="rx-fid">reconstruction fidelity: <b>${fid.lift ? fid.lift + "×" : "—"}</b> vs chance</div>` : ""}
  </div>`;
  const rows = r.queries.map((q) => {
    const items = q.winners.map((w) => {
      const cls = w.you ? "rx-item you" : (w.cited ? "rx-item cited" : "rx-item");
      const tag = w.you ? "YOU" : (w.cited ? "cited" : "");
      const pct = Math.round(w.score * 100);
      return `<div class="${cls}">
        <span class="rx-dom">${escapeHtml(w.domain)}</span>
        <span class="rx-tag">${tag}</span>
        <span class="rx-track"><span style="width:${pct}%"></span></span>
        <span class="rx-sc">${w.score.toFixed(2)}</span></div>`;
    }).join("");
    const yourLine = q.your_rank
      ? `<span class="rx-rank">you: #${q.your_rank}/${q.total_candidates} · ${q.your_score.toFixed(2)}</span>` : "";
    return `<div class="rx-q"><div class="rx-qh"><span>${escapeHtml(q.query)}</span>${yourLine}</div>${items}</div>`;
  }).join("");
  out.innerHTML = head + rows + `<div class="remeasure" style="margin-top:14px">${escapeHtml(r.note || "")}</div>`;
}

function renderAsk() {
  const d = currentData;
  const cached = askCache[d.brand_id];
  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 16px">Ask anything about ${escapeHtml(d.name)}. Answers use this brand's collected AI data when available, otherwise general knowledge.</p>
    <div class="ask-box"><input id="ask-q" type="text" placeholder="e.g. why do buyers pick competitors? what should we change?" autocomplete="off" value="${cached ? escapeHtml(cached.q) : ""}" />
      <button id="ask-btn" class="btn btn-primary btn-sm">Ask</button></div>
    <div id="ask-out">${cached ? cached.html : ""}</div>`;
  const out = $("#ask-out");
  const run = async () => {
    const q = $("#ask-q").value.trim(); if (!q) return;
    const btn = $("#ask-btn"); btn.disabled = true; btn.textContent = "Thinking…";
    out.innerHTML = `<div class="loading"><span class="spin"></span> Retrieving and answering…</div>`;
    try {
      const res = await api(`/api/brands/${d.brand_id}/ask`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }) });
      const tag = res.grounded
        ? `<span class="ask-tag ok">grounded in your data</span>`
        : `<span class="ask-tag">general answer</span>`;
      const sources = (res.sources || []).map((s) => `<div class="ask-src">${escapeHtml(s)}</div>`).join("");
      const html = `<div class="card ask-answer">${tag}<div class="md">${mdToHtml(res.answer)}</div></div>
        ${sources ? `<div class="ask-srcs"><h4>Grounded on</h4>${sources}</div>` : ""}`;
      out.innerHTML = html;
      askCache[d.brand_id] = { q, html };   // persist across tab switches
    } catch (err) { out.innerHTML = `<div class="err-box">Could not answer: ${escapeHtml(err.message)}</div>`; }
    finally { btn.disabled = false; btn.textContent = "Ask"; }
  };
  $("#ask-btn").onclick = run;
  $("#ask-q").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
}

// --- composer ---------------------------------------------------------------

$("#audit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const brand = $("#f-brand").value.trim();
  const category = $("#f-category").value.trim();
  const context = $("#f-context").value.trim();
  const competitor = $("#f-competitor").value.trim();
  if (!brand || !category) return;
  const btn = $("#run-btn"); btn.disabled = true; btn.textContent = "Starting…";
  try {
    const res = await api("/api/audits", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brand, category, context, competitor }) });
    $("#f-brand").value = ""; $("#f-category").value = ""; $("#f-context").value = "";
    $("#f-competitor").value = ""; $("#attach-label").textContent = "Attach file";
    await selectBrand(res.brand_id);
  } catch (err) { alert("Could not start audit: " + err.message); }
  finally { btn.disabled = false; btn.textContent = "Run audit"; }
});

// example chips fill the category
document.querySelectorAll("#cat-examples .ex-chip").forEach((ch) =>
  (ch.onclick = () => { $("#f-category").value = ch.textContent.trim(); $("#f-brand").focus(); }));

// file attach → read text into the context box
$("#f-file").addEventListener("change", (e) => {
  const file = e.target.files[0]; if (!file) return;
  const r = new FileReader();
  r.onload = () => {
    const cur = $("#f-context").value.trim();
    $("#f-context").value = (cur ? cur + "\n\n" : "") + String(r.result).slice(0, 20000);
    $("#attach-label").textContent = file.name;
  };
  r.readAsText(file);
});

$("#new-audit").onclick = showComposer;
window.__newAudit = showComposer;

// Deep-link from GTM Studio's cold-start funnel: /app?brand=ID lands straight on
// that brand (its baseline audit will be in flight, so the progress view shows).
const _bp = new URLSearchParams(location.search).get("brand");
if (_bp) { showPanel(); selectBrand(Number(_bp)); }
else showComposer();
