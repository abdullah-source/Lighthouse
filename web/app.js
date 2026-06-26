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
    renderProgress(data.status, data.name);
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      const s = await api(`/api/brands/${activeId}/status`).catch(() => null);
      if (!s) return;
      if (s.status === "done" || s.status === "error") {
        clearInterval(pollTimer); clearInterval(phraseTimer);
        await loadRecent(); await refreshPanel();
      } else {
        updateStage(s.status);
      }
    }, 2500);
    return;
  }
  clearInterval(phraseTimer);
  currentData = data;
  render();
}

// --- lively progress --------------------------------------------------------

const STAGE_TEXT = {
  pending: "Starting up",
  generating: "Generating real buyer questions",
  probing: "Asking GPT-5, Claude & Perplexity",
  parsing: "Reading what each AI said",
};
const PHRASES = [
  "Triangulating across models…", "Cross-referencing cited sources…",
  "Computing share of voice…", "Mapping the competitor set…",
  "Distilling the verbal vibes…", "Normalizing brand names…",
];

function renderProgress(status, name) {
  panel.innerHTML = `
    <div class="run-card">
      <div class="run-orbit"><span></span><span></span><span></span></div>
      <div class="run-stage" id="run-stage">${escapeHtml(STAGE_TEXT[status] || "Working")}</div>
      <div class="run-phrase" id="run-phrase">${PHRASES[0]}</div>
      <div class="run-for">${name ? "for " + escapeHtml(name) : ""}</div>
      <button class="btn btn-ghost btn-sm run-cancel" id="cancel-btn">Cancel</button>
    </div>`;
  $("#cancel-btn").onclick = cancelActive;
  clearInterval(phraseTimer);
  let i = 0;
  phraseTimer = setInterval(() => {
    i = (i + 1) % PHRASES.length;
    const p = $("#run-phrase"); if (p) p.textContent = PHRASES[i];
  }, 2200);
}
function updateStage(status) {
  const el = $("#run-stage");
  if (el) el.textContent = STAGE_TEXT[status] || "Working";
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
      <div class="tab ${currentTab === "ask" ? "active" : ""}" data-tab="ask">Ask</div>
    </div>
    <div id="tabbody"></div>`;
  panel.querySelectorAll(".tab").forEach((t) =>
    (t.onclick = () => { currentTab = t.dataset.tab; render(); }));
  if (currentTab === "overview") renderOverview();
  else if (currentTab === "vibes") renderVibes();
  else if (currentTab === "action") renderAction();
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
  const cards = comps.map((c) => `
    <div class="rec" data-comp="${escapeHtml(c.brand)}">
      <div class="rec-top"><span class="who">${escapeHtml(c.brand)} is winning here</span>
        <span class="meta muted">${pct(c.rate)} of answers</span></div>
      <p>${escapeHtml(c.brand)} is recommended in ${pct(c.rate)} of responses while ${escapeHtml(d.focal_canonical)} sits at ${pct(d.mention_rate)}. Generate the website change that targets this gap.</p>
      <div class="rec-actions"><button class="btn btn-primary btn-sm gen" data-comp="${escapeHtml(c.brand)}">Generate the change</button></div>
      <div class="gen-out"></div>
    </div>`).join("");
  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 16px">Turn each gap into an actual website change: publish-ready positioning content <b>plus</b> the schema.org markup that reinforces it for AI crawlers, grounded in the vibes you own and the sources the AI trusts.</p>
    ${cards || '<div class="card">Run an audit with competitors to see action recommendations.</div>'}`;

  const copyBtn = (label) => `<button class="btn btn-ghost btn-sm copy">${label}</button>`;
  const wireCopy = (el, getText, note) => el.onclick = async () => {
    try { await navigator.clipboard.writeText(getText()); note.textContent = "Copied."; note.className = "push-note show ok"; }
    catch { note.textContent = "Select and copy manually."; note.className = "push-note show ok"; }
  };

  $("#tabbody").querySelectorAll(".rec").forEach((card) => {
    const out = card.querySelector(".gen-out");
    card.querySelector(".gen").onclick = async (e) => {
      const btn = e.currentTarget; const comp = btn.dataset.comp;
      btn.disabled = true; btn.textContent = "Generating…";
      out.classList.add("show");
      out.innerHTML = `<div class="loading"><span class="spin"></span> Writing positioning content + schema markup…</div>`;
      try {
        const p = await api("/api/recommendations/generate", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ brand_id: d.brand_id, competitor: comp }),
        });
        const notes = (p.verify_notes || []).length
          ? `<div class="verify"><b>Verify before publishing:</b><ul>${p.verify_notes.map((v) => `<li>${escapeHtml(v)}</li>`).join("")}</ul></div>` : "";
        out.innerHTML = `
          ${p.angle ? `<div class="angle"><b>Angle:</b> ${escapeHtml(p.angle)}</div>` : ""}
          <div class="act-block">
            <div class="act-hd"><span>Positioning content</span><span class="copy-slot" data-k="content"></span></div>
            <div class="act-body">${escapeHtml(p.positioning_md || "").replace(/\n/g, "<br>")}</div>
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
      } catch (err) {
        out.innerHTML = `<div class="err-box">Could not generate: ${escapeHtml(err.message)}</div>`;
      } finally { btn.disabled = false; btn.textContent = "Generate the change"; }
    };
  });
}

function renderAsk() {
  const d = currentData;
  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 16px">Ask anything about ${escapeHtml(d.name)}. Answers use this brand's collected AI data when available, otherwise general knowledge.</p>
    <div class="ask-box"><input id="ask-q" type="text" placeholder="e.g. why do buyers pick competitors? what should we change?" autocomplete="off" />
      <button id="ask-btn" class="btn btn-primary btn-sm">Ask</button></div>
    <div id="ask-out"></div>`;
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
      out.innerHTML = `<div class="card ask-answer">${tag}${escapeHtml(res.answer).replace(/\n/g, "<br>")}</div>
        ${sources ? `<div class="ask-srcs"><h4>Grounded on</h4>${sources}</div>` : ""}`;
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

showComposer();
