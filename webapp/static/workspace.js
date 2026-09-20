async function loadProject(projectId) {
  const list = await api("/api/projects");
  const projects = window.PoliviewDemo ? window.PoliviewDemo.filterProjects(list.projects || []) : list.projects || [];
  if (projectId && window.PoliviewDemo && !window.PoliviewDemo.enabled() && window.PoliviewDemo.isProject(projectId)) {
    location.hash = "#/project";
    return;
  }
  const selected =
    projectId && projects.some((item) => item.id === projectId)
      ? projectId
      : projects.find((item) => item.id === "growthboard")?.id || projects[0]?.id || "";
  if (!selected) {
    state.view = "project";
    state.workspace = null;
    state.workspaceId = "";
    state.health = null;
    state.review = null;
    state.error = "";
    subtitleEl.textContent = "Project · no workspace";
    document.title = `${PRODUCT} · Project`;
    render();
    return;
  }
  const switching = state.workspace?.id !== selected;
  if (switching) {
    const bundle = await api(`/api/projects/${encodeURIComponent(selected)}`);
    state.workspace = bundle;
    state.workspaceId = bundle.id;
    state.health = bundle.health;
    state.healthId = bundle.health_run_id || bundle.health?.id || "";
    state.fileCache = {};
    state.openTabs = [{ id: "health", title: "Compliance health", pinned: true }];
    state.activeTab = "health";
    state.focusPolicyId = "";
    state.healthFilter = "failed";
  }
  if (state.workspace) {
    state.workspace.workspaces = projects;
  }
  state.view = "project";
  state.review = null;
  state.error = "";
  const health = displayHealth();
  const checked = hasCheckedHealth();
  subtitleEl.textContent = checked
    ? `${state.workspace?.name || "Project"} · last check ${formatWhen(health.validated_at)}`
    : `${state.workspace?.name || "Project"} · not checked yet`;
  document.title = `${PRODUCT} · ${state.workspace?.name || "Project"}`;
  render();
}

function setProjectHash(projectId) {
  location.hash = projectId ? `#/project/${encodeURIComponent(projectId)}` : "#/project";
}

function renderProject() {
  const workspace = state.workspace;
  if (!workspace) {
    return `<section class="workbench-empty">
      <p class="eyebrow">Project owner</p>
      <h1 class="md-typescale-headline-small">No workspace yet</h1>
      <p class="muted">Turn <strong>Demo</strong> on to restore <strong>GrowthBoard</strong> (fails GDPR transfers and EU AI Act oversight) and <strong>Campus Pilot</strong> (missing transfer evidence).</p>
    </section>`;
  }
  const health = displayHealth();
  return `
    <div class="workbench">
      ${renderProjectLeft(workspace, health)}
      <section class="wb-center">
        ${renderEditorTabs()}
        <div class="wb-editor">${renderEditorBody()}</div>
        ${renderProblemsBar(health)}
        ${renderStatusBar(workspace, health)}
      </section>
      ${renderGuidePlaceholder()}
    </div>`;
}

