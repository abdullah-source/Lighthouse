// app.js - product dashboard. Vanilla fetch, two tabs: Overview + Action.

const $ = (s) => document.querySelector(s);
const listEl = $("#brand-list");
const panel = $("#panel");
let activeId = null;
let pollTimer = null;
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

// --- list -------------------------------------------------------------------

function statusBadge(s) {
  if (s === "error") return `<span class="badge err">error</span>`;
  return `<span class="badge run"><span class="spin"></span>${s || "pending"}</span>`;
}

async function loadList() {
  const brands = await api("/api/brands");
  listEl.innerHTML = "";
  if (!brands.length) {
    listEl.innerHTML = `<li class="bi-cat">No audits yet. Run one above.</li>`;
    return;
  }
  for (const b of brands) {
    const li = document.createElement("li");
    li.className = "brand-item" + (b.id === activeId ? " active" : "");
    li.dataset.id = b.id;
    const right = b.status === "done"
      ? `<span class="bi-rate">${pct(b.mention_rate)}</span>`
      : statusBadge(b.status);
    li.innerHTML = `<div class="bi-top"><span class="bi-name">${escapeHtml(b.name)}</span>${right}</div>
                    <div class="bi-cat">${escapeHtml(b.category)}</div>`;
    li.onclick = () => selectBrand(b.id);
    listEl.appendChild(li);
  }
}

// --- selection + polling ----------------------------------------------------

async function selectBrand(id) {
  activeId = id;
  currentTab = "overview";
  clearInterval(pollTimer);
  [...listEl.children].forEach((c) => c.classList?.toggle("active", Number(c.dataset.id) === id));
  await refreshPanel();
}

async function refreshPanel() {
  if (activeId == null) return;
  let data;
  try { data = await api(`/api/brands/${activeId}`); }
  catch (e) { panel.innerHTML = `<div class="err-box">Could not load: ${escapeHtml(e.message)}</div>`; return; }

  if (data.status === "error") {
    panel.innerHTML = `<div class="err-box"><b>Audit failed.</b><br>
      ${escapeHtml(data.error_message || "Unknown error.")}<br><br>
      This is usually a transient API hiccup. Re-run the audit (same brand + category) and it should go through.</div>`;
    return;
  }
  if (data.status && data.status !== "done") {
    panel.innerHTML = `<div class="loading"><span class="spin"></span>
      Running audit for <b style="color:var(--ink);margin:0 4px">${escapeHtml(data.name)}</b> &middot; ${escapeHtml(data.status)}&hellip;</div>`;
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      const s = await api(`/api/brands/${activeId}/status`).catch(() => null);
      if (s && (s.status === "done" || s.status === "error")) {
        clearInterval(pollTimer); await loadList(); await refreshPanel();
      }
    }, 3000);
    return;
  }
  currentData = data;
  render();
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
      <div class="focal">canonical brand: <b>${escapeHtml(d.focal_canonical)}</b><br>${d.total_responses} responses analyzed</div>
    </div>
    <div class="tabs">
      <div class="tab ${currentTab === "overview" ? "active" : ""}" data-tab="overview">Overview</div>
      <div class="tab ${currentTab === "vibes" ? "active" : ""}" data-tab="vibes">Vibes <span class="preview-tag" style="margin-left:6px">lexical</span></div>
      <div class="tab ${currentTab === "action" ? "active" : ""}" data-tab="action">Action <span class="preview-tag" style="margin-left:6px">wedge</span></div>
      <div class="tab ${currentTab === "ask" ? "active" : ""}" data-tab="ask">Ask <span class="preview-tag" style="margin-left:6px">RAG</span></div>
    </div>
    <div id="tabbody"></div>`;
  panel.querySelectorAll(".tab").forEach((t) =>
    (t.onclick = () => { currentTab = t.dataset.tab; render(); }));
  if (currentTab === "overview") renderOverview();
  else if (currentTab === "vibes") renderVibes();
  else if (currentTab === "action") renderAction();
  else renderAsk();
}

function renderVibes() {
  const d = currentData;
  const lex = d.lexical || {};
  const top = lex.focal_top || [];
  const maxC = lex.max_count || 1;

  // frequency-scaled chips = lightweight word cloud (font 13→26px by count)
  const cloud = top.length
    ? top.map((x) => {
        const size = 13 + Math.round((x.count / maxC) * 13);
        const op = 0.55 + 0.45 * (x.count / maxC);
        return `<span class="vibe" style="font-size:${size}px;opacity:${op}" title="${x.count} mentions">${escapeHtml(x.term)}</span>`;
      }).join("")
    : `<div class="bi-cat">No descriptors captured yet. Re-run an audit to capture how AI describes ${escapeHtml(d.name)}.</div>`;

  const ownChips = (arr) => (arr && arr.length)
    ? arr.map((x) => `<span class="vibe-pill">${escapeHtml(x.term)}<span class="vc">${x.count}</span></span>`).join("")
    : `<div class="bi-cat">Nothing distinctive yet.</div>`;

  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 16px">The <b>lexical environment</b>: the words AI assistants actually use to describe ${escapeHtml(d.name)} and rivals. Lean into the vibes you already own.</p>
    <div class="card">
      <h4>How AI describes ${escapeHtml(d.name)}</h4>
      <div class="vibe-cloud">${cloud}</div>
    </div>
    <div class="cards2">
      <div class="card vibe-own"><h4>Vibes you own <span class="preview-tag" style="margin-left:6px">lean in</span></h4><div class="vibe-pills">${ownChips(lex.you_own)}</div></div>
      <div class="card vibe-them"><h4>Vibes competitors own</h4><div class="vibe-pills">${ownChips(lex.they_own)}</div></div>
    </div>`;
}

