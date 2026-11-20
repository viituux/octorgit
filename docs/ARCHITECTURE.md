# Arquitetura — mapas, histórico e relatórios 0.6.0

CLI → snapshot → filtros → AST Python → índice de módulos → regras Django/DRF → IR → validação de evidências → JSON/Markdown.

`repositories.py` resolve o SHA antes do snapshot público. Não extrai o tar no disco. No modo local, não executa Git e deixa o SHA nulo.

`code_parser.py` extrai arquivos, símbolos e árvores sintáticas. `django_parser.py` indexa imports e definições de nível superior, resolve módulos/reexports locais, seleciona raiz e percorre URLs. As árvores só são dados; nenhum módulo do alvo é importado.

Raiz: `--root-urlconf` tem precedência. Sem ele, um único ROOT_URLCONF literal é usado. Vários valores ou ausência de raiz preservam escopo local e prefixos não confirmados. Branches de settings não são executados.

A expansão mantém evidências de settings, includes e views. Includes cíclicos são interrompidos; profundidade máxima 32, até 10 mil visitas de rota. Configurações dinâmicas e dependências ausentes produzem diagnósticos, sem simular execução.

Regras de router derivam a relação HTTP/ação de bases DRF reconhecidas. Portanto são inferências com evidências das classes e registros. Mixins, herança local, restrições literais de métodos, trailing_slash e algumas opções de @action são suportados.

`documentation.py` valida referências diretas e cadeias e exporta resultados. `benchmark.py` compara com gabaritos JSON explícitos usando método+rota. Duplicatas e métodos desconhecidos contam como falsos positivos. Um manifesto pode restringir arquivos de rotas e relata quantos registros emitidos ficaram fora desse escopo.

SQLite local persiste análises; não há banco ou fila externos. O provedor de IA é opcional desde a versão 0.4.0. Por solicitação do usuário, a versão 0.3.0 acrescenta um servidor HTTP local e uma interface HTML/CSS/JavaScript servida pelo próprio pacote Python.

## Interface local

`web.py` usa ThreadingHTTPServer ligado exclusivamente a 127.0.0.1. Um ThreadPoolExecutor com um worker executa a mesma aquisição, parser e validação da CLI. Estados reais: queued/running/completed/failed, com progresso por etapa (não por percentual de bytes). Nenhum diretório arbitrário do computador é exposto; entradas são GitHub público ou demo integrada.

`static/` contém HTML, CSS, JavaScript e uma fixture JSON. Não existem CDNs, scripts externos ou dependências npm. O provedor é acessado apenas pelo servidor Python, se ativado. Dados do repositório são inseridos por textContent/nós DOM, nunca por innerHTML. Os SVGs são derivados de fatos detectados, com grupos, cartões e conexões azuis. Limites de apresentação são declarados; o mapa de tecnologias mostra até 20 componentes.

POSTs exigem token aleatório de sessão e JSON; Host e Origin são verificados. A CSP impede recursos externos, framing e scripts inline. O servidor local não deve ser publicado ou ligado a todas as interfaces.

Apenas uma análise pode estar ativa. Até oito resultados concluídos/falhos são mantidos em memória; ao atingir o limite, o mais antigo é removido. Análises concluídas/falhas são persistidas atomicamente no SQLite. O cache de oito entradas em memória não limita o histórico em disco. Downloads usam o mesmo exportador da CLI e arquivos temporários descartáveis. Resultados não são escritos em pastas arbitrárias.

A demo contém código sintético autoral, sem SHA e explicitamente identificada. O launcher Windows define PYTHONPATH apenas no processo filho e usa o código src da pasta extraída, sem precisar reinstalar a CLI anterior.

## Limitações

- AST usa a gramática do Python do host.
- Resolução só de imports/declarações de nível superior; sem execução de settings, fluxo condicional ou sys.path customizado (src/backend).
- Ordem e sombreamento complexos, MRO múltipla, monkey patches e decorators customizados exigem regras adicionais. A ausência de diagnóstico não garante completude.
- Includes de regex aninhado e lookups customizados são rejeitados com diagnóstico. URLs de dependências não presentes no snapshot não são analisadas.
- Reatribuições dinâmicas de routers/urlpatterns, métodos genéricos de classes externas e actions com configurações desconhecidas não são totalmente resolvidos.
- HEAD/OPTIONS automáticos, API root e variantes de formato ficam fora da enumeração.
- Campos declarados de serializer, permissões e autenticação são extraídos quando suportados; getters e configurações dinâmicas ficam não confirmados.
- Snapshot/parser ainda não têm processo isolado com orçamento de CPU/memória. Não usar como serviço público antes dessa etapa.

