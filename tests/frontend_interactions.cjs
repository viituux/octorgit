// DOM unit harness only: no browser engine, CSS layout or screenshot validation.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('src/octorgit/static/index.html', 'utf8');
const ids = new Map();
class Node {
  constructor(tag='div') { this.tagName=tag.toUpperCase(); this.children=[];this.attributes={};this.dataset={};this.style={};this.listeners={};this.hidden=false;this.disabled=false;this.value='';this.open=false;this._text='';this.classes=new Set();this.classList={toggle:(name,on)=>{if(on===undefined)on=!this.classes.has(name);on?this.classes.add(name):this.classes.delete(name);},remove:name=>this.classes.delete(name)}; }
  set className(v){this._className=v;this.classes=new Set(v.split(' '));} get className(){return this._className||'';}
  set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
  append(...nodes){for(let node of nodes){if(typeof node==='string')node=new Node('text'),node.textContent=nodes[0];node.parentElement=this;this.children.push(node);}}
  replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
  setAttribute(k,v){this.attributes[k]=String(v);if(k==='id')ids.set(String(v),this);} getAttribute(k){return this.attributes[k];}
  addEventListener(type,handler){(this.listeners[type]??=[]).push(handler);}
  click(){for(const listener of this.listeners.click||[])listener({target:this,preventDefault(){}});}
  focus(){this.focused=true;}scrollIntoView(){this.scrolled=true;}showModal(){this.open=true;}close(){this.open=false;}
  getBoundingClientRect(){return {left:0,top:0,right:100,bottom:100};}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);}
  querySelectorAll(selector){const all=this.children.flatMap(n=>[n,...n.querySelectorAll('*')]);if(selector==='*')return all;return all.filter(n=>selector.split(',').some(s=>s.startsWith('.')?n.classes.has(s.slice(1)):n.tagName.toLowerCase()===s));}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
