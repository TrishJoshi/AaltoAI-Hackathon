const DEMO_KEY = "poliview.demo";
const TOUR_KEY = "poliview.tour";
const DEMO_REVIEW_ORDER = ["gdpr", "eu-ai-act"];
const DEMO_REVIEW_IDS = new Set(DEMO_REVIEW_ORDER);
const STARTER_PROJECT_ID = "growthboard";
const DEMO_ONLY_PROJECT_IDS = new Set(["campus-pilot"]);
const DEMO_PROJECT_IDS = new Set(["growthboard", "campus-pilot"]);

const POLICY_LLM_IN = `Domain: GDPR
Source section: International transfers

Personal data of EU persons must not be
transferred to a third country unless the
destination is the EU, the EEA, or a country
with an adequacy decision. US hosting without
an approved transfer tool is not permitted.

Return JSON matching the PolicyDocument schema.`;

const POLICY_LLM_OUT = `{
  "id": "stmt_transfers",
  "description": "Personal data of EU persons
    may only be stored in the EU, the EEA,
    or an adequate country.",
  "keys": [{
    "id": "data_residency",
    "question": "Where is personal data stored
      in production?",
    "value_enum": ["EU","EEA","adequacy","US","other",""],
    "accepted": ["EU", "EEA", "adequacy"]
  }]
}`;

const PROJECT_LLM_IN = `Project metadata:
  RDS in us-east-1. CRM names and emails.
  Event logs kept indefinitely. No RoPA row.
  Lead-scoring model with no named reviewer.

Keys to fill (enum only — no pass list):
  data_residency: [EU, EEA, adequacy, US, other, ""]
  retention_policy: [defined, indefinite, ""]
  human_oversight: [yes, no, not_applicable, ""]`;

const PROJECT_LLM_OUT = `{
  "answers": {
    "data_residency": "US",
    "retention_policy": "indefinite",
    "human_oversight": "no",
    "ropa_recorded": ""
  },
  "unmapped": []
}`;

let tourIndex = -1;
let tourBound = false;
let placing = false;

function tourEsc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function demoEnabled() {
  const raw = localStorage.getItem(DEMO_KEY);
  if (raw === null) return true;
  return raw === "1";
}

function tourCompleted() {
  return localStorage.getItem(TOUR_KEY) === "done";
}

function filterDemoReviews(reviews) {
  const list = reviews || [];
  if (demoEnabled()) {
    return DEMO_REVIEW_ORDER.map((id) => list.find((item) => item.id === id)).filter(Boolean);
  }
  return list.filter((item) => !DEMO_REVIEW_IDS.has(item.id));
}

function filterDemoProjects(projects) {
  const list = projects || [];
  if (demoEnabled()) {
    return ["growthboard", "campus-pilot"]
      .map((id) => list.find((item) => item.id === id))
      .filter(Boolean);
  }
  return list.filter((item) => item.id === STARTER_PROJECT_ID || !DEMO_PROJECT_IDS.has(item.id));
}

function filterDemoHealth(runs) {
  if (demoEnabled()) return runs;
  return (runs || []).filter(
    (item) => item.kind !== "demo" && !DEMO_ONLY_PROJECT_IDS.has(item.id)
  );
}

function isDemoReview(id) {
  return DEMO_REVIEW_IDS.has(id);
}

function isDemoProject(id) {
  return DEMO_ONLY_PROJECT_IDS.has(id);
}

function syncDemoSwitch() {
  const sw = document.getElementById("demo-switch");
  const on = demoEnabled();
  document.body.dataset.demo = on ? "on" : "off";
  if (sw && sw.selected !== on) sw.selected = on;
}

