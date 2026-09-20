const appEl = document.getElementById("app");
const subtitleEl = document.getElementById("top-subtitle");
const PRODUCT = "Poliview";
let chromeBound = false;
let pendingDelete = null;

const state = {
  view: "list",
  reviews: [],
  review: null,
  sectionId: null,
  statementFocus: 0,
  drafts: {},
  error: "",
  notice: "",
  busy: false,
  healthRuns: [],
  health: null,
  healthId: "",
  healthFilter: "failed",
  workspace: null,
  workspaceId: "",
  openTabs: [],
  activeTab: "health",
  fileCache: {},
  focusPolicyId: "",
  sampleFiles: [],
  checkedWorkspaceId: "",
};

window.addEventListener("hashchange", boot);
window.addEventListener("resize", () => {
  if (state.view === "review") syncDocument(false);
});

function isOwnerView() {
  return state.view === "project" || state.view === "health";
}

function demoOn() {
  return !window.PoliviewDemo || window.PoliviewDemo.enabled();
}

function hasCheckedHealth() {
  if (demoOn()) return true;
  return Boolean(state.checkedWorkspaceId && state.checkedWorkspaceId === state.workspaceId);
}

function displayHealth() {
  if (!hasCheckedHealth()) return {};
  return state.health || state.workspace?.health || {};
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

function markNavCurrent(id, on) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("current", on);
  if (on) el.setAttribute("aria-current", "page");
  else el.removeAttribute("aria-current");
}

function syncChrome() {
  const owner = isOwnerView();
  document.body.dataset.role = owner ? "owner" : "governance";
  const tabs = document.getElementById("role-tabs");
  if (tabs && tabs.activeTabIndex !== (owner ? 1 : 0)) {
    tabs.activeTabIndex = owner ? 1 : 0;
  }
  markNavCurrent("nav-policies", state.view === "list" || state.view === "review");
  markNavCurrent("nav-project", state.view === "project");
  markNavCurrent("nav-health", state.view === "health");
  showProgress(state.busy);
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
    message.textContent = `Remove “${title}” from the library? Projects will no longer be measured against its closed GDPR or AI Act checks (data/policies/${id}.json).`;
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

function futureCopy(value) {
  return `Not in this demo: ${value} Pass / fail / missing info would still come from the comparator, not the model.`;
}

function policyStory(item) {
  const id = String(item?.id || item?.policy_id || "").toLowerCase();
  const domain = String(item?.domain || "").toLowerCase();
  if (id === "gdpr" || domain.includes("gdpr")) {
    return "Personal data of EU persons: transfers, lawful basis, DPA, retention, and the record of processing.";
  }
  if (id === "eu-ai-act" || domain.includes("ai")) {
    return "Production AI that affects people: risk class, human oversight, logging, and a published model card.";
  }
  return "";
}

function policyCardClass(item) {
  const id = String(item?.id || "").toLowerCase();
  const domain = String(item?.domain || "").toLowerCase();
  if (id === "gdpr" || domain.includes("gdpr")) return " domain-gdpr";
  if (id === "eu-ai-act" || domain.includes("ai")) return " domain-aiact";
  return "";
}

function futureHit(innerHtml, value) {
  const copy = futureCopy(value);
  return `<span class="future-hit" tabindex="0" data-future="${escAttr(copy)}" aria-label="${escAttr(copy)}">${innerHtml}</span>`;
}

function bindFutureTips() {
  const tip = document.getElementById("future-tooltip");
  if (!tip) return;
  const hide = () => {
    tip.hidden = true;
  };
  hide();
  if (!window.__futureTipScroll) {
    window.__futureTipScroll = true;
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
  }
  document.querySelectorAll("[data-future]").forEach((el) => {
    const show = () => {
      tip.textContent = el.getAttribute("data-future") || "";
      tip.hidden = false;
      const box = el.getBoundingClientRect();
      const width = Math.min(360, window.innerWidth - 24);
      let left = box.left;
      if (left + width > window.innerWidth - 12) left = Math.max(12, window.innerWidth - width - 12);
      tip.style.width = `${width}px`;
      tip.style.left = `${left}px`;
      tip.style.top = `${Math.max(12, box.top + 8)}px`;
      requestAnimationFrame(() => {
        const height = tip.offsetHeight;
        const spaceBelow = window.innerHeight - box.bottom;
        const spaceAbove = box.top;
        let top;
        if (box.height > 160) {
          top = Math.min(Math.max(12, box.top + 12), window.innerHeight - height - 12);
        } else if (spaceBelow >= height + 12) {
          top = box.bottom + 8;
        } else if (spaceAbove >= height + 12) {
          top = box.top - height - 8;
        } else {
          top = Math.max(12, window.innerHeight - height - 12);
        }
        if (left + width > window.innerWidth - 8) {
          left = Math.max(8, window.innerWidth - width - 8);
          tip.style.left = `${left}px`;
        }
        tip.style.top = `${top}px`;
      });
    };
    el.addEventListener("mouseenter", show);
    el.addEventListener("mouseleave", hide);
    el.addEventListener("focus", show);
    el.addEventListener("blur", hide);
  });
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
      await loadReview(route.id, route.sectionId);
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
    return {
      view: "review",
      id: parts[1],
      sectionId: params.get("sid"),
    };
  }
  return { view: "list" };
}

