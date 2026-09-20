const appEl = document.getElementById("app");
const subtitleEl = document.getElementById("top-subtitle");
const PRODUCT = "Poliview";
let chromeBound = false;
let pendingDelete = null;

const state = {
  view: "list",
  reviews: [],
  review: null,
  tab: "section",
  sectionId: null,
  keys: [],
  statements: [],
  error: "",
  notice: "",
  busy: false,
  versionPreview: null,
  healthRuns: [],
  health: null,
  healthId: "",
  healthFilter: "failed",
  workspace: null,
  workspaceId: "",
  openTabs: [],
  activeTab: "health",
  fileCache: {},
  chat: [],
  chatBusy: false,
  chatError: "",
  focusPolicyId: "",
};

window.addEventListener("hashchange", boot);

function isOwnerView() {
  return state.view === "project" || state.view === "health";
}

function bindChrome() {
  if (chromeBound) return;
  chromeBound = true;
  const tabs = document.getElementById("role-tabs");
  tabs?.addEventListener("change", () => {
    const owner = tabs.activeTabIndex === 1;
    if (owner && !isOwnerView()) location.hash = "#/project";
    if (!owner && isOwnerView()) location.hash = "#/";
  });
  document.getElementById("brand-link")?.addEventListener("click", (event) => {
    event.preventDefault();
    location.hash = isOwnerView() ? "#/project" : "#/";
  });
  document.getElementById("delete-cancel")?.addEventListener("click", () => {
    document.getElementById("delete-dialog")?.close();
    pendingDelete = null;
  });
  document.getElementById("delete-confirm")?.addEventListener("click", () => confirmDeletePolicy());
}

function syncChrome() {
  const owner = isOwnerView();
  document.body.dataset.role = owner ? "owner" : "governance";
  const tabs = document.getElementById("role-tabs");
  if (tabs && tabs.activeTabIndex !== (owner ? 1 : 0)) {
    tabs.activeTabIndex = owner ? 1 : 0;
  }
  document.getElementById("nav-policies")?.toggleAttribute("aria-current", state.view === "list" || state.view === "review");
  document.getElementById("nav-project")?.toggleAttribute("aria-current", state.view === "project");
  document.getElementById("nav-health")?.toggleAttribute("aria-current", state.view === "health");
  showProgress(state.busy || state.chatBusy);
}

function showProgress(on) {
  document.getElementById("global-progress")?.classList.toggle("visible", Boolean(on));
}

function toast(message) {
  const el = document.getElementById("app-snackbar");
  if (!el || !message) return;
  el.textContent = message;
  if (typeof el.show === "function") el.show();
}

function bindDeleteButtons() {
  document.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", () => {
      askDeletePolicy(button.dataset.delete, button.dataset.deleteTitle || button.dataset.delete);
    });
  });
}

function askDeletePolicy(id, title) {
  pendingDelete = id;
  const message = document.getElementById("delete-message");
  if (message) {
    message.textContent = `Remove “${title}” from the library? This also deletes data/policies/${id}.json.`;
  }
  const dialog = document.getElementById("delete-dialog");
  if (dialog && typeof dialog.show === "function") dialog.show();
}

async function confirmDeletePolicy() {
  const id = pendingDelete;
  document.getElementById("delete-dialog")?.close();
  pendingDelete = null;
  if (!id) return;
  state.busy = true;
  showProgress(true);
  try {
    await api(`/api/reviews/${encodeURIComponent(id)}`, { method: "DELETE" });
    toast(`Deleted ${id}.`);
    state.notice = `Deleted ${id}.`;
    state.error = "";
    if (state.review?.id === id) {
      location.hash = "#/";
      return;
    }
    await loadList();
  } catch (err) {
    state.error = err.message;
    render();
  } finally {
    state.busy = false;
    showProgress(false);
  }
}

function banners() {
  return `
    ${state.error ? `<div class="banner error" role="alert"><md-icon>error</md-icon><span>${esc(state.error)}</span></div>` : ""}
    ${state.notice ? `<div class="banner success"><md-icon>check_circle</md-icon><span>${esc(state.notice)}</span></div>` : ""}
  `;
}

function renderLoading() {
  return `<div class="page-loading"><md-circular-progress indeterminate></md-circular-progress><p class="muted">Loading ${PRODUCT}…</p></div>`;
}