function pipelinePolicyHtml() {
  return `
    <p>A DPO or AI Act officer loads the law once. Code splits articles. An agent drafts closed questions. A human marks them covered. That JSON is reused for every product — not a chatbot reread of GDPR or the AI Act.</p>
    <ol class="pipe-flow">
      <li>
        <span class="pipe-badge code">Code · no LLM</span>
        <strong>Split the regulation into sections</strong>
        <p class="muted">Headings become review units. GDPR international transfers is one article; EU AI Act human oversight is another. The model never sees the whole statute as a prompt.</p>
      </li>
      <li>
        <span class="pipe-badge llm">LLM · Policy Agent</span>
        <strong>Draft closed checks as JSON</strong>
        <p class="muted">Each section returns a statement, a question, allowed values, and which values count as a pass. The agent never scores a project.</p>
      </li>
      <li>
        <span class="pipe-badge human">Human · final say</span>
        <strong>Validate once, reuse for every team</strong>
        <p class="muted">Edit the question or the pass list, then mark the article covered. The law does not change every sprint; every new shipment still has to match it.</p>
      </li>
    </ol>
    <div class="io-grid">
      <article class="io-card">
        <h3>What the agent reads</h3>
        <pre>${tourEsc(POLICY_LLM_IN)}</pre>
      </article>
      <article class="io-card">
        <h3>What it returns</h3>
        <pre>${tourEsc(POLICY_LLM_OUT)}</pre>
      </article>
    </div>`;
}

function pipelineProjectHtml() {
  return `
    <p>Owners keep hosting, processor, and model notes in the workspace. A parser fills enums. Code — not the model — returns pass, fail, or missing info. Same answers always produce the same result.</p>
    <ol class="pipe-flow">
      <li>
        <span class="pipe-badge code">Code · no LLM</span>
        <strong>Build a questionnaire from the closed policy</strong>
        <p class="muted">Pass lists stay off this payload. The parser only sees allowed values for GDPR residency, retention, and AI Act oversight.</p>
      </li>
      <li>
        <span class="pipe-badge llm">LLM · Project Parser</span>
        <strong>Fill enums from the workspace</strong>
        <p class="muted">GrowthBoard files say RDS is in <code>us-east-1</code> and lead scoring has no reviewer. The parser picks <code>US</code> and <code>no</code>. It must not invent a verdict.</p>
      </li>
      <li>
        <span class="pipe-badge code">Code · comparator</span>
        <strong>Deterministic verdict</strong>
        <p class="muted"><code>US</code> is a legal answer, but GDPR accepted values are only <code>EU</code> / <code>EEA</code> / <code>adequacy</code> → <strong>fail</strong>. Empty → missing info. Repeatable without a meeting.</p>
      </li>
    </ol>
    <div class="io-grid">
      <article class="io-card">
        <h3>What the parser reads</h3>
        <pre>${tourEsc(PROJECT_LLM_IN)}</pre>
      </article>
      <article class="io-card">
        <h3>What it returns</h3>
        <pre>${tourEsc(PROJECT_LLM_OUT)}</pre>
      </article>
    </div>`;
}

function finishHtml() {
  return `
    <p>The walkthrough is done. Seeded GDPR and EU AI Act cards hide so you can load your own Markdown. <strong>GrowthBoard stays</strong> — README, architecture, processors, and hosting are already filled. The generated answers file is cleared until you check.</p>
    <p class="muted">Open <strong>Project owner → Workspace</strong> and click <strong>Check compliance</strong>. That fills the project schema from those files and the sample GDPR / EU AI Act keys. Turn <strong>Demo</strong> back on to restore the full pitch. The account icon replays this guide.</p>`;
}

