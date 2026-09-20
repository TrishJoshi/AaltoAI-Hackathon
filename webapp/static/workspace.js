async function loadProject(projectId) {
  const list = await api("/api/projects");
  const projects = list.projects || [];
  const selected =
    projectId && projects.some((item) => item.id === projectId)
      ? projectId
      : projects.find((item) => item.id === "growthboard")?.id || projects[0]?.id || "growthboard";
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
    state.chat = [projectWelcome(bundle)];
    state.chatError = "";
    state.healthFilter = "failed";
  }
  state.view = "project";
  state.review = null;
  state.error = "";
  const health = state.health || {};
  subtitleEl.textContent = `${state.workspace?.name || "Project"} · last check ${formatWhen(health.validated_at)}`;
  document.title = `${PRODUCT} · ${state.workspace?.name || "Project"}`;
  render();
}

function projectWelcome(bundle) {
  const health = bundle.health || {};
  const failed = health.failed || 0;
  const missing = health.missing || 0;
  const policies = (health.policies || []).length;
  let content = `I can walk you through **${bundle.name}**’s latest health check. `;
  if (failed) content += `**${failed} check(s) failed** across ${policies} applicable policies. `;
  if (missing) content += `${missing} still need${missing === 1 ? "s" : ""} information. `;
  if (!failed && !missing) content += "Every recorded check currently passes. ";
  content += "Ask why something failed, what to do next, or who to contact.";
  return {
    role: "assistant",
    content,
    prompts: defaultProjectPrompts(health),
  };
}

function defaultProjectPrompts(health) {
  const failed = (health.policies || []).flatMap((policy) =>
    (policy.results || []).filter((item) => item.status === "fail").map((item) => item.description)
  );
  const prompts = ["What should I do first?", "Who do I contact about the failed checks?"];
  if (failed[0]) prompts.unshift(`Why did “${failed[0]}” fail?`);
  const missing = (health.policies || []).some((policy) =>
    (policy.results || []).some((item) => item.status === "missinginfo")
  );
  if (missing) prompts.push("What information is still missing?");
  return prompts.slice(0, 4);
}

function setProjectHash(projectId) {
  location.hash = projectId ? `#/project/${encodeURIComponent(projectId)}` : "#/project";
}

function renderProject() {
  const workspace = state.workspace;
  if (!workspace) {
    return `<section class="workbench-empty"><p class="muted">No project workspace found.</p></section>`;
  }
  const health = state.health || workspace.health || {};
  return `
    <div class="workbench">
      ${renderProjectLeft(workspace, health)}
      <section class="wb-center">
        ${renderEditorTabs()}
        <div class="wb-editor">${renderEditorBody()}</div>
        ${renderProblemsBar(health)}
        ${renderStatusBar(workspace, health)}
      </section>
      ${renderChatPane(workspace, health)}
    </div>`;
}

function renderProjectLeft(workspace, health) {
  const projects = workspace.workspaces || [];
  const options = projects
    .map(
      (item) =>
        `<md-select-option value="${escAttr(item.id)}" ${item.id === workspace.id ? "selected" : ""}><div slot="headline">${esc(item.name)}</div></md-select-option>`
    )
    .join("");
  const policies = health.policies || [];
  const policyRows = policies
    .map((policy) => {
      const failed = policy.failed || 0;
      return `<button type="button" class="policy-preview ${failed ? "has-fail" : "ok"}" data-open-policy="${escAttr(policy.policy_id)}">
        <span>${esc(policy.domain || policy.title)}</span>
        <span class="badge ${failed ? "fail" : "pass"}">${failed} failed</span>
      </button>`;
    })
    .join("");
  const next = nextActions(health)
    .map(
      (item) =>
        `<button type="button" class="next-item" data-ask="${escAttr(item.prompt)}">
          <span class="badge fail">${esc(item.domain)}</span>
          <span>${esc(item.label)}</span>
        </button>`
    )
    .join("");
  const answers = closedAnswers(health)
    .map(
      (item) =>
        `<li class="${item.ok ? "ok" : "fail"}"><code>${esc(item.key)}</code> ${esc(item.value)} <span class="muted">${item.ok ? "accepted" : "not accepted"}</span></li>`
    )
    .join("");
  return `
    <aside class="wb-left">
      <div class="wb-pane">
        <p class="wb-kicker">Project</p>
        <md-outlined-select id="project-switcher" label="Workspace">${options}</md-outlined-select>
        <p class="wb-owner">${esc(workspace.owner || "Project owner")}${workspace.owner_email ? `<br /><a href="mailto:${escAttr(workspace.owner_email)}">${esc(workspace.owner_email)}</a>` : ""}</p>
        <p class="muted wb-desc">${esc(workspace.description || "")}</p>
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">Latest compliance check</p>
        <p class="muted">Last validated ${esc(formatWhen(health.validated_at))}</p>
        <div class="policy-preview-list">${policyRows || "<p class='muted'>No policies in scope.</p>"}</div>
        <md-filled-tonal-button id="recheck-btn" ${state.busy ? "disabled" : ""}>
          <md-icon slot="icon">health_and_safety</md-icon>
          Check compliance
        </md-filled-tonal-button>
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">Explorer</p>
        <button type="button" class="file-row pinned ${state.activeTab === "health" ? "active" : ""}" data-tab="health">
          <span class="pin">📌</span> Compliance health
        </button>
        ${renderFileTree(workspace.tree || [])}
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">External connections</p>
        ${(workspace.connections || [])
          .map(
            (item) =>
              `<button type="button" class="conn-row ${statusClass(item.status)}" data-ask="${escAttr(`What should I do about ${item.name}?`)}">
                <span class="badge ${statusClass(item.status)}">${esc(item.kind)}</span>
                <span><strong>${esc(item.name)}</strong><br /><span class="muted">${esc(item.detail || "")}</span></span>
              </button>`
          )
          .join("")}
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">Next up</p>
        ${next || "<p class='muted'>No remediations queued.</p>"}
      </div>
      <div class="wb-pane">
        <p class="wb-kicker">Closed answers</p>
        <ul class="answer-preview">${answers || "<li class='muted'>No answers recorded.</li>"}</ul>
      </div>
    </aside>`;
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
  const byLine = {};
  for (const finding of file.findings || []) {
    byLine[finding.line] = byLine[finding.line] || [];
    byLine[finding.line].push(finding);
  }
  const rows = lines
    .map((line, index) => {
      const ln = index + 1;
      const hits = byLine[ln] || [];
      const cls = hits.length ? `finding ${hits[0].status}` : "";
      const label = hits.map((item) => item.label || item.statement_id).join(" · ");
      const open = hits[0]
        ? `<button type="button" class="inline-open" data-open-stmt="${escAttr(hits[0].statement_id)}">${esc(label)}</button>`
        : "";
      return `<div class="code-line ${cls}"><span class="ln">${ln}</span><code>${esc(line) || " "}</code>${open}</div>`;
    })
    .join("");
  return `<div class="file-viewer">
    <div class="file-meta"><strong>${esc(file.path)}</strong> <span class="muted">${esc(file.language)}</span></div>
    <div class="code-wrap">${rows}</div>
  </div>`;
}

