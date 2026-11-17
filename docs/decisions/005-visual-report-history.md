# ADR 005 — Mapas vetoriais, evidências locais e histórico por snapshot

Status: adotada em 0.5.0 por solicitação do usuário.

Gerar diagramas SVG determinísticos de fatos extraídos e agrupamentos explicitamente inferidos. Seguir a referência visual com grupos, cartões e conexões azuis; não inventar infraestrutura de nuvem ou diagramas de execução.

Exportar HTML independente com SVGs incorporados, explicações e trechos, com impressão para PDF pelo navegador. Evitar serviços de renderização externos e dependências adicionais no Windows.

Persistir análises em SQLite local por ID, identidade de repositório e SHA/fingerprint. O cache de memória tem oito entradas, mas registros não são apagados automaticamente do disco. Mostrar até 100 recentes e preservar dados entre versões do app. Snippets são limitados e vêm só do snapshot filtrado.

Comparar fatos observados e hashes, marcando documentos para revisão. Destacar parser/raiz diferentes e não afirmar impacto semântico ou completude. Configuração declarada de serializer/permissões/autenticação recebe evidências próprias na IR 0.2.0; lógica dinâmica continua desconhecida.