async function boot() {
  bindChrome();
  if (!location.hash && /\/health\/?$/.test(location.pathname)) {
    location.replace(`${location.pathname.replace(/\/+$/, "") || "/health"}#/health`);
    return;
  }
  if (!location.hash && /\/project\/?$/.test(location.pathname)) {
    location.replace(`${location.pathname.replace(/\/+$/, "") || "/project"}#/project`);
    return;
  }
  if (appEl && !appEl.innerHTML) appEl.innerHTML = renderLoading();
  const route = parseHash();
  try {
    if (route.view === "project") {
      await loadProject(route.projectId);
    } else if (route.view === "health") {
      await loadHealth(route.runId, route.filter);
    } else if (route.view === "review") {
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
  if (parts[0] === "project") {
    return {
      view: "project",
      projectId: params.get("id") || parts[1] || "",
    };
  }
  if (parts[0] === "health") {
    return {
      view: "health",
      runId: params.get("run") || parts[1] || "",
      filter: params.get("filter") === "all" ? "all" : "failed",
    };
  }
  if (parts[0] === "reviews" && parts[1]) {
    const tab = params.get("tab");
    return {
      view: "review",
      id: parts[1],
      tab: tab === "document" || tab === "history" ? tab : "section",
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
  state.notice = "";
  subtitleEl.textContent = "Policy library · versions and coverage";
  document.title = `${PRODUCT} · Policies`;
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
  if (tab !== "history") state.versionPreview = null;
  subtitleEl.textContent = `${review.document.meta.title} · ${review.domain} · v${review.version || 1}`;
  document.title = `${PRODUCT} · ${review.document.meta.title}`;
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
  document.body.classList.toggle("workbench", state.view === "project");
  syncChrome();
  if (state.view === "list") {
    appEl.innerHTML = renderList();
    bindList();
    return;
  }
  if (state.view === "health") {
    appEl.innerHTML = renderHealth();
    bindHealth();
    return;
  }
  if (state.view === "project") {
    appEl.innerHTML = renderProject();
    bindProject();
    return;
  }
  appEl.innerHTML = renderReview();
  bindReview();
}

function renderList() {
  const cards = state.reviews
    .map((item) => {
      const action = item.sync_action || "none";
      const actionLabel = action === "update" ? "Update policies" : "Generate policies";
      const actionBtn =
        action === "none"
          ? ""
          : `<md-filled-tonal-button data-sync="${escAttr(item.id)}">${actionLabel}</md-filled-tonal-button>`;
      const dirty = (item.dirty_section_ids || []).length;
      const dirtyNote = dirty ? ` · ${dirty} section${dirty === 1 ? "" : "s"} need checks` : "";
      return `
      <article class="review-card">
        <div>
          <h2 class="md-typescale-title-large">${esc(item.title)}</h2>
          <p class="muted">${esc(item.domain)} · ${esc(item.filename || item.source_md)} · v${item.version || 1}</p>
          <p class="progress">${esc(progressLabel(item.progress))}${esc(dirtyNote)}</p>
          <p class="muted">Updated ${esc(item.updated_at || "—")}</p>
        </div>
        <div class="card-actions">
          ${actionBtn}
          <md-filled-button href="#/reviews/${encodeURIComponent(item.id)}?tab=section">Open</md-filled-button>
          <md-text-button data-delete="${escAttr(item.id)}" data-delete-title="${escAttr(item.title)}">
            <md-icon slot="icon">delete</md-icon>
            Delete
          </md-text-button>
        </div>
      </article>`;
    })
    .join("");
  const options = state.reviews
    .map(
      (item) =>
        `<md-select-option value="${escAttr(item.id)}"><div slot="headline">${esc(item.title)} (v${item.version || 1})</div></md-select-option>`
    )
    .join("");
  return `
    ${banners()}
    <section class="page-header">
      <p class="eyebrow">Governance</p>
      <h1 class="md-typescale-headline-medium">Policy library</h1>
      <p class="muted">Turn law or company policy into closed checks. You keep final say before a project is measured against them.</p>
    </section>
    <form id="upload-form" class="pane upload-card">
      <div class="row">
        <div class="field">
          <md-outlined-select id="upload-target" label="Target" name="review_id">
            <md-select-option value="" selected><div slot="headline">New policy</div></md-select-option>
            ${options}
          </md-outlined-select>
        </div>
        <div class="field" id="title-field">
          <md-outlined-text-field id="upload-title" label="Policy name" name="title" placeholder="e.g. GDPR recitals"></md-outlined-text-field>
        </div>
        <div class="field">
          <md-outlined-text-field id="upload-domain" label="Domain" name="domain" value="InfoSec" required></md-outlined-text-field>
        </div>
        <div class="field file-pick" style="min-width:18rem;flex:1">
          <input id="file-input" type="file" name="file" hidden accept=".md,.txt,text/markdown,.pdf" />
          <md-outlined-button id="pick-file" type="button">
            <md-icon slot="icon">upload_file</md-icon>
            <span id="file-label">Choose Markdown</span>
          </md-outlined-button>
        </div>
        <md-filled-button type="submit">Upload</md-filled-button>
      </div>
      <p class="muted" style="margin:0.7rem 0 0">Upload Markdown to start or version a review. PDF can be added later — convert to Markdown for now.</p>
    </form>
    <div class="review-list">${cards || "<p class='muted'>No policies yet.</p>"}</div>
  `;
}

function bindList() {
  const target = document.getElementById("upload-target");
  const titleField = document.getElementById("title-field");
  const toggleTitle = () => {
    if (!titleField) return;
    titleField.style.display = target?.value ? "none" : "";
  };
  target?.addEventListener("change", toggleTitle);
  toggleTitle();
  document.getElementById("pick-file")?.addEventListener("click", () => {
    document.getElementById("file-input")?.click();
  });
  document.getElementById("file-input")?.addEventListener("change", (event) => {
    const label = document.getElementById("file-label");
    if (label) label.textContent = event.target.files[0]?.name || "Choose Markdown";
  });
  document.getElementById("upload-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = document.getElementById("file-input")?.files[0];
    const reviewId = document.getElementById("upload-target")?.value || "";
    const title = document.getElementById("upload-title")?.value?.trim() || "";
    const domain = document.getElementById("upload-domain")?.value || "InfoSec";
    if (!file) {
      state.error = "Choose a Markdown file.";
      render();
      return;
    }
    if (!reviewId && !title) {
      state.error = "Give the new policy a name.";
      render();
      return;
    }
    const payload = new FormData();
    payload.append("domain", domain);
    payload.append("file", file);
    payload.append("review_id", reviewId);
    payload.append("title", title);
    try {
      const response = await fetch("/api/reviews/upload", { method: "POST", body: payload });
      const data = await response.json();
      if (!response.ok) throw new Error(formatDetail(data.detail));
      const isUpdate = Boolean(reviewId);
      state.notice = isUpdate
        ? `Stored ${data.filename || file.name} as v${data.version}. Use Update policies to refresh changed checks.`
        : `Added ${data.filename || file.name}. Use Generate policies to draft closed checks.`;
      toast(state.notice);
      await loadList();
    } catch (err) {
      state.error = err.message;
      render();
    }
  });
  document.querySelectorAll("[data-sync]").forEach((button) => {
    button.addEventListener("click", () => syncPolicies(button.dataset.sync, true));
  });
  bindDeleteButtons();
}

function renderReview() {
  const review = state.review;
  const progress = progressLabel(review.progress || summarizeProgress(review));
  const action = review.sync_action || "none";
  const syncLabel = action === "update" ? "Update policies" : "Generate policies";
  const syncBtn =
    action === "none"
      ? ""
      : `<md-filled-tonal-button id="sync-policies" ${state.busy ? "disabled" : ""}>${syncLabel}</md-filled-tonal-button>`;
  const tabs = `
    <md-tabs id="review-tabs" class="review-tabs" aria-label="Review views">
      <md-secondary-tab ${state.tab === "section" ? "active" : ""}>Section review</md-secondary-tab>
      <md-secondary-tab ${state.tab === "document" ? "active" : ""}>Full document</md-secondary-tab>
      <md-secondary-tab ${state.tab === "history" ? "active" : ""}>Version history</md-secondary-tab>
    </md-tabs>`;
  const body =
    state.tab === "document" ? renderDocument() : state.tab === "history" ? renderHistory() : renderSection();
  return `
    ${banners()}
    <p><md-text-button href="#/">
      <md-icon slot="icon">arrow_back</md-icon>
      Policy library
    </md-text-button></p>
    <div class="nav-sections">
      <h1 class="md-typescale-headline-small" style="margin:0">${esc(review.document.meta.title)}</h1>
      <span class="progress">${esc(progress)} · v${review.version || 1}</span>
      ${syncBtn}
      <md-outlined-button id="export-cli">Export for CLI</md-outlined-button>
      <md-text-button id="delete-policy" data-delete="${escAttr(review.id)}" data-delete-title="${escAttr(review.document.meta.title)}">
        <md-icon slot="icon">delete</md-icon>
        Delete
      </md-text-button>
    </div>
    ${tabs}
    ${body}
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
      <md-outlined-button data-nav="-1" ${index === 0 ? "disabled" : ""}>Previous</md-outlined-button>
      <strong>Section ${index + 1} / ${state.review.sections.length}</strong>
      <md-outlined-button data-nav="1" ${index === state.review.sections.length - 1 ? "disabled" : ""}>Next</md-outlined-button>
      <span class="badge ${status}">${labelStatus(status)}</span>
      ${needsGeneration(section.id) ? `<span class="badge pending">Needs checks</span>` : ""}
    </div>
    <div class="split">
      <section class="pane">
        <header><h2>${esc(section.title)}</h2></header>
        <div class="body md">${esc(section.markdown)}</div>
      </section>
      <section class="pane">
        <header>
          <h2>Closed checks for this section</h2>
        </header>
        <div class="body">
          <p class="muted">These keys and statements should cover the obligations in the text. Edit them so they match human intent — you keep final say.</p>
          ${state.keys.map((key, i) => renderKeyCard(key, i)).join("")}
          <md-outlined-button id="add-key">Add key</md-outlined-button>
          ${state.statements.map((item, i) => renderStatementCard(item, i)).join("")}
          <md-outlined-button id="add-statement">Add statement</md-outlined-button>
          <div class="actions">
            <md-filled-button id="save-section" ${state.busy ? "disabled" : ""}>Save checks</md-filled-button>
            <md-outlined-button id="ask-ai" ${state.busy ? "disabled" : ""}>Ask AI</md-outlined-button>
            <md-filled-tonal-button id="mark-covered" ${state.busy ? "disabled" : ""}>Mark exhaustively covered</md-filled-tonal-button>
            <md-text-button id="mark-waived" ${state.busy ? "disabled" : ""}>No concrete restriction</md-text-button>
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
        `<md-input-chip label="${escAttr(value === "" ? "(empty)" : value)}" data-del-enum="${index}:${enumIndex}"></md-input-chip>`
    )
    .join("");
  return `
    <article class="card" data-key="${index}">
      <h3>Key</h3>
      <div class="field"><md-outlined-text-field label="Id" data-key-field="id" data-i="${index}" value="${escAttr(key.id)}"></md-outlined-text-field></div>
      <div class="field"><md-outlined-text-field label="Question" data-key-field="question" data-i="${index}" value="${escAttr(key.question)}"></md-outlined-text-field></div>
      <div class="field"><md-outlined-text-field type="textarea" rows="3" label="Explanation" data-key-field="explanation" data-i="${index}" value="${escAttr(key.explanation)}"></md-outlined-text-field></div>
      <div class="field">
        <p class="muted" style="margin:0 0 0.35rem">Value enum</p>
        <div class="chips">${chips}</div>
        <div class="enum-row">
          <md-outlined-text-field data-enum-input="${index}" label="Add enum value"></md-outlined-text-field>
          <md-text-button type="button" data-add-enum="${index}">Add</md-text-button>
        </div>
      </div>
      <label class="muted"><md-checkbox data-key-field="required" data-i="${index}" ${key.required ? "checked" : ""}></md-checkbox> Required</label>
      <div class="actions"><md-text-button data-remove-key="${index}">Remove key</md-text-button></div>
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
          return `<label><md-checkbox data-accepted="${index}:${escAttr(key.id)}:${escAttr(value)}" ${checked}></md-checkbox> ${esc(label)}</label>`;
        })
        .join("");
      return `<div><strong>${esc(key.id)}</strong><div class="accepted-grid">${boxes || "<span class='muted'>Add enum values on the key first.</span>"}</div></div>`;
    })
    .join("");
  return `
    <article class="card">
      <h3>Statement</h3>
      <div class="field"><md-outlined-text-field label="Id" data-stmt-field="id" data-i="${index}" value="${escAttr(item.id)}"></md-outlined-text-field></div>
      <div class="field"><md-outlined-text-field type="textarea" rows="2" label="Description" data-stmt-field="description" data-i="${index}" value="${escAttr(item.description)}"></md-outlined-text-field></div>
      <p class="muted">Accepted values that constitute a pass</p>
      ${keyOptions || "<p class='muted'>Add a key first.</p>"}
      <div class="actions"><md-text-button data-remove-stmt="${index}">Remove statement</md-text-button></div>
    </article>
  `;
}

