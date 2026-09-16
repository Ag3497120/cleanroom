const $ = (id) => document.getElementById(id);
const kinds = ["SELF_REPORTED", "EXPLAINED", "APPLIED", "TRANSFERRED"];
const words = {
  ja: {
    skip: "本文へ", navMap: "経験の地図", navTrail: "記録の流れ", navBookmarks: "次のしおり",
    notAReportCard: "成績表ではなく、あなたのノート。",
    railNote: "何を作り、どう考えたか。自分に必要な経験だけ、少しずつ残していく。",
    local: "このMacの中だけ", readOnly: "読み取り専用", language: "表示言語", refresh: "更新",
    chapter: "PERSONAL NOTEBOOK / 経験の積み重ね", title: "できたことに、続きを。",
    intro: "自分の言葉で説明したこと。実際に使ったこと。別の場面へ持ち出したこと。その足跡を、プロジェクトを越えて見渡します。",
    edition: "自分のペースで", recordCount: "本人が残した記録", techCount: "つながった技術", projectCount: "記録のあるプロジェクト名",
    countNote: "件数は記録の数です。能力、学習時間、独力での実装を表す数値ではありません。",
    find: "記録を探す", searchPlaceholder: "技術、経験、自分の言葉から",
    technology: "技術", allTechnologies: "すべての技術", kind: "残した経験", allKinds: "すべての経験",
    project: "プロジェクト", allProjects: "すべてのプロジェクト", apply: "絞り込む", clear: "解除",
    mapHeading: "経験の地図", mapHint: "技術の付いた点を選ぶと、その記録へ。縦は技術、横は記録した月です。",
    readAsList: "一覧で読む", emptyTitle: "ここから、あなたの足跡に。",
    emptyBody: "自分の説明や使った場面を残すと、この地図に並びます。空白は、能力がないという意味ではありません。",
    noMatch: "この条件に合う記録はありません。条件を解除して、ほかの足跡も見られます。",
    noDates: "日付のある記録はまだありません。日付を推測せず、下の一覧に表示します。",
    trailEyebrow: "YOUR WORDS", trailTitle: "記録の流れ", more: "もう少し前の記録",
    bookmarkEyebrow: "AT YOUR PACE", bookmarkTitle: "次のしおり",
    bookmarkNote: "本人が「取り組みたい」「次の機会に」と選んだ項目だけ。期限も、全部を埋める義務もありません。",
    shelfTitle: "任せることも、自分の選択", aiDrafts: "AIが残した手順の下書き",
    reference: "参照できればよいと選んだもの", delegate: "任せると選んだもの",
    shelfNote: "この棚は個人ノート全体の件数です。AIの手順を、本人の習得に数えません。委譲の選択で実行権限は増えません。",
    footer: "My Atlas / 記録は手元に。判断はあなたに。", detailEyebrow: "FROM YOUR NOTEBOOK",
    close: "閉じる", detailBoundary: "本人が残した経験の記録です。AIによる採点や、能力の認定ではありません。",
    SELF_REPORTED: "自分で残した経験", EXPLAINED: "自分の言葉で説明", APPLIED: "実際に使った", TRANSFERRED: "別の場面で使った",
    WANT: "取り組みたい", NEXT_TIME: "次の機会に", REFERENCE: "必要なときに参照", DELEGATE: "任せておく",
    UNSELECTED: "まだ選んでいない", NOT_NEEDED: "今は必要ない",
    DRAFT: "手順の下書き", REVIEW_REQUIRED: "手順を見直す", RETIRED: "今は使わない",
    noBookmarks: "必要になったとき、My skillsで選んでおけます。今は仕事を進めるだけでも構いません。",
    moreBookmarks: "件のしおりがあります。全体はCLIのMy skillsで開けます。",
    general: "技術の指定なし", noDate: "日付の記録なし", noProject: "個人の記録",
    updatedRecord: "この記録の更新日", ownerEntry: "本人の記録日", readAt: "表示データの取得",
    recordsUnit: "件", filterAll: "個人ノートの経験を表示しています。",
    filterMonth: "選んだ月", graphLimit: "地図は最大12技術・18か月。検索や一覧で範囲を変えられます。",
    graphOlder: "表示より前の記録も一覧に残っています。",
    graphMulti: "複数の技術を付けた同じ記録は、複数の行に現れることがあります。",
    optionsLimit: "技術・プロジェクトの候補は各256件まで表示します。それ以外は文章検索で探せます。",
    loading: "ノートを開いています。", loadError: "ノートを読み込めませんでした。ターミナルの表示を確認してから、更新してください。",
    linkNeeded: "ターミナルに表示された、この起動専用のURLから開いてください。",
    expired: "この画面の接続が切れています。起動中のターミナルに表示されたURLを開き直してください。",
    notebookPaused: "個人ノートへの自動収録は停止中です。保存済みの記録はそのまま読めます。",
    ownWords: "本人が残した言葉", noOwnWords: "この項目には、本人の文章はまだ添えていません。",
    procedure: "関連するAIの手順", procedureNote: "AIが提案した下書きです。本人の経験や、実行済みの証拠とは別です。",
    purpose: "用途", inputs: "入力", outputs: "出力", steps: "手順案", applicable_when: "使う条件",
    stop_when: "立ち止まる条件", verification_methods: "確認方法の案", human_decisions: "人間に残す判断の案",
    source_event_ids: "出典イベント", provenance: "来歴", sourceRun: "作業ID", sourceRef: "元の記録",
    model: "整理モデル", definitionHash: "手順の版ハッシュ", privacy: "AIへの個人共有",
    shareOn: "この項目は共有を選択済み。全体の共有設定も必要です。",
    shareOff: "この項目の個人共有は選択されていません。",
    cliTitle: "記録を続ける", cliNote: "このWeb画面からは書き換えません。ターミナルのMy skillsで、必要な項目だけ選べます。",
    historyNote: "地図は現在の経験記録を表示します。以前の選択・説明はCLIのHistoryへ。",
    copy: "コマンドをコピー", copied: "コピーしました", copyFailed: "コピーできませんでした。表示されたコマンドを選択できます。",
    graphLabel: "技術ごと、記録した月ごとの経験。技術の付いた点を選択できます。",
  },
  en: {
    skip: "Skip to content", navMap: "Experience map", navTrail: "Notebook trail", navBookmarks: "Next bookmarks",
    notAReportCard: "Your notebook. Not a report card.",
    railNote: "What you made. How you thought. Keep the experiences that matter to you, a little at a time.",
    local: "Only on this computer", readOnly: "Read-only", language: "Language", refresh: "Refresh",
    chapter: "PERSONAL NOTEBOOK / EXPERIENCE OVER TIME", title: "Give your experience a next chapter.",
    intro: "What you explained in your own words. What you used. What you carried into another situation. See those traces across your projects.",
    edition: "At your own pace", recordCount: "Records you left", techCount: "Connected technologies", projectCount: "Recorded project names",
    countNote: "These are record counts. They do not measure ability, study time, or unaided implementation.",
    find: "Find a record", searchPlaceholder: "A technology, experience, or your own words",
    technology: "Technology", allTechnologies: "All technologies", kind: "Experience", allKinds: "All experiences",
    project: "Project", allProjects: "All projects", apply: "Filter", clear: "Clear",
    mapHeading: "Experience map", mapHint: "Choose a technology-tagged point to read its records. Technology runs down, recorded month runs across.",
    readAsList: "Read as a list", emptyTitle: "A place for your own traces.",
    emptyBody: "Leave your explanation or a situation where you used something, and it appears here. Empty space says nothing about your ability.",
    noMatch: "No records match these filters. Clear them to see your other traces.",
    noDates: "These records have no recorded date. Read them below; no dates have been guessed.",
    trailEyebrow: "YOUR WORDS", trailTitle: "Notebook trail", more: "Earlier records",
    bookmarkEyebrow: "AT YOUR PACE", bookmarkTitle: "Next bookmarks",
    bookmarkNote: "Only what you chose to explore or revisit. No deadlines and no requirement to fill every space.",
    shelfTitle: "Delegating is a choice, too", aiDrafts: "AI procedure drafts",
    reference: "Chosen as a reference", delegate: "Chosen for delegation",
    shelfNote: "This shelf counts your entire personal notebook. AI procedures are not your acquired skills. Delegation does not grant tool permissions.",
    footer: "My Atlas / Your records. Your judgment.", detailEyebrow: "FROM YOUR NOTEBOOK",
    close: "Close", detailBoundary: "An experience recorded by its owner. Not an AI score or a certification of ability.",
    SELF_REPORTED: "Experience you recorded", EXPLAINED: "Explained in your words", APPLIED: "Used in practice", TRANSFERRED: "Used in another setting",
    WANT: "Want to explore", NEXT_TIME: "Next opportunity", REFERENCE: "Keep as a reference", DELEGATE: "Leave to automation",
    UNSELECTED: "No choice yet", NOT_NEEDED: "Not needed now",
    DRAFT: "Procedure draft", REVIEW_REQUIRED: "Revisit this procedure", RETIRED: "Not in use",
    noBookmarks: "Choose a bookmark in My skills when it becomes useful. For now, simply continuing your work is enough.",
    moreBookmarks: "bookmarks in total. Open My skills in the CLI for the full board.",
    general: "No technology tag", noDate: "No date recorded", noProject: "Personal record",
    updatedRecord: "Record updated", ownerEntry: "Owner entry date", readAt: "Data read",
    recordsUnit: "records", filterAll: "Showing experiences in your personal notebook.",
    filterMonth: "Selected month", graphLimit: "The map shows up to 12 technologies and 18 months. Use search or the list for other records.",
    graphOlder: "Earlier records remain available in the list.",
    graphMulti: "One record with several technology tags can appear on more than one row.",
    optionsLimit: "The selectors show up to 256 technologies and project names each. Use text search for others.",
    loading: "Opening your notebook.", loadError: "The notebook could not be loaded. Check the terminal, then refresh.",
    linkNeeded: "Open the private URL printed by the running CLI.",
    expired: "This connection is no longer available. Reopen the URL printed by the running CLI.",
    notebookPaused: "Automatic capture into the personal notebook is paused. Saved records remain readable.",
    ownWords: "Your words", noOwnWords: "You have not attached your own words to this item.",
    procedure: "Related AI procedure", procedureNote: "A proposal from AI. Separate from your experience and from execution evidence.",
    purpose: "Purpose", inputs: "Inputs", outputs: "Outputs", steps: "Proposed steps", applicable_when: "When to use",
    stop_when: "When to pause", verification_methods: "Suggested checks", human_decisions: "Suggested owner decisions",
    source_event_ids: "Source events", provenance: "Provenance", sourceRun: "Work ID", sourceRef: "Source record",
    model: "Reflection model", definitionHash: "Procedure version hash", privacy: "Personal sharing with AI",
    shareOn: "Sharing is selected for this item. The global sharing setting must also be enabled.",
    shareOff: "Personal sharing has not been selected for this item.",
    cliTitle: "Continue your record", cliNote: "This web view does not edit anything. Choose what matters to you in My skills in the terminal.",
    historyNote: "The map shows current experience records. Earlier choices and explanations are in CLI History.",
    copy: "Copy command", copied: "Copied", copyFailed: "Could not copy. You can select the displayed command.",
    graphLabel: "Experience by technology and recorded month. Technology-tagged points are selectable.",
  },
};
Object.assign(words.ja, {
  unpackNav: "紐解きノート", unpackTitle: "自分に必要な分だけ、紐解く。",
  unpackIntro: "要約から詳しい解説、実装中に残した元の記録まで。読む粒度を変えても、元の記録はそのままです。",
  unpackCommand: "新しい解説はCLIのUnpackから。", moreGuides: "以前の解説",
  guideDepth: "読む粒度", guideSummary: "要約", guideFull: "詳しい解説", guideSources: "元の作業記録",
  noGuides: "今、全部を学ぶ必要はありません。知りたくなったスキルや技術を選ぶと、その作業の記録から解説を残せます。",
  guideBoundary: "AIの解説候補です。本人の習得記録や実行証拠とは別で、読むだけでは状態を変更しません。",
  guideCoverage: "元資料の範囲", guidePart: "ページ", guidePending: "解説は未完了です。元の記録は保持しています。",
  startingPoint: "今回の出発点", recordedBasis: "記録に基づく説明", addedBasis: "後から補った解説",
  whyThisWork: "この仕事とのつながり", exercise: "小さく試すなら", check: "自分で確かめる問い",
  nextSmallStep: "次の小さな一歩", nextOpportunity: "次の機会に", gaps: "記録からは分からないこと",
  sourceReferences: "参照した記録", canDelegate: "参照や委譲でもよいこと",
  optionalResources: "必要なときの本・資料", resourceBoundary: "検索結果を元にした候補です。書籍本文・版・章構成・適合性を確認済みという意味ではありません。",
  suggestedFocus: "読むときの観点", suggestedSearches: "次に探すなら", searchUnrequested: "今回はWeb検索を行っていません。",
});
Object.assign(words.en, {
  unpackNav: "Unpacking notes", unpackTitle: "Unpack only what matters to you.",
  unpackIntro: "A summary, a detailed explanation, or the original implementation records. Changing the view never replaces the source.",
  unpackCommand: "Create a new guide through Unpack in the CLI.", moreGuides: "Earlier guides",
  guideDepth: "Reading depth", guideSummary: "Summary", guideFull: "Full explanation", guideSources: "Original work records",
  noGuides: "You do not need to learn everything now. When a skill or technology interests you, build a guide from its actual work records.",
  guideBoundary: "An AI explanation proposal, separate from your experience and execution evidence. Reading never changes your status.",
  guideCoverage: "Source coverage", guidePart: "page", guidePending: "The explanation is unfinished. Original records are retained.",
  startingPoint: "Your starting point", recordedBasis: "Explanation based on records", addedBasis: "Additional explanation",
  whyThisWork: "Why it matters in this work", exercise: "A small practice", check: "A way to check for yourself",
  nextSmallStep: "One small next step", nextOpportunity: "Another opportunity", gaps: "What the records do not establish",
  sourceReferences: "Source references", canDelegate: "What can remain a reference or be delegated",
  optionalResources: "Optional books and resources", resourceBoundary: "Candidates based on search results. Book contents, editions, chapter structure, and suitability have not been verified.",
  suggestedFocus: "A useful focus", suggestedSearches: "Possible next searches", searchUnrequested: "No web search was made for this guide.",
});
let currentGuide = null;
let guideItems = [];
let guideListSequence = 0;
Object.assign(words.ja, {connectionsTitle:"経験と手順のつながり", connectionsIntro:"AIの手順・作業中の説明・本人の言葉を区別します。つながりは習得率ではありません。", openObsidian:"Obsidianでノートを開く", connectionsSetup:"最初からObsidianで始める設定も選べます。", ownerNode:"本人の言葉",skillNode:"AIの手順",workNode:"作業中の説明",technologyNode:"記録にある技術", graphEmpty:"まだつながりの記録がありません。能力不足を意味しません。"});
Object.assign(words.en, {connectionsTitle:"Experience, procedures, connections", connectionsIntro:"Your words, AI procedures and implementation notes stay distinct. Connections are not mastery scores.", openObsidian:"Open the notebook in Obsidian", connectionsSetup:"You can also start with an Obsidian-first notebook.", ownerNode:"Your words",skillNode:"AI procedure",workNode:"During work",technologyNode:"Recorded technology",graphEmpty:"No connections recorded yet. This does not imply a lack of ability."});
let locale = document.documentElement.lang === "en" ? "en" : "ja";
let localeChosen = false;
let snapshot = null;
let entries = [];
let selectedMonth = "";
let controller = null;
let requestSequence = 0;
let detailSequence = 0;
let currentDetail = null;
let currentFilters = { search: "", technology: "", kind: "", project: "", month: "" };
let token = "";
try {
  const fragment = new URLSearchParams(location.hash.slice(1));
  token = fragment.get("token") || sessionStorage.getItem("cleanroom.atlas.token") || "";
  if (fragment.has("token")) {
    sessionStorage.setItem("cleanroom.atlas.token", token);
    history.replaceState(null, "", location.pathname + location.search);
  }
} catch {
  token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
  history.replaceState(null, "", location.pathname + location.search);
}
const t = (key) => words[locale][key] || key;
const number = (value) => Number(value || 0).toLocaleString(locale);
const node = (tag, className, text) => {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = String(text);
  return result;
};
const dateText = (value, monthOnly = false) => {
  if (!value) return t("noDate");
  const date = new Date(value.length === 7 ? value + "-01T12:00:00Z" : value.slice(0, 10) + "T12:00:00Z");
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, {
    year: "numeric", month: "short", ...(monthOnly ? {} : { day: "numeric" }), timeZone: "UTC",
  }).format(date);
};
function notice(text) {
  $("notice").textContent = text;
  $("notice").hidden = !text;
}
function translate() {
  document.documentElement.lang = locale;
  document.title = "Cleanroom / My Atlas";
  $("locale").value = locale;
  document.querySelectorAll("[data-i18n]").forEach((item) => { item.textContent = t(item.dataset.i18n); });
  document.querySelectorAll("[data-placeholder]").forEach((item) => { item.placeholder = t(item.dataset.placeholder); });
  const selected = $("kind").value;
  $("kind").replaceChildren(node("option", "", t("allKinds")));
  $("kind").firstChild.value = "";
  for (const kind of kinds) {
    const option = node("option", "", t(kind));
    option.value = kind;
    $("kind").append(option);
  }
  $("kind").value = selected;
  $("legend").replaceChildren();
  for (const kind of kinds) {
    const label = node("span", "legend-item");
    const glyph = node("span", "glyph " + kind);
    glyph.setAttribute("aria-hidden", "true");
    label.append(glyph, node("span", "", t(kind)));
    $("legend").append(label);
  }
}
async function api(path, signal) {
  if (!token) throw new Error("linkNeeded");
  let response;
  try {
    response = await fetch(path, {
      headers: { Authorization: "Bearer " + token }, cache: "no-store",
      credentials: "omit", referrerPolicy: "no-referrer", signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("loadError");
  }
  if (response.status === 401 || response.status === 403) throw new Error("expired");
  if (!response.ok) throw new Error("loadError");
  return response.json();
}
function fillSelect(id, values, emptyLabel, selected) {
  const target = $(id);
  target.replaceChildren(node("option", "", emptyLabel));
  target.firstChild.value = "";
  const choices = [...values];
  if (selected && !choices.includes(selected)) choices.unshift(selected);
  for (const value of choices) {
    const option = node("option", "", value);
    option.value = value;
    target.append(option);
  }
  target.value = selected;
}
function restoreFilters() {
  $("search").value = currentFilters.search;
  $("technology").value = currentFilters.technology;
  $("kind").value = currentFilters.kind;
  $("project").value = currentFilters.project;
}
function render() {
  if (!snapshot) return;
  const data = snapshot;
  $("record-count").textContent = number(data.summary.records);
  $("tech-count").textContent = number(data.summary.technologies);
  $("project-count").textContent = number(data.summary.project_names);
  $("draft-count").textContent = number(data.summary.AI_procedure_drafts);
  $("reference-count").textContent = number(data.summary.reference_choices);
  $("delegate-count").textContent = number(data.summary.delegation_choices);
  fillSelect("technology", data.options.technologies, t("allTechnologies"), currentFilters.technology);
  fillSelect("project", data.options.projects, t("allProjects"), currentFilters.project);
  restoreFilters();
  $("active-filter").textContent = selectedMonth
    ? t("filterMonth") + ": " + dateText(selectedMonth, true) : t("filterAll");
  $("trail-count").textContent = number(data.summary.records) + " " + t("recordsUnit");
  $("updated").textContent = t("readAt") + ": " + dateText(data.read_at);
  $("more").hidden = !data.has_more;
  const hints = [t("graphLimit"), t("graphMulti"), t("historyNote")];
  if (data.graph.older_months_present) hints.push(t("graphOlder"));
  if (data.options.omitted_technologies || data.options.omitted_projects) hints.push(t("optionsLimit"));
  $("chart-limit").textContent = hints.join(" ");
  renderGraph(data.graph);
  renderEntries();
  renderBookmarks(data.bookmarks);
  renderGuides(data.learning_guides || { items: [], has_more: false });
  renderConnections(data.connections || { nodes: [], edges: [], obsidian_url: null });
  $("bookmark-more").textContent = data.bookmark_total > data.bookmarks.length
    ? number(data.bookmark_total) + " " + t("moreBookmarks") : "";
  if (!data.personal_notebook_enabled) notice(t("notebookPaused"));
}
function svg(tag, attrs = {}, text) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = text;
  return element;
}
function renderGraph(graph) {
  const container = $("chart");
  container.replaceChildren();
  const empty = !graph.cells.length || !graph.months.length || !graph.technologies.length;
  $("empty").hidden = !empty;
  $("map-range").textContent = graph.months.length
    ? dateText(graph.months[0], true) + " / " + dateText(graph.months.at(-1), true) : "";
  if (empty) {
    const body = $("empty").querySelector("[data-i18n='emptyBody']");
    if (body) body.textContent = snapshot.summary.records > 0 ? t("noDates")
      : snapshot.summary.all_records > 0 ? t("noMatch") : t("emptyBody");
    return;
  }
  const left = 180;
  const width = Math.max(780, left + graph.months.length * 58);
  const height = 72 + graph.technologies.length * 64;
  const right = width - 42;
  const xFor = (index) => graph.months.length === 1 ? (left + right) / 2
    : left + (right - left) * index / (graph.months.length - 1);
  const drawing = svg("svg", { viewBox: "0 0 " + width + " " + height, role: "group", "aria-label": t("graphLabel") });
  const labelEvery = graph.months.length > 12 ? 3 : graph.months.length > 6 ? 2 : 1;
  graph.months.forEach((month, index) => {
    const x = xFor(index);
    drawing.append(svg("line", { x1: x, x2: x, y1: 35, y2: height - 20, class: "chart-rule" }));
    if (index % labelEvery === 0 || index === graph.months.length - 1) {
      drawing.append(svg("text", { x, y: 19, "text-anchor": "middle", class: "chart-time" }, month));
    }
  });
  graph.technologies.forEach((technology, index) => {
    const y = 62 + index * 64;
    drawing.append(svg("line", { x1: left - 16, x2: right + 20, y1: y, y2: y, class: "chart-row" }));
    const name = technology || t("general");
    const label = svg("text", { x: 12, y: y + 4, class: "chart-label" }, [...name].length > 17 ? [...name].slice(0, 16).join("") + "..." : name);
    label.append(svg("title", {}, name));
    drawing.append(label);
  });
  const offsets = [[-9, -9], [9, -9], [-9, 9], [9, 9]];
  graph.cells.forEach((cell) => {
    const row = graph.technologies.indexOf(cell.technology);
    const column = graph.months.indexOf(cell.month);
    const kindIndex = kinds.indexOf(cell.kind);
    if (row < 0 || column < 0 || kindIndex < 0) return;
    const [dx, dy] = offsets[kindIndex];
    const x = xFor(column) + dx;
    const y = 62 + row * 64 + dy;
    const label = (cell.technology || t("general")) + " / " + dateText(cell.month, true)
      + " / " + t(cell.kind) + " / " + number(cell.count) + " " + t("recordsUnit");
    const point = svg("g", { class: "chart-point " + cell.kind, tabindex: 0, role: "button", "aria-label": label });
    point.append(svg("title", {}, label));
    if (cell.kind === "EXPLAINED") {
      point.append(svg("rect", { x: x - 7, y: y - 7, width: 14, height: 14, rx: 2, class: "dot" }));
    } else if (cell.kind === "APPLIED") {
      point.append(svg("path", { d: "M " + x + " " + (y - 8) + " L " + (x + 8) + " " + y + " L " + x + " " + (y + 8) + " L " + (x - 8) + " " + y + " Z", class: "dot" }));
    } else {
      point.append(svg("circle", { cx: x, cy: y, r: 7, class: "dot" }));
    }
    if (cell.count > 1) point.append(svg("text", { x, y: y + 3, "text-anchor": "middle", class: "dot-count", "pointer-events": "none" }, cell.count > 9 ? "+" : cell.count));
    const choose = () => {
      selectedMonth = cell.month;
      currentFilters = { ...currentFilters, month: cell.month, kind: cell.kind, technology: cell.technology };
      loadPage(false).then(() => $("trail").scrollIntoView({ block: "start", behavior: "auto" }));
    };
    if (cell.technology) {
      point.addEventListener("click", choose);
      point.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); }
      });
    } else {
      point.setAttribute("role", "img");
      point.removeAttribute("tabindex");
    }
    drawing.append(point);
  });
  container.append(drawing);
}
function renderEntries() {
  $("entries").replaceChildren();
  for (const entry of entries) {
    const article = node("article", "entry");
    const time = node("time", "", dateText(entry.date));
    if (entry.date) time.dateTime = entry.date;
    time.title = entry.date_basis === "RECORD_UPDATED" ? t("updatedRecord") : t("ownerEntry");
    const body = node("div", "entry-body");
    const button = node("button", "entry-title", entry.title);
    button.type = "button";
    button.addEventListener("click", () => openEntry(entry));
    const meta = node("div", "entry-meta");
    meta.append(node("span", "entry-kind " + entry.kind, t(entry.kind)),
      node("span", "", (entry.technologies || []).join(" / ") || t("general")),
      node("span", "", entry.project || t("noProject")));
    body.append(button);
    if (entry.excerpt) body.append(node("p", "entry-excerpt", entry.excerpt));
    body.append(meta);
    article.append(time, body);
    $("entries").append(article);
  }
}
function renderBookmarks(bookmarks) {
  $("bookmark-list").replaceChildren();
  if (!bookmarks.length) {
    $("bookmark-list").append(node("p", "muted", t("noBookmarks")));
    return;
  }
  for (const item of bookmarks) {
    const box = node("article", "bookmark");
    const button = node("button", "entry-title", item.title);
    button.type = "button";
    button.addEventListener("click", () => openEntry(item));
    box.append(node("span", "small-cap blue", t(item.plan)), button);
    if (item.technologies.length) box.append(node("p", "muted", item.technologies.join(" / ")));
    $("bookmark-list").append(box);
  }
}
async function loadPage(append) {
  controller?.abort();
  controller = new AbortController();
  const sequence = ++requestSequence;
  notice(t("loading"));
  $("refresh").disabled = true;
  $("more").disabled = true;
  const query = new URLSearchParams({ ...currentFilters, offset: String(append ? entries.length : 0), limit: "24" });
  try {
    const data = await api("/api/atlas?" + query, controller.signal);
    if (sequence !== requestSequence) return;
    if (!localeChosen) {
      locale = data.locale === "en" ? "en" : "ja";
      translate();
    }
    snapshot = data;
    entries = append ? [...entries, ...data.entries] : data.entries;
    notice("");
    render();
  } catch (error) {
    if (sequence === requestSequence && error.name !== "AbortError") notice(t(error.message in words[locale] ? error.message : "loadError"));
  } finally {
    if (sequence === requestSequence) {
      $("refresh").disabled = false;
      $("more").disabled = false;
    }
  }
}
function detailSection(title, value, isList = false) {
  if (value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length)) return;
  $("detail-body").append(node("h3", "detail-label", title));
  if (isList && Array.isArray(value)) {
    const list = node("ul", "detail-note");
    value.forEach((item) => list.append(node("li", "", typeof item === "string" ? item : JSON.stringify(item))));
    $("detail-body").append(list);
  } else {
    $("detail-body").append(node("p", "detail-note", typeof value === "string" ? value : JSON.stringify(value)));
  }
}
function renderDetail(data) {
  $("detail-title").textContent = data.title;
  $("detail-meta").textContent = [
    data.kind ? t(data.kind) : data.plan ? t(data.plan) : "",
    (data.technologies || []).join(" / "), data.project || t("noProject"),
    data.date ? (data.date_basis === "RECORD_UPDATED" ? t("updatedRecord") : t("ownerEntry")) + ": " + dateText(data.date) : "",
  ].filter(Boolean).join(" · ");
  $("detail-body").replaceChildren();
  detailSection(t("ownWords"), data.text || t("noOwnWords"));
  if (data.plan) detailSection(t("bookmarkTitle"), t(data.plan));
  if (typeof data.share_with_ai === "boolean") detailSection(t("privacy"), t(data.share_with_ai ? "shareOn" : "shareOff"));
  if (data.procedure) {
    detailSection(t("procedure"), t("procedureNote"));
    const procedure = data.procedure;
    for (const name of ["purpose", "inputs", "outputs", "steps", "applicable_when", "stop_when", "verification_methods", "human_decisions", "source_event_ids"]) {
      detailSection(t(name), procedure[name], Array.isArray(procedure[name]));
    }
  }
  if (data.provenance) {
    const labels = { project_name: "project", run_id: "sourceRun", source_ref: "sourceRef", model: "model", definition_sha256: "definitionHash" };
    for (const [key, label] of Object.entries(labels)) detailSection(t(label), data.provenance[key]);
  }
  if (data.skill_id) {
    detailSection(t("cliTitle"), t("cliNote"));
    const command = "verantyx my-skills";
    $("detail-body").append(node("pre", "copy-command", command));
    const copy = node("button", "quiet-button", t("copy"));
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(command); copy.textContent = t("copied"); }
      catch { copy.textContent = t("copyFailed"); }
    });
    $("detail-body").append(copy);
  }
}
async function openEntry(entry) {
  currentGuide = null;
  $("guide-controls").hidden = true;
  document.querySelector("#detail [data-i18n='detailBoundary']").textContent = t("detailBoundary");
  const sequence = ++detailSequence;
  currentDetail = null;
  $("detail-title").textContent = entry.title;
  $("detail-meta").textContent = "";
  $("detail-body").replaceChildren(node("p", "detail-note", t("loading")));
  if (!$("detail").open) $("detail").showModal();
  const params = new URLSearchParams({ id: entry.record_id });
  if (entry.observation !== null && entry.observation !== undefined) params.set("observation", String(entry.observation));
  try {
    const data = await api("/api/entry?" + params);
    if (sequence !== detailSequence || !$("detail").open) return;
    currentDetail = data;
    renderDetail(data);
  } catch (error) {
    if (sequence === detailSequence) $("detail-body").replaceChildren(node("p", "detail-note", t(error.message in words[locale] ? error.message : "loadError")));
  }
}
function renderGuides(data, append = false) {
  if (!append) ++guideListSequence;
  guideItems = append ? [...guideItems, ...data.items] : data.items;
  $("guides").replaceChildren();
  $("more-guides").hidden = !data.has_more;
  if (!guideItems.length) $("guides").append(node("p", "muted", t("noGuides")));
  for (const item of guideItems) {
    const box = node("article", "entry");
    const time = node("time", "", dateText(item.created_at));
    const body = node("div", "entry-body");
    const title = node("button", "entry-title", item.title);
    title.type = "button";
    title.addEventListener("click", () => openGuide(item.id, "summary"));
    body.append(title, node("p", "entry-meta", [
      item.target.technology || "", t("guideCoverage") + ": " + String(item.coverage.page + 1)
        + "/" + String(item.coverage.pages), item.status === "PROPOSED" ? "" : t("guidePending"),
    ].filter(Boolean).join(" · ")));
    box.append(time, body);
    $("guides").append(box);
  }
}
function renderGuide(data) {
  $("guide-controls").hidden = false;
  $("guide-depth").value = data.detail;
  $("detail-title").textContent = data.title;
  $("detail-meta").textContent = dateText(data.created_at) + " / " + t("guideCoverage") + ": "
    + String(data.coverage.page + 1) + "/" + String(data.coverage.pages) + " " + t("guidePart")
    + " / " + data.coverage.events + " " + t("recordsUnit");
  document.querySelector("#detail [data-i18n='detailBoundary']").textContent = t("guideBoundary");
  $("detail-body").replaceChildren();
  if (data.status !== "PROPOSED") $("detail-body").append(node("p", "detail-note", t("guidePending")));
  if (data.detail === "sources") {
    $("detail-body").append(node("pre", "source-record", JSON.stringify({
      events: data.source_events, profile_snapshot_history: data.profile_snapshot_history,
      rejected_notes: data.rejected_notes,
    }, null, 2)));
    return;
  }
  if (data.detail === "summary") {
    detailSection(t("guideSummary"), data.summary);
    detailSection(t("nextOpportunity"), data.next_opportunity);
    detailSection(t("gaps"), data.gaps, true);
    return;
  }
  const guideDocument = data.document;
  if (!guideDocument) return;
  detailSection(t("startingPoint"), guideDocument.starting_point);
  for (const part of guideDocument.parts) {
    $("detail-body").append(node("h3", "detail-label", part.title),
      node("span", "small-cap", t(part.basis === "RECORDED" ? "recordedBasis" : "addedBasis")),
      node("p", "detail-note", part.explanation));
    for (const [key, label] of [["why_for_this_work", "whyThisWork"], ["exercise", "exercise"],
      ["check", "check"], ["next_small_step", "nextSmallStep"]]) detailSection(t(label), part[key]);
    detailSection(t("sourceReferences"), part.source_event_ids, true);
  }
  detailSection(t("canDelegate"), guideDocument.can_delegate.map((item) => item.text), true);
  detailSection(t("nextOpportunity"), guideDocument.next_opportunity);
  detailSection(t("gaps"), guideDocument.gaps, true);
  if (guideDocument.resources.length) {
    detailSection(t("optionalResources"), t("resourceBoundary"));
    for (const recommendation of guideDocument.resources) {
      const resource = data.resources.results.find((item) => item.id === recommendation.resource_id);
      if (!resource) continue;
      let url;
      try { url = new URL(resource.url); } catch { continue; }
      if (url.protocol !== "https:" || url.username || url.password) continue;
      const link = node("a", "resource-link", resource.title);
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      $("detail-body").append(link, node("p", "detail-note", recommendation.why));
      detailSection(t("suggestedFocus"), recommendation.suggested_focus);
      $("detail-body").append(node("p", "footnote", resource.provider + " / " + dateText(resource.retrieved_at)));
    }
  } else if (data.resources.status === "NOT_REQUESTED") {
    $("detail-body").append(node("p", "footnote", t("searchUnrequested")));
  }
  detailSection(t("suggestedSearches"), guideDocument.suggested_searches, true);
}
async function openGuide(identity, detail) {
  const sequence = ++detailSequence;
  currentDetail = null;
  currentGuide = { id: identity, data: null };
  $("guide-controls").hidden = false;
  $("guide-depth").value = detail;
  $("detail-title").textContent = t("unpackNav");
  $("detail-meta").textContent = "";
  document.querySelector("#detail [data-i18n='detailBoundary']").textContent = t("guideBoundary");
  $("detail-body").replaceChildren(node("p", "detail-note", t("loading")));
  if (!$("detail").open) $("detail").showModal();
  try {
    const data = await api("/api/guide?" + new URLSearchParams({ id: identity, detail }));
    if (sequence !== detailSequence || !$("detail").open) return;
    currentGuide = { id: identity, data };
    renderGuide(data);
  } catch (error) {
    if (sequence === detailSequence) $("detail-body").replaceChildren(
      node("p", "detail-note", t(error.message in words[locale] ? error.message : "loadError")));
  }
}
$("guide-depth").addEventListener("change", () => {
  if (currentGuide) openGuide(currentGuide.id, $("guide-depth").value);
});
$("more-guides").addEventListener("click", async () => {
  const sequence = guideListSequence;
  $("more-guides").disabled = true;
  try {
    const data = await api("/api/guides?offset=" + guideItems.length);
    if (sequence === guideListSequence) renderGuides(data, true);
  } catch { notice(t("loadError")); }
  finally { $("more-guides").disabled = false; }
});

