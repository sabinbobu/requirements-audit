/* requirements-audit editor UI.
 *
 * Vanilla JS, no build step. Talks only to the FastAPI endpoints — no pipeline
 * logic lives here (same thin-client rule the previous UI followed). State is
 * a single object; every mutation re-renders the affected view.
 */
"use strict";

const $ = (sel) => document.querySelector(sel);

const state = {
  docs: [],            // [{doc_id, chunk_count, source}]
  openDoc: null,       // doc_id currently in the editor
  chunks: {},          // doc_id -> [chunk]
  findings: [],        // audit findings, as returned by /audit or /audit/stream
  byReq: new Map(),    // requirement_id -> [finding]
  reqDoc: new Map(),   // requirement_id -> doc_id (for jump-to-requirement)
  decisions: new Map(),// finding key -> "accepted" | "dismissed" (session-only;
                       // persisting reviews through the API is a roadmap item)
  screen: "dashboard", // "dashboard" | "workspace" — the two top-level views
  dashboardSelection: null, // doc_id selected (not yet opened) on the dashboard
  lastAuditDocId: null, // doc_id the most recent audit was scoped to (null = full corpus)
};

function findChunk(reqId) {
  const docId = state.reqDoc.get(reqId);
  if (!docId) return null;
  return (state.chunks[docId] || []).find((c) => c.requirement_id === reqId) || null;
}

const findingKey = (f) =>
  `${f.candidate.req_a}|${f.candidate.req_b}|${f.candidate.conflict_type}`;

function rerenderAll() {
  renderProblems();
  renderExplorer();
  renderEditor();
}

/* ─── screens: dashboard (landing) vs workspace (editor + panel) ───────── */
function showScreen(name) {
  state.screen = name;
  $("#dashboard").hidden = name !== "dashboard";
  $("#workspace").hidden = name !== "workspace";
  if (name === "workspace" && state.openDoc) renderEditor();
}

function docExt(doc) {
  return (doc.source || "").split(".").pop()?.toLowerCase() || "";
}

function renderDashboard() {
  const list = $("#dashboard-doc-list");
  list.innerHTML = "";
  for (const d of state.docs) {
    const ext = docExt(d);
    const li = document.createElement("li");
    li.className = "doc-card" + (d.doc_id === state.dashboardSelection ? " selected" : "");
    li.setAttribute("role", "option");
    li.innerHTML =
      `<span class="doc-badge ${ext}">${ext.toUpperCase() || "?"}</span>` +
      `<span class="doc-name">${d.source || d.doc_id}</span>` +
      `<span class="doc-count">${d.chunk_count} reqs</span>` +
      `<button class="doc-open-btn" type="button">open →</button>`;
    li.onclick = (e) => {
      if (e.target.closest(".doc-open-btn")) return;
      state.dashboardSelection = d.doc_id;
      renderDashboard();
    };
    li.querySelector(".doc-open-btn").onclick = (e) => {
      e.stopPropagation();
      state.openDoc = d.doc_id;
      showScreen("workspace");
    };
    list.appendChild(li);
  }
  const auditBtn = $("#dashboard-audit-btn");
  auditBtn.disabled = !state.dashboardSelection;
  auditBtn.textContent = state.dashboardSelection
    ? `▶ Run audit on ${state.dashboardSelection}`
    : "▶ Run audit (select a document)";
}

/* conflict type -> problem severity (superseded refs are warnings: the text is
 * stale rather than self-contradictory; value conflicts are errors) */
const SEVERITY = {
  numeric_mismatch: "error",
  incompatible_constraint: "error",
  superseded_reference: "warning",
};

const status = (msg) => { $("#status-msg").textContent = msg; };
const stats = (msg) => { $("#status-stats").textContent = msg; };

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

/* ─── health + explorer ────────────────────────────────────────────────── */
async function loadHealth() {
  const el = $("#health");
  try {
    const h = await api("/healthz");
    el.textContent = `v${h.version} · ${h.chunks} chunks`;
    el.className = "health ok";
  } catch (e) {
    el.textContent = "API unreachable";
    el.className = "health bad";
  }
}

async function loadDocs() {
  state.docs = await api("/documents");
  renderExplorer();
  renderDashboard();
  // Preload every doc's chunks: the corpus is small, and jump-to-requirement
  // across documents needs the req -> doc map up front.
  for (const d of state.docs) {
    const detail = await api(`/documents/${d.doc_id}`);
    state.chunks[d.doc_id] = detail.chunks;
    for (const c of detail.chunks) state.reqDoc.set(c.requirement_id, d.doc_id);
  }
  // Pick a default document for the editor without forcing a render — the
  // workspace is not visible until the user leaves the dashboard.
  if (!state.openDoc && state.docs.length) state.openDoc = state.docs[0].doc_id;
  renderExplorer();
}