function renderProjectLeft(workspace, health) {
  const checked = hasCheckedHealth();
  const projects = workspace.workspaces || [];
  const options = projects
    .map(
      (item) =>
        `<md-select-option value="${escAttr(item.id)}" ${item.id === workspace.id ? "selected" : ""}><div slot="headline">${esc(item.name)}</div></md-select-option>`
    )
    .join("");
  const policies = checked ? health.policies || [] : [];
  const policyRows = checked
    ? policies
        .map((policy) => {
          const failed = policy.failed || 0;
          return `<button type="button" class="policy-preview ${failed ? "has-fail" : "ok"}" data-open-policy="${escAttr(policy.policy_id)}">
        <span>${esc(policy.domain || policy.title)}</span>
        <span class="badge ${failed ? "fail" : "pass"}">${failed} failed</span>
      </button>`;
        })
        .join("")
    : `<p class="muted">No results yet. Click Check compliance to score this workspace against GDPR and the EU AI Act.</p>`;
  const next = checked
    ? nextActions(health)
        .map(
          (item) =>
            `<button type="button" class="next-item" data-open-stmt="${escAttr(item.statement_id)}">
          <span class="badge fail">${esc(item.domain)}</span>
          <span>${esc(item.label)}</span>
        </button>`
        )
        .join("")
    : "";
  const answers = checked
    ? closedAnswers(health)
        .map(
          (item) =>
            `<li class="${item.ok ? "ok" : "fail"}"><code>${esc(item.key)}</code> ${esc(item.value)} <span class="muted">${item.ok ? "accepted" : "not accepted"}</span></li>`
        )
        .join("")
    : "";
  return `
    <aside class="wb-left" data-tour="workspace">
      <div class="wb-pane">
        <p class="wb-kicker">Project</p>
        <md-outlined-select id="project-switcher" label="Workspace">${options}</md-outlined-select>
        <p class="wb-owner">${esc(workspace.owner || "Project owner")}${workspace.owner_email ? `<br /><a href="mailto:${escAttr(workspace.owner_email)}">${esc(workspace.owner_email)}</a>` : ""}</p>
        <p class="muted wb-desc">${esc(workspace.description || "")}</p>
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">Latest compliance check</p>
        <p class="muted">${checked ? `Last validated ${esc(formatWhen(health.validated_at))}` : "Not checked yet. Check compliance fills answers from these files and the sample GDPR / EU AI Act keys."}</p>
        <div class="policy-preview-list">${policyRows || "<p class='muted'>No policies in scope.</p>"}</div>
        <md-filled-tonal-button id="recheck-btn" data-tour="check-compliance" title="Compare this workspace to the closed GDPR and EU AI Act checks" ${state.busy ? "disabled" : ""}>
          <md-icon slot="icon">health_and_safety</md-icon>
          Check compliance
        </md-filled-tonal-button>
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">Explorer</p>
        <p class="muted add-file-hint">Starter files: hosting region, processors, retention, and the lead-scoring model. The parser reads these on Check compliance.</p>
        <button type="button" class="file-row pinned ${state.activeTab === "health" ? "active" : ""}" data-tab="health">
          <span class="pin">📌</span> Compliance health
        </button>
        ${renderFileTree(visibleProjectTree(workspace.tree || []))}
        <form id="add-project-file" class="add-file-form" action="#" method="post">
          <p class="muted add-file-hint">Add a technical note (region, DPA, reviewer, model card). It is included on the next check.</p>
          <md-outlined-text-field id="add-file-path" label="Path" placeholder="docs/notes.md"></md-outlined-text-field>
          <input id="add-file-input" type="file" hidden accept=".md,.txt,.json,.yml,.yaml,.py,.js,.ts,.csv,.toml,.html,.css" />
          <md-outlined-button id="add-file-pick" type="button">
            <md-icon slot="icon">upload_file</md-icon>
            <span id="add-file-label">Choose file</span>
          </md-outlined-button>
          <md-outlined-text-field id="add-file-context" type="textarea" rows="3" label="Or paste context"></md-outlined-text-field>
          <md-filled-button type="button" id="add-file-submit" ${state.busy ? "disabled" : ""}>
            <md-icon slot="icon">note_add</md-icon>
            Add to project
          </md-filled-button>
        </form>
        <div class="explorer-future">
          ${futureHit(
            `<md-text-button disabled title="Search is not in this demo"><md-icon slot="icon">search</md-icon>Search</md-text-button>`,
            "search would help a project owner find transfer or model-card evidence while they compare the workspace to GDPR and the EU AI Act."
          )}
        </div>
      </div>
      <div class="wb-pane future-pane" tabindex="0" data-future="${escAttr(futureCopy("live AWS, processor, and identity feeds would refresh residency and oversight evidence without a meeting."))}">
        <p class="wb-kicker">External connections</p>
        ${(workspace.connections || [])
          .map((item) => {
            const live = checked ? statusClass(item.status) : "pending";
            return `<div class="conn-row ${live}">
                <span class="badge ${live}">${esc(item.kind)}</span>
                <span><strong>${esc(item.name)}</strong><br /><span class="muted">${esc(item.detail || "")}</span></span>
              </div>`;
          })
          .join("")}
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">Next up</p>
        ${next || `<p class='muted'>${checked ? "No remediations queued." : "Next actions appear after Check compliance."}</p>`}
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">Closed answers</p>
        <ul class="answer-preview">${answers || `<li class='muted'>${checked ? "No answers recorded." : "Closed answers (residency, oversight, model card) appear after Check compliance."}</li>`}</ul>
      </div>
    </aside>`;
}

function isGeneratedProjectSchema(path) {
  const name = String(path || "")
    .replace(/\\/g, "/")
    .split("/")
    .pop()
    .toLowerCase();
  return name === "answers.json";
}

function visibleProjectTree(nodes) {
  if (demoOn()) return nodes || [];
  return (nodes || [])
    .filter((node) => !isGeneratedProjectSchema(node.path))
    .map((node) => {
      if (node.kind !== "dir") return node;
      return { ...node, children: visibleProjectTree(node.children || []) };
    })
    .filter((node) => node.kind !== "dir" || (node.children && node.children.length));
}