$("filters").addEventListener("submit", (event) => {
  event.preventDefault();
  selectedMonth = "";
  currentFilters = {
    search: $("search").value.trim(), technology: $("technology").value,
    kind: $("kind").value, project: $("project").value, month: "",
  };
  loadPage(false);
});
$("clear").addEventListener("click", () => {
  selectedMonth = "";
  currentFilters = { search: "", technology: "", kind: "", project: "", month: "" };
  loadPage(false);
});
$("locale").addEventListener("change", () => {
  localeChosen = true;
  locale = $("locale").value === "en" ? "en" : "ja";
  translate();
  notice("");
  render();
  if (currentDetail && $("detail").open) renderDetail(currentDetail);
  if (currentGuide?.data && $("detail").open) renderGuide(currentGuide.data);
});
$("refresh").addEventListener("click", () => loadPage(false));
$("more").addEventListener("click", () => loadPage(true));
$("close-detail").addEventListener("click", () => $("detail").close());
$("detail").addEventListener("close", () => { ++detailSequence; currentDetail = null; currentGuide = null; });
translate();
loadPage(false);


function renderConnections(data) {
  const root = $("connections-graph"), list = $("connections-list");
  root.replaceChildren(); list.replaceChildren();
  const vault = $("obsidian-open");
  vault.hidden = !data.obsidian_url;
  if (data.obsidian_url?.startsWith("obsidian://open?")) vault.href = data.obsidian_url;
  if (!data.nodes.length) { root.append(node("p", "empty", t("graphEmpty"))); return; }
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const height = Math.max(200, Math.ceil(data.nodes.length / 6) * 80 + 50);
  svg.setAttribute("viewBox", "0 0 900 " + height);
  svg.setAttribute("role", "img"); svg.setAttribute("aria-label", t("connectionsIntro"));
  const positions = new Map(data.nodes.map((item, index) =>
    [item.id, {x:75 + (index % 6) * 150, y:40 + Math.floor(index / 6) * 80}]));
  for (const edge of data.edges) {
    const a = positions.get(edge.source), b = positions.get(edge.target);
    if (!a || !b) continue;
    const line = document.createElementNS(ns, "line");
    for (const [name, value] of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y})) line.setAttribute(name, value);
    svg.append(line);
  }
  for (const item of data.nodes) {
    const p = positions.get(item.id), circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", p.x); circle.setAttribute("cy", p.y);
    circle.setAttribute("r", item.kind === "owner" ? 9 : 6); circle.setAttribute("class", item.kind);
    const title = document.createElementNS(ns, "title"); title.textContent = t(item.kind + "Node") + ": " + item.label;
    circle.append(title); svg.append(circle);
    const label = document.createElementNS(ns, "text");
    label.setAttribute("x", p.x); label.setAttribute("y", p.y + 24); label.setAttribute("text-anchor", "middle");
    label.textContent = item.label.length > 18 ? item.label.slice(0, 18) + "…" : item.label; svg.append(label);
    const row = node("div", "connection-link");
    row.append(node("span", "", t(item.kind + "Node") + " / " + item.label));
    if (item.obsidian_url?.startsWith("obsidian://open?")) {
      const link = node("a", "", "Obsidian"); link.href = item.obsidian_url; row.append(link);
    }
    list.append(row);
  }
  root.append(svg);
}