function docProblemCounts(docId) {
  let errors = 0, warnings = 0;
  for (const [req, findings] of state.byReq) {
    if (state.reqDoc.get(req) !== docId) continue;
    for (const f of findings) {
      SEVERITY[f.candidate.conflict_type] === "warning" ? warnings++ : errors++;
    }
  }
  return { errors, warnings };
}

function renderExplorer() {
  const ul = $("#file-list");
  ul.innerHTML = "";
  for (const d of state.docs) {
    const li = document.createElement("li");
    li.setAttribute("role", "option");
    if (d.doc_id === state.openDoc) li.classList.add("active");
    const name = document.createElement("span");
    name.textContent = d.source || d.doc_id; // real filename: SYS.md, BRAKE.pdf, …
    li.appendChild(name);
    const { errors, warnings } = docProblemCounts(d.doc_id);
    if (errors || warnings) {
      const badge = document.createElement("span");
      badge.className = errors ? "file-badge" : "file-badge warn";
      badge.textContent = errors + warnings;
      li.appendChild(badge);
    }
    li.onclick = () => openDoc(d.doc_id);
    ul.appendChild(li);
  }
}

/* ─── editor ───────────────────────────────────────────────────────────── */
async function openDoc(docId) {
  if (!state.chunks[docId]) {
    const detail = await api(`/documents/${docId}`);
    state.chunks[docId] = detail.chunks;
  }
  state.openDoc = docId;
  renderExplorer();
  renderEditor();
}

function problemCard(finding, ownReq) {
  const c = finding.candidate;
  const severity = SEVERITY[c.conflict_type] ?? "error";
  const other = c.req_a === ownReq ? c.req_b : c.req_a;
  const otherQuote = c.req_a === ownReq ? c.evidence_quote_b : c.evidence_quote_a;
  const card = document.createElement("div");
  card.className = `req-problem-card ${severity}`;
  const label = c.conflict_type.replace(/_/g, " ");
  card.innerHTML =
    `<strong>${severity === "warning" ? "⚠" : "✖"} ${label}</strong> with ` +
    `<span class="other-req" data-req="${other}">${other}</span>` +
    `<span class="conf"> · confidence ${finding.verdict.confidence.toFixed(2)}</span>` +
    `<br/><em>“${otherQuote}”</em>`;
  card.querySelector(".other-req").onclick = () => jumpTo(other);

  // Human-review gate: accept/dismiss, session-only (persistence: roadmap).
  const controls = document.createElement("div");
  controls.className = "review-controls";
  const decision = state.decisions.get(findingKey(finding));
  for (const [label, value] of [["✓ Accept", "accepted"], ["✕ Dismiss", "dismissed"]]) {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.title = "Review decision (session-only)";
    btn.classList.toggle("chosen", decision === value);
    btn.onclick = () => {
      state.decisions.set(findingKey(finding), decision === value ? undefined : value);
      rerenderAll();
    };
    controls.appendChild(btn);
  }
  const resolveBtn = document.createElement("button");
  resolveBtn.className = "resolve-btn";
  resolveBtn.textContent = "⇄ Resolve";
  resolveBtn.title = "Compare both sides and edit them to clear this conflict";
  resolveBtn.onclick = () => openCompare(finding);
  controls.appendChild(resolveBtn);

  if (decision) {
    const tag = document.createElement("span");
    tag.className = `decided ${decision}`;
    tag.textContent = decision;
    controls.appendChild(tag);
  }
  card.appendChild(controls);
  if (decision === "dismissed") card.classList.add("dismissed");
  return card;
}