for (const match of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
  const node=new Node(match[1]);node.id=match[3];ids.set(node.id,node);
  for(const attribute of match[2].matchAll(/([\w-]+)="([^"]*)"/g)){node.attributes[attribute[1]]=attribute[2];if(attribute[1]==='class')node.className=attribute[2];if(attribute[1].startsWith('data-'))node.dataset[attribute[1].slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=attribute[2];}
}
const dataNodes=[];
for(const match of html.matchAll(/<(button|div|section)\b([^>]*\bdata-(document|page|go|settings-tab|settings-panel)="([^"]+)"[^>]*)>/g)){
 const id=/\bid="([^"]+)"/.exec(match[2])?.[1];const node=id?ids.get(id):new Node(match[1]);const key=match[3].replace(/-([a-z])/g,(_,c)=>c.toUpperCase());node.dataset[key]=match[4];dataNodes.push(node);
}
const allNodes=()=>[...new Set([...ids.values(),...dataNodes])];
function select(selector){if(selector.startsWith('#'))return ids.get(selector.slice(1))||null;if(selector==='meta[name=octorgit-token]')return {content:'test-session'};if(selector==='dialog[open]')return allNodes().find(n=>n.tagName==='DIALOG'&&n.open)||null;return null;}
function selectAll(selector){if(selector.startsWith('[data-')){const key=selector.slice(6,-1).replace(/-([a-z])/g,(_,c)=>c.toUpperCase());return allNodes().filter(n=>key in n.dataset);}if(selector.startsWith('.'))return allNodes().filter(n=>n.classes.has(selector.slice(1)));return [];}
const document={querySelector:select,querySelectorAll:selectAll,createElement:tag=>new Node(tag),createElementNS:(_,tag)=>new Node(tag),createTextNode:text=>{const n=new Node('text');n.textContent=text;return n;},addEventListener(){},body:new Node('body')};
const sandbox={document,console,URL,Blob,setTimeout:()=>0,sessionStorage:{setItem(){}},matchMedia:()=>({matches:false}),fetch:()=>{throw Error('Unexpected network in DOM unit test');},setBusy(){}};
vm.createContext(sandbox);
const source=fs.readFileSync('src/octorgit/static/app.js','utf8').replace(/\binit\(\);\s*$/,'');
vm.runInContext(source,sandbox);
const run=code=>vm.runInContext(code,sandbox);
run(String.raw`state.job='test-job';state.data={analysis:{repository:{url:'https://github.com/test/repo',branch:'main',commit_sha:'a'.repeat(40)},files:[{path:'app.py'}],endpoints:[{method:'GET',route:'health/',view:'views.health',scope:'explicit_root',confidence:'extracted',serializer:null,permissions:null,authentication:null,configuration:{},unknown_fields:[],evidence:{file:'app.py',start_line:1,end_line:1,symbol:null},evidence_chain:[{file:'app.py',start_line:1,end_line:1,symbol:null}]}],technology:{languages:[{name:'Python',files:1}],components:[{id:'application',kind:'application',name:'Código',scope:'repository',confidence:'inferred',evidence_chain:[]},{id:'db',kind:'database',name:'SQLite',scope:'sqlite_connection',confidence:'extracted',evidence_chain:[{file:'app.py',start_line:1,end_line:1,symbol:null}]}],relations:[{source:'application',target:'db',kind:'database_configuration'}]}},insights:{snippets:{}},documents:{'README.md':'# Meu projeto\n## Arquitetura\nTexto seguro <script>não executar</script>','ARCHITECTURE.md':'test'}};state.baseId='base-job';`);
ids.get('diagram-kind').value='arquitetura';
// Icons use bundled paths and aliases; repository names never become HTML or URLs.
sandbox.iconCatalog=JSON.parse(fs.readFileSync('src/octorgit/static/icons/catalog.json','utf8'));
run('state.icons=iconCatalog;');
assert.equal(run("technologyIcon('PostgreSQL · db','database').dataset.technology"),'postgresql');
assert.equal(run("technologyIcon('Docker Compose','infrastructure').dataset.technology"),'docker');
assert.equal(run("technologyIcon('<script>unknown</script>','database').children[0].getAttribute('fill')"),'none');
// Graph must be usable, backed by actual components, with adjacent evidence.
run(`state.page='architecture';renderMainDiagram();`);
assert.equal(ids.get('architecture-graph').children[0].className,'graph-workspace');
assert.ok(ids.get('architecture-graph').textContent.includes('SQLite'));
run(`showTechnology(state.data.analysis.technology.components[1]);`);
assert.equal(ids.get('architecture-detail').hidden,false);
assert.equal(ids.get('architecture-detail-title').textContent,'SQLite');
// Endpoints show route and code evidence in a side pane without opening a modal.
run(`state.page='endpoints';showEvidence(state.data.analysis.endpoints[0]);`);
assert.equal(ids.get('endpoint-detail-title').textContent,'GET health/');
assert.equal(ids.get('endpoint-dialog').open,false);
// Real report URL retains selected comparison; PDF dialog does not claim direct PDF output.
run('prepareExport();');
assert.equal(ids.get('export-dialog').open,true);
assert.equal(ids.get('export-open-report').href,'/api/jobs/test-job/report?base=base-job');
assert.ok(html.includes('não baixa um PDF automaticamente'));
// Tabs select the panel and update accessibility state.
ids.get('settings-api-tab').click();
assert.equal(ids.get('settings-api-panel').hidden,false);
assert.equal(ids.get('settings-usage-panel').hidden,true);
assert.equal(ids.get('settings-api-tab').getAttribute('aria-selected'),'true');
// Search must return a real route and navigate to its evidence on selection.
ids.get('global-search').value='health';run('searchAnalysis();');
assert.ok(ids.get('search-results').textContent.includes('GET health/'));
ids.get('search-results').children[0].click();
assert.equal(run('state.page'),'endpoints');
// Document outline must derive from headings, with repository content treated as text.
run(`state.document='README.md';renderDocument();`);
assert.equal(ids.get('document-outline').children.length,2);
assert.ok(ids.get('document-content').textContent.includes('<script>não executar</script>'));
assert.equal(ids.get('document-content').querySelectorAll('script').length,0);
// AI summary is split into nine concise sections with an index, rather than one raw block.
run(`state.data.documents['AI.md']='summary';state.data.ai={template_version:'project-summary-v1',sections:Array.from({length:9},(_,index)=>({category:'category-'+index,title:'Categoria '+index,claims:[{text:'Texto curto da categoria.',confidence:'unconfirmed',evidence_chain:[]}]}))};state.document='AI.md';renderDocument();`);
assert.equal(ids.get('document-content').children.filter(node=>node.className==='project-summary-section').length,9);
assert.equal(ids.get('document-outline').children.length,9);
console.log('Frontend interaction units passed: graph, evidence panes, export, tabs, search, documentation.');