function renderFileTree(nodes, depth = 0) {
  return nodes
    .map((node) => {
      if (node.kind === "dir") {
        return `<details class="dir-node" open style="--d:${depth}">
          <summary>${esc(node.name)}</summary>
          ${renderFileTree(node.children || [], depth + 1)}
        </details>`;
      }
      const active = state.activeTab === `file:${node.path}` ? "active" : "";
      const marks = findingCount(node.path);
      return `<button type="button" class="file-row ${active}" data-open-file="${escAttr(node.path)}" style="--d:${depth}">
        <span>${esc(node.name)}</span>
        ${marks ? `<span class="gutter-fail">${marks}</span>` : ""}
      </button>`;
    })
    .join("");
}

function findingCount(path) {
  if (!hasCheckedHealth()) return 0;
  return (state.workspace?.findings || []).filter((item) => item.path === path && item.status === "fail").length;
}

function renderEditorTabs() {
  const tabs = (state.openTabs || [])
    .map((tab) => {
      const active = state.activeTab === tab.id ? "active" : "";
      const close = tab.pinned
        ? ""
        : `<button type="button" class="tab-close" data-close-tab="${escAttr(tab.id)}" aria-label="Close">×</button>`;
      const pin = tab.pinned ? `<span class="pin">📌</span>` : "";
      return `<div class="wb-tab ${active} ${tab.pinned ? "pinned" : ""}">
        <button type="button" data-tab="${escAttr(tab.id)}">${pin}${esc(tab.title)}</button>
        ${close}
      </div>`;
    })
    .join("");
  return `<div class="wb-tabs">${tabs}</div>`;
}

function renderEditorBody() {
  if (state.activeTab === "health") {
    return renderHealth({ embedded: true });
  }
  if (state.activeTab.startsWith("file:")) {
    const path = state.activeTab.slice(5);
    const file = state.fileCache[path];
    if (!file) return `<p class="muted" style="padding:1rem">Loading ${esc(path)}…</p>`;
    return renderFileViewer(file);
  }
  return `<p class="muted" style="padding:1rem">Select a file.</p>`;
}

function renderFileViewer(file) {
  const lines = String(file.content || "").split("\n");
  const rows = lines
    .map((line, index) => {
      const ln = index + 1;
      return `<div class="code-line"><span class="ln">${ln}</span><code>${esc(line) || " "}</code></div>`;
    })
    .join("");
  return `<div class="file-viewer">
    <div class="file-meta">
      <strong>${esc(file.path)}</strong> <span class="muted">${esc(file.language)}</span>
      <span class="file-actions">
        ${futureHit(
          `<md-text-button disabled title="In-app edit is not in this demo"><md-icon slot="icon">edit</md-icon>Edit</md-text-button>`,
          "in-app editing would let the team move off us-east-1 or add a model card in the same files the comparator reads."
        )}
        ${futureHit(
          `<md-text-button disabled title="Save is not in this demo"><md-icon slot="icon">save</md-icon>Save</md-text-button>`,
          "saving project files here would keep GDPR and EU AI Act evidence in sync for the next compliance check."
        )}
        ${futureHit(
          `<md-text-button disabled title="Commit is not in this demo"><md-icon slot="icon">commit</md-icon>Commit</md-text-button>`,
          "commits would record who changed hosting or oversight evidence after a fail or missing-info result."
        )}
      </span>
    </div>
    <div class="code-wrap">${rows}</div>
  </div>`;
}

function renderProblemsBar(health) {
  if (!hasCheckedHealth()) {
    return `<details class="wb-problems">
      <summary>Problems <span class="badge pending">—</span></summary>
      <div class="problem-list"><p class="muted">No check yet. Click Check compliance to see GDPR and EU AI Act fails or missing info.</p></div>
    </details>`;
  }
  const problems = (health.policies || []).flatMap((policy) =>
    (policy.results || [])
      .filter((item) => item.status === "fail" || item.status === "missinginfo")
      .map((item) => ({ policy, item }))
  );
  const rows = problems
    .map(
      (row) =>
        `<button type="button" class="problem-row" data-open-stmt="${escAttr(row.item.statement_id)}">
          <span class="badge ${statusClass(row.item.status)}">${esc(row.item.status)}</span>
          <span>${esc(row.policy.domain)} · ${esc(row.item.description)}</span>
        </button>`
    )
    .join("");
  return `<details class="wb-problems">
    <summary>Problems <span class="badge fail">${problems.length}</span></summary>
    <div class="problem-list">${rows || "<p class='muted'>No open problems.</p>"}</div>
  </details>`;
}