function renderEditor() {
  const openMeta = state.docs.find((d) => d.doc_id === state.openDoc);
  $("#open-doc-name").textContent = openMeta?.source || state.openDoc;
  const body = $("#editor-body");
  body.innerHTML = "";
  let lastSection = null;

  for (const chunk of state.chunks[state.openDoc] ?? []) {
    const section = chunk.section_path[chunk.section_path.length - 1];
    if (section !== lastSection) {
      const h = document.createElement("div");
      h.className = "section-header";
      h.textContent = section;
      body.appendChild(h);
      lastSection = section;
    }

    const findings = state.byReq.get(chunk.requirement_id) ?? [];
    const worst = findings.some((f) => SEVERITY[f.candidate.conflict_type] !== "warning")
      ? "error"
      : findings.length ? "warning" : null;

    const art = document.createElement("article");
    art.className = "req" + (worst ? ` problem-${worst}` : "");
    art.id = `req-${chunk.requirement_id}`;

    const gutter = document.createElement("div");
    gutter.className = "gutter";
    gutter.innerHTML = `<span class="req-id">${chunk.requirement_id}</span>` +
      (chunk.status === "superseded" ? `<span class="status superseded">superseded</span>` : "");
    art.appendChild(gutter);

    const content = document.createElement("div");
    content.className = "req-content";
    const title = document.createElement("h4");
    title.className = "req-title" + (worst ? ` squiggle-${worst}` : "");
    title.textContent = chunk.title;
    const text = document.createElement("p");
    text.className = "req-text";
    text.textContent = chunk.text;
    content.append(title, text);

    const params = Object.entries(chunk.parameters ?? {});
    if (params.length) {
      const p = document.createElement("div");
      p.className = "req-params";
      p.textContent = params.map(([k, v]) => `${k} = ${v}`).join("   ");
      content.appendChild(p);
    }
    for (const f of findings) content.appendChild(problemCard(f, chunk.requirement_id));

    art.appendChild(content);
    body.appendChild(art);
  }
}

async function jumpTo(reqId) {
  const docId = state.reqDoc.get(reqId);
  if (!docId) return;
  if (docId !== state.openDoc) await openDoc(docId);
  const el = document.getElementById(`req-${reqId}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.remove("flash");
  void el.offsetWidth; // restart the CSS animation
  el.classList.add("flash");
}

/* ─── audit progress overlay ────────────────────────────────────────────── */
function showAuditOverlay(docId) {
  $("#audit-overlay").hidden = false;
  $("#audit-overlay-title").textContent = docId ? `Auditing ${docId}…` : "Auditing full corpus…";
  $("#audit-stage-chips").innerHTML = "";
  setAuditProgress(null, null);
}

function hideAuditOverlay() {
  $("#audit-overlay").hidden = true;
}

function setAuditProgress(done, total) {
  const fill = $("#audit-progress-fill");
  const label = $("#audit-progress-label");
  if (total) {
    fill.classList.remove("indeterminate");
    fill.style.width = `${Math.round((done / total) * 100)}%`;
    label.textContent = `comparator: ${done} / ${total} pairs`;
  } else {
    // No total yet (deterministic stages, or an LLM-free audit): an
    // indeterminate bar still shows the run is alive.
    fill.classList.add("indeterminate");
    fill.style.width = "100%";
    label.textContent = "preparing…";
  }
}

function auditStageChip(stepRecord) {
  const chip = document.createElement("span");
  chip.className = "stage-chip done";
  chip.textContent = `${stepRecord.name} ${stepRecord.latency_ms.toFixed(0)}ms`;
  return chip;
}

function applyAuditReport(report) {
  state.findings = report.findings;
  state.lastAuditDocId = report.doc_id ?? null; // "resolve" re-runs this same scope
  state.byReq = new Map();
  for (const f of report.findings) {
    for (const req of [f.candidate.req_a, f.candidate.req_b]) {
      if (!state.byReq.has(req)) state.byReq.set(req, []);
      state.byReq.get(req).push(f);
    }
  }
  renderProblems();
  renderExplorer();
  renderEditor();
  const mode = report.llm_used ? "LLM-verified" : "deterministic rules (no LLM key)";
  const scope = report.doc_id ? `scoped to ${report.doc_id}` : "full corpus";
  status(`audit: ${report.findings.length} problem(s) · ${scope} · ${mode}`);
  const t = report.trace;
  stats(
    `${t.total_latency_ms.toFixed(0)} ms · ${t.usage?.input_tokens ?? 0}/${t.usage?.output_tokens ?? 0} tok` +
    (t.estimated_usd ? ` · ~$${t.estimated_usd.toFixed(4)}` : "")
  );
}

/* ─── compare / resolve (Beyond-Compare-style) ──────────────────────────── */
let compareState = null; // { reqA, reqB, diffKeys, orig: {a,b}, edited: {a,b} }

function diffParamKeys(paramsA, paramsB) {
  const a = paramsA || {}, b = paramsB || {};
  // Only keys present on both sides with different values are "the conflict" —
  // a key unique to one side isn't part of what's contradicting.
  return Object.keys(a).filter((k) => k in b && a[k] !== b[k]);
}

function openCompare(finding) {
  const c = finding.candidate;
  const chunkA = findChunk(c.req_a);
  const chunkB = findChunk(c.req_b);
  if (!chunkA || !chunkB) {
    status("resolve failed: source requirement not loaded — try re-ingesting");
    return;
  }
  compareState = {
    reqA: c.req_a,
    reqB: c.req_b,
    diffKeys: diffParamKeys(chunkA.parameters, chunkB.parameters),
    orig: {
      a: { text: chunkA.text, params: { ...chunkA.parameters } },
      b: { text: chunkB.text, params: { ...chunkB.parameters } },
    },
    edited: {
      a: { text: chunkA.text, params: { ...chunkA.parameters } },
      b: { text: chunkB.text, params: { ...chunkB.parameters } },
    },
  };
  $("#compare-title").textContent = `Resolve: ${c.req_a} ↔ ${c.req_b}`;
  renderCompare();
  $("#compare-status").textContent = "";
  $("#compare-resolve-btn").disabled = false;
  $("#compare-overlay").hidden = false;
}

function closeCompare() {
  $("#compare-overlay").hidden = true;
  compareState = null;
}

function renderCompare() {
  const { reqA, reqB, diffKeys, edited } = compareState;
  const chunkA = findChunk(reqA), chunkB = findChunk(reqB);
  $("#compare-a-label").textContent = `${chunkA.doc_id} · ${reqA}`;
  $("#compare-b-label").textContent = `${chunkB.doc_id} · ${reqB}`;
  $("#compare-a-text").value = edited.a.text;
  $("#compare-b-text").value = edited.b.text;

  for (const useBtn of document.querySelectorAll(".compare-use-btn")) {
    useBtn.hidden = diffKeys.length === 0; // nothing to sync for a pure-text conflict
  }

  for (const side of ["a", "b"]) {
    const container = $(`#compare-${side}-params`);
    container.innerHTML = "";
    for (const key of diffKeys) {
      const row = document.createElement("div");
      row.className = "compare-param-row diff";
      const input = document.createElement("input");
      input.type = "text";
      input.value = edited[side].params[key] ?? "";
      input.oninput = (e) => { compareState.edited[side].params[key] = e.target.value; };
      const label = document.createElement("label");
      label.textContent = key;
      row.append(label, input);
      container.appendChild(row);
    }
  }
}