function setHash(reviewId, sectionId) {
  const params = new URLSearchParams();
  if (sectionId) params.set("sid", sectionId);
  const query = params.toString();
  location.hash = `#/reviews/${reviewId}${query ? `?${query}` : ""}`;
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
  const [data, files] = await Promise.all([
    api("/api/reviews"),
    api("/api/data/markdown").catch(() => ({ files: [] })),
  ]);
  state.view = "list";
  const reviews = data.reviews || [];
  state.reviews = window.PoliviewDemo ? window.PoliviewDemo.filterReviews(reviews) : reviews;
  state.sampleFiles = files.files || [];
  state.review = null;
  state.error = "";
  state.notice = "";
  subtitleEl.textContent = "Governance · GDPR & EU AI Act";
  document.title = `${PRODUCT} · Policies`;
  render();
}

async function loadReview(id, sectionId) {
  if (window.PoliviewDemo && !window.PoliviewDemo.enabled() && window.PoliviewDemo.isReview(id)) {
    location.hash = "#/";
    return;
  }
  const alreadyOpen = state.review?.id === id && state.view === "review";
  if (!alreadyOpen) {
    const review = await api(`/api/reviews/${id}`);
    state.review = review;
    state.drafts = {};
    state.statementFocus = 0;
  }
  state.view = "review";
  const first = state.review.sections[0]?.id;
  const nextId =
    sectionId && state.review.sections.some((item) => item.id === sectionId) ? sectionId : first;
  state.error = "";
  subtitleEl.textContent = `${state.review.document.meta.title} · ${state.review.domain} · v${state.review.version || 1}`;
  document.title = `${PRODUCT} · ${state.review.document.meta.title}`;
  if (alreadyOpen && document.getElementById("doc-paper")) {
    showSection(nextId, true);
    return;
  }
  state.sectionId = nextId;
  render();
}

function sectionStatements(sectionId) {
  if (!state.drafts[sectionId]) {
    state.drafts[sectionId] = (state.review?.document.statements || [])
      .filter((item) => item.source_section_id === sectionId)
      .map((item) => ({
        ...clone(item),
        keys: (item.keys || []).map((key) => ({
          ...clone(key),
          accepted: [...(key.accepted || [])],
          value_enum: [...(key.value_enum || [])],
        })),
      }));
  }
  return state.drafts[sectionId];
}

