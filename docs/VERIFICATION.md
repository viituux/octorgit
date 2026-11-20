# Visual Stitch 0.9.0 — 20/11/2026

- 110 testes Python passaram, incluindo estrutura HTML, seletores, fontes locais, proteção de caminhos e contratos anteriores.
- Unidades DOM em Node passaram para canvas, painéis de evidências, busca, abas, índice de documentação e preparação da exportação. O harness não é um navegador e não valida CSS/layout.
- JavaScript e Bash passaram na verificação de sintaxe. Fluxo HTTP de demo, imagem, relatório com seis SVGs e ZIP conferido.
- Não houve inspeção interativa em navegador: o ambiente não disponibiliza o controlador de preview. Não foi instalado um navegador alternativo.
- Cinco PNGs e HTMLs do ZIP do Stitch foram inspecionados como referência. Código remoto, handlers inline e dados fictícios do protótipo não foram incorporados ao runtime.

# Conexão GitHub 0.8.0 — 20/11/2026

107 testes locais passaram. Novos testes cobrem conexão/desconexão, token em header, hosts e redirects, paginação, snapshot privado por SHA com branch explícita, proteção HTTP, consentimento de IA e ausência da credencial no histórico/exports. Foram usados tokens e respostas sintéticos; não foi usado um token pessoal real nem baixado um repositório privado real nesta versão. Não houve inspeção interativa do navegador.

# Administração de IA 0.7.1 — 20/11/2026

100 testes locais passaram, com regressão de timestamps idênticos para ordenação determinística no Windows, incluindo consumo/custo Decimal, dados desconhecidos, persistência sem segredo, troca de tarifas/perfil, pausa, cache, raciocínio, falhas com tokens reportados e API HTTP protegida. Integrações usam transporte/respostas simulados, sem chamada autenticada real nem verificação de fatura. A inspeção interativa do navegador não foi executada nesta versão.

# Correções de precisão 0.6.1 — 20/11/2026

89 testes passaram localmente, incluindo seis novos testes de regressão com variações: separação de endpoints auxiliares, fixture como raiz, Compose com chaves aninhadas/indentação diferente e SQLite com aliases/sombreamento/import isolado. Nenhuma chamada de IA foi necessária.

# Verificações 0.6.0 — 17/11/2026

- 83 testes unittest passaram localmente: tecnologias/evidências, mapas/relatórios, configurações sem persistir chave, transporte simulado dos três adaptadores, isolamento de cache e API local.
- SVG de arquitetura renderizado com Inkscape e inspecionado como imagem. Não houve teste interativo do navegador nesta versão.
- Nenhuma chamada autenticada real a provedores de IA. Compatibilidade final depende de modelo, protocolo, conta e cota.
- Identificação de linguagens é por extensão; extração de endpoints continua limitada a Python/Django/DRF. Infraestrutura é declaração estática, não observação de runtime.
- O gate de dez repositórios e cinco desenvolvedores continua pendente. Resultados de benchmarks anteriores abaixo não foram ampliados nesta versão.

# Windows e Linux — 0.5.1 — 17/11/2026

- Suite local: **65 testes passaram**. Inicializador Linux exercitado a partir de outra pasta, incluindo HTTP e histórico.
- Correção de portabilidade: poda de diretórios locais usa caminhos POSIX no filtro, inclusive no Windows.
- Inicializadores separados: ABRIR_OCTORGIT.bat (CRLF) e ABRIR_OCTORGIT.sh (LF, executável, Bash).
- Python 3.11+ e navegador são necessários. Não são binários .exe/AppImage independentes de Python.
- Histórico respeita LOCALAPPDATA no Windows e XDG_DATA_HOME/fallback .local/share no Linux.
- Workflow GitHub Actions adicionado para Windows/Linux com Python 3.11 e 3.14; execução remota aprovada nas quatro combinações, no commit fde9e94e3acfca1a6fade8c435a72a44f68f55b6. Run: https://github.com/viituux/octorgit/actions/runs/44146982322.
- Teste de links simbólicos pode ser pulado no Windows se o sistema não conceder a permissão específica; as demais verificações continuam.

Verificações da versão anterior, com seus próprios escopos:

# Verificações 0.5.0 — 17/11/2026

IR 0.2.0, Python 3.12.14 no ambiente Linux.

- Suite completa: **62 testes passaram**. Sintaxe JavaScript: node --check passou.
- Guia e snippets conferidos contra linhas reais das fixtures.
- Metadados de serializer/permissão/autenticação, overrides de ação, defaults DRF e getters dinâmicos testados com validação de evidências.
- Persistência: resultado e snippets recuperados por uma nova instância de Jobs e após reiniciar o servidor HTTP. Cache de oito entradas não apaga análises do SQLite. Falha de gravação gera aviso e preserva resultado em memória.
- Comparação de demo: rota health/ removida, status/ adicionada e permissão alterada; documentos sinalizados para revisão. Diferença de parser/escopo não é tratada como prova de mudança de código.
- Seis SVGs validados como XML sem scripts/imagens externas. HTML independente incorpora os seis, escapa código e tem CSS de impressão.
- Rotas HTTP de relatório, SVG, comparação e ZIP verificadas, incluindo base inexistente e seleção sem comparação.
- Uma imagem do SVG de arquitetura foi rasterizada e inspecionada, com agrupamentos e conexões azuis. Isso não equivale a inspeção visual da interface no navegador.
- Caso público reavaliado nesta versão: 9/9 endpoints no escopo de negócio do manifesto rest-framework-tutorial (zero FP/FN); ver docs/benchmarks/public-result-v05.json. O escopo parcial não corresponde ao projeto inteiro.
- Preview de navegador continua indisponível: a ferramenta exigida pelo ambiente gerenciado não está presente. Não foi executado teste nativo em Windows nem geração de PDF por Edge/Chrome.
- Gemini permanece opcional e testado com respostas simuladas; não houve nova chamada autenticada. O gate de dez repositórios e cinco desenvolvedores continua pendente.

Artefato de exemplo: examples/relatorio-visual/RELATORIO-EXEMPLO.html, baseado em fixtures autorais sem SHA real. Informações históricas das entregas anteriores estão abaixo.

# Verificações Gemini — 16/11/2026

Versão 0.4.0, IR 0.1.0, Python 3.12.14.

- Suite completa: **46 testes passaram**, incluindo os 34 testes anteriores.
- Integração Gemini testada com transporte/respostas simulados, sem chave real.
- Testes cobrem: contexto limitado, ausência de código bruto, JSON estruturado, IDs inventados, rejeição de falso nível extracted, chave ausente, erro de cota/permissão sanitizado, saída truncada, cache por commit e preservação dos documentos estáticos em falha.
- Serviço local testado com geração simulada de AI.md e AI.json.
- A credencial colada na conversa não foi usada em chamadas, arquivos ou testes.
- **Chamada real autenticada ao Gemini não executada**. Compatibilidade da chave/modelo/cota será verificada no computador do usuário com uma nova chave.
- Inspeção visual de navegador e execução nativa no Windows continuam não verificadas neste ambiente; a ferramenta de preview necessária não está disponível.

Referências oficiais consultadas nesta entrega: https://aistudio.google.com/docs/api-key e https://aistudio.google.com/api-reference/generate-content. O endpoint generateContent segue suportado; a integração não usa o novo fluxo de Interactions.

As verificações anteriores abaixo são históricas e mantêm seus respectivos escopos.

# Verificações da interface local — 16/11/2026

Versão 0.3.0, IR 0.1.0, Python 3.12.14 no ambiente Linux desta conversa.

| Verificação | Resultado |
| --- | --- |
| `PYTHONPATH=src python -m unittest discover -s tests -v` | 34 testes passaram |
| `node --check src/octorgit/static/app.js` | Sintaxe JavaScript válida |
| Contrato HTML/JS | Seletores literais conferidos e IDs únicos |
| Fluxo HTTP de demo | Início, progresso, 11 registros, evidências, documentos e ZIP |
| Fluxo HTTP público real | 27 arquivos aceitos, 16 símbolos, 11 registros, 2 diagnósticos |
| Wheel Python | Construído com HTML/CSS/JS/demo e verificado fora do checkout |
| Host/Origin/token e entrada local arbitrária | Rejeições testadas |
| Concorrência e histórico | Uma análise ativa e retenção de até oito resultados |