function useSide(side) {
  const other = side === "a" ? "b" : "a";
  for (const key of compareState.diffKeys) {
    compareState.edited[other].params[key] = compareState.edited[side].params[key];
  }
  renderCompare();
}

function _sideChanged(side) {
  const { orig, edited } = compareState;
  return (
    edited[side].text !== orig[side].text ||
    JSON.stringify(edited[side].params) !== JSON.stringify(orig[side].params)
  );
}

async function resolveCompare() {
  const { reqA, reqB, edited } = compareState;
  const btn = $("#compare-resolve-btn");
  btn.disabled = true;
  $("#compare-status").textContent = "saving…";

  try {
    const edits = [];
    if (_sideChanged("a")) edits.push([reqA, edited.a]);
    if (_sideChanged("b")) edits.push([reqB, edited.b]);
    if (!edits.length) {
      $("#compare-status").textContent = "no changes to save";
      btn.disabled = false;
      return;
    }

    const updated = await Promise.all(
      edits.map(([reqId, side]) =>
        api(`/requirements/${encodeURIComponent(reqId)}`, {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ text: side.text, parameters: side.params }),
        })
      )
    );
    // Refresh the locally cached chunks so the editor reflects the edit
    // immediately, even before the re-audit's response comes back.
    for (const chunk of updated) {
      const list = state.chunks[chunk.doc_id];
      if (list) {
        const idx = list.findIndex((c) => c.requirement_id === chunk.requirement_id);
        if (idx >= 0) list[idx] = chunk;
      }
    }
    const rescopeTo = state.lastAuditDocId;
    closeCompare();
    await runAudit(rescopeTo);
  } catch (e) {
    $("#compare-status").textContent = `save failed: ${e.message}`;
    btn.disabled = false;
  }
}