function renderProblemsBar(health) {
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

function renderStatusBar(workspace, health) {
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

function renderChatPane(workspace, health) {
  const messages = (state.chat || [])
    .map((item) => `<article class="chat-msg ${item.role}"><p>${formatChat(item.content)}</p></article>`)
    .join("");
  const last = [...(state.chat || [])].reverse().find((item) => item.role === "assistant");
  const prompts = (last?.prompts || defaultProjectPrompts(health))
    .map((prompt) => `<md-assist-chip label="${escAttr(prompt)}" data-ask="${escAttr(prompt)}"></md-assist-chip>`)
    .join("");
  const context = state.activeTab.startsWith("file:")
    ? `Looking at ${state.activeTab.slice(5)}`
    : "Looking at Compliance health";
  return `
    <aside class="wb-chat">
      <header>
        <strong>Compliance guide</strong>
        <p class="muted">${esc(context)} · ${(health.failed || 0)} failed</p>
      </header>
      <div class="chat-log" id="chat-log">${messages}</div>
      <div class="chat-prompts">${prompts}</div>
      ${state.chatError ? `<div class="banner error">${esc(state.chatError)}</div>` : ""}
      <form id="chat-form" class="chat-form">
        <md-outlined-text-field id="chat-input" type="textarea" rows="3" label="Ask the guide" ${state.chatBusy ? "disabled" : ""}></md-outlined-text-field>
        <md-filled-button type="submit" ${state.chatBusy ? "disabled" : ""}>${state.chatBusy ? "Thinking…" : "Send"}</md-filled-button>
      </form>
    </aside>`;
}

function formatChat(text) {
  return esc(text)
    .replaceAll("\n", "<br />")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function nextActions(health) {
  const items = [];
  for (const policy of health.policies || []) {
    for (const result of policy.results || []) {
      if (result.status !== "fail") continue;
      items.push({
        domain: policy.domain,
        label: result.remediation?.actions?.[0] || result.description,
        prompt: `How do I fix: ${result.description}?`,
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
  document.querySelectorAll("[data-ask]").forEach((button) => {
    button.addEventListener("click", () => sendChat(button.dataset.ask));
  });
  document.getElementById("chat-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("chat-input");
    const text = input?.value.trim();
    if (text) sendChat(text);
  });
  const log = document.getElementById("chat-log");
  if (log) log.scrollTop = log.scrollHeight;
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
    const bundle = await api(`/api/projects/${encodeURIComponent(state.workspaceId)}/check`, {
      method: "POST",
      body: "{}",
    });
    state.workspace = bundle;
    state.health = bundle.health;
    state.notice = "Compliance re-checked against current project answers.";
    toast(state.notice);
    state.chat = [
      ...state.chat,
      {
        role: "assistant",
        content: `Health check refreshed at ${formatWhen(bundle.health?.validated_at)}. ${bundle.health?.failed || 0} failed, ${bundle.health?.passed || 0} passed.`,
        prompts: defaultProjectPrompts(bundle.health),
      },
    ];
  } catch (err) {
    state.error = err.message;
  } finally {
    state.busy = false;
    render();
  }
}

async function sendChat(text) {
  const content = String(text || "").trim();
  if (!content || state.chatBusy) return;
  state.chat.push({ role: "user", content });
  state.chatBusy = true;
  state.chatError = "";
  showProgress(true);
  render();
  const input = document.getElementById("chat-input");
  if (input) input.value = "";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(state.workspaceId)}/chat`, {
      method: "POST",
      body: JSON.stringify({
        messages: state.chat.map((item) => ({ role: item.role, content: item.content })),
        active_file: state.activeTab.startsWith("file:") ? state.activeTab.slice(5) : "",
        focus_policy_id: state.focusPolicyId,
      }),
    });
    state.chat.push({
      role: "assistant",
      content: payload.reply || "I could not build a reply.",
      prompts: payload.suggested_prompts || [],
    });
  } catch (err) {
    state.chatError = err.message;
  } finally {
    state.chatBusy = false;
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
  boot();
}

start();