function blankKey(index) {
  return {
    id: `key_${index}`,
    question: "",
    explanation: "",
    value_enum: ["yes", "no"],
    accepted: [],
    required: true,
  };
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

function statementStatus(item) {
  const keys = item.keys || [];
  if (!item.description?.trim() && !keys.length) return "pending";
  const ready =
    Boolean(item.description?.trim()) &&
    keys.length > 0 &&
    keys.every(
      (key) =>
        key.id &&
        key.question?.trim() &&
        (key.value_enum || []).length &&
        (key.accepted || []).length
    );
  return ready ? "ready" : "incomplete";
}

function labelStatementStatus(status) {
  if (status === "ready") return "Ready";
  if (status === "incomplete") return "Needs details";
  return "Empty";
}

function sectionIndex() {
  const index = state.review?.sections.findIndex((item) => item.id === state.sectionId);
  return index >= 0 ? index : 0;
}

function showSection(sectionId, animate) {
  if (!state.review?.sections.some((item) => item.id === sectionId)) return;
  const changed = state.sectionId !== sectionId;
  if (changed) {
    state.sectionId = sectionId;
    state.statementFocus = 0;
  }
  syncDocument(Boolean(animate));
  refreshSummary();
  refreshNav();
  if (!changed) return;
  refreshInspector();
  focusStatement(0);
}

function syncDocument(animate) {
  const paper = document.getElementById("doc-paper");
  if (!paper) return;
  paper.querySelectorAll(".doc-section").forEach((el) => {
    const selected = el.dataset.section === state.sectionId;
    el.classList.toggle("selected", selected);
    const heading = el.querySelector(".doc-section-title");
    if (selected) heading?.setAttribute("data-tour", "source-text");
    else heading?.removeAttribute("data-tour");
  });
  const active = document.getElementById(`block-${state.sectionId}`);
  if (active && animate) {
    active.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function stepSection(delta) {
  const index = state.review.sections.findIndex((item) => item.id === state.sectionId);
  const next = state.review.sections[index + delta];
  if (!next) return;
  showSection(next.id, true);
  setHash(state.review.id, next.id);
}

function refreshNav() {
  const index = sectionIndex();
  const total = state.review?.sections.length || 0;
  document.getElementById("prev-section")?.toggleAttribute("disabled", index <= 0);
  document.getElementById("next-section")?.toggleAttribute("disabled", index >= total - 1);
  const label = document.getElementById("section-pos");
  if (label) label.textContent = `Article ${total ? index + 1 : 0} / ${total}`;
}

function refreshInspector() {
  const el = document.getElementById("statement-sidebar");
  if (!el) return;
  el.innerHTML = renderInspector();
  bindInspector();
}

function refreshSummary() {
  document.querySelectorAll(".status-chip").forEach((chip) => {
    const sameSection = chip.dataset.jumpSection === state.sectionId;
    const stmt = chip.dataset.jumpStmt;
    const current = sameSection && (stmt === "" || Number(stmt) === state.statementFocus);
    chip.classList.toggle("current", current);
  });
}

function focusStatement(index) {
  const statements = sectionStatements(state.sectionId);
  const bounded = Math.max(0, Math.min(Number(index) || 0, Math.max(statements.length - 1, 0)));
  state.statementFocus = bounded;
  document.querySelectorAll(".statement-card.focused, .inspector-stmt.focused").forEach((card) => {
    card.classList.remove("focused");
  });
  const card = document.getElementById(`stmt-card-${state.sectionId}-${bounded}`);
  const readout = document.getElementById(`inspect-stmt-${state.sectionId}-${bounded}`);
  card?.classList.add("focused");
  readout?.classList.add("focused");
  readout?.scrollIntoView({ block: "nearest", inline: "nearest" });
  refreshSummary();
}

function progressLabel(progress) {
  const done = (progress.covered || 0) + (progress.no_restriction || 0);
  return `${done}/${progress.total} reviewed · ${progress.pending || 0} pending`;
}

function render() {
  document.body.classList.toggle("workbench", state.view === "project");
  document.body.classList.toggle("review-doc", state.view === "review");
  syncChrome();
  if (state.view === "list") {
    appEl.innerHTML = renderList();
    bindList();
    bindFutureTips();
  } else if (state.view === "health") {
    appEl.innerHTML = renderHealth();
    bindHealth();
    bindFutureTips();
  } else if (state.view === "project") {
    appEl.innerHTML = renderProject();
    bindProject();
    bindFutureTips();
  } else {
    appEl.innerHTML = renderReview();
    bindReview();
    bindFutureTips();
    syncDocument(false);
  }
  window.dispatchEvent(new CustomEvent("poliview:render", { detail: { view: state.view } }));
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
      const seeded = window.PoliviewDemo?.isReview?.(item.id);
      const story = policyStory(item);
      return `
      <article class="review-card${seeded ? " seeded" : ""}${policyCardClass(item)}" data-tour="policy-${escAttr(item.id)}">
        <div>
          <p class="card-kicker"><span class="badge ${domainBadge(item.domain)}">${esc(item.domain)}</span>${seeded ? `<span class="muted">Demo standard</span>` : ""}</p>
          <h2 class="md-typescale-title-large">${esc(item.title)}</h2>
          ${story ? `<p class="card-blurb">${esc(story)}</p>` : ""}
          <p class="muted">${esc(item.filename || item.source_md)} · v${item.version || 1}</p>
          <p class="progress">${esc(progressLabel(item.progress))}${esc(dirtyNote)}</p>
          <p class="muted">Updated ${esc(item.updated_at || "—")}</p>
        </div>
        <div class="card-actions">
          ${actionBtn}
          <md-filled-button href="#/reviews/${encodeURIComponent(item.id)}">Open</md-filled-button>
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
  const fileOptions = (state.sampleFiles || [])
    .map(
      (file) =>
        `<md-select-option value="${escAttr(file.path)}"><div slot="headline">${esc(file.name)}</div><div slot="supporting-text">${esc(file.folder)}</div></md-select-option>`
    )
    .join("");
  return `
    ${banners()}
    <section class="page-header" data-tour="library">
      <p class="eyebrow">Governance · DPO &amp; AI Act officer</p>
      <h1 class="md-typescale-headline-medium">Policy library</h1>
      <p class="muted">Load the law once — GDPR for personal data, the EU AI Act for production models. Close the questions. Keep final say. Every product team then ships against the same checks.</p>
    </section>
    <form id="upload-form" class="pane upload-card" data-tour="upload">
      <div class="row">
        <div class="field">
          <md-outlined-select id="upload-target" label="Target" name="review_id">
            <md-select-option value="" selected><div slot="headline">New policy</div></md-select-option>
            ${options}
          </md-outlined-select>
        </div>
        <div class="field" id="title-field">
          <md-outlined-text-field id="upload-title" label="Policy name" name="title" placeholder="e.g. GDPR Arts. 44–46"></md-outlined-text-field>
        </div>
        <div class="field">
          <md-outlined-text-field id="upload-domain" label="Domain" name="domain" value="GDPR" required></md-outlined-text-field>
        </div>
        <div class="field" style="min-width:18rem;flex:1">
          <md-outlined-select id="upload-file" label="Markdown in /data/policies" name="path">
            <md-select-option value="" selected><div slot="headline">Select a policy file from /data/policies</div></md-select-option>
            ${fileOptions}
          </md-outlined-select>
        </div>
        ${futureHit(
          `<md-outlined-button disabled type="button" title="PDF ingest is not in this demo"><md-icon slot="icon">picture_as_pdf</md-icon>Upload PDF</md-outlined-button>`,
          "a DPO could drop the full GDPR or EU AI Act PDF here. Split → draft → human sign-off would stay the same."
        )}
        <md-filled-button type="submit">Load from /data/policies</md-filled-button>
      </div>
      <p class="muted" style="margin:0.7rem 0 0">Markdown listed here lives in <code>/data/policies</code>. Edit on disk, then load — no file explorer. Use <strong>Generate policies</strong> to draft closed checks; you keep final say.</p>
    </form>
    <div class="review-list" data-tour="demo-policies">${cards || `<p class='muted'>No policies in your library. Load Markdown from <code>/data/policies</code> above${window.PoliviewDemo && !window.PoliviewDemo.enabled() ? ", or turn <strong>Demo</strong> on to restore GDPR, the EU AI Act, GrowthBoard, and Campus Pilot" : ""}.</p>`}</div>
  `;
}

function bindList() {
  const target = document.getElementById("upload-target");
  const titleField = document.getElementById("title-field");
  const fileSelect = document.getElementById("upload-file");
  const toggleTitle = () => {
    if (!titleField) return;
    titleField.style.display = target?.value ? "none" : "";
  };
  const fillFromPath = () => {
    const path = fileSelect?.value || "";
    if (!path || target?.value) return;
    const titleEl = document.getElementById("upload-title");
    const domainEl = document.getElementById("upload-domain");
    if (titleEl) titleEl.value = guessTitleFromPath(path);
    if (domainEl) domainEl.value = guessDomainFromPath(path);
  };
  target?.addEventListener("change", toggleTitle);
  fileSelect?.addEventListener("change", fillFromPath);
  toggleTitle();
  document.getElementById("upload-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const path = fileSelect?.value || "";
    const reviewId = target?.value || "";
    const title = document.getElementById("upload-title")?.value?.trim() || "";
    const domain = document.getElementById("upload-domain")?.value || "GDPR";
    if (!path) {
      state.error = "Select a Markdown file from /data/policies.";
      render();
      return;
    }
    if (!reviewId && !title) {
      state.error = "Give the new policy a name.";
      render();
      return;
    }
    try {
      const data = await api("/api/reviews/from-data", {
        method: "POST",
        body: JSON.stringify({
          path,
          domain,
          title,
          review_id: reviewId,
        }),
      });
      const isUpdate = Boolean(reviewId);
      const name = path.split("/").pop();
      state.notice = isUpdate
        ? `Stored ${data.filename || name} as v${data.version}. Use Update policies so new GDPR or EU AI Act text refreshes only the changed checks.`
        : `Loaded ${data.filename || name}. Use Generate policies to draft closed checks; you keep final say.`;
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
      ${futureHit(
        `<md-text-button disabled title="Version history is not in this demo"><md-icon slot="icon">history</md-icon>Version history</md-text-button>`,
        "legal could compare earlier signed-off drafts of GDPR or the EU AI Act before a shipment is measured."
      )}
      ${futureHit(
        `<md-text-button disabled title="Share for sign-off is not in this demo"><md-icon slot="icon">ios_share</md-icon>Share for sign-off</md-text-button>`,
        "a DPO or AI Act officer could send this closed schema to another reviewer without changing how projects are compared."
      )}
      <md-text-button id="delete-policy" data-delete="${escAttr(review.id)}" data-delete-title="${escAttr(review.document.meta.title)}">
        <md-icon slot="icon">delete</md-icon>
        Delete
      </md-text-button>
    </div>
    ${renderStatusSummary()}
    ${renderDocument()}
  `;
}

function summarizeProgress(review) {
  const progress = { pending: 0, covered: 0, no_restriction: 0, total: review.sections.length };
  for (const section of review.sections) {
    progress[sectionStatus(section.id)] += 1;
  }
  return progress;
}

function statementCounts() {
  let ready = 0;
  let incomplete = 0;
  let empty = 0;
  let waived = 0;
  for (const section of state.review?.sections || []) {
    const statements = sectionStatements(section.id);
    if (sectionStatus(section.id) === "no_restriction" && !statements.length) {
      waived += 1;
      continue;
    }
    if (!statements.length) {
      empty += 1;
      continue;
    }
    for (const item of statements) {
      const status = statementStatus(item);
      if (status === "ready") ready += 1;
      else if (status === "incomplete") incomplete += 1;
      else empty += 1;
    }
  }
  return { ready, incomplete, empty, waived };
}

function renderStatusSummary() {
  const counts = statementCounts();
  const groups = (state.review.sections || [])
    .map((section) => {
      const statements = sectionStatements(section.id);
      const status = sectionStatus(section.id);
      let chips = "";
      if (status === "no_restriction" && !statements.length) {
        chips = `<button type="button" class="status-chip no_restriction ${section.id === state.sectionId ? "current" : ""}" data-jump-section="${escAttr(section.id)}" data-jump-stmt="">No restriction</button>`;
      } else if (!statements.length) {
        chips = `<button type="button" class="status-chip pending ${section.id === state.sectionId ? "current" : ""}" data-jump-section="${escAttr(section.id)}" data-jump-stmt="">No check yet</button>`;
      } else {
        chips = statements
          .map((item, index) => {
            const stmtStatus = statementStatus(item);
            const current =
              section.id === state.sectionId && index === state.statementFocus ? "current" : "";
            const label = item.description?.trim() || item.id || `Statement ${index + 1}`;
            return `<button type="button" class="status-chip ${stmtStatus} ${current}" data-jump-section="${escAttr(section.id)}" data-jump-stmt="${index}" title="${escAttr(label)}">${esc(labelStatementStatus(stmtStatus))} · ${esc(label)}</button>`;
          })
          .join("");
      }
      return `<div class="status-section">
        <p class="status-section-title"><span class="badge ${status}">${labelStatus(status)}</span> ${esc(section.title)}</p>
        <div class="status-chips">${chips}</div>
      </div>`;
    })
    .join("");
  return `
    <section class="status-summary" id="status-summary">
      <div class="status-summary-head">
        <div>
          <h2>All checks</h2>
          <p class="muted">Every closed statement in this ${esc(state.review?.domain || "regulation")}. Click one to jump to that article.</p>
        </div>
        <div class="status-summary-counts">
          <span class="status-count ready">${counts.ready} ready</span>
          <span class="status-count incomplete">${counts.incomplete} need details</span>
          <span class="status-count pending">${counts.empty} empty</span>
          ${counts.waived ? `<span class="status-count waived">${counts.waived} no restriction</span>` : ""}
        </div>
      </div>
      ${groups}
    </section>`;
}

function renderDocSection(section) {
  const status = sectionStatus(section.id);
  const selected = section.id === state.sectionId;
  return `
    <section class="doc-section ${status}${selected ? " selected" : ""}" id="block-${section.id}" data-section="${escAttr(section.id)}">
      <h2 class="doc-section-title"${selected ? ' data-tour="source-text"' : ""}>
        ${esc(section.title)}
        <span class="badge ${status}">${labelStatus(status)}</span>
        ${needsGeneration(section.id) ? `<span class="badge pending">Needs checks</span>` : ""}
      </h2>
      <div class="md">${esc(section.markdown)}</div>
    </section>`;
}

function renderKeyReadout(item, index) {
  const status = statementStatus(item);
  const focused = index === state.statementFocus ? "focused" : "";
  const keys = (item.keys || [])
    .map((key) => {
      const accepted = new Set(key.accepted || []);
      const chips = (key.value_enum || [])
        .map((value) => {
          const label = value === "" ? "(empty)" : value;
          const pass = accepted.has(value);
          return `<span class="${pass ? "accept-chip" : "enum-chip"}">${esc(label)}</span>`;
        })
        .join("");
      const acceptedList = (key.accepted || [])
        .map((value) => `<span class="accept-chip">${esc(value === "" ? "(empty)" : value)}</span>`)
        .join("");
      return `<div class="inspector-key">
        <p class="inspector-key-id">${esc(key.id || "key")}${key.required ? " · required" : ""}</p>
        <p class="inspector-question">${esc(key.question || "No question yet")}</p>
        <p class="muted" style="margin:0.35rem 0 0.2rem">Accepted (pass)</p>
        <div class="chips">${acceptedList || "<span class='muted'>None yet</span>"}</div>
        <p class="muted" style="margin:0.45rem 0 0.2rem">Possible values</p>
        <div class="chips">${chips || "<span class='muted'>None yet</span>"}</div>
      </div>`;
    })
    .join("");
  return `
    <article class="inspector-stmt ${focused}" id="inspect-stmt-${escAttr(state.sectionId)}-${index}"${index === 0 ? ' data-tour="closed-check"' : ""}>
      <div class="inspector-stmt-head">
        <span class="badge ${status}">${labelStatementStatus(status)}</span>
        <strong>${esc(item.description?.trim() || item.id || `Statement ${index + 1}`)}</strong>
      </div>
      ${keys || "<p class='muted'>No keys on this statement yet.</p>"}
    </article>`;
}

function renderInspector() {
  const section = currentSection();
  if (!section) {
    return `<h2>Closed checks</h2><p class="muted">Click an article in the document. Projects are measured against these values, not the paragraph.</p>`;
  }
  const status = sectionStatus(section.id);
  const statements = sectionStatements(section.id);
  const index = sectionIndex();
  const total = state.review.sections.length;
  const incomplete = statements.some((item) => statementStatus(item) !== "ready");
  let body = "";
  if (status === "no_restriction" && !statements.length) {
    body = `<p class="stmt-nav-empty"><span class="badge no_restriction">No restriction</span> This article has no closed check — it does not constrain the project.</p>`;
  } else if (!statements.length) {
    body = `<p class="stmt-nav-empty muted">No statements yet. Add one to turn this article into a closed check a project can fail or pass.</p>`;
  } else {
    body = statements.map((item, stmtIndex) => renderKeyReadout(item, stmtIndex)).join("");
  }
  return `
    <div class="inspector-nav">
      <button type="button" class="nav-chip" id="prev-section" ${index === 0 ? "disabled" : ""}>Previous</button>
      <strong id="section-pos">Article ${total ? index + 1 : 0} / ${total}</strong>
      <button type="button" class="nav-chip" id="next-section" ${index >= total - 1 ? "disabled" : ""}>Next</button>
    </div>
    <h2>Closed checks</h2>
    <p class="muted">Questions and accepted answers for this article. The comparator uses these values — not the model, and not the prose.</p>
    <p class="sidebar-section-title"><span class="badge ${status}">${labelStatus(status)}</span> ${esc(section.title)}</p>
    ${body}
    <div class="actions" data-tour="final-say">
      <md-filled-button type="button" data-save-sec="${escAttr(section.id)}" title="Save the closed questions and pass list" ${state.busy ? "disabled" : ""}>Save checks</md-filled-button>
      <md-filled-tonal-button type="button" data-cover-sec="${escAttr(section.id)}" title="Human final say: this check matches the article" ${state.busy ? "disabled" : ""}>Mark as covered</md-filled-tonal-button>
      <md-text-button type="button" data-waive-sec="${escAttr(section.id)}" title="This article does not impose a checkable restriction" ${state.busy ? "disabled" : ""}>No restriction in this article</md-text-button>
    </div>
    <details class="edit-checks"${incomplete ? " open" : ""}>
      <summary>Edit this check</summary>
      ${statements.map((item, stmtIndex) => renderStatementCard(section.id, item, stmtIndex)).join("")}
      <md-outlined-button type="button" data-add-stmt="${escAttr(section.id)}">Add statement</md-outlined-button>
    </details>
  `;
}

function renderNestedKey(sectionId, stmtIndex, key, keyIndex) {
  const chips = (key.value_enum || [])
    .map(
      (value, enumIndex) =>
        `<md-input-chip label="${escAttr(value === "" ? "(empty)" : value)}" data-del-enum="${escAttr(sectionId)}:${stmtIndex}:${keyIndex}:${enumIndex}"></md-input-chip>`
    )
    .join("");
  const accepted = key.accepted || [];
  const boxes = (key.value_enum || [])
    .map((value) => {
      const checked = accepted.includes(value) ? "checked" : "";
      const label = value === "" ? "(empty)" : value;
      return `<label><md-checkbox data-sid="${escAttr(sectionId)}" data-si="${stmtIndex}" data-ki="${keyIndex}" data-accepted-value="${escAttr(value)}" ${checked}></md-checkbox> ${esc(label)}</label>`;
    })
    .join("");
  return `
    <article class="key-card">
      <h4>Question</h4>
      <div class="field"><md-outlined-text-field label="Key id" data-sid="${escAttr(sectionId)}" data-si="${stmtIndex}" data-ki="${keyIndex}" data-key-field="id" value="${escAttr(key.id)}"></md-outlined-text-field></div>
      <div class="field"><md-outlined-text-field label="Question" data-sid="${escAttr(sectionId)}" data-si="${stmtIndex}" data-ki="${keyIndex}" data-key-field="question" value="${escAttr(key.question)}"></md-outlined-text-field></div>
      <div class="field"><md-outlined-text-field type="textarea" rows="3" label="Explanation" data-sid="${escAttr(sectionId)}" data-si="${stmtIndex}" data-ki="${keyIndex}" data-key-field="explanation" value="${escAttr(key.explanation)}"></md-outlined-text-field></div>
      <div class="field">
        <p class="muted" style="margin:0 0 0.35rem">Possible values</p>
        <div class="chips">${chips}</div>
        <div class="enum-row">
          <md-outlined-text-field data-enum-input="${escAttr(sectionId)}:${stmtIndex}:${keyIndex}" label="Add possible value"></md-outlined-text-field>
          <md-text-button type="button" data-add-enum="${escAttr(sectionId)}:${stmtIndex}:${keyIndex}">Add</md-text-button>
        </div>
      </div>
      <div class="field">
        <p class="muted" style="margin:0 0 0.35rem">Accepted values (pass)</p>
        <div class="accepted-grid">${boxes || "<span class='muted'>Add a possible value first.</span>"}</div>
      </div>
      <label class="muted"><md-checkbox data-sid="${escAttr(sectionId)}" data-si="${stmtIndex}" data-ki="${keyIndex}" data-key-field="required" ${key.required ? "checked" : ""}></md-checkbox> Required</label>
      <div class="actions"><md-text-button data-remove-key="${escAttr(sectionId)}:${stmtIndex}:${keyIndex}">Remove question</md-text-button></div>
    </article>
  `;
}

function renderStatementCard(sectionId, item, index) {
  const keys = (item.keys || [])
    .map((key, keyIndex) => renderNestedKey(sectionId, index, key, keyIndex))
    .join("");
  const focused = sectionId === state.sectionId && index === state.statementFocus ? "focused" : "";
  const status = statementStatus(item);
  return `
    <article class="card statement-card ${focused}" id="stmt-card-${escAttr(sectionId)}-${index}"${sectionId === state.sectionId && index === 0 ? ' data-tour="closed-check"' : ""}>
      <div class="statement-card-head">
        <h3>Statement</h3>
        <span class="badge ${status}">${labelStatementStatus(status)}</span>
      </div>
      <div class="field"><md-outlined-text-field label="Id" data-sid="${escAttr(sectionId)}" data-si="${index}" data-stmt-field="id" value="${escAttr(item.id)}"></md-outlined-text-field></div>
      <div class="field"><md-outlined-text-field type="textarea" rows="2" label="Statement" data-sid="${escAttr(sectionId)}" data-si="${index}" data-stmt-field="description" value="${escAttr(item.description)}"></md-outlined-text-field></div>
      ${keys || "<p class='muted'>Add a question so this statement can be checked.</p>"}
      <div class="actions">
        <md-outlined-button type="button" data-add-key="${escAttr(sectionId)}:${index}">Add question</md-outlined-button>
        <md-text-button type="button" data-remove-stmt="${escAttr(sectionId)}:${index}">Remove statement</md-text-button>
      </div>
    </article>
  `;
}

function renderDocument() {
  const review = state.review;
  const sections = (review.sections || []).map((section) => renderDocSection(section)).join("");
  return `
    <div class="doc-shell">
      <div class="doc-canvas">
        <article class="doc-paper" id="doc-paper">
          <header class="doc-paper-head">
            <p class="doc-kicker">${esc(review.domain || "Regulation")} · ${esc(review.filename || review.source_md || "Markdown")}</p>
            <h1>${esc(review.document.meta.title)}</h1>
            <p class="muted">${esc(policyStory(review) || "Click an article. Closed questions and accepted answers for that section appear on the right.")}</p>
          </header>
          ${sections || "<p class='muted'>No sections.</p>"}
        </article>
      </div>
      <aside class="doc-inspector" id="statement-sidebar">${renderInspector()}</aside>
    </div>
  `;
}

function bindReview() {
  bindDeleteButtons();
  document.getElementById("sync-policies")?.addEventListener("click", () => syncPolicies(state.review.id, false));
  document.getElementById("doc-paper")?.addEventListener("click", (event) => {
    const section = event.target.closest("[data-section]");
    if (!section) return;
    showSection(section.dataset.section, true);
    setHash(state.review.id, section.dataset.section);
  });
  document.getElementById("status-summary")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-jump-section]");
    if (!chip) return;
    showSection(chip.dataset.jumpSection, true);
    if (chip.dataset.jumpStmt !== "") focusStatement(Number(chip.dataset.jumpStmt));
    setHash(state.review.id, chip.dataset.jumpSection);
  });
  bindInspector();
}