function renderGuidePlaceholder() {
  return `
    <aside class="wb-chat future-pane" tabindex="0" data-future="${escAttr(futureCopy("a project assistant that explains a failed transfer or missing model card, what to do next, and whether to email the DPO or the AI Act officer."))}">
      <p class="wb-kicker">Compliance guide</p>
      <p class="muted">${hasCheckedHealth() ? "Ask why a GDPR or EU AI Act check failed, what to do first, or who to contact. The guide would not pick the verdict." : "Click Check compliance first. The guide would then explain fail or missing-info results — it would not pick the verdict."}</p>
      <div class="chat-log">
        <p class="chat-bubble muted">${hasCheckedHealth() ? "Guide replies would use these same pass / fail / missing-info results. The model would not decide whether GrowthBoard is compliant." : "No results yet. After Check compliance, this guide would talk about the same comparator output."}</p>
      </div>
      <div class="chat-compose">
        <md-outlined-text-field disabled label="Ask the guide"></md-outlined-text-field>
        <md-filled-button disabled>Send</md-filled-button>
      </div>
    </aside>`;
}

function renderStatusBar(workspace, health) {
  if (!hasCheckedHealth()) {
    return `<footer class="wb-status">
    <span class="badge pending">Not checked</span>
    <span class="grow">${esc(workspace.name)} · ${esc(activeTabTitle())}</span>
    <span>Click Check compliance to score these files against GDPR and the EU AI Act</span>
  </footer>`;
  }
  return `<footer class="wb-status">
    <span class="badge ${statusClass(health.overall_status)}">${labelHealthStatus(health.overall_status)}</span>
    <span>${health.failed || 0} failed</span>
    <span>${health.missing || 0} missing</span>
    <span>${health.passed || 0} passed</span>
    <span class="grow">${esc(workspace.name)} · ${esc(activeTabTitle())}</span>
    <span>Last check ${esc(formatWhen(health.validated_at))}</span>
  </footer>`;
}

function activeTabTitle() {
  const tab = (state.openTabs || []).find((item) => item.id === state.activeTab);
  return tab?.title || "Compliance health";
}

function nextActions(health) {
  const items = [];
  for (const policy of health.policies || []) {
    for (const result of policy.results || []) {
      if (result.status !== "fail") continue;
      items.push({
        domain: policy.domain,
        label: result.remediation?.actions?.[0] || result.description,
        statement_id: result.statement_id,
      });
    }
  }
  return items.slice(0, 3);
}

function closedAnswers(health) {
  const seen = new Map();
  for (const policy of health.policies || []) {
    for (const result of policy.results || []) {
      for (const [key, value] of Object.entries(result.answers || {})) {
        const accepted = result.accepted?.[key] || [];
        const ok = result.status === "pass" || (value !== "" && accepted.includes(value));
        if (!seen.has(key)) seen.set(key, { key, value: value === "" ? "(empty)" : value, ok });
        else if (!ok) seen.set(key, { key, value: value === "" ? "(empty)" : value, ok: false });
      }
    }
  }
  return [...seen.values()];
}

function bindProject() {
  bindHealth();
  document.getElementById("project-switcher")?.addEventListener("change", (event) => {
    state.workspace = null;
    setProjectHash(event.target.value);
  });
  document.getElementById("recheck-btn")?.addEventListener("click", recheckProject);
  document.querySelectorAll("[data-open-file]").forEach((button) => {
    button.addEventListener("click", () => openProjectFile(button.dataset.openFile));
  });
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      render();
    });
  });
  document.querySelectorAll("[data-close-tab]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      closeTab(button.dataset.closeTab);
    });
  });
  document.querySelectorAll("[data-open-policy]").forEach((button) => {
    button.addEventListener("click", () => openHealthPolicy(button.dataset.openPolicy));
  });
  document.querySelectorAll("[data-open-stmt]").forEach((button) => {
    button.addEventListener("click", () => openHealthStatement(button.dataset.openStmt));
  });
  document.getElementById("add-file-pick")?.addEventListener("click", () => {
    document.getElementById("add-file-input")?.click();
  });
  document.getElementById("add-file-input")?.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    const label = document.getElementById("add-file-label");
    if (label) label.textContent = file?.name || "Choose file";
    const pathField = document.getElementById("add-file-path");
    if (file && pathField && !pathField.value) pathField.value = file.name;
  });
  document.getElementById("add-project-file")?.addEventListener("submit", addProjectFile);
  document.getElementById("add-file-submit")?.addEventListener("click", addProjectFile);
}

