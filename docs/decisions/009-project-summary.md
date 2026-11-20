# ADR 009 — Resumo de projeto por categorias

Solicitação do usuário: a IA deve analisar e escrever cada categoria de um resumo estruturado, em um padrão de documentação de projetos, sem despejar todo o inventário.

Definir nove categorias obrigatórias, uma chamada de IA por geração, limites de texto e referências por IDs. Não completar categorias ausentes com texto supostamente gerado pela IA; rejeitar e preservar a análise estática. Manter propósito de negócio, execução, testes e implantação desconhecidos quando o contexto não sustentar afirmações.

Separar resumo principal de anexo técnico completo. Preservar AI.md por compatibilidade, introduzir PROJECT.md e template_version. Resultados históricos continuam legíveis; novas gerações usam o novo contrato. Referências válidas não comprovam significado, e testes simulados não medem qualidade em projetos reais.