const STEPS = [
  {
    id: "roles",
    route: "#/",
    target: '[data-tour="roles"]',
    kicker: "Step 1 · Two roles",
    title: "Governance writes the checks. Teams ship against them.",
    body: `<p><strong>Governance</strong> is a DPO or AI Act officer: load GDPR or the EU AI Act, close the questions, keep final say. <strong>Project owner</strong> is the product team: Workspace and Health show pass, fail, or missing info — with why, what to do, and who to contact — without a meeting.</p>
      <p class="muted">The model never picks the verdict. A deterministic comparator does.</p>`,
  },
  {
    id: "library",
    route: "#/",
    target: '[data-tour="library"]',
    kicker: "Step 2 · Governance",
    title: "Load a regulation once. Reuse it for every product.",
    body: `<p>Upload the text once — here, sliced GDPR articles as Markdown. An agent drafts closed questions; you validate. That JSON is the source of truth every shipment is measured against. The law does not change every sprint; every new product still has to match it.</p>`,
  },
  {
    id: "policies",
    route: "#/",
    target: '[data-tour="demo-policies"]',
    kicker: "Step 3 · Two EU standards",
    title: "GDPR for personal data. EU AI Act for the model.",
    body: `<p><strong>GDPR</strong> covers transfers, lawful basis, processor agreements, retention, and the record of processing. <strong>EU AI Act</strong> covers risk class, human oversight, logging, and a model card. One product is scored against both — no second policy reread.</p>`,
  },
  {
    id: "section",
    route: "#/reviews/gdpr?sid=sec_international_transfers",
    target: '[data-tour="source-text"]',
    kicker: "Step 4 · Source of truth",
    title: "Read the article. The closed keys sit on the right.",
    body: `<p>The GDPR text is the document. Click <strong>International transfers</strong>: accepted answers are <code>EU</code>, <code>EEA</code>, or <code>adequacy</code> — not <code>US</code>. Projects are measured against that JSON, not the paragraph.</p>`,
  },
  {
    id: "pipeline-policy",
    route: "#/reviews/gdpr?sid=sec_international_transfers",
    wide: true,
    kicker: "Step 5 · How a regulation becomes policy",
    title: "Parse in code. Draft with an agent. You keep final say.",
    html: pipelinePolicyHtml,
  },
  {
    id: "final-say",
    route: "#/reviews/gdpr?sid=sec_international_transfers",
    target: '[data-tour="final-say"]',
    kicker: "Step 6 · Final say",
    title: "Nothing is law until a human covers it",
    body: `<p>Change the question, the enum, or the pass list. <strong>Mark as covered</strong> when the check matches the article. Until then this is a draft — Generate policies is not a verdict.</p>`,
  },
  {
    id: "workspace",
    route: "#/project/growthboard",
    target: '[data-tour="workspace"]',
    kicker: "Step 7 · Project owner",
    title: "GrowthBoard fails both standards — on purpose",
    body: `<p>Hosting in <code>us-east-1</code> is a GDPR transfer of EU CRM data. Logs are kept indefinitely. A lead-scoring model ranks contacts with no named reviewer and no model card — EU AI Act gaps. Switch to <strong>Campus Pilot</strong> for the missing-info contrast: region not documented.</p>`,
  },
  {
    id: "pipeline-project",
    route: "#/project/growthboard",
    wide: true,
    kicker: "Step 8 · Why this is not another chatbot",
    title: "Parser fills enums. The algorithm judges.",
    html: pipelineProjectHtml,
  },
  {
    id: "health",
    route: "#/project/growthboard",
    target: '[data-tour="finding"]',
    open: true,
    kicker: "Step 9 · Act without a meeting",
    title: "Fail, why, next step, who to contact",
    body: `<p><strong>GDPR:</strong> transfers fail because the answer is <code>US</code>; accepted is only <code>EU</code> / <code>EEA</code> / <code>adequacy</code>. Contact the DPO. <strong>EU AI Act:</strong> lead scoring is high-risk with no human in the loop and no model card. Contact the AI Act officer.</p>
      <p class="muted">Same answers, same result every time — unless governance changes the closed checks.</p>`,
  },
  {
    id: "check-compliance",
    route: "#/project/growthboard",
    target: '[data-tour="check-compliance"]',
    kicker: "Step 10 · Try it yourself",
    title: "Check compliance against the sample policy",
    body: `<p>Four project files stay in this workspace — README, architecture, processors, and hosting. They are the metadata the parser reads. The generated answers file is not kept after the guide.</p>
      <p>After this guide, click <strong>Check compliance</strong>. That fills the project schema from those files and the keys GDPR and the EU AI Act require. The comparator — not the model — picks pass, fail, or missing info.</p>`,
  },
  {
    id: "account",
    route: "#/",
    target: '[data-tour="account"]',
    kicker: "Step 11 · Your library",
    title: "Hide the pitch. Keep the workspace.",
    html: finishHtml,
    nextLabel: "Try Check compliance",
  },
];

