const appEl = document.getElementById("app");
const subtitleEl = document.getElementById("top-subtitle");

const state = {
  view: "list",
  reviews: [],
  review: null,
  tab: "section",
  sectionId: null,
  keys: [],
  statements: [],
  error: "",
  busy: false,
};

window.addEventListener("hashchange", boot);
boot();

async function boot() {
  const route = parseHash();
  try {
    if (route.view === "review") {
      await loadReview(route.id, route.tab, route.sectionId);
    } else {
      await loadList();
    }
  } catch (err) {
    state.error = err.message || String(err);
    render();
  }
}

function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  const params = new URLSearchParams(query);
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "reviews" && parts[1]) {
    return {
      view: "review",
      id: parts[1],
      tab: params.get("tab") === "document" ? "document" : "section",
      sectionId: params.get("sid"),
    };
  }
  return { view: "list" };
}

function setHash(reviewId, tab, sectionId) {
  const params = new URLSearchParams();
  params.set("tab", tab);
  if (sectionId) params.set("sid", sectionId);
  location.hash = `#/reviews/${reviewId}?${params.toString()}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!response.ok) {
    throw new Error(formatDetail(data?.detail) || `HTTP ${response.status}`);
  }
  return data;
}

function formatDetail(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg || JSON.stringify(item))
      .join("; ");
  }
  return JSON.stringify(detail);
}

async function loadList() {
  const data = await api("/api/reviews");
  state.view = "list";
  state.reviews = data.reviews || [];
  state.review = null;
  state.error = "";
  subtitleEl.textContent = "Compliance team · section coverage";
  render();
}

async function loadReview(id, tab, sectionId) {
  const review = await api(`/api/reviews/${id}`);
  state.view = "review";
  state.review = review;
  state.tab = tab || "section";
  const first = review.sections[0]?.id;
  state.sectionId = sectionId && review.sections.some((s) => s.id === sectionId) ? sectionId : first;
  pullDraft();
  state.error = "";
  subtitleEl.textContent = `${review.document.meta.title} · ${review.domain}`;
  render();
}

function pullDraft() {
  if (!state.review || !state.sectionId) {
    state.keys = [];
    state.statements = [];
    return;
  }
  const sid = state.sectionId;
  const statements = state.review.document.statements.filter((item) => item.source_section_id === sid);
  const referenced = new Set(statements.flatMap((item) => Object.keys(item.accepted || {})));
  state.statements = statements.map(clone);
  state.keys = state.review.document.keys
    .filter((key) => key.source_section_id === sid || referenced.has(key.id))
    .map(clone);
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function currentSection() {
  return state.review?.sections.find((item) => item.id === state.sectionId) || null;
}

function sectionStatus(sectionId) {
  return state.review?.reviews?.[sectionId]?.status || "pending";
}

function progressLabel(progress) {
  const done = (progress.covered || 0) + (progress.no_restriction || 0);
  return `${done}/${progress.total} reviewed · ${progress.pending || 0} pending`;
}

function render() {
  if (state.view === "list") {
    appEl.innerHTML = renderList();
    bindList();
    return;
  }
  appEl.innerHTML = renderReview();
  bindReview();
}

function renderList() {
  const cards = state.reviews
    .map(
      (item) => `
      <article class="review-card">
        <div>
          <h2>${esc(item.title)}</h2>
          <p class="muted">${esc(item.domain)} · ${esc(item.source_md)}</p>
          <p class="progress">${esc(progressLabel(item.progress))}</p>
        </div>
        <a class="btn" href="#/reviews/${encodeURIComponent(item.id)}?tab=section">Open</a>
      </article>`
    )
    .join("");
  return `
    ${state.error ? `<div class="flash">${esc(state.error)}</div>` : ""}
    <h1>Reviews</h1>
    <p class="muted">Open a converted policy Markdown file. Review each section against closed auto-checks, then clear leftover blocks in the full document.</p>
    <form id="create-form" class="row">
      <div class="field">
        <label>Domain</label>
        <input name="domain" value="InfoSec" required />
      </div>
      <div class="field" style="min-width:22rem;flex:1">
        <label>Markdown path in repo</label>
        <input name="source_md" value="examples/policies/infosec.md" required />
      </div>
      <button class="btn" type="submit">Create review</button>
    </form>
    <form id="upload-form" class="row" style="margin-top:0.6rem">
      <div class="field">
        <label>Or upload .md</label>
        <input type="file" name="file" accept=".md,.txt,text/markdown" />
      </div>
      <div class="field">
        <label>Domain</label>
        <input name="domain" value="InfoSec" required />
      </div>
      <button class="btn secondary" type="submit">Upload</button>
    </form>
    <div class="review-list">${cards || "<p class='muted'>No reviews yet.</p>"}</div>
  `;
}

function bindList() {
  document.getElementById("create-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      const created = await api("/api/reviews", {
        method: "POST",
        body: JSON.stringify({
          domain: form.domain.value,
          source_md: form.source_md.value,
        }),
      });
      setHash(created.id, "section", created.sections[0]?.id);
    } catch (err) {
      state.error = err.message;
      render();
    }
  });
  document.getElementById("upload-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const file = form.file.files[0];
    if (!file) {
      state.error = "Choose a Markdown file.";
      render();
      return;
    }
    const payload = new FormData();
    payload.append("domain", form.domain.value);
    payload.append("file", file);
    try {
      const response = await fetch("/api/reviews/upload", { method: "POST", body: payload });
      const data = await response.json();
      if (!response.ok) throw new Error(formatDetail(data.detail));
      setHash(data.id, "section", data.sections[0]?.id);
    } catch (err) {
      state.error = err.message;
      render();
    }
  });
}

function renderReview() {
  const review = state.review;
  const progress = progressLabel(review.progress || summarizeProgress(review));
  const tabs = `
    <nav class="tabs">
      <button data-tab="section" class="${state.tab === "section" ? "active" : ""}">Section review</button>
      <button data-tab="document" class="${state.tab === "document" ? "active" : ""}">Full document</button>
    </nav>`;
  return `
    ${state.error ? `<div class="flash">${esc(state.error)}</div>` : ""}
    <p><a href="#/">All reviews</a></p>
    <div class="nav-sections">
      <h1 style="margin:0;font-size:1.35rem">${esc(review.document.meta.title)}</h1>
      <span class="progress">${esc(progress)}</span>
      <button class="btn secondary" id="export-cli">Export for CLI</button>
    </div>
    ${tabs}
    ${state.tab === "document" ? renderDocument() : renderSection()}
  `;
}

function summarizeProgress(review) {
  const progress = { pending: 0, covered: 0, no_restriction: 0, total: review.sections.length };
  for (const section of review.sections) {
    progress[sectionStatus(section.id)] += 1;
  }
  return progress;
}

function renderSection() {
  const section = currentSection();
  if (!section) return "<p>No sections.</p>";
  const index = state.review.sections.findIndex((item) => item.id === section.id);
  const status = sectionStatus(section.id);
  return `
    <div class="nav-sections">
      <button class="btn ghost" data-nav="-1" ${index === 0 ? "disabled" : ""}>Previous</button>
      <strong>Section ${index + 1} / ${state.review.sections.length}</strong>
      <button class="btn ghost" data-nav="1" ${index === state.review.sections.length - 1 ? "disabled" : ""}>Next</button>
      <span class="badge ${status}">${labelStatus(status)}</span>
    </div>
    <div class="split">
      <section class="pane">
        <header><h2>${esc(section.title)}</h2></header>
        <div class="body md">${esc(section.markdown)}</div>
      </section>
      <section class="pane">
        <header>
          <h2>Auto-checks for this section</h2>
        </header>
        <div class="body">
          <p class="muted">These closed keys and statements should exhaustively cover the obligations in the text. Edit them so they match human intent.</p>
          ${state.keys.map((key, i) => renderKeyCard(key, i)).join("")}
          <button class="btn secondary" id="add-key">Add key</button>
          ${state.statements.map((item, i) => renderStatementCard(item, i)).join("")}
          <button class="btn secondary" id="add-statement">Add statement</button>
          <div class="actions">
            <button class="btn" id="save-section" ${state.busy ? "disabled" : ""}>Save checks</button>
            <button class="btn secondary" id="ask-ai" ${state.busy ? "disabled" : ""}>Ask AI</button>
            <button class="btn good" id="mark-covered" ${state.busy ? "disabled" : ""}>Mark exhaustively covered</button>
            <button class="btn warn" id="mark-waived" ${state.busy ? "disabled" : ""}>No concrete restriction</button>
          </div>
        </div>
      </section>
    </div>
  `;
}

function renderKeyCard(key, index) {
  const chips = (key.value_enum || [])
    .map(
      (value, enumIndex) =>
        `<span class="chip">${esc(value === "" ? "(empty)" : value)} <button type="button" data-del-enum="${index}:${enumIndex}" aria-label="Remove">×</button></span>`
    )
    .join("");
  return `
    <article class="card" data-key="${index}">
      <h3>Key</h3>
      <div class="field"><label>Id</label><input data-key-field="id" data-i="${index}" value="${escAttr(key.id)}" /></div>
      <div class="field"><label>Question</label><input data-key-field="question" data-i="${index}" value="${escAttr(key.question)}" /></div>
      <div class="field"><label>Explanation</label><textarea data-key-field="explanation" data-i="${index}" rows="3">${esc(key.explanation)}</textarea></div>
      <div class="field">
        <label>Value enum</label>
        <div class="chips">${chips}</div>
        <div class="enum-row">
          <input data-enum-input="${index}" placeholder="Add enum value" />
          <button class="btn ghost" type="button" data-add-enum="${index}">Add</button>
        </div>
      </div>
      <label class="muted"><input type="checkbox" data-key-field="required" data-i="${index}" ${key.required ? "checked" : ""} /> Required</label>
      <div class="actions"><button class="btn ghost" data-remove-key="${index}">Remove key</button></div>
    </article>
  `;
}

function renderStatementCard(item, index) {
  const keyOptions = state.keys
    .map((key) => {
      const selected = item.accepted?.[key.id] || [];
      const boxes = (key.value_enum || [])
        .map((value) => {
          const checked = selected.includes(value) ? "checked" : "";
          const label = value === "" ? "(empty)" : value;
          return `<label><input type="checkbox" data-accepted="${index}:${escAttr(key.id)}:${escAttr(value)}" ${checked} /> ${esc(label)}</label>`;
        })
        .join("");
      return `<div><strong>${esc(key.id)}</strong><div class="accepted-grid">${boxes || "<span class='muted'>Add enum values on the key first.</span>"}</div></div>`;
    })
    .join("");
  return `
    <article class="card">
      <h3>Statement</h3>
      <div class="field"><label>Id</label><input data-stmt-field="id" data-i="${index}" value="${escAttr(item.id)}" /></div>
      <div class="field"><label>Description</label><textarea data-stmt-field="description" data-i="${index}" rows="2">${esc(item.description)}</textarea></div>
      <p class="muted">Accepted values that constitute a pass</p>
      ${keyOptions || "<p class='muted'>Add a key first.</p>"}
      <div class="actions"><button class="btn ghost" data-remove-stmt="${index}">Remove statement</button></div>
    </article>
  `;
}

function renderDocument() {
  const pending = state.review.sections.filter((item) => sectionStatus(item.id) === "pending");
  const sidebar = pending.length
    ? pending
        .map(
          (item) =>
            `<button data-jump="${item.id}">${esc(item.title)}</button>`
        )
        .join("")
    : "<p class='muted'>Every section has been reviewed.</p>";
  const blocks = state.review.sections
    .map((section) => {
      const status = sectionStatus(section.id);
      return `
        <article class="section-block ${status}" id="block-${section.id}">
          <header>
            <h2 style="margin:0;font-size:1rem">${esc(section.title)}</h2>
            <span class="badge ${status}">${labelStatus(status)}</span>
          </header>
          <div class="md">${esc(section.markdown)}</div>
          <div class="actions" style="padding:0 1rem 0.9rem">
            <button class="btn secondary" data-review-sec="${section.id}">Review this section</button>
            <button class="btn warn" data-waive-sec="${section.id}">No concrete restriction</button>
            <button class="btn secondary" data-ai-sec="${section.id}">Ask AI</button>
          </div>
        </article>`;
    })
    .join("");
  return `
    <div class="doc-layout">
      <aside class="sidebar">
        <h2>Not yet reviewed</h2>
        ${sidebar}
      </aside>
      <div>${blocks}</div>
    </div>
  `;
}

function bindReview() {
  document.getElementById("export-cli")?.addEventListener("click", async () => {
    try {
      const result = await api(`/api/reviews/${state.review.id}/export`);
      state.error = "";
      alert(`Wrote ${result.path}`);
    } catch (err) {
      state.error = err.message;
      render();
    }
  });
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => setHash(state.review.id, button.dataset.tab, state.sectionId));
  });
  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = state.review.sections.findIndex((item) => item.id === state.sectionId);
      const next = state.review.sections[index + Number(button.dataset.nav)];
      if (next) setHash(state.review.id, "section", next.id);
    });
  });
  document.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(`block-${button.dataset.jump}`)?.scrollIntoView({ behavior: "smooth" });
    });
  });
  document.querySelectorAll("[data-review-sec]").forEach((button) => {
    button.addEventListener("click", () => setHash(state.review.id, "section", button.dataset.reviewSec));
  });
  document.querySelectorAll("[data-waive-sec]").forEach((button) => {
    button.addEventListener("click", () => setStatus(button.dataset.waiveSec, "no_restriction"));
  });
  document.querySelectorAll("[data-ai-sec]").forEach((button) => {
    button.addEventListener("click", () => generateSection(button.dataset.aiSec, true));
  });
  document.getElementById("add-key")?.addEventListener("click", () => {
    state.keys.push({
      id: `key_${state.keys.length + 1}`,
      question: "",
      explanation: "",
      value_enum: ["yes", "no", ""],
      required: true,
      source_section_id: state.sectionId,
    });
    render();
  });
  document.getElementById("add-statement")?.addEventListener("click", () => {
    const first = state.keys[0]?.id;
    state.statements.push({
      id: `stmt_${state.statements.length + 1}`,
      description: "",
      accepted: first ? { [first]: [] } : {},
      source_section_id: state.sectionId,
    });
    render();
  });
  document.querySelectorAll("[data-key-field]").forEach((input) => {
    input.addEventListener("input", () => {
      const key = state.keys[Number(input.dataset.i)];
      if (input.dataset.keyField === "required") key.required = input.checked;
      else key[input.dataset.keyField] = input.value;
    });
    if (input.dataset.keyField === "required") {
      input.addEventListener("change", () => {
        state.keys[Number(input.dataset.i)].required = input.checked;
      });
    }
  });
  document.querySelectorAll("[data-stmt-field]").forEach((input) => {
    input.addEventListener("input", () => {
      state.statements[Number(input.dataset.i)][input.dataset.stmtField] = input.value;
    });
  });
  document.querySelectorAll("[data-add-enum]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.addEnum);
      const field = document.querySelector(`[data-enum-input="${index}"]`);
      const value = field.value;
      state.keys[index].value_enum = state.keys[index].value_enum || [];
      state.keys[index].value_enum.push(value);
      field.value = "";
      render();
    });
  });
  document.querySelectorAll("[data-del-enum]").forEach((button) => {
    button.addEventListener("click", () => {
      const [keyIndex, enumIndex] = button.dataset.delEnum.split(":").map(Number);
      state.keys[keyIndex].value_enum.splice(enumIndex, 1);
      render();
    });
  });
  document.querySelectorAll("[data-remove-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.removeKey);
      const removed = state.keys.splice(index, 1)[0];
      state.statements.forEach((item) => {
        delete item.accepted[removed.id];
      });
      render();
    });
  });
  document.querySelectorAll("[data-remove-stmt]").forEach((button) => {
    button.addEventListener("click", () => {
      state.statements.splice(Number(button.dataset.removeStmt), 1);
      render();
    });
  });
  document.querySelectorAll("[data-accepted]").forEach((input) => {
    input.addEventListener("change", () => {
      const [stmtIndex, keyId, value] = splitAccepted(input.dataset.accepted);
      const stmt = state.statements[stmtIndex];
      stmt.accepted[keyId] = stmt.accepted[keyId] || [];
      if (input.checked && !stmt.accepted[keyId].includes(value)) stmt.accepted[keyId].push(value);
      if (!input.checked) stmt.accepted[keyId] = stmt.accepted[keyId].filter((item) => item !== value);
    });
  });
  document.getElementById("save-section")?.addEventListener("click", saveSection);
  document.getElementById("ask-ai")?.addEventListener("click", () => generateSection(state.sectionId, false));
  document.getElementById("mark-covered")?.addEventListener("click", async () => {
    await saveSection();
    await setStatus(state.sectionId, "covered");
  });
  document.getElementById("mark-waived")?.addEventListener("click", () => setStatus(state.sectionId, "no_restriction"));
}

function splitAccepted(raw) {
  const [stmtIndex, ...rest] = raw.split(":");
  const value = rest.pop();
  const keyId = rest.join(":");
  return [Number(stmtIndex), keyId, value];
}

async function saveSection() {
  state.busy = true;
  state.error = "";
  render();
  try {
    const statements = state.statements.map((item) => ({
      ...item,
      accepted: Object.fromEntries(
        Object.entries(item.accepted || {}).filter(([, values]) => values.length)
      ),
      source_section_id: state.sectionId,
    }));
    const emptyAccepted = statements.find((item) => !Object.keys(item.accepted).length);
    if (emptyAccepted) {
      throw new Error(`Statement ${emptyAccepted.id} needs at least one accepted value.`);
    }
    const keys = state.keys.map((key) => ({
      ...key,
      source_section_id: key.source_section_id || state.sectionId,
    }));
    const emptyEnum = keys.find((key) => !key.value_enum?.length);
    if (emptyEnum) throw new Error(`Key ${emptyEnum.id} needs at least one enum value.`);
    const review = await api(`/api/reviews/${state.review.id}/sections/${state.sectionId}`, {
      method: "PATCH",
      body: JSON.stringify({ keys, statements }),
    });
    state.review = review;
    pullDraft();
  } catch (err) {
    state.error = err.message;
  } finally {
    state.busy = false;
    render();
  }
}

async function generateSection(sectionId, stayOnDocument) {
  state.busy = true;
  state.error = "";
  render();
  try {
    const review = await api(`/api/reviews/${state.review.id}/sections/${sectionId}/generate`, {
      method: "POST",
      body: "{}",
    });
    state.review = review;
    state.sectionId = sectionId;
    pullDraft();
    if (stayOnDocument) setHash(review.id, "document", sectionId);
    else setHash(review.id, "section", sectionId);
  } catch (err) {
    state.error = err.message;
  } finally {
    state.busy = false;
    render();
  }
}

async function setStatus(sectionId, status) {
  state.busy = true;
  state.error = "";
  render();
  try {
    const review = await api(`/api/reviews/${state.review.id}/sections/${sectionId}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
    state.review = review;
    pullDraft();
  } catch (err) {
    state.error = err.message;
  } finally {
    state.busy = false;
    render();
  }
}

function labelStatus(status) {
  if (status === "covered") return "Covered";
  if (status === "no_restriction") return "No restriction";
  return "Pending";
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escAttr(value) {
  return esc(value).replaceAll('"', "&quot;");
}