function renderDocument() {
  const pending = state.review.sections.filter((item) => sectionStatus(item.id) === "pending");
  const sidebar = pending.length
    ? pending
        .map(
          (item) =>
            `<md-text-button data-jump="${item.id}">${esc(item.title)}</md-text-button>`
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
            ${needsGeneration(section.id) ? `<span class="badge pending">Needs checks</span>` : ""}
          </header>
          <div class="md">${esc(section.markdown)}</div>
          <div class="actions" style="padding:0 1rem 0.9rem">
            <md-outlined-button data-review-sec="${section.id}">Review this section</md-outlined-button>
            <md-text-button data-waive-sec="${section.id}">No concrete restriction</md-text-button>
            <md-outlined-button data-ai-sec="${section.id}">Ask AI</md-outlined-button>
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

function renderHistory() {
  const versions = [...(state.review.versions || [])].sort((a, b) => b.version - a.version);
  const rows = versions
    .map((item) => {
      const changed = (item.changed_section_ids || []).length
        ? `${item.changed_section_ids.length} changed section(s)`
        : "no section diffs recorded";
      const active = state.versionPreview?.version === item.version ? "active" : "";
      return `
        <button class="version-row ${active}" data-version="${item.version}">
          <strong>v${item.version}</strong>
          <span>${esc(item.action)} · ${esc(item.filename)}</span>
          <span class="muted">${esc(item.created_at)} · ${esc(changed)}</span>
        </button>`;
    })
    .join("");
  const preview = state.versionPreview
    ? `<section class="pane"><header><h2>v${state.versionPreview.version} source</h2></header><div class="body md">${esc(state.versionPreview.markdown)}</div></section>`
    : `<p class="muted">Select a version to view the Markdown snapshot stored in this document repo.</p>`;
  return `
    <div class="doc-layout">
      <aside class="sidebar">
        <h2>Versions</h2>
        ${rows || "<p class='muted'>No snapshots yet.</p>"}
      </aside>
      <div>${preview}</div>
    </div>
  `;
}

function bindReview() {
  bindDeleteButtons();
  document.getElementById("sync-policies")?.addEventListener("click", () => syncPolicies(state.review.id, false));
  document.querySelectorAll("[data-version]").forEach((button) => {
    button.addEventListener("click", () => loadVersion(Number(button.dataset.version)));
  });
  document.getElementById("export-cli")?.addEventListener("click", async () => {
    try {
      const result = await api(`/api/reviews/${state.review.id}/export`);
      state.error = "";
      toast(`Wrote ${result.path}`);
    } catch (err) {
      state.error = err.message;
      render();
    }
  });
  document.getElementById("review-tabs")?.addEventListener("change", (event) => {
    const names = ["section", "document", "history"];
    const index = event.target.activeTabIndex;
    setHash(state.review.id, names[index] || "section", state.sectionId);
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
    const apply = () => {
      const key = state.keys[Number(input.dataset.i)];
      if (!key) return;
      if (input.dataset.keyField === "required") key.required = Boolean(input.checked);
      else key[input.dataset.keyField] = input.value;
    };
    input.addEventListener("input", apply);
    input.addEventListener("change", apply);
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
      const value = field?.value ?? "";
      state.keys[index].value_enum = state.keys[index].value_enum || [];
      state.keys[index].value_enum.push(value);
      field.value = "";
      render();
    });
  });
  document.querySelectorAll("[data-del-enum]").forEach((button) => {
    const remove = () => {
      const [keyIndex, enumIndex] = button.dataset.delEnum.split(":").map(Number);
      state.keys[keyIndex].value_enum.splice(enumIndex, 1);
      render();
    };
    button.addEventListener("remove", remove);
    button.addEventListener("click", remove);
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
  showProgress(true);
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
  showProgress(true);
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
  showProgress(true);
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

async function syncPolicies(reviewId, stayOnList) {
  state.busy = true;
  state.error = "";
  state.notice = "Generating closed checks…";
  showProgress(true);
  toast(state.notice);
  try {
    const result = await api(`/api/reviews/${reviewId}/generate-policies`, {
      method: "POST",
      body: "{}",
    });
    const generated = result.generated || [];
    const errors = result.errors || [];
    const remaining = result.remaining || 0;
    let notice = generated.length
      ? `Updated checks for ${generated.length} section(s). Saved closed JSON to data/policies/${reviewId}.json.`
      : "No sections needed generation.";
    if (remaining) {
      notice += ` ${remaining} still waiting — click Generate policies again for the next batch.`;
    }
    if (stayOnList) {
      await loadList();
      state.notice = notice;
      if (errors.length) state.error = errors.join("; ");
      render();
      return;
    }
    state.notice = notice;
    if (errors.length) state.error = errors.join("; ");
    state.review = result;
    pullDraft();
  } catch (err) {
    state.error = err.message;
    state.notice = "";
  } finally {
    state.busy = false;
    render();
  }
}

async function loadVersion(version) {
  try {
    state.versionPreview = await api(`/api/reviews/${state.review.id}/versions/${version}`);
    state.error = "";
  } catch (err) {
    state.error = err.message;
  }
  render();
}

function needsGeneration(sectionId) {
  return Boolean(state.review?.reviews?.[sectionId]?.needs_generation);
}

function setHealthHash(runId, filter) {
  const params = new URLSearchParams();
  if (runId) params.set("run", runId);
  if (filter && filter !== "failed") params.set("filter", filter);
  const query = params.toString();
  location.hash = query ? `#/health?${query}` : "#/health";
}

function pickDefaultHealthId(runs) {
  const demo = runs.find((item) => item.kind === "demo") || runs[0];
  return demo?.id || "";
}

async function loadHealth(runId, filter) {
  if (!location.hash && location.pathname.replace(/\/+$/, "").endsWith("/health")) {
    location.replace("#/health");
    return;
  }
  const data = await api("/api/health/runs");
  const runs = data.runs || [];
  const selected = runId && runs.some((item) => item.id === runId) ? runId : pickDefaultHealthId(runs);
  state.view = "health";
  state.healthRuns = runs;
  state.healthFilter = filter === "all" ? "all" : "failed";
  state.healthId = selected;
  state.review = null;
  if (!selected) {
    state.health = null;
    state.error = "";
    subtitleEl.textContent = "Project compliance · no health checks yet";
    document.title = `${PRODUCT} · Compliance health`;
    render();
    return;
  }
  if (state.health?.id === selected) {
    state.error = "";
    subtitleEl.textContent = `${state.health.project_name || "Project"} · compliance health`;
    document.title = `${PRODUCT} · ${state.health.project_name || "Health"}`;
    render();
    return;
  }
  const snapshot = await api(`/api/health/runs/${encodeURIComponent(selected)}`);
  state.health = snapshot;
  state.error = "";
  subtitleEl.textContent = `${snapshot.project_name || "Project"} · last check ${formatWhen(snapshot.validated_at)}`;
  document.title = `${PRODUCT} · ${snapshot.project_name || "Project"} health`;
  render();
}

function renderHealth(options = {}) {
  const embedded = Boolean(options.embedded);
  const snapshot = state.health;
  const option = (item) => {
      const selected = item.id === state.healthId ? "selected" : "";
      return `<md-select-option value="${escAttr(item.id)}" ${selected}><div slot="headline">${esc(item.label || item.project_name || item.id)}</div></md-select-option>`;
    };
  const demoRuns = state.healthRuns.filter((item) => item.kind === "demo");
  const workspaceRuns = state.healthRuns.filter((item) => item.kind !== "demo");
  const optionsHtml = [
    ...demoRuns.map((item) => option({ ...item, label: `Demo · ${item.label || item.project_name || item.id}` })),
    ...workspaceRuns.map((item) =>
      option({ ...item, label: item.label || item.project_name || item.id })
    ),
  ].join("");
  if (!snapshot) {
    return `
      ${banners()}
      <section class="health-page">
        <div class="health-toolbar">
          <div>
            <p class="eyebrow">Project owner</p>
            <h1>Compliance health</h1>
            <p class="muted">This page attaches to a project. For the demo, pick a stored result.</p>
          </div>
        </div>
        <p class="muted">No health-check results found. Run <code>python main.py check</code> or keep the demo file in <code>examples/health</code>.</p>
      </section>`;
  }
  const filter = state.healthFilter;
  const totals = {
    passed: snapshot.passed || 0,
    failed: snapshot.failed || 0,
    missing: snapshot.missing || 0,
    total: snapshot.total || 0,
    pass_pct: snapshot.pass_pct || 0,
  };
  const failedOnly = filter !== "all";
  const policies = (snapshot.policies || [])
    .map((policy) => renderHealthPolicy(policy, failedOnly))
    .join("");
  const picker = embedded
    ? ""
    : `<div class="field health-run-picker">
          <md-outlined-select id="health-run" label="Results (demo picker)">${optionsHtml}</md-outlined-select>
        </div>`;
  return `
    ${banners()}
    <section class="health-page${embedded ? " embedded" : ""}">
      <div class="health-toolbar">
        <div>
          <p class="eyebrow">Project owner</p>
          <h1>Compliance health</h1>
          <p class="muted">${esc(snapshot.project_name || "Untitled project")}${snapshot.project_source ? ` · ${esc(snapshot.project_source)}` : ""}</p>
        </div>
        ${picker}
      </div>
      <div class="health-meta">
        <div><span class="meta-label">Last validated</span><strong>${esc(formatWhen(snapshot.validated_at))}</strong></div>
        <div><span class="meta-label">Checks run</span><strong>${totals.total}</strong></div>
        <div><span class="meta-label">Passed</span><strong>${totals.passed}</strong></div>
        <div><span class="meta-label">Failed</span><strong>${totals.failed}</strong></div>
        <div><span class="meta-label">Missing info</span><strong>${totals.missing}</strong></div>
        <div><span class="meta-label">Policies in scope</span><strong>${(snapshot.policies || []).length}</strong></div>
      </div>
      <div class="health-overview">
        <article class="donut-card featured">
          <h2>Overall</h2>
          ${donutChart(totals, "Overall pass rate")}
          <p class="donut-caption">${totals.passed}/${totals.total} checks passed</p>
          <span class="badge ${statusClass(snapshot.overall_status)}">${labelHealthStatus(snapshot.overall_status)}</span>
        </article>
        ${(snapshot.policies || []).map((policy) => renderPolicyDonut(policy)).join("")}
      </div>
      <div class="health-filter-row">
        <md-tabs id="health-filter" class="health-filter" aria-label="Check filter">
          <md-secondary-tab ${failedOnly ? "active" : ""}>Failed only</md-secondary-tab>
          <md-secondary-tab ${failedOnly ? "" : "active"}>All checks</md-secondary-tab>
        </md-tabs>
        <p class="muted">${failedOnly ? "Showing failed checks. Switch to all checks to include passes and missing information." : "Showing every check that applies to this project."}</p>
      </div>
      ${failedOnly && totals.failed === 0 ? `<div class="banner success"><md-icon>check_circle</md-icon><span>No failed checks on this health run.${totals.missing ? " Some checks still need information — open All checks." : ""}</span></div>` : ""}
      <div class="policy-list">${policies}</div>
    </section>`;
}

function renderPolicyDonut(policy) {
  const counts = {
    passed: policy.passed || 0,
    failed: policy.failed || 0,
    missing: policy.missing || 0,
    total: policy.total || 0,
    pass_pct: policy.pass_pct || 0,
  };
  return `
    <article class="donut-card">
      <h2>${esc(policy.domain || policy.title)}</h2>
      ${donutChart(counts, `${policy.title} pass rate`)}
      <p class="donut-caption">${counts.passed}/${counts.total} passed</p>
      <p class="muted donut-org">${esc(policy.organization || policy.title)}</p>
    </article>`;
}

function donutChart(counts, label, size = 148) {
  const cx = size / 2;
  const cy = size / 2;
  const r = Math.max(18, size * 0.35);
  const stroke = Math.max(8, Math.round(size * 0.095));
  const font = size > 120 ? 22 : 15;
  const sub = size > 120 ? 11 : 9;
  const circumference = 2 * Math.PI * r;
  const total = counts.total || 0;
  const slices = [
    { n: counts.passed || 0, color: "#146c2e" },
    { n: counts.failed || 0, color: "#ba1a1a" },
    { n: counts.missing || 0, color: "#4b607c" },
  ];
  let offset = 0;
  const arcs = total
    ? slices
        .filter((slice) => slice.n > 0)
        .map((slice) => {
          const length = (slice.n / total) * circumference;
          const circle = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${slice.color}" stroke-width="${stroke}" stroke-linecap="butt" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})"></circle>`;
          offset += length;
          return circle;
        })
        .join("")
    : "";
  const pct = total ? counts.pass_pct : 0;
  return `
    <svg class="donut-svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${escAttr(label)}: ${pct}% passed">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#bec9c8" stroke-width="${stroke}"></circle>
      ${arcs}
      <text x="${cx}" y="${cy - 2}" text-anchor="middle" fill="#191c1c" font-size="${font}" font-weight="700">${pct}%</text>
      <text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="#3f4948" font-size="${sub}">passed</text>
    </svg>
    <ul class="donut-legend">
      <li><span class="swatch pass"></span> Passed ${counts.passed || 0}</li>
      <li><span class="swatch fail"></span> Failed ${counts.failed || 0}</li>
      <li><span class="swatch missing"></span> Missing ${counts.missing || 0}</li>
    </ul>`;
}

function renderHealthPolicy(policy, failedOnly) {
  const results = policy.results || [];
  const visible = failedOnly ? results.filter((item) => item.status === "fail") : results;
  const counts = {
    failed: policy.failed || results.filter((item) => item.status === "fail").length,
    passed: policy.passed || 0,
    missing: policy.missing || 0,
    total: policy.total || results.length,
  };
  const open = visible.length > 0 ? "open" : "";
  const checks = visible.length
    ? visible.map((item) => renderHealthCheck(item, policy)).join("")
    : `<p class="muted empty-checks">${failedOnly ? "No failed checks on this policy." : "No checks recorded."}</p>`;
  const owners = (policy.owners || [])
    .map((person) => `${person.name}${person.role === "owner" ? " (owner)" : ""}`)
    .join(", ");
  return `
    <details class="policy-acc" id="policy-${escAttr(policy.policy_id)}" ${open}>
      <summary>
        <span>
          <strong>${esc(policy.title)}</strong>
          <span class="muted"> ${esc(policy.domain)} · v${esc(policy.version || "1.0")} · ${esc(policy.organization || "")}</span>
        </span>
        <span class="policy-summary-meta">
          <span class="badge ${counts.failed ? "fail" : "pass"}">${counts.failed} failed</span>
          <span class="muted">${counts.passed}/${counts.total} passed</span>
        </span>
      </summary>
      <div class="policy-acc-body">
        <p class="muted">${owners ? `Policy contacts: ${esc(owners)}` : ""}</p>
        ${checks}
      </div>
    </details>`;
}

function renderHealthCheck(item, policy) {
  const failed = item.status !== "pass";
  const answers = Object.entries(item.answers || {})
    .map(([key, value]) => {
      const question = item.questions?.[key] || key;
      const accepted = (item.accepted?.[key] || []).map((entry) => (entry === "" ? "(empty)" : entry)).join(", ");
      return `<li><strong>${esc(question)}</strong><br /><span class="muted">${esc(key)} = ${esc(value === "" ? "(empty)" : value)}${accepted ? ` · accepted: ${esc(accepted)}` : ""}</span></li>`;
    })
    .join("");
  const rem = item.remediation || {};
  const actions = (rem.actions || []).map((row) => `<li>${esc(row)}</li>`).join("");
  const steps = (rem.steps || []).map((row, index) => `<li><span class="step-n">${index + 1}</span>${esc(row)}</li>`).join("");
  const contacts = (rem.contacts && rem.contacts.length ? rem.contacts : policy.owners || [])
    .map(
      (person) => `
        <li class="contact-card">
          <span class="badge ${person.role === "owner" ? "covered" : "no_restriction"}">${esc(person.role || "member")}</span>
          <div>
            <strong>${esc(person.name)}</strong>
            <p class="muted">${esc([person.title, person.organization].filter(Boolean).join(" · "))}</p>
            ${person.email ? `<a href="mailto:${escAttr(person.email)}">${esc(person.email)}</a>` : ""}
          </div>
        </li>`
    )
    .join("");
  const extra = failed
    ? `
      <div class="check-grid">
        <section>
          <h4>Why this ${item.status === "missinginfo" ? "needs information" : "failed"}</h4>
          <p>${esc(item.why || item.detail)}</p>
          ${answers ? `<ul class="answer-list">${answers}</ul>` : ""}
        </section>
        <section>
          <h4>What you can do</h4>
          <ul>${actions || "<li class='muted'>No suggested actions.</li>"}</ul>
        </section>
        <section>
          <h4>Steps</h4>
          <ol class="step-list">${steps || "<li class='muted'>No steps recorded.</li>"}</ol>
        </section>
        <section>
          <h4>Who to contact</h4>
          <ul class="contact-list">${contacts || "<li class='muted'>No policy owners listed.</li>"}</ul>
        </section>
      </div>`
    : `
      <p>${esc(item.why || item.detail || "This check passed.")}</p>
      ${answers ? `<ul class="answer-list">${answers}</ul>` : ""}`;
  return `
    <details class="check-acc ${item.status}">
      <summary>
        <span class="badge ${statusClass(item.status)}">${labelHealthStatus(item.status)}</span>
        <span>${esc(item.description || item.statement_id)}</span>
      </summary>
      <div class="check-acc-body">${extra}</div>
    </details>`;
}

function bindHealth() {
  document.getElementById("health-run")?.addEventListener("change", (event) => {
    state.health = null;
    setHealthHash(event.target.value, state.healthFilter);
  });
  document.getElementById("health-filter")?.addEventListener("change", (event) => {
    const next = event.target.activeTabIndex === 1 ? "all" : "failed";
    if (state.view === "project") {
      state.healthFilter = next;
      render();
      return;
    }
    setHealthHash(state.healthId, next);
  });
}

function statusClass(status) {
  if (status === "pass") return "pass";
  if (status === "fail") return "fail";
  if (status === "missinginfo") return "missing";
  return "pending";
}

function labelHealthStatus(status) {
  if (status === "pass") return "Pass";
  if (status === "fail") return "Fail";
  if (status === "missinginfo") return "Missing info";
  return status || "Unknown";
}

function formatWhen(value) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }) + " UTC";
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
