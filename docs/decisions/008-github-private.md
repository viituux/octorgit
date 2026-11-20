# ADR 008 — Conexão GitHub com acesso privado

Solicitação do usuário: conectar a conta e analisar repositórios privados. A conexão do ChatGPT não fornece credencial distribuível ao aplicativo local. Usar token pessoal explícito em memória, preferencialmente fine-grained Contents Read-only, sem OAuth ou armazenamento de segredo. Listar repositórios acessíveis e resolver snapshots por SHA. Reaproveitar limites/filtros sem executar o alvo.

Confirmar visibilidade por metadados e exigir consentimento separado para IA em projetos privados. Preservar histórico local com avisos claros e não colocar dados privados reais nos exemplos ou releases. Desconectar não apaga histórico ou revoga a credencial no GitHub.