async function addProjectFile(event) {
  event.preventDefault();
  const pathField = document.getElementById("add-file-path");
  const contextField = document.getElementById("add-file-context");
  const fileInput = document.getElementById("add-file-input");
  const file = fileInput?.files?.[0];
  let path = (pathField?.value || "").trim();
  let content = contextField?.value || "";
  if (file) {
    if (file.name.toLowerCase().endsWith(".pdf")) {
      const message = "PDF upload is not enabled yet. Use Markdown or another text file.";
      state.error = message;
      toast(message);
      return;
    }
    try {
      content = await file.text();
    } catch {
      const message = "Could not read that file as text.";
      state.error = message;
      toast(message);
      return;
    }
    if (!path) path = file.name;
  }
  if (!path) path = "context.md";
  if (!file && !String(content).trim()) {
    const message = "Choose a file or paste project context.";
    state.error = message;
    toast(message);
    return;
  }
  state.busy = true;
  state.error = "";
  showProgress(true);
  try {
    const bundle = await api(`/api/projects/${encodeURIComponent(state.workspaceId)}/files`, {
      method: "POST",
      body: JSON.stringify({ path, content }),
    });
    state.workspace = bundle;
    state.health = bundle.health;
    delete state.fileCache[path];
    state.notice = `Added ${path} to the project.`;
    toast(state.notice);
  } catch (err) {
    state.error = err.message;
    toast(err.message);
  } finally {
    state.busy = false;
    showProgress(false);
  }
  if (!state.error) await openProjectFile(path);
  else render();
}

async function openProjectFile(path) {
  const tabId = `file:${path}`;
  if (!state.openTabs.some((tab) => tab.id === tabId)) {
    state.openTabs.push({ id: tabId, title: path.split("/").pop(), pinned: false });
  }
  state.activeTab = tabId;
  if (!state.fileCache[path]) {
    render();
    try {
      state.fileCache[path] = await api(
        `/api/projects/${encodeURIComponent(state.workspaceId)}/files?path=${encodeURIComponent(path)}`
      );
    } catch (err) {
      state.error = err.message;
    }
  }
  render();
}

function closeTab(tabId) {
  state.openTabs = state.openTabs.filter((tab) => tab.id !== tabId || tab.pinned);
  if (state.activeTab === tabId) state.activeTab = "health";
  render();
}

function openHealthPolicy(policyId) {
  state.activeTab = "health";
  state.focusPolicyId = policyId;
  render();
  document.getElementById(`policy-${policyId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function openHealthStatement(statementId) {
  state.activeTab = "health";
  state.healthFilter = "all";
  render();
  const details = [...document.querySelectorAll(".check-acc")].find((item) =>
    item.textContent.includes(statementId)
  );
  const match = [...document.querySelectorAll(".check-acc")].find((item) => {
    const summary = item.querySelector("summary");
    return summary && statementMatches(item, statementId);
  });
  const target = match || details;
  if (target) {
    target.open = true;
    target.closest(".policy-acc") && (target.closest(".policy-acc").open = true);
    target.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function statementMatches(element, statementId) {
  const policy = (state.health?.policies || []).find((item) =>
    (item.results || []).some((row) => row.statement_id === statementId)
  );
  const result = policy?.results?.find((row) => row.statement_id === statementId);
  if (!result) return false;
  return element.textContent.includes(result.description);
}

async function recheckProject() {
  state.busy = true;
  state.error = "";
  showProgress(true);
  try {
    const parse = !demoOn();
    const bundle = await api(`/api/projects/${encodeURIComponent(state.workspaceId)}/check`, {
      method: "POST",
      body: JSON.stringify({ parse }),
    });
    state.workspace = bundle;
    state.health = bundle.health;
    if (!demoOn()) state.checkedWorkspaceId = state.workspaceId;
    const health = displayHealth();
    subtitleEl.textContent = `${state.workspace?.name || "Project"} · last check ${formatWhen(health.validated_at)}`;
    state.notice = demoOn()
      ? "Re-checked against current answers. GDPR transfers and EU AI Act oversight still come from the comparator, not the model."
      : "Parser filled answers from the starter files and the sample GDPR / EU AI Act keys. The comparator — not the model — picked pass, fail, or missing info.";
    toast(state.notice);
  } catch (err) {
    state.error = err.message;
  } finally {
    state.busy = false;
    render();
  }
}

async function start() {
  bindChrome();
  try {
    await Promise.race([
      customElements.whenDefined("md-filled-button"),
      new Promise((resolve) => setTimeout(resolve, 5000)),
    ]);
  } catch (_) {
    /* offline CDN: still boot the demo with unupgraded tags */
  }
  await boot();
  window.PoliviewTour?.onAppReady();
}

start();