function bindInspector() {
  document.getElementById("prev-section")?.addEventListener("click", () => stepSection(-1));
  document.getElementById("next-section")?.addEventListener("click", () => stepSection(1));
  document.querySelectorAll("[data-waive-sec]").forEach((button) => {
    button.addEventListener("click", () => setStatus(button.dataset.waiveSec, "no_restriction"));
  });
  document.querySelectorAll("[data-save-sec]").forEach((button) => {
    button.addEventListener("click", () => saveSection(button.dataset.saveSec));
  });
  document.querySelectorAll("[data-cover-sec]").forEach((button) => {
    button.addEventListener("click", async () => {
      const sectionId = button.dataset.coverSec;
      await saveSection(sectionId);
      if (!state.error) await setStatus(sectionId, "covered");
    });
  });
  document.querySelectorAll("[data-add-stmt]").forEach((button) => {
    button.addEventListener("click", () => {
      const sectionId = button.dataset.addStmt;
      const statements = sectionStatements(sectionId);
      statements.push({
        id: `stmt_${statements.length + 1}`,
        description: "",
        source_section_id: sectionId,
        keys: [blankKey(1)],
      });
      state.statementFocus = statements.length - 1;
      render();
    });
  });
  document.querySelectorAll("[data-add-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const [sectionId, stmtIndex] = splitIndex(button.dataset.addKey);
      const stmt = sectionStatements(sectionId)[stmtIndex];
      stmt.keys = stmt.keys || [];
      stmt.keys.push(blankKey(stmt.keys.length + 1));
      render();
    });
  });
  document.querySelectorAll("[data-stmt-field]").forEach((input) => {
    input.addEventListener("input", () => {
      const stmt = sectionStatements(input.dataset.sid)[Number(input.dataset.si)];
      if (stmt) stmt[input.dataset.stmtField] = input.value;
    });
  });
  document.querySelectorAll("[data-key-field]").forEach((input) => {
    const apply = () => {
      const key = sectionStatements(input.dataset.sid)[Number(input.dataset.si)]?.keys?.[Number(input.dataset.ki)];
      if (!key) return;
      if (input.dataset.keyField === "required") key.required = Boolean(input.checked);
      else key[input.dataset.keyField] = input.value;
    };
    input.addEventListener("input", apply);
    input.addEventListener("change", apply);
  });
  document.querySelectorAll("[data-add-enum]").forEach((button) => {
    button.addEventListener("click", () => {
      const [sectionId, stmtIndex, keyIndex] = splitIndex(button.dataset.addEnum);
      const key = sectionStatements(sectionId)[stmtIndex]?.keys?.[keyIndex];
      const field = document.querySelector(`[data-enum-input="${button.dataset.addEnum}"]`);
      const value = field?.value ?? "";
      if (!key) return;
      key.value_enum = key.value_enum || [];
      key.value_enum.push(value);
      if (field) field.value = "";
      render();
    });
  });
  document.querySelectorAll("[data-del-enum]").forEach((button) => {
    const remove = () => {
      const [sectionId, stmtIndex, keyIndex, enumIndex] = splitIndex(button.dataset.delEnum);
      const key = sectionStatements(sectionId)[stmtIndex]?.keys?.[keyIndex];
      if (!key) return;
      const [removed] = key.value_enum.splice(Number(enumIndex), 1);
      key.accepted = (key.accepted || []).filter((value) => value !== removed);
      render();
    };
    button.addEventListener("remove", remove);
    button.addEventListener("click", remove);
  });
  document.querySelectorAll("[data-remove-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const [sectionId, stmtIndex, keyIndex] = splitIndex(button.dataset.removeKey);
      const stmt = sectionStatements(sectionId)[stmtIndex];
      stmt?.keys?.splice(keyIndex, 1);
      render();
    });
  });
  document.querySelectorAll("[data-remove-stmt]").forEach((button) => {
    button.addEventListener("click", () => {
      const [sectionId, stmtIndex] = splitIndex(button.dataset.removeStmt);
      const list = sectionStatements(sectionId);
      list.splice(stmtIndex, 1);
      state.statementFocus = Math.min(state.statementFocus, Math.max(0, list.length - 1));
      render();
    });
  });
  document.querySelectorAll("[data-accepted-value]").forEach((input) => {
    input.addEventListener("change", () => {
      const key = sectionStatements(input.dataset.sid)[Number(input.dataset.si)]?.keys?.[Number(input.dataset.ki)];
      if (!key) return;
      const value = input.dataset.acceptedValue;
      key.accepted = key.accepted || [];
      if (input.checked && !key.accepted.includes(value)) key.accepted.push(value);
      if (!input.checked) key.accepted = key.accepted.filter((item) => item !== value);
    });
  });
}

