# ADR 002 — Montagem de rotas com escopo e evidências

Status: adotada no parser 0.2.0 / IR 0.1.0.

Selecionar raiz explicitamente ou por ROOT_URLCONF literal único. Nunca inferir que um URLconf solto é a raiz do projeto. Manter modo local quando houver ambiguidade.

Expandir includes e routers por regras estáticas, sem carregar Django nem o projeto. Separar métodos extraídos de convenções inferidas do DRF. Registrar a cadeia de evidências e as lacunas.

Medir pares método/rota contra gabaritos explícitos; publicar o escopo e contar duplicatas/métodos desconhecidos como erros. Gabaritos sintéticos e um caso público parcial não atendem ao gate de dez repositórios e cinco desenvolvedores.

IR 0.1.0 muda semântica/estrutura dos endpoints; consumidores de 0.0.1 precisam migrar. Configurações dinâmicas permanecem não confirmadas.
