# Plano de validação do MVP

Não há evidência nesta entrega para afirmar 90% de recall, 95% de referências válidas em documentação de IA ou preferência de usuários.

Selecione 10 projetos públicos Django/DRF: pelo menos dois simples, três com includes aninhados, três com routers/ViewSets e dois maiores com padrões dinâmicos. Registre URL, licença, branch, SHA e motivo da escolha. Não use só fixtures que espelhem o parser.

Para pelo menos três, crie um gabarito manual por SHA com método, rota completa, arquivo e linha. Faça revisão por outra pessoa quando possível. Não use a saída do parser como gabarito.

| Métrica | Cálculo |
| --- | --- |
| Precisão | Endpoints corretos / endpoints emitidos |
| Recall | Endpoints corretos / endpoints no gabarito |
| Referências válidas | Referências verificadas / referências emitidas |
| Cobertura | Python analisados / Python elegíveis; relatar também exclusões |
| Tempo | Tempo total por análise, máquina e SHA registrados |
| Tokens/custo | Não aplicável enquanto não existir LLM |

Uma rota local com método desconhecido não conta como endpoint completo correto. Defina política de equivalência de parâmetros e barras finais antes de medir.

Compare as mesmas tarefas e SHAs em duas ferramentas concorrentes; registre versão, data, saída e critérios. Depois teste com 5–10 desenvolvedores, distribuindo grupos e projetos para reduzir o efeito de aprendizado. Use cinco perguntas fixas e registre tempo, acerto, utilidade, confiança e intenção de reutilização.

Gate proposto: detecção correta de pelo menos 90% dos endpoints, mais de 95% de referências válidas e cinco desenvolvedores preferindo a saída em utilidade e confiança. Se falhar, corrigir análise antes de desenvolver a interface.

## Benchmarks incrementais disponíveis

Há três fixtures com gabaritos explícitos em `tests/fixtures/*/expected.json` e um gabarito público parcial em `docs/benchmarks/rest-framework-tutorial.json`. Eles foram escritos por inspeção estática, ainda sem revisão humana independente. Os relatórios entregues registram escopo e exclusões; não extrapolar os resultados para o projeto inteiro ou para dez repositórios.

Gabaritos usam caminhos sem barra inicial sintética. Não equivalem `{pk}` de DRF a qualquer conversor Django. Duplicatas e métodos desconhecidos são erros, não acertos parciais. Os manifests declaram a exclusão de HEAD/OPTIONS automáticos.

Para o benchmark público, `route_files` seleciona apenas as rotas de negócio de `snippets/urls.py`; schema/docs e dependências de login não contam no denominador. O relatório registra quantidade de emissões fora do escopo e diagnósticos pendentes. Um avaliador deve revisar as exclusões antes de adotar os números.