function splitIndex(raw) {
  return String(raw || "").split(":").map((part, index) => (index === 0 ? part : Number(part)));
}

async function saveSection(sectionId) {
  state.busy = true;
  state.error = "";
  showProgress(true);
  try {
    const statements = sectionStatements(sectionId).map((item) => ({
      ...item,
      source_section_id: sectionId,
      keys: (item.keys || []).map((key) => ({
        ...key,
        accepted: key.accepted || [],
        value_enum: key.value_enum || [],
      })),
    }));
    const emptyKeys = statements.find((item) => !item.keys.length);
    if (emptyKeys) throw new Error(`Statement ${emptyKeys.id} needs at least one question.`);
    const emptyAccepted = statements.find((item) => item.keys.some((key) => !key.accepted.length));
    if (emptyAccepted) {
      throw new Error(`Statement ${emptyAccepted.id} needs at least one accepted value.`);
    }
    const emptyEnum = statements.flatMap((item) => item.keys).find((key) => !key.value_enum.length);
    if (emptyEnum) throw new Error(`Key ${emptyEnum.id} needs at least one possible value.`);
    const review = await api(`/api/reviews/${state.review.id}/sections/${sectionId}`, {
      method: "PATCH",
      body: JSON.stringify({ statements }),
    });
    state.review = review;
    delete state.drafts[sectionId];
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
    delete state.drafts[sectionId];
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
      ? `Updated closed checks for ${generated.length} section(s). Saved JSON to data/policies/${reviewId}.json — this is what projects are compared against.`
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
    state.drafts = {};
  } catch (err) {
    state.error = err.message;
    state.notice = "";
  } finally {
    state.busy = false;
    render();
  }
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
  const visible = window.PoliviewDemo ? window.PoliviewDemo.filterHealth(runs) : runs;
  if (window.PoliviewDemo?.enabled()) {
    const demo = visible.find((item) => item.kind === "demo") || visible[0];
    return demo?.id || "";
  }
  return visible[0]?.id || "";
}

