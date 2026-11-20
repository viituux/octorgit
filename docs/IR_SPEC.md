# IR 0.3.0

Contrato inicial de rotas introduzido em 0.1.0: endpoints podem representar pares método/rota completos ou rotas com método desconhecido. Parser atual: 0.6.0. Cada registro de domínio e evidência leva `schema_version` e `parser_version`; métricas são agregados.

| Campo | Conteúdo |
| --- | --- |
| repository | URL, branch/ref, SHA e origem; SHA nulo em fixtures locais |
| files | Caminho, linguagem, SHA-256 UTF-8 e linhas |
| symbols | ID `arquivo:nome.qualificado`, nome, tipo e evidência |
| imports | Origem, destino textual, `resolved`, `target_file` e evidência |
| relations | Relações `imports` entre arquivos locais identificados |
| endpoints | Método/rota, view, escopo, confiança e cadeia de evidências |
| routing | Arquivos de raiz, seleção e política de métodos automáticos |
| diagnostics | Limitações, ambiguidades e erros de parsing detectados |
| skipped | Caminho excluído e motivo; sem conteúdo |
| metrics | Cobertura de parsing entre arquivos Python aceitos |

## Endpoints

- `route`: caminho sem barra inicial adicionada; concatenação literal dos prefixos `path`.
- `route_kind`: `path`, `regex` (sem montagem aninhada) ou `drf_template`.
- `method`: HTTP em maiúsculas ou null quando desconhecido.
- `view`: nome qualificado resolvido quando possível; no router, inclui a ação.
- `scope`: `configured_root` (ROOT_URLCONF único), `explicit_root` (argumento) ou `local_urlconf` (prefixo desconhecido).
- `confidence`: `extracted`, `inferred` (convenções de router), `unconfirmed` (método desconhecido).
- `evidence`: declaração principal da rota/registro.
- `evidence_chain`: configuração, montagens, construtor/registro do router e classe/método/decorator quando identificados.
- `unknown_fields`: campos realmente desconhecidos entre serializer, permissions, authentication, método e prefixo.

`drf_template` usa `{pk}` para o lookup padrão `[^/.]+`, sem prometer semântica de conversores Django. Métodos HEAD/OPTIONS automáticos, API root e formatos não são enumerados. Registrá-los como lacuna evita uma alegação de cobertura completa.

Import resolvido significa arquivo local encontrado, não prova de resolução de qualquer atributo em runtime. Relações são de arquivo, não de dependência semântica completa. Não há importação real nem avaliação de expressões.

## Evidências

`file`, `symbol` (ou null), `start_line`, `end_line` inclusivas e `confidence`. O validador percorre também `evidence_chain` e verifica arquivo, linhas e existência do símbolo na IR. Não prova semanticamente que a inferência é verdadeira em runtime. Hash do arquivo usa texto UTF-8 sem normalização de linhas.

Alterações incompatíveis futuras exigem nova versão e atualização dos consumidores.

## Mudança em 0.2.0

`serializer`: nome qualificado ou null. `permissions` e `authentication`: listas de nomes qualificados (incluindo lista vazia explicitamente declarada) ou null. `configuration` contém um registro versionado para cada campo, com value, confidence e evidence_chain. Os links apontam para declarações estáticas; não garantem aplicação efetiva em runtime.

Getters dinâmicos e expressões não resolvidas continuam com value null. Defaults globais só são aplicados como declaração quando REST_FRAMEWORK é literal/único e a view é reconhecida como DRF, sem override dinâmico. Não importar configurações do alvo.

Cobertura, snippets, timeline e comparação são artefatos derivados do resultado. Ficam fora da IR para não misturar observações de código com apresentação, persistência ou sugestões de leitura. Os resultados API incluem insights, history e previous_id; o SQLite preserva o payload vinculado às versões.

## Mudança em 0.3.0

`technology` contém `languages`, `components`, `relations` e notas de limite. Componentes incluem kind, scope, confidence e evidence_chain. Relações distinguem configuração literal de banco, depends_on e contexto de build. Dependência de driver/cliente não confirma servidor em execução. Extensões identificam linguagens, sem habilitar novos parsers de endpoints. O capítulo/tela de primeiro contato foi removido; resultados antigos devem ser reanalisados para obter este contrato.

## Parser 0.6.1 — contrato IR 0.3.0 preservado

Diagnóstico `auxiliary_file_excluded_from_endpoints` identifica arquivos de pastas auxiliares omitidos da resolução Django. Inventário e símbolos permanecem disponíveis; imports/rotas são resolvidos somente nos arquivos da aplicação. Tecnologia usa scope `sqlite_connection` e relação `database_configuration` para chamadas SQLite estaticamente reconhecidas, sem alegar execução.

## Parser 0.8.0

`repository.private` informa a visibilidade confirmada na API GitHub quando autenticado; resultados antigos/fixtures podem omitir esse campo. Conteúdo privado só pode alimentar IA na interface após consentimento explícito por análise. Nenhuma credencial integra a IR.