/* ─── audit / problems panel (SSE over fetch, with a progress overlay) ──── */
async function runAudit(docId) {
  const btn = $("#audit-btn");
  btn.disabled = true;
  showAuditOverlay(docId);
  status(docId ? `auditing ${docId}…` : "auditing full corpus…");

  try {
    const res = await fetch("/audit/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ doc_id: docId || null }),
    });
    if (!res.ok) {
      const detail = (await res.json()).detail ?? res.statusText;
      throw new Error(detail);
    }
    // Minimal SSE parse: the server emits single-line `event:`/`data:` frames.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", event = "", report = null;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep the trailing partial line
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) {
          const data = line.slice(5).trim();
          if (event === "stage") {
            $("#audit-stage-chips").appendChild(auditStageChip(JSON.parse(data)));
          } else if (event === "progress") {
            const p = JSON.parse(data);
            setAuditProgress(p.done, p.total);
          } else if (event === "report") {
            report = JSON.parse(data);
          } else if (event === "error") {
            throw new Error(data);
          }
        }
      }
    }
    if (!report) throw new Error("audit stream ended with no report");

    hideAuditOverlay();
    if (docId) await openDoc(docId);
    showScreen("workspace");
    switchPanel("problems");
    applyAuditReport(report);
  } catch (e) {
    hideAuditOverlay();
    status(`audit failed: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
}

function renderProblems() {
  const page = $("#panel-problems");
  const count = $("#problem-count");
  page.innerHTML = "";
  count.hidden = state.findings.length === 0;
  count.textContent = state.findings.length;

  if (!state.findings.length) {
    page.innerHTML = `<div class="empty-state small">No contradictions found. 🎉</div>`;
    return;
  }
  for (const f of state.findings) {
    const c = f.candidate;
    const severity = SEVERITY[c.conflict_type] ?? "error";
    const decision = state.decisions.get(findingKey(f));
    const row = document.createElement("div");
    row.className = "problem-row" + (decision === "dismissed" ? " dismissed" : "");
    row.innerHTML =
      `<span class="icon ${severity}">${severity === "warning" ? "⚠" : "✖"}</span>` +
      `<span class="ptype">${c.conflict_type}</span>` +
      `<span class="pmsg"><span class="pair">${c.req_a}</span> ↔ <span class="pair">${c.req_b}</span>` +
      ` — “${c.evidence_quote_a}” vs “${c.evidence_quote_b}”</span>` +
      `<span class="conf">${(f.verdict.confidence * 100).toFixed(0)}%</span>`;
    row.onclick = () => jumpTo(c.req_a);
    const resolveBtn = document.createElement("button");
    resolveBtn.className = "resolve-btn";
    resolveBtn.textContent = "⇄ Resolve";
    resolveBtn.onclick = (e) => {
      e.stopPropagation();
      openCompare(f);
    };
    row.appendChild(resolveBtn);
    page.appendChild(row);
  }
}

/* ─── query / answer panel (SSE over fetch) ────────────────────────────── */
async function ask(question) {
  const btn = $("#query-btn");
  btn.disabled = true;
  switchPanel("answer");
  const page = $("#panel-answer");
  page.innerHTML = `<div class="stage-chips"></div>`;
  const chips = page.querySelector(".stage-chips");
  status("querying…");

  try {
    const res = await fetch("/query", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) {
      const detail = (await res.json()).detail ?? res.statusText;
      throw new Error(detail);
    }
    // Minimal SSE parse: the server emits single-line `event:`/`data:` frames.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", event = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep the trailing partial line
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) handleQueryEvent(event, line.slice(5).trim(), chips, page);
      }
    }
    status("answer ready");
  } catch (e) {
    page.innerHTML = `<div class="answer-error">✖ ${e.message}</div>`;
    status("query failed");
  } finally {
    btn.disabled = false;
  }
}

function handleQueryEvent(event, data, chips, page) {
  if (event === "stage") {
    const s = JSON.parse(data);
    const chip = document.createElement("span");
    chip.className = "stage-chip done";
    chip.textContent = `${s.name} ${s.latency_ms.toFixed(0)}ms`;
    chips.appendChild(chip);
  } else if (event === "answer") {
    const a = JSON.parse(data);
    const div = document.createElement("div");
    div.className = "answer-text";
    div.textContent = a.text;
    page.appendChild(div);
    if (a.citations?.length) {
      const cts = document.createElement("div");
      cts.className = "citations";
      for (const c of a.citations) {
        const chip = document.createElement("span");
        chip.className = "citation-chip";
        chip.textContent = `${c.doc_id} · ${c.requirement_id}`;
        chip.title = c.quote;
        chip.onclick = () => jumpTo(c.requirement_id);
        cts.appendChild(chip);
      }
      page.appendChild(cts);
    }
  } else if (event === "trace") {
    const t = JSON.parse(data);
    stats(
      `${t.total_latency_ms.toFixed(0)} ms · ${t.usage?.input_tokens ?? 0}/${t.usage?.output_tokens ?? 0} tok` +
      (t.estimated_usd ? ` · ~$${t.estimated_usd.toFixed(4)} (${t.pricing_model})` : "")
    );
  } else if (event === "error") {
    const div = document.createElement("div");
    div.className = "answer-error";
    div.textContent = `✖ ${data}`;
    page.appendChild(div);
  }
}

/* ─── panel tabs / ingest / wiring ─────────────────────────────────────── */
function switchPanel(name) {
  for (const b of document.querySelectorAll("#panel-tabs button"))
    b.classList.toggle("active", b.dataset.tab === name);
  for (const p of document.querySelectorAll(".panel-page"))
    p.classList.remove("active");
  $(`#panel-${name}`).classList.add("active");
}

async function ingest() {
  status("ingesting corpus/…");
  try {
    const r = await api("/ingest", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ corpus_dir: "corpus/" }),
    });
    status(`ingest: ${r.new_docs.length} new · ${r.updated_docs.length} updated · ${r.unchanged_docs.length} unchanged · ${r.chunks} chunks`);
    await Promise.all([loadHealth(), loadDocs()]);
  } catch (e) {
    status(`ingest failed: ${e.message}`);
  }
}