function renderAsk() {
  const d = currentData;
  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 16px">Ask anything about ${escapeHtml(d.name)} and its category. Answers are grounded in your own ingested context (retrieval-augmented).</p>
    <div class="ask-box">
      <input id="ask-q" type="text" placeholder="e.g. what do our buyers care about most? why might AI skip us?" autocomplete="off" />
      <button id="ask-btn" class="btn btn-primary btn-sm">Ask</button>
    </div>
    <div id="ask-out"></div>`;

  const out = $("#ask-out");
  const run = async () => {
    const q = $("#ask-q").value.trim();
    if (!q) return;
    const btn = $("#ask-btn");
    btn.disabled = true; btn.textContent = "Thinking…";
    out.innerHTML = `<div class="loading"><span class="spin"></span> Retrieving and answering…</div>`;
    try {
      const res = await api(`/api/brands/${d.brand_id}/ask`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const sources = (res.sources || [])
        .map((s) => `<div class="ask-src">${escapeHtml(s)}</div>`).join("");
      out.innerHTML = `<div class="card ask-answer">${escapeHtml(res.answer).replace(/\n/g, "<br>")}</div>
        ${sources ? `<div class="ask-srcs"><h4>Grounded on</h4>${sources}</div>` : ""}`;
    } catch (err) {
      out.innerHTML = `<div class="err-box">Could not answer: ${escapeHtml(err.message)}</div>`;
    } finally { btn.disabled = false; btn.textContent = "Ask"; }
  };
  $("#ask-btn").onclick = run;
  $("#ask-q").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
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
    .map((s) => `<div class="provrow"><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.domain)}</a><span class="meta">${s.count}</span></div>`)
    .join("");
  const provCard = (prov.top_sources && prov.top_sources.length)
    ? `<div class="card prov-card">
        <h4>Sources the AI cites <span class="preview-tag" style="margin-left:6px">the why</span></h4>
        <p class="muted" style="margin:-4px 0 12px;font-size:13px">From ${prov.responses_with_sources} retrieval answers via ${escapeHtml((prov.engines || []).join(", ") || "Perplexity")}. These are the pages the engine trusts in this category. Where you are absent from the top sources is where you lose.</p>
        <div class="provrows">${provSources}</div>
      </div>`
    : `<div class="card prov-card">
        <h4>Sources the AI cites <span class="preview-tag" style="margin-left:6px">the why</span></h4>
        <p class="bi-cat">No citations captured yet. This needs a retrieval engine: add a Perplexity key and re-run to see the sources behind each answer.</p>
      </div>`;
  const pnl = d.panel;
  const panelCard = pnl
    ? `<div class="panel-band ${pnl.grounded ? "grounded" : ""}">
        <div class="pb-head">
          <span class="pb-tag">${pnl.grounded ? "Grounded panel" : "Generic panel"}</span>
          <span class="pb-meta">v${pnl.version} &middot; ${pnl.query_count} buyer queries &middot; frozen</span>
        </div>
        ${pnl.grounded
          ? (pnl.seed_summary ? `<div class="pb-summary">${escapeHtml(pnl.seed_summary)}</div>` : "")
          : `<div class="pb-summary muted">Generic questions. Add your own customer context on the next run to ground the panel in how your buyers actually ask.</div>`}
      </div>`
    : "";
  $("#tabbody").innerHTML = `
    ${panelCard}
    <div class="kpis">
      <div class="kpi"><div class="label">Mention rate</div><div class="val accent">${pct(d.mention_rate)}</div></div>
      <div class="kpi"><div class="label">Avg position</div><div class="val">${num(d.avg_position)}</div></div>
      <div class="kpi"><div class="label">Share of voice</div><div class="val">${pct(d.share_of_voice)}</div></div>
      <div class="kpi"><div class="label">Responses</div><div class="val">${d.total_responses}</div></div>
    </div>
    <div class="norm">
      <div class="big">${n.merged ?? 0}</div>
      <div class="txt">raw brand variants merged by <b>brand-identity normalization</b>.<br>
        ${n.raw_variants ?? 0} raw mentions resolved to <b>${n.canonical_brands ?? 0}</b> real brands.
        Without this, "${escapeHtml(d.focal_canonical)}" and its product names would be counted separately.</div>
    </div>
    <div class="cards2">
      <div class="card"><h4>You vs competitors (mentions)</h4>${focalBar}${competitors || '<div class="bi-cat">No competitors found.</div>'}</div>
      <div class="card"><h4>By model</h4>${models || '<div class="bi-cat">No model data.</div>'}</div>
    </div>
    ${provCard}`;
}

function renderAction() {
  const d = currentData;
  const comps = (d.competitors || []).slice(0, 4);
  const cards = comps.map((c, i) => `
    <div class="rec" data-i="${i}">
      <div class="rec-top">
        <span class="who">${escapeHtml(c.brand)} is winning here</span>
        <span class="meta muted">${pct(c.rate)} of answers${c.avg_position != null ? " &middot; pos " + c.avg_position : ""}</span>
      </div>
      <p>${escapeHtml(c.brand)} is recommended in ${pct(c.rate)} of responses while ${escapeHtml(d.focal_canonical)} sits at ${pct(d.mention_rate)}.
         Generate a publish-ready fix that targets this gap and cites the AI responses behind it.</p>
      <div class="rec-actions">
        <button class="btn btn-primary btn-sm gen" data-comp="${escapeHtml(c.brand)}">Generate fix</button>
        <button class="btn btn-ghost btn-sm push">Copy &amp; push <span class="preview-tag" style="margin-left:6px">preview</span></button>
      </div>
      <div class="gen-out"></div>
      <div class="push-note"></div>
    </div>`).join("");

  $("#tabbody").innerHTML = `
    <p class="muted" style="margin:-4px 0 16px">The wedge: measurement tells you where you lose. This turns each gap into a publish-ready change, in one step.</p>
    ${cards || '<div class="card">Run an audit with competitors to see action recommendations.</div>'}`;

  $("#tabbody").querySelectorAll(".rec").forEach((card) => {
    const out = card.querySelector(".gen-out");
    card.querySelector(".gen").onclick = async (e) => {
      const btn = e.currentTarget;
      const comp = btn.dataset.comp;
      btn.disabled = true; btn.textContent = "Generating…";
      try {
        const art = await api("/api/recommendations/generate", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ brand_id: d.brand_id, competitor: comp }),
        });
        out.textContent = art.body || "(no content)";
        out.classList.add("show");
      } catch (err) {
        out.textContent = "Could not generate: " + err.message; out.classList.add("show");
      } finally { btn.disabled = false; btn.textContent = "Generate fix"; }
    };
    const note = card.querySelector(".push-note");
    const flash = (msg, tone) => {
      note.textContent = msg;
      note.className = "push-note show" + (tone ? " " + tone : "");
    };
    card.querySelector(".push").onclick = async () => {
      const text = out.textContent.trim();
      if (!out.classList.contains("show") || !text) {
        flash("Generate the fix first, then copy it to push into your CMS.", "warn");
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
        flash("Copied. Paste into your CMS to publish. Direct one-click push (Shopify / Webflow / WordPress) ships in v2.", "ok");
      } catch {
        flash("Select the text above to copy. Direct push (Shopify / Webflow / WordPress) ships in v2.", "ok");
      }
    };
  });
}

// --- new audit --------------------------------------------------------------

$("#audit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const brand = $("#f-brand").value.trim();
  const category = $("#f-category").value.trim();
  const context = $("#f-context").value.trim();
  if (!brand || !category) return;
  const btn = $("#run-btn");
  btn.disabled = true; btn.textContent = "Starting…";
  try {
    const res = await api("/api/audits", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brand, category, context }),
    });
    $("#f-brand").value = ""; $("#f-category").value = ""; $("#f-context").value = "";
    await loadList(); await selectBrand(res.brand_id);
  } catch (err) { alert("Could not start audit: " + err.message); }
  finally { btn.disabled = false; btn.textContent = "Run audit"; }
});

$("#refresh").addEventListener("click", loadList);

// Example category chips fill the field (and nudge focus to brand).
document.querySelectorAll("#cat-examples .ex-chip").forEach((ch) => {
  ch.addEventListener("click", () => { $("#f-category").value = ch.textContent.trim(); $("#f-brand").focus(); });
});

loadList();