function bindTourChrome() {
  if (tourBound) return;
  tourBound = true;
  document.getElementById("demo-switch")?.addEventListener("change", (event) => {
    applyDemoMode(Boolean(event.target.selected), { restartTour: false });
  });
  document.getElementById("account-button")?.addEventListener("click", () => {
    startTour();
  });
  document.getElementById("tour-skip")?.addEventListener("click", () => skipTour());
  document.getElementById("tour-back")?.addEventListener("click", () => goTour(-1));
  document.getElementById("tour-next")?.addEventListener("click", () => goTour(1));
  window.addEventListener("resize", () => {
    if (tourIndex >= 0) placeTour();
  });
  window.addEventListener("poliview:render", () => {
    if (tourIndex >= 0) requestAnimationFrame(() => placeTour());
  });
  syncDemoSwitch();
}

async function applyDemoMode(on, { restartTour } = {}) {
  localStorage.setItem(DEMO_KEY, on ? "1" : "0");
  syncDemoSwitch();
  if (!on) window.PoliviewApp?.onDemoOff?.();
  if (!on && tourIndex >= 0) hideTour();
  const hash = location.hash || "#/";
  const onHiddenDemoRoute =
    hash.includes("/reviews/gdpr") ||
    hash.includes("/reviews/eu-ai-act") ||
    hash.includes("/project/campus-pilot") ||
    hash.includes("demo_compliance");
  if (!on && onHiddenDemoRoute) {
    location.hash = "#/project/growthboard";
    toast("Campus Pilot and seeded GDPR / EU AI Act reviews are hidden. GrowthBoard stays — click Check compliance to fill the project schema.");
    return;
  }
  await boot();
  if (restartTour && on) {
    await startTour();
    return;
  }
  toast(
    on
      ? "Demo restored: GDPR, EU AI Act, GrowthBoard, and Campus Pilot. Account icon replays the walkthrough."
      : "Seeded GDPR and EU AI Act reviews are hidden. GrowthBoard keeps the starter files — click Check compliance to fill the project schema."
  );
}

function hideTour() {
  tourIndex = -1;
  const root = document.getElementById("tour-root");
  if (root) root.hidden = true;
  document.body.classList.remove("touring");
}

function skipTour() {
  localStorage.setItem(TOUR_KEY, "done");
  hideTour();
  toast("Walkthrough skipped. Demo fixtures stay until you turn Demo off.");
}

async function startTour() {
  if (!demoEnabled()) {
    localStorage.setItem(DEMO_KEY, "1");
    syncDemoSwitch();
    if (!location.hash || location.hash === "#/") await boot();
    else location.hash = "#/";
    await waitRender();
  }
  tourIndex = 0;
  document.body.classList.add("touring");
  const root = document.getElementById("tour-root");
  if (root) root.hidden = false;
  await showStep(0);
}

async function goTour(delta) {
  if (tourIndex < 0) return;
  const next = tourIndex + delta;
  if (next < 0) return;
  if (next >= STEPS.length) {
    await finishTour();
    return;
  }
  tourIndex = next;
  await showStep(next);
}

async function finishTour() {
  localStorage.setItem(TOUR_KEY, "done");
  hideTour();
  await applyDemoMode(false);
  if (!location.hash.includes("/project/growthboard")) {
    location.hash = "#/project/growthboard";
  }
}

async function showStep(index) {
  const step = STEPS[index];
  if (!step) return;
  if (step.route && normalizeHash(location.hash) !== normalizeHash(step.route)) {
    location.hash = step.route;
    await waitRender();
  }
  const title = document.getElementById("tour-title");
  const kicker = document.getElementById("tour-kicker");
  const body = document.getElementById("tour-body");
  const progress = document.getElementById("tour-progress");
  const nextBtn = document.getElementById("tour-next");
  const backBtn = document.getElementById("tour-back");
  const card = document.getElementById("tour-card");
  if (title) title.textContent = step.title;
  if (kicker) kicker.textContent = step.kicker;
  if (body) body.innerHTML = typeof step.html === "function" ? step.html() : step.body || "";
  if (progress) progress.textContent = `${index + 1} / ${STEPS.length}`;
  if (nextBtn) nextBtn.textContent = step.nextLabel || (index === STEPS.length - 1 ? "Use my own data" : "Next");
  if (backBtn) backBtn.disabled = index === 0;
  card?.classList.toggle("wide", Boolean(step.wide));
  await waitForTarget(step.target);
  if (step.open) openTourTarget(step.target);
  await waitFrame();
  placeTour();
}