async function uploadFile(file) {
  status(`uploading ${file.name}…`);
  const body = new FormData();
  body.append("file", file);
  try {
    const r = await api("/upload", { method: "POST", body }); // no content-type: browser sets the multipart boundary
    const added = [...r.new_docs, ...r.updated_docs];
    status(added.length
      ? `uploaded ${file.name}: ${added.join(", ")} (${r.chunks} chunks total)`
      : `uploaded ${file.name}: already ingested, unchanged`);
    await Promise.all([loadHealth(), loadDocs()]);
  } catch (e) {
    // 400 = wrong type, 413 = too big, 422 = unparseable — the detail explains which.
    status(`upload failed: ${e.message}`);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Topbar: "Run audit" scopes to whatever document is open in the editor
  // (full corpus if none) — the dashboard's own button scopes to its picker.
  $("#audit-btn").onclick = () => runAudit(state.openDoc);
  $("#dashboard-btn").onclick = () => showScreen("dashboard");

  // Workspace explorer toolbar.
  $("#ingest-btn").onclick = ingest;
  $("#upload-btn").onclick = () => $("#upload-input").click();
  $("#upload-input").onchange = (e) => {
    const file = e.target.files[0];
    if (file) uploadFile(file);
    e.target.value = ""; // allow re-uploading the same filename
  };

  // Dashboard toolbar — same ingest()/uploadFile() handlers, which already
  // refresh both the explorer and the dashboard document list.
  $("#dashboard-ingest-btn").onclick = ingest;
  $("#dashboard-upload-btn").onclick = () => $("#dashboard-upload-input").click();
  $("#dashboard-upload-input").onchange = (e) => {
    const file = e.target.files[0];
    if (file) uploadFile(file);
    e.target.value = "";
  };

  // Dashboard document picker + audit entry points.
  $("#dashboard-audit-btn").onclick = () => runAudit(state.dashboardSelection);
  $("#dashboard-audit-all-btn").onclick = () => runAudit(null);
  $("#dashboard-browse-btn").onclick = () => {
    if (!state.openDoc && state.docs.length) state.openDoc = state.docs[0].doc_id;
    showScreen("workspace");
  };

  document.querySelectorAll("#panel-tabs button").forEach(
    (b) => (b.onclick = () => switchPanel(b.dataset.tab))
  );
  $("#query-form").onsubmit = (e) => {
    e.preventDefault();
    const q = $("#query-input").value.trim();
    if (q) ask(q);
  };

  // Compare / resolve overlay.
  $("#compare-close-btn").onclick = closeCompare;
  $("#compare-resolve-btn").onclick = resolveCompare;
  document.querySelectorAll(".compare-use-btn").forEach(
    (b) => (b.onclick = () => useSide(b.dataset.use))
  );
  $("#compare-a-text").oninput = (e) => { if (compareState) compareState.edited.a.text = e.target.value; };
  $("#compare-b-text").oninput = (e) => { if (compareState) compareState.edited.b.text = e.target.value; };

  showScreen("dashboard");
  loadHealth();
  loadDocs().catch((e) => status(`load failed: ${e.message} — ingest the corpus first (↻)`));
});