## IA configurável

`ai_engine.py` define LLMProvider e adaptadores Google, OpenAI compatível e Anthropic, construção de contexto, contrato JSON, validação e cache. `ai_config.py` valida protocolo, modelo e endereço. A chave chega por POST protegido ou ambiente e fica em memória. Só preferências sem chave são persistidas. O navegador recebe somente status de presença/modelo. Cada job captura o provedor configurado antes de iniciar.

Fluxo: IR validada → seleção de fatos com IDs → limite de 32.000 bytes → API escolhida → JSON estruturado → validação de esquema/IDs → enriquecimento com evidências originais → AI.md e AI.json. O modelo não fornece caminhos/linhas usados na exportação: os IDs são resolvidos pela aplicação para evidências da IR.

As explicações são sempre inferred ou unconfirmed; nunca extracted. Inferências exigem IDs válidos e informações não confirmadas não podem alegar evidências. A validação comprova a existência da referência, não o significado da afirmação. Prompts tratam todos os dados do repositório como não confiáveis; isso não constitui uma garantia absoluta contra prompt injection.

Uma chamada, sem retry automático. Em erros de rede, chave/cota ou resposta inválida, o job conclui a parte estática e expõe o erro de IA separadamente. O cache mantém até oito resultados válidos por provedor/endereço/contexto/commit/modelo, só na sessão. Nenhuma chave ou corpo de erro bruto é registrado ou exportado.

## Mapas e histórico (0.6.0)

`insights.py` deriva cobertura e snippets limitados de fontes já filtradas. Referências preservam arquivo/linhas/versão. Snippets têm cerca de 30 linhas, 400 caracteres por linha, até 1.500 referências e 2 MB por análise; são mostrados por nós DOM e escapados no HTML.

`history.py` salva metadata/payload em SQLite com operações parametrizadas e uma conexão por operação. O servidor local usa LOCALAPPDATA/OctorGit no Windows; --data-dir permite substituição. A API expõe as 100 análises recentes, preservando registros antigos. Falha de gravação aparece no resultado, que continua em memória para exportação.

`compare_analyses` exige identidade de repositório igual e compara multiconjuntos método/rota/escopo, configurações declaradas e hashes de arquivos. Não executa Git nem presume ancestralidade entre os SHAs. Alteração de arquivo de evidência é indicação conservadora de revisão; não prova mudança semântica de cada endpoint. Parser/raiz diferentes geram avisos.

`reports.py` produz seis SVGs e HTML independente sem scripts/recursos externos. A tela usa os mesmos SVGs e o relatório em iframe same-origin com scripts bloqueados. Imprimir/salvar PDF é função do navegador, sem dependência adicional na instalação. A CLI também exporta o relatório e os SVGs, mas não mantém histórico SQLite; isso pertence ao aplicativo local.

## Configuração dos endpoints

A IR 0.2.0 inclui permissions e configuration com evidências por campo. São reconhecidos atributos/decorators diretos, herança local simples, @action e defaults literais únicos de REST_FRAMEWORK para views DRF. Lista vazia é declaração explícita; não é confundida com ausência de informação. Getters dinâmicos impedem afirmar uma configuração efetiva. A declaração não comprova comportamento em runtime.

## Tecnologias — 0.6.0

`technology.py` examina extensões, manifests conhecidos, DATABASES literal, Dockerfile, Compose, Kubernetes, Terraform e Render sem executar comandos ou carregar dependências. Mantém evidências e distingue clientes de servidores declarados. `reports.py` gera ícones e relações estáticas; não usa IA para inventar imagens. Hospedagem não detectada é explicitamente não confirmada. Primeiro contato foi removido da interface e relatório.

## Administração de consumo — 0.7.0

`ai_usage.py` mantém ledger SQLite separado, com tarifas por hash de provedor/endereço/modelo e política global de orçamento/pausa. `MeteredProvider` registra antes da chamada e finaliza com tokens numéricos normalizados, inclusive quando o adaptador rejeita uma resposta após receber metadados. O cache de DocumentationEngine evita chamar o wrapper novamente. Tokens não fornecidos ficam null. Eventos interrompidos permanecem started, sem alegar cobrança zero. Custos usam Decimal e a tarifa capturada na abertura. O painel usa mês UTC e distingue subtotal conhecido de registros sem custo. Chamadas da CLI não são instrumentadas. GET /api/ai/usage retorna resumo mensal e 50 eventos; POST protegido salva tarifas/política com verificação de perfil para evitar salvar preços no destino errado.