async function loadHealth(runId, filter) {
  if (!location.hash && location.pathname.replace(/\/+$/, "").endsWith("/health")) {
    location.replace("#/health");
    return;
  }
  const data = await api("/api/health/runs");
  const runs = window.PoliviewDemo ? window.PoliviewDemo.filterHealth(data.runs || []) : data.runs || [];
  const selected = runId && runs.some((item) => item.id === runId) ? runId : pickDefaultHealthId(runs);
  state.view = "health";
  state.healthRuns = runs;
  state.healthFilter = filter === "all" ? "all" : "failed";
  state.healthId = selected;
  state.review = null;
  if (!selected) {
    state.health = null;
    state.error = "";
    subtitleEl.textContent = "Project owner · compliance health";
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
  if (embedded && !hasCheckedHealth()) {
    return `
      <section class="health-page embedded health-pending">
        <p class="eyebrow">Project owner</p>
        <h1>Compliance health</h1>
        <p class="muted">No results yet. Starter files are project metadata only. Click <strong>Check compliance</strong> to fill answers from those files and the sample GDPR / EU AI Act keys. The comparator — not the model — picks pass, fail, or missing info.</p>
      </section>`;
  }
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
            <p class="muted">Results for a shipment against the closed GDPR and EU AI Act checks: fail, why, what to do, who to contact.</p>
          </div>
        </div>
        <p class="muted">No health-check results found. Open GrowthBoard from <strong>Project owner → Workspace</strong>, or turn <strong>Demo</strong> on.</p>
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
          <md-outlined-select id="health-run" label="Stored results">${optionsHtml}</md-outlined-select>
        </div>`;
  return `
    ${banners()}
    <section class="health-page${embedded ? " embedded" : ""}">
      <div class="health-toolbar">
        <div>
          <p class="eyebrow">Project owner</p>
          <h1>Compliance health</h1>
          <p class="muted">${esc(snapshot.project_name || "Untitled project")} · ${esc((snapshot.policies || []).map((item) => item.domain).filter(Boolean).join(" + ") || "closed GDPR and EU AI Act checks")}</p>
        </div>
        ${picker}
        ${futureHit(
          `<md-outlined-button disabled title="Export is not in this demo"><md-icon slot="icon">download</md-icon>Export report</md-outlined-button>`,
          "stakeholders could receive this GDPR / EU AI Act report without another meeting."
        )}
      </div>
      <div class="health-meta">
        <div><span class="meta-label">Last validated</span><strong>${esc(formatWhen(snapshot.validated_at))}</strong></div>
        <div><span class="meta-label">Checks run</span><strong>${totals.total}</strong></div>
        <div><span class="meta-label">Passed</span><strong>${totals.passed}</strong></div>
        <div><span class="meta-label">Failed</span><strong>${totals.failed}</strong></div>
        <div><span class="meta-label">Missing info</span><strong>${totals.missing}</strong></div>
        <div><span class="meta-label">Policies in scope</span><strong>${(snapshot.policies || []).length}</strong></div>
      </div>
      <div class="health-overview" data-tour="health">
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
        <p class="muted">${failedOnly ? "Failed GDPR and EU AI Act checks first. Open All checks for passes and missing information." : "Every closed check that applies to this project, including passes."}</p>
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
    <article class="donut-card" data-tour="health-${escAttr(policy.policy_id || policy.domain)}">
      <h2>${esc(policy.domain || policy.title)}</h2>
      ${donutChart(counts, `${policy.title} pass rate`)}
      <p class="donut-caption">${counts.passed}/${counts.total} passed</p>
      <p class="muted donut-org">${esc(policyStory(policy) || policy.organization || policy.title)}</p>
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
        <p class="muted">${owners ? `Policy contacts: ${esc(owners)}` : "No policy contacts listed."}</p>
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
          ${futureHit(
          `<md-filled-tonal-button disabled title="Notify owner is not in this demo"><md-icon slot="icon">notifications</md-icon>Notify owner</md-filled-tonal-button>`,
          "a failed transfer or missing human-oversight check could open a ticket with the DPO or AI Act officer without leaving this report."
          )}
        </section>
      </div>`
    : `
      <p>${esc(item.why || item.detail || "This check passed.")}</p>
      ${answers ? `<ul class="answer-list">${answers}</ul>` : ""}`;
  return `
    <details class="check-acc ${item.status}"${item.status === "fail" ? " data-tour=\"finding\"" : ""}>
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

function domainBadge(domain) {
  const value = String(domain || "").toLowerCase();
  if (value.includes("gdpr")) return "covered";
  if (value.includes("ai")) return "missing";
  return "pending";
}

function guessDomainFromPath(path) {
  const lower = String(path || "").toLowerCase();
  if (lower.includes("gdpr")) return "GDPR";
  if (lower.includes("ai-act") || lower.includes("ai_act")) return "AI Act";
  if (lower.includes("infosec")) return "InfoSec";
  return "GDPR";
}

function guessTitleFromPath(path) {
  const name = String(path || "").split("/").pop() || "";
  return name.replace(/\.(md|txt)$/i, "").replace(/[-_]/g, " ");
}

function hideGeneratedProjectSchema() {
  state.checkedWorkspaceId = "";
  const schemaTab = "file:answers.json";
  state.openTabs = (state.openTabs || []).filter((tab) => tab.id !== schemaTab);
  if (state.activeTab === schemaTab) state.activeTab = "health";
  if (state.fileCache) delete state.fileCache["answers.json"];
}

window.PoliviewApp = {
  onDemoOff: hideGeneratedProjectSchema,
};

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
