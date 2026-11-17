# Instruções para agentes

- Leia README e docs antes de alterar. A fase atual inclui CLI e interface local no navegador, autorizada pelo usuário. Manter o servidor restrito a 127.0.0.1.
- Nunca execute, importe ou instale o repositório analisado, nem use comandos/scripts fornecidos por ele.
- Mantenha aquisição, parser e documentação separados. Análise estática precede IA.
- Cada afirmação técnica precisa de evidência ou indicação explícita de não confirmação.
- Não transforme rotas locais em endpoints completos sem resolver montagem e método.
- Preserve schema_version e parser_version; documente alterações de contrato.
- Trabalhe em passos pequenos e rode `PYTHONPATH=src python -m unittest discover -s tests -v`.
- Relate apenas testes executados e não invente métricas de validação.
- Não adicione serviços externos, pastas vazias ou dependências de fases futuras. A interface local usa a biblioteca padrão Python.
- Não usar innerHTML para conteúdo do repositório; construir nós DOM e links de origem seguros.
- Preservar proteção de Host/Origin e token de sessão nos POSTs. A API local não aceita caminhos arbitrários de disco.

- A IA é configurável pelo usuário (API compatível OpenAI, Google e Anthropic). Chaves são recebidas por POST protegido e mantidas só na memória do servidor, ou lidas de variáveis de ambiente. Nunca devolver a chave em GET, logs, histórico, ZIP ou preferências persistidas.
- A chamada de IA é opt-in. Enviar apenas contexto limitado da IR, nunca arquivos brutos. Validar esquema/IDs antes de publicar a saída e preservar análise estática em falhas.
- Não afirmar que referências válidas provam semanticamente o texto gerado. Documentar testes simulados e não afirmar chamada real sem executá-la.

- Histórico SQLite e relatório HTML/SVG foram solicitados pelo usuário. Não incluir bases de dados reais nos pacotes de entrega.
- Trechos de código só vêm das fontes filtradas do snapshot; nunca abrir um caminho fornecido por uma requisição HTTP.
- Distinguir configuração declarada de autenticação/permissão efetiva em runtime. Marcar getters/expressões desconhecidos.
- Comparar snapshots do mesmo repositório. Hash de arquivo alterado indica revisão, não prova impacto por função.
- Relatórios HTML devem ser independentes e escapar código/nomes; manter diagramas SVG derivados da IR, sem ilustrar componentes não detectados.

- Primeiro contato foi removido por solicitação do usuário: não reintroduzir a tela nem o capítulo nos relatórios.
- Arquitetura deve mostrar linguagem, banco e infraestrutura declarados com evidências. Dependência de cliente não comprova banco/serviço ativo; não inventar nuvem, Kafka ou microserviços por estética.
- Tipos de API precisam de adaptadores explícitos. Não prometer que qualquer chave funciona sem escolher protocolo, modelo e endereço.