function normalizeHash(hash) {
  const value = String(hash || "#/");
  return value.startsWith("#") ? value : `#${value}`;
}

function openTourTarget(selector) {
  if (!selector) return;
  document.querySelectorAll(selector).forEach((node) => {
    if (node instanceof HTMLDetailsElement) node.open = true;
    node.closest?.("details") && (node.closest("details").open = true);
  });
}

async function waitForTarget(selector, timeout = 2200) {
  if (!selector) return null;
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const node = document.querySelector(selector);
    if (node) {
      const rect = node.getBoundingClientRect();
      if (rect.width > 4 && rect.height > 4) return node;
    }
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
  return document.querySelector(selector);
}

function placeTour() {
  if (placing || tourIndex < 0) return;
  placing = true;
  try {
    const step = STEPS[tourIndex];
    const card = document.getElementById("tour-card");
    const spot = document.getElementById("tour-spot");
    if (!card || !spot || !step) return;
    const target = step.target ? document.querySelector(step.target) : null;
    if (target) {
      target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
    }
    requestAnimationFrame(() => {
      const node = step.target ? document.querySelector(step.target) : null;
      layoutTour(card, spot, node, Boolean(step.wide));
    });
  } finally {
    placing = false;
  }
}

function layoutTour(card, spot, target, wide) {
  const pad = 10;
  const root = document.getElementById("tour-root");
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const cardW = wide ? Math.min(720, vw - 24) : Math.min(400, vw - 24);
  card.style.width = `${cardW}px`;
  card.style.maxWidth = `${vw - 24}px`;
  const cardHGuess = card.offsetHeight || 280;
  if (!target || wide || cardHGuess > vh * 0.5) {
    spot.hidden = true;
    root?.classList.add("no-spot");
    card.classList.add("centered");
    card.style.left = "";
    card.style.top = "";
    card.style.transform = "";
    return;
  }
  root?.classList.remove("no-spot");
  card.classList.remove("centered");
  card.style.transform = "none";
  spot.hidden = false;
  const rect = target.getBoundingClientRect();
  const cardH = Math.min(card.offsetHeight || 280, vh - 24);
  const spotLeft = Math.max(pad, rect.left - pad);
  const spotW = Math.min(rect.width + pad * 2, vw - spotLeft - pad);
  let spotTop = Math.max(pad, rect.top - pad);
  let spotH = Math.min(rect.height + pad * 2, Math.round(vh * 0.3), vh - spotTop - pad);
  let left = Math.min(Math.max(12, rect.left), vw - cardW - 12);
  let top = spotTop + spotH + 12;
  if (top + cardH > vh - 12) {
    top = Math.max(12, vh - cardH - 16);
    left = Math.max(12, (vw - cardW) / 2);
    if (top > 72) {
      spotH = Math.max(40, Math.min(spotH, top - spotTop - 12));
    } else {
      spotTop = Math.max(pad, Math.min(spotTop, 56));
      spotH = Math.max(36, Math.min(spotH, 72));
    }
  }
  spot.style.top = `${spotTop}px`;
  spot.style.left = `${spotLeft}px`;
  spot.style.width = `${Math.max(48, spotW)}px`;
  spot.style.height = `${Math.max(36, spotH)}px`;
  if (left + cardW > vw - 12) left = Math.max(12, vw - cardW - 12);
  if (left < 12) left = 12;
  card.style.left = `${left}px`;
  card.style.top = `${top}px`;
}

function waitRender() {
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      window.removeEventListener("poliview:render", onRender);
      requestAnimationFrame(() => requestAnimationFrame(resolve));
    };
    const onRender = () => done();
    window.addEventListener("poliview:render", onRender);
    setTimeout(done, 900);
  });
}

function waitFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

function onAppReady() {
  bindTourChrome();
  if (!tourCompleted() && demoEnabled()) {
    setTimeout(() => startTour(), 450);
  }
}

window.PoliviewDemo = {
  enabled: demoEnabled,
  filterReviews: filterDemoReviews,
  filterProjects: filterDemoProjects,
  filterHealth: filterDemoHealth,
  isReview: isDemoReview,
  isProject: isDemoProject,
  sync: syncDemoSwitch,
};

window.PoliviewTour = {
  start: startTour,
  onAppReady,
};