O fluxo público usou https://github.com/encode/rest-framework-tutorial no SHA `68c0f79c37bbda4f665711446ee32cbf9f54de7d`. Dois dos onze registros têm método desconhecido (schema/docs de dependência externa). Não houve execução do código alvo.

## Limites de verificação desta interface

A inspeção visual e os cliques em navegador **não foram realizados**: o ambiente não disponibilizou a ferramenta de navegador necessária ao preview gerenciado. Foram testados o serviço HTTP, os recursos empacotados, o contrato de seletores e a sintaxe JS. Não afirmar teste visual ou teste nativo de Windows. O launcher .bat foi inspecionado e usa CRLF/ASCII, mas não foi executado em Windows neste ambiente.

A interface usa CSS responsivo, controles semânticos, navegação por teclado, texto seguro no DOM e estados de vazio/progresso/falha. A experiência visual ainda deve ser conferida em Edge/Chrome no computador do usuário.

## Gate de qualidade do parser

A interface foi solicitada antes da validação completa do MVP. Os resultados incrementais anteriores e seus escopos permanecem abaixo; não contam como validação em dez projetos ou com cinco desenvolvedores.

# Verificações — 16/11/2026

Parser 0.2.0, IR 0.1.0, Python 3.12.14. Nenhum código dos projetos analisados foi executado; não foi necessário instalar Django/DRF.

| Verificação | Resultado |
| --- | --- |
| `PYTHONPATH=src python -m unittest discover -s tests -v` | 26 testes passaram |
| Três fixtures com manifests revisáveis | 20 acertos, 0 falsos positivos, 0 falsos negativos |
| Repositório público, escopo de negócio selecionado | 9 acertos, 0 falsos positivos, 0 falsos negativos |
| CLI via console script instalado, raiz config.urls, fixture DRF | 10 pares método/rota, 1 diagnóstico |
| Validação de evidências do exemplo local e público | Passou, incluindo cadeias |

## Caso público e limites dos resultados

URL: https://github.com/encode/rest-framework-tutorial

SHA: `68c0f79c37bbda4f665711446ee32cbf9f54de7d`.

O manifesto seleciona apenas rotas de negócio registradas em `snippets/urls.py`. Inclui ações ModelViewSet, ReadOnlyModelViewSet e highlight. Não inclui métodos automáticos, API root, variantes de formato, login/logout ou schema/docs. Foram emitidas outras duas rotas fora desse escopo, com método desconhecido. Portanto 9/9 **não é recall do projeto inteiro**.

Os gabaritos foram escritos por inspeção estática nesta implementação, sem derivar a lista esperada da saída do parser. Ainda precisam de revisão humana independente. Três fixtures e um caso público parcial não substituem dez repositórios reais nem testes com cinco desenvolvedores.

O relatório público mantém diagnósticos para a API root/formatos e o módulo externo `rest_framework.urls`. Métodos das views externas de schema/docs permanecem não confirmados. Serializer/autenticação continuam não confirmados em todos os resultados.

## Artefatos e reprodução

- `tests/fixtures/*/expected.json`: expectativas dos três projetos sintéticos.
- `docs/benchmarks/rest-framework-tutorial.json`: gabarito público, SHA, fontes por linhas e exclusões.
- `docs/benchmarks/fixture-result.json` e `public-result.json`: relatórios executados.
- `examples/generated/`: exemplo local atualizado.
- `examples/public-generated/`: análise pública com referências por commit, sem snapshot do código.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m octorgit.benchmark --fixtures tests/fixtures --output results/fixtures.json
PYTHONPATH=src python -m octorgit.benchmark --public-manifest docs/benchmarks/rest-framework-tutorial.json --output results/public.json
```

Escolha arquivos de relatório novos; o benchmark recusa sobrescrita. O teste público requer rede e está sujeito ao rate limit anônimo do GitHub. Os testes unitários não usam rede.

A instalação editável já foi verificada na entrega inicial. O console script existente foi exercitado nesta atualização; o pyproject agora declara 0.2.0. A próxima instalação atualizará também os metadados da distribuição.
