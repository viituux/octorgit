"use strict";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {job: null, data: null, page: "overview", document: "README.md", history: [], busy: false, endpointPage: 0};
const pageNames = {github: "Conexão GitHub",overview: "Visão geral", endpoints: "Endpoints", architecture: "Arquitetura", documents: "Documentação", history: "Histórico salvo", coverage: "Relatório de cobertura", compare: "Comparar versões", report: "Relatório visual", settings: "Administração de IA"};
const descriptions = {github: "Conecte sua conta e escolha repositórios públicos ou privados com acesso permitido.",overview: "Transforme um repositório Python em um mapa que você pode verificar.", endpoints: "Do método à view, com as referências que sustentam cada descoberta.", architecture: "Linguagens, bancos e infraestrutura identificados com evidências.", documents: "Consulte, confira e exporte o conhecimento extraído do repositório.", history: "Retome snapshots e evidências salvos no seu computador.", coverage: "Veja o que foi lido, filtrado e permaneceu desconhecido.", compare: "Rotas, configurações e documentos que precisam de revisão.", report: "Compartilhe explicações e diagramas em um documento independente.", settings: "Escolha seu provedor, modelo, endereço de API e chave para esta sessão."};
const confidenceNames = {extracted: "Extraído", inferred: "Inferido", unconfirmed: "Não confirmado"};
const gaps = {auxiliary_file_excluded_from_endpoints: "Arquivo de teste, exemplo ou documentação excluído da análise de endpoints",default_router_api_root_and_format_suffix_not_enumerated: "API root e sufixos de formato do DefaultRouter não enumerados", include_module_not_found: "Módulo de URLs não encontrado no snapshot", view_symbol_not_resolved: "Não foi possível resolver o símbolo da view", custom_lookup_not_supported: "Lookup personalizado ainda não suportado", nested_regex_not_supported: "Montagem de regex aninhado não suportada", regex_include_not_supported: "Include com regex não suportado", include_cycle_or_depth_limit: "Include cíclico ou limite de profundidade atingido", dynamic_urlpatterns_not_supported: "urlpatterns construído de forma dinâmica", dynamic_route_not_supported: "Declaração dinâmica de rota não suportada", relative_import_outside_package: "Import relativo fora do pacote selecionado", root_urlconf_module_not_found: "Módulo raiz de URLs não encontrado", multiple_root_urlconfs_select_explicitly: "Várias raízes de URLs encontradas; selecione uma nas opções", python_parse_failed: "Arquivo incompatível com o parser Python", custom_action_not_supported: "Configuração de ação personalizada não suportada", dynamic_include_not_supported: "Include dinâmico não suportado", custom_dispatch_not_supported: "Dispatch personalizado exige análise adicional", viewset_base_not_supported: "Base do ViewSet não reconhecida", as_view_overrides_not_supported: "Opções de as_view ainda não suportadas"};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function message(text) { $("#message").textContent = text || ""; $("#message").hidden = !text; }
function pill(text, kind = "neutral") { return element("span", `pill ${kind}`, text); }
function methodBadge(method) { return element("span", `method method-${(method || "unknown").toLowerCase()}`, method || "?"); }
function sourceRef(ref) {
  const label = `${ref.file}:${ref.start_line}${ref.end_line !== ref.start_line ? `–${ref.end_line}` : ""}`;
  const repo = state.data?.analysis.repository;
  if (repo?.url && /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(repo.url) && /^[a-f0-9]{40}$/.test(repo.commit_sha || "")) {
    const a = element("a", "source-link", label);
    a.href = `${repo.url}/blob/${repo.commit_sha}/${ref.file.split("/").map(encodeURIComponent).join("/")}#L${ref.start_line}-L${ref.end_line}`;
    a.target = "_blank"; a.rel = "noopener noreferrer";
    return a;
  }
  return element("code", "", label);
}
async function api(path, payload) {
  const options = payload === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "X-OctorGit-Token": $("meta[name=octorgit-token]").content}, body: JSON.stringify(payload)};
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error("Não foi possível conectar ao aplicativo. Confira se a janela do OctorGit continua aberta."); }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Não foi possível concluir a operação.");
  return data;
}
function page(name) {
  state.page = name;
  $$(".page-panel").forEach(panel => panel.hidden = panel.id !== `page-${name}`);
  $$(".nav-item").forEach(button => { const current = button.dataset.page === name; button.classList.toggle("active", current); if (current) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current"); });
  $("#breadcrumb-page").textContent = pageNames[name];
  $("#page-title").replaceChildren();
  if (name === "overview" && !state.data) { $("#page-title").textContent = "Conheça seu repositório."; }
  else $("#page-title").textContent = pageNames[name];
  $("#page-description").textContent = descriptions[name];
  $("#analysis-form-card").hidden = name !== "overview" || Boolean(state.data);
  $("#new-analysis").hidden = !state.data && name === "overview";
  document.body.dataset.page = name;
  if (name === "history") loadHistory();
  if (name === "settings") loadAIUsage();
  if (name === "github") loadGitHub();
}
function setBusy(busy) {
  state.busy = busy;
  ["#analyze-button", "#demo-button", "#welcome-demo", "#demo-next-button"].forEach(id => $(id).disabled = busy);
  $("#analyze-button").textContent = busy ? "Analisando…" : "Analisar repositório ↗";
  $("#new-analysis").disabled = busy;
  $("#top-new-analysis").disabled = busy;
  ["#save-ai-settings", "#test-ai-settings", "#clear-ai-key"].forEach(id => $(id).disabled = busy);
  if (state.aiConfigured !== undefined) $("#use-ai").disabled = busy || !state.aiConfigured;
}
function progress(job) {
  $("#progress-card").hidden = false;
  $("#progress-title").textContent = job.stage;
  $("#progress-repo").textContent = job.label;
  $("#progress-value").textContent = `${job.progress}%`;
  $("#analysis-progress").value = job.progress;
  $("#analysis-progress").textContent = `${job.progress}%`;
}
async function poll(job) {
  const id = job.id;
  while (true) {
    progress(job);
    if (job.status === "completed") { await openResult(id); break; }
    if (job.status === "failed") { $("#progress-card").hidden = true; throw new Error(job.error || "A análise não pôde ser concluída."); }
    await new Promise(resolve => setTimeout(resolve, 650));
    job = await api(`/api/jobs/${id}`);
  }
}
async function start(source) {
  if (state.busy) return;
  message(""); setBusy(true);
  const payload = source.startsWith("demo") ? {source} : {source: "github", repo: $("#repository").value.trim(), branch: $("#branch").value.trim(), root_urlconf: $("#root-urlconf").value.trim()};
  payload.use_ai = $("#use-ai").checked;
  payload.private_ai_consent = $("#private-ai-consent").checked;
  try {
    const job = await api("/api/jobs", payload);
    state.job = job.id;
    try { sessionStorage.setItem("octorgit-job", job.id); } catch {}
    await loadHistory();
    await poll(job);
  } catch (error) { message(error.message); $("#progress-card").hidden = true; }
  finally { setBusy(false); await loadHistory(); await loadAIUsage(); }
}
async function openResult(id) {
  const data = await api(`/api/jobs/${id}/result`);
  state.job = id; state.data = data; state.document = data.ai?.status === "completed" ? "AI.md" : "README.md";
  $$("[data-document]").forEach(tab => tab.setAttribute("aria-selected", String(tab.dataset.document === state.document)));
  state.endpointPage = 0; state.componentId = null;
  $("#endpoint-detail").hidden = true; $("#architecture-detail").hidden = true; state.baseId = data.previous_id;
  try { sessionStorage.setItem("octorgit-job", id); } catch {}
  $("#progress-card").hidden = true;
  $("#endpoint-search").value = ""; $("#method-filter").value = ""; $("#confidence-filter").value = "";
  message(""); renderResult(); page("overview");
}
function renderResult() {
  const ir = state.data.analysis;
  if (state.data.storage_error) message(state.data.storage_error);
  const repo = ir.repository;
  $("#context-repo").textContent = repo.url?.split("/").slice(-2).join("/") || "Exemplo integrado";
  $("#context-branch").textContent = repo.branch || "Fixture local";
  $("#open-export").disabled = false;
  renderDiscoveryBoard();
  $("#project-stack").textContent = (ir.technology?.languages || []).map(l => l.name).slice(0,3).join(" / ") || "Inventário";
  const ai = state.data.ai;
  const notice = $("#ai-result-notice");
  notice.hidden = !ai || ai.status === "disabled";
  notice.classList.toggle("failed", ai?.status === "failed");
  if (ai?.status === "completed") notice.textContent = `IA · ${ai.provider} · ${ai.model} · ${ai.cache_hit ? "Cache local · sem nova chamada ou consumo de tokens" : `${ai.usage.totalTokenCount ?? "?"} tokens informados na geração`}. Consulte o Resumo com IA em Documentação. As referências foram verificadas; as explicações continuam sendo inferências.`;
  else if (ai?.status === "failed") notice.textContent = `A análise estática foi concluída, mas a IA não gerou o documento: ${ai.error}`;
  $("#welcome").hidden = true; $("#overview-results").hidden = false; $("#repository-bar").hidden = false;
  $("#repository-name").textContent = repo.url ? repo.url.replace("https://github.com/", "") : "Exemplo integrado · Django/DRF";
  $("#repository-meta").textContent = repo.commit_sha ? `${repo.private ? "Privado · " : ""}${repo.branch || "ref"} · commit ${repo.commit_sha.slice(0, 12)}` : "Fixture local · sem commit SHA · dados de demonstração";
  $("#download-all").href = `/api/jobs/${state.job}/download`;
  $("#stat-files").textContent = ir.files.length;
  $("#stat-files-detail").textContent = `${ir.metrics.python_files_parsed} Python analisados · ${ir.metrics.skipped_files} excluídos`;
  $("#stat-symbols").textContent = ir.symbols.length;
  $("#stat-endpoints").textContent = ir.endpoints.length;
  $("#stat-endpoints-detail").textContent = `${ir.endpoints.filter(e => e.method).length} com método identificado`;
  $("#stat-gaps").textContent = ir.diagnostics.length;
  $("#nav-endpoints").textContent = ir.endpoints.length;
  $("#project-summary").replaceChildren(element("p", "", `${ir.files.length} arquivos aceitos e ${ir.symbols.length} símbolos compõem este snapshot. O parser encontrou ${ir.endpoints.length} registros de rotas e métodos.`));
  const summary = [["Raiz de URLs", ir.routing.roots.join(", ") || "Não identificada"], ["Cobertura entre Python aceitos", ir.metrics.parsing_coverage === null ? "Não aplicável" : `${Math.round(ir.metrics.parsing_coverage * 100)}%`], ["Relações de import locais", String(ir.relations.length)]];
  summary.forEach(([label, value]) => { const row = element("div", "summary-metric"); row.append(element("span", "", label), element("strong", "", value)); $("#project-summary").append(row); });
  $("#confidence-summary").replaceChildren();
  Object.entries(confidenceNames).forEach(([key, label]) => { const count = ir.endpoints.filter(e => e.confidence === key).length; const row = element("div", "confidence-row"); row.append(pill(label, key === "extracted" ? "success" : key), element("span", "small-muted", key === "extracted" ? "Declaração explícita" : key === "inferred" ? "Convenção de framework" : "Método não identificado"), element("strong", "", count)); $("#confidence-summary").append(row); });
  $("#gaps-count").textContent = `${ir.diagnostics.length} diagnóstico(s)`;
  $("#gaps-list").replaceChildren();
  if (!ir.diagnostics.length) $("#gaps-list").append(element("p", "project-summary", "Nenhum diagnóstico emitido. Isso não garante cobertura completa: consulte os limites abaixo."));
  ir.diagnostics.slice(0, 100).forEach(gap => { const row = element("div", "gap-item"); const body = element("div", "", gaps[gap.reason] || `Construção não suportada: ${gap.reason}`); body.append(element("code", "", gap.file)); row.append(element("span", "", "◉"), body); $("#gaps-list").append(row); });
  if (ir.diagnostics.length > 100) $("#gaps-list").append(element("p", "card-note", "Mostrando os primeiros 100 diagnósticos. Consulte o JSON para a lista completa."));
  renderEndpoints(); renderArchitecture(); renderDocument(); renderInsights(); refreshVisuals();
}
function filteredEndpoints() {
  const search = $("#endpoint-search").value.toLocaleLowerCase();
  const method = $("#method-filter").value;
  const confidence = $("#confidence-filter").value;
  return (state.data?.analysis.endpoints || []).filter(e => (!search || `${e.route} ${e.view}`.toLocaleLowerCase().includes(search)) && (!method || (e.method || "?") === method) && (!confidence || confidence === e.confidence));
}
function renderEndpoints() {
  const endpoints = filteredEndpoints();
  const count = endpoints.length;
  const startAt = state.endpointPage * 40;
  $("#endpoint-count").textContent = `${count} registro(s)`;
  $("#endpoint-rows").replaceChildren();
  $("#endpoint-empty").hidden = count > 0;
  $("#endpoint-empty").textContent = state.data ? "Nenhuma rota encontrada com esses filtros. Uma ausência de rotas não comprova ausência de endpoints." : "Faça uma análise para explorar as rotas.";
  endpoints.slice(startAt, startAt + 40).forEach(e => {
    const row = element("tr");
    const methodCell = element("td"); methodCell.append(methodBadge(e.method));
    const routeCell = element("td"); const button = element("button", "route-button", e.route || "(raiz)"); button.type = "button"; button.addEventListener("click", () => showEvidence(e)); routeCell.append(button);
    const viewCell = element("td"); viewCell.append(element("code", "", e.view));
    const configurationCell = element("td");
    configurationCell.append(element("code", "", e.serializer || "Serializer não confirmado"), element("div", "small-muted", `Permissões: ${displayValue(e.permissions)}`), element("div", "small-muted", `Autenticação: ${displayValue(e.authentication)}`));
    const confidenceCell = element("td"); confidenceCell.append(pill(confidenceNames[e.confidence], e.confidence === "extracted" ? "success" : e.confidence));
    const originCell = element("td"); originCell.append(sourceRef(e.evidence));
    const detailCell = element("td"); const detail = element("button", "text-button", "Ver"); detail.type = "button"; detail.setAttribute("aria-label", `Ver evidências de ${e.method || "método desconhecido"} ${e.route || "raiz"}`); detail.addEventListener("click", () => showEvidence(e)); detailCell.append(detail);
    row.append(methodCell, routeCell, viewCell, configurationCell, confidenceCell, originCell, detailCell); $("#endpoint-rows").append(row);
  });
  $("#endpoint-pagination").hidden = count <= 40;
  $("#previous-page").disabled = state.endpointPage === 0;
  $("#next-page").disabled = startAt + 40 >= count;
  $("#endpoint-page-label").textContent = `Página ${state.endpointPage + 1} de ${Math.max(1, Math.ceil(count / 40))}`;
}
function showEvidence(endpoint) {
  $("#endpoint-detail").hidden = false;
  $("#endpoint-detail-title").textContent = `${endpoint.method || "?"} ${endpoint.route || "(raiz)"}`;
  const content = $("#endpoint-detail-content"); content.replaceChildren();
  [["View / ação", endpoint.view], ["Escopo", {explicit_root: "Raiz selecionada explicitamente", configured_root: "Raiz detectada em ROOT_URLCONF", local_urlconf: "URLconf local — prefixo não confirmado"}[endpoint.scope]], ["Confiança", confidenceNames[endpoint.confidence]]].forEach(([label, value]) => { const row = element("div", "detail-row"); row.append(element("span", "", label), element("code", "", value)); content.append(row); });
  for (const [field, title] of [["serializer", "Serializer declarado"], ["permissions", "Permissões declaradas"], ["authentication", "Autenticação declarada"]]) {
    const row = element("div", "detail-row"); row.append(element("span", "", title), element("code", "", displayValue(endpoint[field]))); content.append(row);
  }
  content.append(element("h3", "", "Cadeia de evidências"));
  const list = element("ol", "evidence-list");
  const seen = new Set();
  const detailRefs = [...endpoint.evidence_chain, ...Object.values(endpoint.configuration || {}).flatMap(c => c.evidence_chain)];
  const codePanel = element("div", "code-panel evidence-code");
  detailRefs.forEach(ref => { const key = `${ref.file}:${ref.start_line}:${ref.end_line}`; if (seen.has(key)) return; seen.add(key); const item = element("li"); item.append(sourceRef(ref)); const viewCode = element("button", "text-button", "Ver trecho"); viewCode.type = "button"; viewCode.addEventListener("click", () => showCode(codePanel, ref)); item.append(document.createTextNode(" · "), viewCode); if (ref.symbol) item.append(element("div", "small-muted", ref.symbol)); list.append(item); });
  content.append(list);
  content.append(codePanel); showCode(codePanel, [...detailRefs].reverse().find(r => r.symbol) || endpoint.evidence);
  const labels = {permissions: "permissões", serializer: "serializer", authentication: "autenticação", method: "método HTTP", mounted_prefix: "prefixo de montagem"};
  content.append(element("p", "detail-notice", `Ainda não confirmado: ${endpoint.unknown_fields.map(k => labels[k] || k).join(", ")}. Rotas de router seguem convenções estáticas do DRF. Em exemplos locais, as referências indicam arquivos da fixture e não abrem código no GitHub.`));
  $("#endpoint-detail-title").focus({preventScroll:true});
  if (matchMedia("(max-width:1250px)").matches) $("#endpoint-detail").scrollIntoView({block:"nearest"});
}
function svgElement(tag, attributes = {}, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== undefined) node.textContent = text;
  return node;
}
function renderArchitecture() {
  if (!state.data) return;
  const ir = state.data.analysis;
  renderMainDiagram(); renderTechnology();
  $("#graph-caption").textContent = "Linhas contínuas: configuração/build. Tracejadas: depends_on; não comprovam tráfego real. Clique nos componentes para conferir evidências. Até 20 componentes no canvas; inventário completo abaixo.";
  $("#mermaid-source").textContent = state.data.documents["ARCHITECTURE.md"].split("```mermaid\n")[1]?.split("```")[0] || "Nenhum diagrama disponível.";
  $("#imports-count").textContent = `${ir.imports.length} imports`;
  $("#import-rows").replaceChildren();
  ir.imports.slice(0, 100).forEach(item => { const tr = element("tr"); const source = element("td"); source.append(element("code", "", item.source)); const target = element("td"); target.append(element("code", "", item.target)); const status = element("td"); status.append(pill(item.resolved ? "Local" : "Não resolvido", item.resolved ? "success" : "neutral")); if (item.resolved) status.append(element("div", "small-muted", item.target_file)); tr.append(source, target, status); $("#import-rows").append(tr); });
  $("#import-caption").textContent = `${Math.min(ir.imports.length, 100)} de ${ir.imports.length} imports exibidos. Imports não resolvidos podem ser bibliotecas externas ou módulos que o parser não conseguiu localizar.`;
}
function appendInline(parent, text) {
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https:\/\/github\.com\/[^\s)]+\))/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(last, match.index)));
    const token = match[0];
    if (token.startsWith("`")) parent.append(element("code", "", token.slice(1, -1)));
    else if (token.startsWith("**")) parent.append(element("strong", "", token.slice(2, -2)));
    else { const parts = /^\[([^\]]+)\]\((.+)\)$/.exec(token); const a = element("a", "", parts[1]); a.href = parts[2]; a.target = "_blank"; a.rel = "noopener noreferrer"; parent.append(a); }
    last = match.index + token.length;
  }
  parent.append(document.createTextNode(text.slice(last)));
}
function renderDocument() {
  if (!state.data) return;
  const text = state.data.documents[state.document];
  const content = $("#document-content"); content.replaceChildren();
  $("#document-outline").replaceChildren();
  if (text === undefined) {
    $("#download-document").hidden = true;
    content.append(element("p", "empty-state", state.data.ai?.status === "failed" ? `A IA não gerou documentação: ${state.data.ai.error}` : "Ative Usar IA ao iniciar uma nova análise para gerar este documento."));
    return;
  }
  $("#download-document").hidden = false;
  $("#download-document").href = `/api/jobs/${state.job}/documents/${state.document}`;
  if (state.document === "AI.md" && state.data.ai?.template_version === "project-summary-v1") { renderProjectSummary(content); return; }
  if (state.document.endsWith(".json")) { content.append(element("pre", "", text)); return; }
  let fenced = false, code = [], list = null;
  for (const line of text.split("\n")) {
    if (line.startsWith("```")) { if (fenced) { content.append(element("pre", "", code.join("\n"))); code = []; } fenced = !fenced; list = null; continue; }
    if (fenced) { code.push(line); continue; }
    if (!line.trim()) { list = null; continue; }
    const heading = /^(#{1,3}) (.*)/.exec(line);
    if (heading) { const node = element(`h${heading[1].length}`); appendInline(node, heading[2]); content.append(node); list = null; }
    else if (line.startsWith("- ")) { if (!list) { list = element("ul"); content.append(list); } const li = element("li"); appendInline(li, line.slice(2)); list.append(li); }
    else { const p = element("p"); appendInline(p, line.trim()); content.append(p); list = null; }
  }
  if (fenced && code.length) content.append(element("pre", "", code.join("\n")));
  content.querySelectorAll("h1,h2,h3").forEach((heading, index) => { heading.id = `doc-section-${index}`; const button = element("button", "", heading.textContent); button.type = "button"; button.addEventListener("click", () => heading.scrollIntoView({block:"start", behavior:"smooth"})); $("#document-outline").append(button); });
}
function renderProjectSummary(content) {
  const ai = state.data.ai;
  content.append(element("h1", "", "Resumo técnico do projeto"), element("p", "detail-notice", "Documentação padronizada escrita pela IA a partir de fatos selecionados. As explicações continuam sendo inferências; o inventário completo está nos documentos técnicos e no anexo do relatório."));
  ai.sections.forEach((section, index) => {
    const card = element("section", "project-summary-section"), heading = element("h2", "", `${String(index+1).padStart(2,"0")} · ${section.title}`); heading.id = `summary-${section.category}`; card.append(heading);
    section.claims.forEach(claim => {
      card.append(pill(confidenceNames[claim.confidence], claim.confidence === "inferred" ? "inferred" : "unconfirmed"), element("p", "", claim.text));
      if (claim.evidence_chain.length) { const details = element("details", "summary-evidence"); details.append(element("summary", "", "Ver evidências")); const list = element("ul"); claim.evidence_chain.forEach(ref=>{const li=element("li");li.append(sourceRef(ref));list.append(li);}); details.append(list); card.append(details); }
    });
    content.append(card);
    const button = element("button", "", section.title);button.type="button";button.addEventListener("click",()=>heading.scrollIntoView({block:"start",behavior:"smooth"}));$("#document-outline").append(button);
  });
}
async function loadHistory() {
  try { const response = await api("/api/jobs"); state.history = response.jobs; renderHistory(); }
  catch (error) { if (state.page === "history") message(error.message); }
}
function renderHistory() {
  const recent = $("#recent-jobs"), list = $("#history-list"); recent.replaceChildren(); list.replaceChildren();
  if (!state.history.length) { recent.append(element("p", "", "Sua primeira análise começa por aqui.")); list.append(element("p", "empty-state", "Nenhuma análise salva. Comece por uma URL ou pelo exemplo integrado.")); return; }
  state.history.forEach((job, i) => {
    const completed = job.status === "completed";
    if (i < 4) { const recentButton = element("button", "recent-job"); recentButton.type = "button"; recentButton.append(element("span", "", completed ? "✓" : job.status === "failed" ? "!" : "◷"), element("span", "", job.label)); recentButton.disabled = !completed || state.busy; recentButton.addEventListener("click", () => openResult(job.id).catch(e => message(e.message))); recent.append(recentButton); }
    const row = element("div", "history-item"); row.append(element("span", "small-icon", completed ? "✓" : job.status === "failed" ? "!" : "◷"));
    const info = element("div", "history-info"); info.append(element("strong", "", job.label), element("p", "", `${new Date(job.created_at).toLocaleString("pt-BR")} · ${job.commit_sha ? job.commit_sha.slice(0, 12) : "fixture " + (job.fingerprint || "")} · ${job.summary ? `${job.summary.endpoints} rotas/métodos · ${job.summary.files} arquivos` : job.error || job.stage}`)); row.append(info);
    row.append(pill(completed ? "Concluída" : job.status === "failed" ? "Falhou" : "Em andamento", completed ? "success" : "neutral"));
    if (completed) { const button = element("button", "button secondary", "Abrir →"); button.type = "button"; button.disabled = state.busy; button.addEventListener("click", () => openResult(job.id).catch(e => message(e.message))); row.append(button); }
    list.append(row);
  });
}

function displayValue(value) {
  if (value === null || value === undefined) return "Não confirmado";
  return Array.isArray(value) ? (value.join(", ") || "Lista vazia declarada") : String(value);
}
function showCode(target, ref) {
  target.replaceChildren();
  if (!ref) { target.append(element("p", "empty-state", "Referência não disponível.")); return; }
  target.append(element("h3", "code-heading", `${ref.file}:${ref.start_line}–${ref.end_line}`));
  const snippet = Object.values(state.data.insights?.snippets || {}).find(s => s.evidence.file === ref.file && s.evidence.start_line === ref.start_line && s.evidence.end_line === ref.end_line);
  if (!snippet) { target.append(element("p", "card-note", "Trecho não salvo neste recorte. Consulte o código no commit pela referência."), sourceRef(ref)); return; }
  const pre = element("pre", "source-code");
  snippet.lines.forEach(row => { const line = element("span", `code-line${row.number >= ref.start_line && row.number <= ref.end_line ? " code-highlight" : ""}`); line.append(element("span", "line-number", row.number), element("span", "", row.text)); pre.append(line); });
  target.append(pre);
  if (snippet.truncated) target.append(element("p", "card-note", "Trecho limitado. A declaração pode continuar além destas linhas."));
}
function visualUrl(kind, download = false) {
  return `/api/jobs/${state.job}/diagrams/${kind}.svg?base=${encodeURIComponent(state.baseId || "none")}${download ? "&download=1" : ""}`;
}
function renderMainDiagram() {
  if (!state.data) return;
  const kind = $("#diagram-kind").value;
  const graph = $("#architecture-graph"); graph.replaceChildren();
  if (kind === "arquitetura" && state.data.analysis.technology) { renderInteractiveArchitecture(graph); $("#download-svg").href = visualUrl(kind, true); return; }
  const image = element("img", "visual-diagram"); image.alt = `Diagrama visual: ${kind}`; image.src = visualUrl(kind); image.width = state.diagramWidth || 1000;
  graph.append(image); $("#download-svg").href = visualUrl(kind, true);
}
function renderInsights() {
  const insights = state.data.insights;
  const coverage = insights.coverage;
  const container = $("#coverage-content"); container.replaceChildren();
  container.append(element("p", "detail-notice", coverage.note));
  const list = element("div", "coverage-counters");
  [["Python aceitos", coverage.python_accepted], ["Python analisados", coverage.python_parsed], ["Erros de parsing", coverage.python_failed], ["Arquivos excluídos", coverage.skipped_files]].forEach(([title, count]) => { const item = element("div"); item.append(element("strong", "", count), element("span", "", title)); list.append(item); }); container.append(list);
  const unknown = element("div", "coverage-fields"); unknown.append(element("h3", "", "Campos de endpoints ainda não confirmados"));
  Object.entries(coverage.endpoint_unknowns).forEach(([key, count]) => unknown.append(element("p", "", `${key}: ${count} de ${state.data.analysis.endpoints.length} registros`))); container.append(unknown);
  const table = element("table"); const head = element("thead"); const header = element("tr"); ["Diretório", "Aceitos", "Python", "Analisados"].forEach(t => header.append(element("th", "", t))); head.append(header); table.append(head); const body = element("tbody");
  coverage.groups.forEach(g => { const row = element("tr"); [g.directory, g.accepted, g.python, g.parsed].forEach(v => row.append(element("td", "", v))); body.append(row); }); table.append(body); const scroll = element("div", "table-scroll"); scroll.append(table); container.append(scroll);
  const reasons = element("div", "coverage-fields"); reasons.append(element("h3", "", "Motivos das exclusões e lacunas"));
  [...Object.entries(coverage.skip_reasons), ...Object.entries(coverage.diagnostic_reasons)].forEach(([key, count]) => reasons.append(element("p", "", `${gaps[key] || key}: ${count}`))); container.append(reasons);
  const select = $("#comparison-base"); select.replaceChildren(); const empty = element("option", "", "Sem base de comparação"); empty.value = ""; select.append(empty);
  (state.data.history || []).filter(j => j.id !== state.job).forEach(job => { const option = element("option", "", `${(job.commit_sha || "fixture " + job.fingerprint).slice(0, 24)} · ${new Date(job.created_at).toLocaleString("pt-BR")}`); option.value = job.id; select.append(option); });
  select.value = state.baseId || "";
  $("#comparison-target").textContent = `Depois: ${state.data.analysis.repository.commit_sha || "fixture local · " + (state.history.find(j => j.id === state.job)?.fingerprint || "sem SHA")}`;
}
async function refreshVisuals() {
  if (!state.data) return;
  renderMainDiagram();
  for (const [id, kind] of [["#coverage-diagram", "cobertura"], ["#comparison-diagram", "comparacao"]]) { $(id).hidden = false; $(id).src = visualUrl(kind); }
  const query = `?base=${encodeURIComponent(state.baseId || "none")}`;
  const report = `/api/jobs/${state.job}/report${query}`;
  $("#download-report").href = report + "&download=1";
  $("#download-all").href = `/api/jobs/${state.job}/download${query}`;
  $("#report-open").hidden = false; $("#report-open").href = report;
  $("#report-empty").hidden = true; $("#report-preview").hidden = false; $("#report-preview").loading = "lazy"; $("#report-preview").src = report;
  $("#download-comparison").hidden = false; $("#download-comparison").href = report + "&download=1";
  const jobId = state.job, baseId = state.baseId;
  try {
    const data = await api(`/api/jobs/${jobId}/compare${query}`);
    if (state.job !== jobId || state.baseId !== baseId) return;
    const content = $("#comparison-content"); content.replaceChildren();
    const diff = data.comparison;
    if (!diff) { content.append(element("p", "empty-state", "Escolha uma análise anterior do mesmo projeto. Para experimentar, analise o exemplo e depois clique em Testar exemplo alterado.")); return; }
    content.append(element("p", "detail-notice", diff.note));
    diff.warnings.forEach(w => content.append(element("p", "detail-notice", w)));
    for (const [title, rows] of [["Rotas adicionadas", diff.added], ["Rotas removidas", diff.removed]]) {
      content.append(element("h3", "", `${title} · ${rows.length}`));
      rows.slice(0, 100).forEach(e => content.append(element("p", "diff-route", `${e.method || "?"} ${e.route || "(raiz)"} → ${e.view}`)));
    }
    content.append(element("h3", "", `Registros para revisão · ${diff.changed.length}`));
    diff.changed.slice(0, 100).forEach(row => content.append(element("p", "diff-route", `${row.after.method || "?"} ${row.after.route}: ${row.fields.map(f => ({evidence_file_changed: "arquivo de evidência alterado", permissions: "permissões", authentication: "autenticação", view: "view/ação", confidence: "confiança"}[f] || f)).join(", ")}`)));
    content.append(element("h3", "", "Arquivos e documentação"));
    ["added", "removed", "changed"].forEach(key => content.append(element("p", "", `${{added: "Arquivos adicionados", removed: "Arquivos removidos", changed: "Arquivos alterados"}[key]}: ${diff.files[key].length}`)));
    diff.documents_to_review.forEach(row => content.append(element("p", "", `${row.document}: ${row.reason}`)));
    content.append(element("p", "card-note", "Até 100 registros exibidos por grupo. As diferenças são observações do parser, não uma análise de impacto completa."));
  } catch (error) { message(error.message); }
}

function applyPublicAI(config) {
  state.aiConfig = config; state.aiConfigured = config.configured;
  $("#use-ai").disabled = state.busy || !config.configured;
  if (!config.configured) $("#use-ai").checked = false;
  $("#ai-provider").value = config.provider;
  $("#ai-model").value = config.model;
  $("#ai-base-url").value = config.base_url;
  $("#ai-api-key").value = "";
  $("#ai-api-key").type = "password"; $("#toggle-ai-key").textContent = "Mostrar";
  $("#ai-config-status").textContent = config.configured ? `IA configurada para esta sessão · ${config.model}. A conexão só é verificada quando você testa ou gera explicações.` : "Configure seu provedor e sua chave em Configurações de IA para habilitar as explicações.";
  $("#ai-key-status").textContent = config.key_present ? "Chave presente na memória. Deixe o campo vazio para mantê-la no mesmo destino, ou cole uma nova para substituir." : "Nenhuma chave nesta sessão. Servidores em localhost podem funcionar sem chave.";
  if (config.persistence_error) $("#ai-settings-message").textContent = config.persistence_error;
}
function aiPayload() {
  return {provider: $("#ai-provider").value, model: $("#ai-model").value.trim(), base_url: $("#ai-base-url").value.trim(), api_key: $("#ai-api-key").value.trim()};
}
function settingsBusy(busy) {
  ["#save-ai-settings", "#test-ai-settings", "#clear-ai-key"].forEach(id => $(id).disabled = busy || state.busy);
}
async function saveAI(event) {
  event.preventDefault(); settingsBusy(true);
  try {
    const data = await api("/api/ai/config", aiPayload());
    applyPublicAI(data.ai);
    await loadAIUsage();
    $("#ai-settings-message").textContent = data.ai.persistence_error || (data.ai.configured ? "Configuração aplicada. A chave fica só na memória desta sessão. Você já pode testar a conexão ou usar IA na próxima análise." : "Preferências aplicadas. Configure uma chave para habilitar a geração com este provedor.");
  } catch (error) { $("#ai-settings-message").textContent = error.message; }
  finally { settingsBusy(false); }
}
async function testAI() {
  const fields = aiPayload();
  if (!state.aiConfig || fields.api_key || ["provider", "model", "base_url"].some(k => fields[k] !== state.aiConfig[k])) {
    $("#ai-settings-message").textContent = "Aplique as configurações antes de testar a conexão."; return;
  }
  settingsBusy(true); $("#ai-settings-message").textContent = "Testando a API configurada, sem enviar dados do repositório…";
  try {
    const data = await api("/api/ai/test", {});
    $("#ai-settings-message").textContent = `Conexão e resposta JSON verificadas · ${data.model} · ${data.usage.totalTokenCount ?? "?"} tokens informados.`;
  } catch (error) { $("#ai-settings-message").textContent = error.message; }
  finally { settingsBusy(false); await loadAIUsage(); }
}
function technologyIcon(name, kind = "application", className = "technology-icon") {
  const key = name.split(" · ")[0].trim().toLowerCase().replace(/\s+\((?:cliente|driver)\)$/, "");
  const catalog = state.icons || {icons:{},aliases:{}};
  const icon = catalog.icons[catalog.aliases[key]];
  const svg = svgElement("svg", {viewBox:"0 0 24 24",width:28,height:28,"aria-hidden":"true",focusable:"false",class:className});
  if(icon){icon.paths.forEach(path=>svg.append(svgElement("path",{d:path,fill:icon.color})));svg.dataset.technology=catalog.aliases[key];}
  else {
    const paths = {database:"M3 5C3 1 21 1 21 5V19C21 23 3 23 3 19ZM3 5C3 9 21 9 21 5M3 12C3 16 21 16 21 12",cache:"M3 5H21V20H3ZM6 9H18M6 13H18M6 17H14",cloud:"M5 20C-2 17 2 9 8 11C7 1 22 1 21 12C27 15 23 21 19 20Z",infrastructure:"M3 3H21V10H3ZM3 14H21V21H3ZM6 6H8M6 17H8",queue:"M5 5L12 12L19 5M12 12V21M3 3H7V7H3ZM17 3H21V7H17Z",proxy:"M3 8H21M3 16H21M17 4L21 8L17 12M7 12L3 16L7 20",application:"M3 4H21V18H3ZM8 22H16M12 18V22M7 9L5 11L7 13M17 9L19 11L17 13",service:"M3 4H21V18H3ZM8 22H16M12 18V22"};
    svg.append(svgElement("path",{d:paths[kind]||paths.application,fill:"none",stroke:"currentColor","stroke-width":1.5,"stroke-linecap":"round","stroke-linejoin":"round"}));
  }
  return svg;
}
function componentMark(component, languages = []) {
  const wrap=element("span","node-icon technology-icon-wrap");
  const names=component.kind==="application" ? languages.slice(0,3).map(item=>item.name) : [component.name];
  (names.length?names:[component.name]).forEach(name=>wrap.append(technologyIcon(name,component.kind)));
  return wrap;
}
function renderTechnology() {
  const summary = $("#technology-summary"), list = $("#technology-components"); summary.replaceChildren(); list.replaceChildren();
  const tech = state.data.analysis.technology;
  if (!tech) { list.append(element("p", "empty-state", "Esta análise é de uma versão anterior. Analise novamente o mesmo SHA para detectar linguagem, banco e infraestrutura.")); return; }
  const groups = [["Linguagens", tech.languages.map(l => `${l.name} (${l.files})`).join(", ")], ["Frameworks", tech.components.filter(c => c.kind === "framework").map(c => c.name).join(", ")], ["Bancos", tech.components.filter(c => c.kind === "database").map(c => c.name).join(", ")], ["Infraestrutura declarada", tech.components.filter(c => ["cloud", "infrastructure", "proxy", "ci"].includes(c.kind)).map(c => c.name).join(", ")]];
  groups.forEach(([title, value], index) => { const card = element("div", "card technology-stat"); card.append(element("span", "", title), element("strong", "", value || "Não confirmado")); const icons=element("div","technology-icon-row"); const items=index===0?tech.languages.map(l=>({name:l.name,kind:"application"})):tech.components.filter(c=>index===1?c.kind==="framework":index===2?c.kind==="database":["cloud","infrastructure","proxy","ci"].includes(c.kind));const seen=new Set();items.forEach(item=>{if(!seen.has(item.name)&&seen.size<6){seen.add(item.name);icons.append(technologyIcon(item.name,item.kind));}});card.append(icons); summary.append(card); });
  const scopes = {dependency: "Dependência", import: "Import", compose_service: "Serviço Compose", django_settings: "Configuração Django", sqlite_connection: "Chamada SQLite declarada", build_configuration: "Build", terraform_declaration: "Terraform", manifest: "Manifesto", deployment_manifest: "Deploy declarado", compose_manifest: "Compose", ci_configuration: "CI declarada", repository: "Inventário de código"};
  tech.components.forEach(component => {
    const card = element("button", "technology-component"); card.type = "button";
    card.append(componentMark(component, tech.languages), element("strong", "", component.name), pill(scopes[component.scope] || component.scope), element("span", "small-muted", component.evidence_chain.length ? `${component.evidence_chain.length} referência(s) · ver código →` : "Inferido do inventário"));
    card.addEventListener("click", () => showTechnology(component, scopes[component.scope])); list.append(card);
  });
  const note = element("p", "card-note", tech.limits.join(" ")); list.append(note);
}
function showTechnology(component, scope) {
  const inArchitecture = state.page === "architecture";
  if (inArchitecture) { $("#architecture-detail").hidden = false; state.componentId = component.id; $$(".architecture-node").forEach(node => node.classList.toggle("selected", node.dataset.component === component.id)); }
  const title = $(inArchitecture ? "#architecture-detail-title" : "#dialog-title"); title.textContent = component.name;
  const content = $(inArchitecture ? "#architecture-detail-content" : "#dialog-content"); content.replaceChildren();
  content.append(componentMark(component,state.data.analysis.technology?.languages || []));
  [["Tipo", technologyKinds[component.kind] || component.kind], ["Origem", scope || technologyScopes[component.scope] || component.scope], ["Confiança", confidenceNames[component.confidence] || component.confidence]].forEach(([label, value]) => { const row = element("div", "detail-row"); row.append(element("span", "", label), element("code", "", value)); content.append(row); });
  const code = element("div", "code-panel evidence-code");
  content.append(element("h3", "", "Evidências no repositório")); const refs = element("ol", "evidence-list");
  component.evidence_chain.forEach(ref => { const li = element("li"); const button = element("button", "text-button", "Ver código"); button.type = "button"; button.addEventListener("click", () => showCode(code, ref)); li.append(sourceRef(ref), document.createTextNode(" · "), button); refs.append(li); });
  content.append(refs, code, element("p", "detail-notice", component.confidence === "unconfirmed" ? "Não foram encontradas declarações suficientes. Isso não comprova ausência desta tecnologia." : "Declaração encontrada no repositório. Bibliotecas, manifests e arquivos de build não comprovam serviço implantado ou tráfego real."));
  showCode(code, component.evidence_chain[0]);
  if (!inArchitecture && !$("#endpoint-dialog").open) $("#endpoint-dialog").showModal();
  if (inArchitecture) { title.focus({preventScroll:true}); if (matchMedia("(max-width:1250px)").matches) $("#architecture-detail").scrollIntoView({block:"nearest"}); }
}

const technologyKinds = {application:"Aplicação", framework:"Framework", database:"Banco de dados", cache:"Cache", queue:"Fila", service:"Serviço", cloud:"Hospedagem", infrastructure:"Infraestrutura", driver:"Driver", library:"Biblioteca", worker:"Worker", proxy:"Proxy", ci:"Integração contínua"};
const technologyScopes = {repository:"Inventário de código", dependency:"Dependência", import:"Import", compose_service:"Serviço Compose", django_settings:"Configuração Django", sqlite_connection:"Conexão SQLite declarada", manifest:"Manifesto", build_configuration:"Build", compose_manifest:"Compose", deployment_manifest:"Deploy declarado", terraform_declaration:"Terraform", ci_configuration:"CI declarada", unconfirmed:"Sem evidência suficiente"};
function renderDiscoveryBoard() {
  const ir = state.data.analysis, tech = ir.technology, board = $("#discovery-board"); board.replaceChildren();
  const categories = [["Código e frameworks", ["framework","library"]], ["Bancos e dados", ["database","driver","cache","queue"]], ["Infraestrutura", ["infrastructure","cloud","proxy","service","worker","ci"]]];
  categories.forEach(([title,kinds]) => {
    const column = element("section", "discovery-column"), components = (tech?.components || []).filter(c => kinds.includes(c.kind));
    const heading = element("h2", "discovery-heading", title); heading.append(element("span", "", components.length)); column.append(heading);
    if (title === "Código e frameworks" && tech?.languages.length) { const card = element("button", "discovery-card"); card.type="button"; const marks=element("span","technology-icon-row");tech.languages.slice(0,4).forEach(l=>marks.append(technologyIcon(l.name)));card.append(marks); card.append(element("strong", "", tech.languages.map(l=>l.name).join(" / ")), element("p", "", "Linguagens identificadas pelas extensões dos arquivos."), pill("Inventário de código")); card.addEventListener("click",()=>page("architecture")); column.append(card); }
    components.slice(0,3).forEach(component => { const card = element("button","discovery-card"); card.type="button"; card.append(componentMark(component),element("strong","",component.name), element("p","",technologyScopes[component.scope] || component.scope), pill(`${component.evidence_chain.length} referência(s)`)); card.addEventListener("click",()=>showTechnology(component)); column.append(card); });
    if (!components.length && title!=="Código e frameworks") { const card=element("div","discovery-card"); card.append(element("strong","","Não confirmado"),element("p","","Nenhuma declaração reconhecida neste recorte.")); column.append(card); }
    board.append(column);
  });
  const column=element("section","discovery-column"), heading=element("h2","discovery-heading","Pontos para revisar"); heading.append(element("span","",ir.diagnostics.length)); column.append(heading);
  const explore=element("button","discovery-card dark-card"); explore.type="button"; explore.append(element("strong","","Explorar arquitetura"),element("p","","Conecte cada descoberta ao arquivo e às linhas que sustentam a análise.")); explore.addEventListener("click",()=>page("architecture")); column.append(explore);
  ir.diagnostics.slice(0,2).forEach(gap=>{const card=element("button","discovery-card");card.type="button";card.append(element("strong","",gaps[gap.reason] || gap.reason),element("p","",gap.file));card.addEventListener("click",()=>page("coverage"));column.append(card);}); board.append(column);
  const counts = ir.technology?.languages.map(l=>l.files) || [];
  const spark=element("div","stat-spark"); spark.setAttribute("aria-hidden","true");
  const largest=Math.max(1,...counts); counts.slice(0,8).forEach(value=>{const bar=element("span");bar.style.height=`${Math.max(4,value/largest*30)}px`;spark.append(bar);});
  $("#stat-files").parentElement.querySelector(".stat-spark")?.remove(); if(counts.length) $("#stat-files").parentElement.append(spark);
}
function renderInteractiveArchitecture(graph) {
  const tech=state.data.analysis.technology;
  const selected=tech.components.filter(c=>c.kind==="application" || (!["framework","driver","library","ci"].includes(c.kind) && !["dependency","import"].includes(c.scope))).filter(c=>c.name!=="Docker" || !tech.components.some(x=>x.name==="Docker Compose")).slice(0,20);
  if(!selected.some(c=>c.kind==="database")) selected.push({id:"unknown-database",kind:"database",name:"Banco não confirmado",scope:"unconfirmed",confidence:"unconfirmed",evidence_chain:[]});
  if(!selected.some(c=>c.kind==="cloud")) selected.push({id:"unknown-cloud",kind:"cloud",name:"Hospedagem não confirmada",scope:"unconfirmed",confidence:"unconfirmed",evidence_chain:[]});
  const canvas=element("div","graph-workspace"); canvas.style.width=`${state.diagramWidth || 1000}px`;
  const positions=new Map(), columnRows=[0,0,0], columnX=[30,350,670];
  selected.forEach(component=>{const column=component.kind==="application" || component.kind==="service" ? 1 : ["database","cache","proxy"].includes(component.kind) ? 0 : 2;positions.set(component.id,{x:columnX[column],y:55+columnRows[column]++*195});});
  const height=Math.max(480,Math.max(...columnRows)*195+90); canvas.style.height=`${height}px`;
  const lines=svgElement("svg",{viewBox:`0 0 1000 ${height}`,preserveAspectRatio:"none","aria-hidden":"true"});
  const defs=svgElement("defs"),marker=svgElement("marker",{id:"connection-arrow",viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:5,markerHeight:5,orient:"auto-start-reverse"});marker.append(svgElement("path",{d:"M 0 0 L 10 5 L 0 10 z",fill:"#62625a"}));defs.append(marker);lines.append(defs);
  tech.relations.forEach(relation=>{const a=positions.get(relation.source),b=positions.get(relation.target);if(!a||!b)return;const left=a.x>b.x;const sameColumn=a.x===b.x;const fromX=a.x+(left?0:236),toX=b.x+(sameColumn?236:left?236:0),fromY=a.y+65,toY=b.y+65;const bend=sameColumn?a.x+295:(fromX+toX)/2;
    const path=svgElement("path",{d:`M ${fromX} ${fromY} C ${bend} ${fromY}, ${bend} ${toY}, ${toX} ${toY}`,stroke:"#77776b","stroke-width":1.3,fill:"none","marker-end":"url(#connection-arrow)"});if(relation.kind==="declared_dependency")path.setAttribute("stroke-dasharray","5 5");lines.append(path);
  }); canvas.append(lines);
  selected.forEach(component=>{const pos=positions.get(component.id),card=element("button",`architecture-node${state.componentId===component.id?" selected":""}`);card.type="button";card.dataset.component=component.id;card.style.left=`${pos.x/10}%`;card.style.top=`${pos.y}px`;card.style.width="23.6%";
    card.append(componentMark(component,tech.languages),pill(confidenceNames[component.confidence],component.confidence==="unconfirmed"?"unconfirmed":"neutral"),element("strong","",component.kind==="application"?(tech.languages.map(l=>l.name).join(" / ")||component.name):component.name));
    const ref=component.evidence_chain[0];card.append(element("span","small-muted",component.kind==="application" ? tech.components.filter(c=>c.kind==="framework").map(c=>c.name).join(" · ") || "Inventário de código" : technologyKinds[component.kind] || component.kind),element("span","small-muted",ref?`${ref.file}:${ref.start_line}`:"Sem evidência suficiente"));card.addEventListener("click",()=>showTechnology(component));canvas.append(card);
  }); graph.append(canvas);
}

let githubGeneration = 0;
let githubBusy = false;
function githubButtons() {
  const connected = state.github?.connected;
  $("#github-connect").disabled = githubBusy;
  $("#github-disconnect").disabled = githubBusy || !connected;
  $("#github-refresh").disabled = githubBusy || !connected;
  $("#github-prev").disabled = githubBusy || !connected || (state.githubPage || 1) <= 1;
  $("#github-next").disabled = githubBusy || !connected || !state.githubHasMore;
}
function showGitHubConnection(data) {
  state.github = data;
  $("#github-state").textContent = data.connected ? `Conectado · ${data.login}` : "Desconectado";
  githubButtons();
}
async function loadGitHub() {
  try { showGitHubConnection(await api("/api/github/connection")); }
  catch (error) { $("#github-message").textContent = error.message; }
}
function renderGitHubRepos() {
  const container = $("#github-repositories"); container.replaceChildren();
  const filter = $("#github-repo-filter").value;
  const rows = (state.githubRepos || []).filter(row => filter === "all" || row.private === (filter === "private"));
  rows.forEach(repo => {
    const card = element("div", "github-repo-card");
    card.append(element("strong", "", repo.full_name), pill(repo.private ? "Privado" : "Público"), element("span", "small-muted", `Branch padrão: ${repo.default_branch || "não informada"}`));
    const select = element("button", "button secondary", "Usar este repositório"); select.type = "button";
    select.addEventListener("click", () => { $("#repository").value = repo.url; $("#branch").value = repo.default_branch; $("#private-ai-consent").checked = false; page("overview"); $("#analysis-form-card").hidden = false; $("#repository").focus(); });
    card.append(select); container.append(card);
  });
  if (!rows.length) container.append(element("p", "empty-state", "Nenhum repositório nesta página/filtro. Confira os repositórios selecionados no token e aprovações da organização."));
  $("#github-page").textContent = `Página ${state.githubPage || 1}`;
  githubButtons();
}
async function listGitHubRepos(number = 1) {
  if (githubBusy) return;
  githubBusy = true; githubButtons();
  const generation = githubGeneration;
  $("#github-message").textContent = "Consultando repositórios permitidos…";
  try {
    const data = await api(`/api/github/repos?page=${number}`);
    if (generation !== githubGeneration) return;
    state.githubRepos = data.repositories; state.githubPage = data.page; state.githubHasMore = data.has_more;
    renderGitHubRepos(); $("#github-message").textContent = "Lista carregada. Selecione um repositório para preencher a análise.";
  } catch (error) { $("#github-message").textContent = error.message; }
  finally { githubBusy = false; githubButtons(); }
}
$("#github-connect-form").addEventListener("submit", async event => {
  event.preventDefault(); if (githubBusy) return;
  githubBusy = true; githubButtons(); githubGeneration++;
  try {
    const data = await api("/api/github/connect", {token: $("#github-token").value.trim()});
    showGitHubConnection(data); state.githubRepos = []; state.githubPage = 1;
    $("#github-message").textContent = `Conta ${data.login} verificada. O acesso a cada repositório depende das permissões do token.`;
  } catch (error) { $("#github-message").textContent = error.message; }
  finally { $("#github-token").value = ""; githubBusy = false; githubButtons(); }
  if (state.github?.connected) await listGitHubRepos(1);
});
$("#github-disconnect").addEventListener("click", async () => {
  if (githubBusy) return;
  githubBusy = true; githubButtons(); githubGeneration++;
  try {
    showGitHubConnection(await api("/api/github/disconnect", {}));
    $("#github-token").value = ""; $("#private-ai-consent").checked = false;
    state.githubRepos = []; state.githubPage = 1; state.githubHasMore = false;
    $("#github-repositories").replaceChildren(element("p", "empty-state", "Conta desconectada. As análises já salvas continuam no histórico local."));
    $("#github-message").textContent = "Token removido da sessão. Pedidos em andamento podem terminar.";
  } catch (error) { $("#github-message").textContent = error.message; }
  finally { githubBusy = false; githubButtons(); }
});
$("#github-refresh").addEventListener("click", () => listGitHubRepos(state.githubPage || 1));
$("#github-prev").addEventListener("click", () => listGitHubRepos((state.githubPage || 1)-1));
$("#github-next").addEventListener("click", () => listGitHubRepos((state.githubPage || 1)+1));
$("#github-repo-filter").addEventListener("change", renderGitHubRepos);

const usageNumber = value => value === null || value === undefined ? "Desconhecido" : new Intl.NumberFormat("pt-BR").format(value);
const usageMoney = value => value === null || value === undefined ? "Desconhecido" : new Intl.NumberFormat("pt-BR", {style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6}).format(Number(value));
async function loadAIUsage() {
  try {
    const data = await api("/api/ai/usage"); state.usage = data;
    const totals = data.totals, summary = $("#ai-usage-summary"); summary.replaceChildren();
    [["Chamadas no mês", usageNumber(totals.requests)], ["Tokens conhecidos", usageNumber(totals.total_tokens)], ["Subtotal estimado", usageMoney(totals.estimated_cost)], ["Custos desconhecidos", usageNumber(totals.unknown_costs)]].forEach(([title, value]) => { const card = element("div", "card technology-stat"); card.append(element("span", "", title), element("strong", "", value)); summary.append(card); });
    const status = `${data.month} (UTC) · entrada ${usageNumber(totals.input_tokens)} · saída ${usageNumber(totals.output_tokens)} · ${totals.errors} erro(s) · ${totals.unknown_tokens} chamada(s) sem total de tokens. ${data.persistent ? "Histórico salvo neste computador." : "Histórico apenas nesta sessão."}`;
    $("#ai-budget-status").textContent = `${data.policy.paused ? "CHAMADAS PAUSADAS. " : ""}${totals.budget_reached ? "ORÇAMENTO ESTIMADO ATINGIDO. " : ""}${data.policy.monthly_budget === null ? "Sem orçamento definido. " : `Orçamento ${usageMoney(data.policy.monthly_budget)}. `}${totals.unknown_costs ? "Subtotal parcial: existem custos desconhecidos. " : ""}${status}`;
    $("#ai-budget-status").classList.toggle("usage-alert", totals.budget_reached || data.policy.paused);
    $("#ai-input-price").value = data.prices.input_per_million ?? "";
    $("#ai-output-price").value = data.prices.output_per_million ?? "";
    $("#ai-monthly-budget").value = data.policy.monthly_budget ?? "";
    $("#ai-calls-paused").checked = data.policy.paused;
    $("#ai-price-profile").textContent = `Tarifa do perfil aplicado: ${data.profile.provider} / ${data.profile.model}. Aplique primeiro qualquer troca de provedor/modelo na configuração acima.`;
    const rows = $("#ai-usage-rows"); rows.replaceChildren();
    data.recent.forEach(event => {
      const row = element("tr");
      const status = {started: "Em andamento ou interrompida", received: "Resposta recebida", error: "Erro · cobrança não confirmada"}[event.status] || event.status;
      [new Date(event.created_at).toLocaleString("pt-BR"), `${event.provider} / ${event.model}`, `${event.purpose === "analysis" ? "Análise" : "Teste de conexão"} · ${status}`, usageNumber(event.input_tokens), usageNumber(event.output_tokens), usageNumber(event.total_tokens), usageMoney(event.estimated_cost)].forEach(value => row.append(element("td", "", value)));
      rows.append(row);
    });
    if (!data.recent.length) { const row = element("tr"), cell = element("td", "empty-state", "Nenhuma chamada registrada. O acompanhamento começa nesta versão."); cell.colSpan = 7; row.append(cell); rows.append(row); }
  } catch (error) { $("#ai-budget-message").textContent = error.message; }
}
$("#refresh-ai-usage").addEventListener("click", loadAIUsage);
$("#ai-budget-form").addEventListener("submit", async event => {
  event.preventDefault(); $("#save-ai-budget").disabled = true;
  try {
    await api("/api/ai/usage", {profile_id: state.usage?.profile.id, input_per_million: $("#ai-input-price").value, output_per_million: $("#ai-output-price").value, monthly_budget: $("#ai-monthly-budget").value, paused: $("#ai-calls-paused").checked});
    $("#ai-budget-message").textContent = "Gestão salva. As novas tarifas serão usadas nas próximas chamadas; chamadas em andamento mantêm a tarifa inicial.";
    await loadAIUsage();
  } catch (error) { $("#ai-budget-message").textContent = error.message; }
  finally { $("#save-ai-budget").disabled = false; }
});
$("#export-ai-usage").addEventListener("click", () => {
  if (!state.usage) return;
  const rows = [["Data UTC", "Provedor", "Modelo", "Finalidade", "Estado", "Entrada", "Saída", "Total", "Estimativa USD"], ...state.usage.recent.map(e => [e.created_at, e.provider, e.model, e.purpose, e.status, e.input_tokens, e.output_tokens, e.total_tokens, e.estimated_cost])];
  const csv = rows.map(row => row.map(value => { let text = value === null ? "desconhecido" : String(value); if (/^[=+@\-]/.test(text)) text = "'" + text; return '"' + text.replaceAll('"', '""') + '"'; }).join(";")).join("\r\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF" + csv], {type: "text/csv;charset=utf-8"})); const link = element("a"); link.href = url; link.download = "octorgit-consumo-ia.csv"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

function prepareExport() {
  if(!state.data){message("Faça uma análise para exportar um relatório.");return;}
  const query=`base=${encodeURIComponent(state.baseId || "none")}`;
  $("#export-download-html").textContent = state.data.ai?.template_version === "project-summary-v1" ? "Baixar resumo HTML" : "Baixar relatório HTML";
  $("#export-repository").textContent=`${state.data.analysis.repository.url || "Exemplo integrado"} · ${state.data.analysis.repository.commit_sha || "Fixture sem SHA"}`;
  $("#export-open-report").href=`/api/jobs/${state.job}/report?${query}`;
  $("#export-open-technical").href=`/api/jobs/${state.job}/report?${query}&view=technical`;
  $("#export-download-html").href=`/api/jobs/${state.job}/report?${query}&download=1`;
  $("#export-dialog").showModal();
}
["#open-export","#document-export"].forEach(id=>$(id).addEventListener("click",prepareExport));
$("#close-export").addEventListener("click",()=>$("#export-dialog").close());
$("#top-new-analysis").addEventListener("click",()=>$("#new-analysis").click());
$("#close-endpoint-detail").addEventListener("click",()=>{$("#endpoint-detail").hidden=true;$("#endpoint-search").focus();});
$("#close-architecture-detail").addEventListener("click",()=>{$("#architecture-detail").hidden=true;state.componentId=null;$$(".architecture-node").forEach(node=>node.classList.remove("selected"));$("#diagram-kind").focus();});
$("#diagram-fit").addEventListener("click",()=>{state.diagramWidth=1000;renderMainDiagram();});
function searchAnalysis(){
  const results=$("#search-results");results.replaceChildren();const query=$("#global-search").value.trim().toLocaleLowerCase();
  if(!state.data){results.append(element("p","empty-state","Faça uma análise para buscar componentes, rotas e arquivos."));return;}
  if(!query){results.append(element("p","empty-state","Digite para buscar na análise atual."));return;}
  const ir=state.data.analysis;
  const hits=[...(ir.technology?.components || []).filter(c=>c.name.toLocaleLowerCase().includes(query)).map(c=>({name:c.name,type:"Componente",action:()=>{page("architecture");showTechnology(c);}})),...ir.endpoints.filter(e=>`${e.route} ${e.view}`.toLocaleLowerCase().includes(query)).map(e=>({name:`${e.method||"?"} ${e.route || "(raiz)"}`,type:"Endpoint",action:()=>{page("endpoints");showEvidence(e);}})),...ir.files.filter(f=>f.path.toLocaleLowerCase().includes(query)).map(f=>({name:f.path,type:"Arquivo",action:()=>{const ref=Object.values(state.data.insights.snippets).find(s=>s.file===f.path)?.evidence;$("#dialog-title").textContent=f.path;showCode($("#dialog-content"),ref);$("#endpoint-dialog").showModal();}}))];
  hits.slice(0,20).forEach(hit=>{const button=element("button","search-hit");button.type="button";button.append(element("strong","",hit.name),element("span","",hit.type));button.addEventListener("click",()=>{$("#search-dialog").close();hit.action();});results.append(button);});
  if(!hits.length)results.append(element("p","empty-state","Nenhum resultado encontrado."));
  if(hits.length>20)results.append(element("p","small-muted","Mostrando 20 resultados. Refine sua busca."));
}
$("#open-search").addEventListener("click",()=>{$("#search-dialog").showModal();searchAnalysis();$("#global-search").focus();});
$("#close-search").addEventListener("click",()=>$("#search-dialog").close());
$("#global-search").addEventListener("input",searchAnalysis);
document.addEventListener("keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="k"){event.preventDefault();if(!document.querySelector("dialog[open]"))$("#open-search").click();}});
const settingsTabs=$$("[data-settings-tab]");
settingsTabs.forEach((button,index)=>{button.tabIndex=button.getAttribute("aria-selected")==="true"?0:-1;button.addEventListener("click",()=>{settingsTabs.forEach(tab=>{const selected=tab===button;tab.setAttribute("aria-selected",String(selected));tab.tabIndex=selected?0:-1;});$$("[data-settings-panel]").forEach(panel=>panel.hidden=panel.dataset.settingsPanel!==button.dataset.settingsTab);if(button.dataset.settingsTab==="usage")loadAIUsage();});button.addEventListener("keydown",event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();const next=event.key==="Home"?0:event.key==="End"?settingsTabs.length-1:(index+(event.key==="ArrowRight"?1:-1)+settingsTabs.length)%settingsTabs.length;settingsTabs[next].click();settingsTabs[next].focus();});});

$("#analysis-form").addEventListener("submit", event => { event.preventDefault(); start("github"); });
$("#demo-button").addEventListener("click", () => start("demo"));
$("#welcome-demo").addEventListener("click", () => start("demo"));
$("#new-analysis").addEventListener("click", () => { page("overview"); $("#analysis-form-card").hidden = false; $("#repository").focus(); });
$$("[data-page]").forEach(button => button.addEventListener("click", () => page(button.dataset.page)));
$$("[data-go]").forEach(button => button.addEventListener("click", () => page(button.dataset.go)));
$("#close-dialog").addEventListener("click", () => $("#endpoint-dialog").close());
$("#endpoint-dialog").addEventListener("click", event => { if (event.target === $("#endpoint-dialog")) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
["#endpoint-search", "#method-filter", "#confidence-filter"].forEach(selector => $(selector).addEventListener(selector.includes("search") ? "input" : "change", () => { state.endpointPage = 0; renderEndpoints(); }));
$("#previous-page").addEventListener("click", () => { state.endpointPage--; renderEndpoints(); });
$("#next-page").addEventListener("click", () => { state.endpointPage++; renderEndpoints(); });
$("#show-mermaid").addEventListener("click", () => { $("#mermaid-source").hidden = !$("#mermaid-source").hidden; $("#show-mermaid").textContent = $("#mermaid-source").hidden ? "Código Mermaid" : "Ocultar código"; });
$$("[data-document]").forEach(button => button.addEventListener("click", () => { state.document = button.dataset.document; $$("[data-document]").forEach(tab => tab.setAttribute("aria-selected", String(tab === button))); renderDocument(); }));
$$("[data-document]").forEach(button => button.addEventListener("keydown", event => {
  const tabs = $$("[data-document]");
  const current = tabs.indexOf(button);
  let next;
  if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
  else if (event.key === "ArrowLeft") next = (current + tabs.length - 1) % tabs.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = tabs.length - 1;
  else return;
  event.preventDefault(); tabs[next].focus(); tabs[next].click();
}));
$("#diagram-kind").addEventListener("change", renderMainDiagram);
$("#diagram-larger").addEventListener("click", () => { state.diagramWidth = Math.min(2400, (state.diagramWidth || 1000) + 200); renderMainDiagram(); });
$("#diagram-smaller").addEventListener("click", () => { state.diagramWidth = Math.max(600, (state.diagramWidth || 1000) - 200); renderMainDiagram(); });
$("#comparison-base").addEventListener("change", () => { state.baseId = $("#comparison-base").value || null; refreshVisuals(); });
$("#demo-next-button").addEventListener("click", () => start("demo-next"));
$("#refresh-history").addEventListener("click", loadHistory);
$("#ai-settings-form").addEventListener("submit", saveAI);
$("#test-ai-settings").addEventListener("click", testAI);
$("#toggle-ai-key").addEventListener("click", () => { const field = $("#ai-api-key"); field.type = field.type === "password" ? "text" : "password"; $("#toggle-ai-key").textContent = field.type === "password" ? "Mostrar" : "Ocultar"; });
$("#ai-provider").addEventListener("change", () => { const preset = state.aiConfig?.presets[$("#ai-provider").value]; if (preset) { $("#ai-model").value = preset.model; $("#ai-base-url").value = preset.base_url; } $("#ai-api-key").value = ""; $("#ai-key-status").textContent = "Ao trocar de provedor ou endereço, informe a chave desse destino. A chave anterior não é reutilizada automaticamente."; });
$("#clear-ai-key").addEventListener("click", async () => { settingsBusy(true); try { applyPublicAI((await api("/api/ai/config", {clear_key: true})).ai); $("#ai-settings-message").textContent = "Chave removida da sessão. Preferências não secretas mantidas."; } catch (error) { $("#ai-settings-message").textContent = error.message; } finally { settingsBusy(false); } });
async function init() {
  try { state.icons = await api("/technology-icons.json"); } catch { state.icons = {icons:{},aliases:{}}; }
  try { applyPublicAI((await api("/api/config")).ai); }
  catch { $("#ai-config-status").textContent = "Não foi possível consultar a configuração de IA. Atualize a página."; }
  await loadHistory();
  await loadAIUsage();
  let saved;
  try { saved = sessionStorage.getItem("octorgit-job"); } catch {}
  if (!saved || !state.history.some(j => j.id === saved)) saved = state.history.find(j => j.status === "completed")?.id;
  if (saved && state.history.some(j => j.id === saved)) {
    setBusy(true);
    try { const job = await api(`/api/jobs/${saved}`); if (job.status !== "failed") await poll(job); }
    catch (error) { message(error.message); }
    finally { setBusy(false); }
  }
}
init();
