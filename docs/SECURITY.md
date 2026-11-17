# Segurança e limites

Não executar código é um requisito: não importar módulos do alvo, executar Git com configuração do alvo, instalar dependências nem executar setup.py, comandos de README ou Dockerfiles. O downloader só aceita URLs HTTPS de owner/repo no GitHub. Não suporta credenciais ou URLs arbitrárias.

O tar é percorrido sem extração: links e membros especiais são descartados; caminhos absolutos e traversal são rejeitados pelos filtros. No modo local, links simbólicos são ignorados; use apenas fixtures locais confiáveis, sem modificações concorrentes. Este modo não é um sandbox contra corrida de filesystem.

Limites iniciais: arquivo de download 20 MiB comprimidos; soma declarada de membros 50 MiB; 512 KiB por arquivo; 10 mil entradas; timeout de rede por operação de 30 segundos. Esses controles **não equivalem a isolamento de CPU/memória, deadline global ou proteção completa contra arquivos comprimidos adversariais**. Não exponha esta CLI como um serviço público antes de implementar execução isolada, limites de recursos e quotas.

Filtros excluem diretórios comuns, nomes sensíveis, binários e alguns padrões de credenciais. A detecção é heurística: não garante encontrar todo segredo. A IR contém nomes, caminhos, rotas e metadados que também podem ser sensíveis. Markdown gerado de entradas não confiáveis deve ser visualizado com HTML desativado e sanitização adequada.

Sem a opção IA, nenhum dado é enviado a LLM. Com ela, contexto selecionado da IR vai ao provedor selecionado e a credencial é enviada somente no header de autenticação da API configurada. O código bruto não é enviado. O GitHub recebe as requisições públicas de metadados e snapshot. Ao integrar IA, enviar apenas o contexto mínimo da IR, informar o usuário, tratar texto do alvo como dado não confiável e validar resposta estruturada. Não registrar conteúdo ou tokens em logs.

Os limites e filtros devem ganhar testes adversariais adicionais antes do MVP web. Privados, OAuth, retenção e LGPD continuam fora desta fase.

## Interface local (0.3.0)

Servidor apenas em 127.0.0.1; não oferecemos opção de host público. Host e Origin são restritos aos endereços loopback autorizados, e POST exige token aleatório da instância. A API não aceita upload, caminhos de disco, shell ou comandos do repositório. Uma análise por vez, até oito resultados em memória, JSON de entrada limitado a 4 KiB.

HTML e scripts são locais e empacotados. Conteúdo do repositório é renderizado como texto/nós DOM, com links HTTPS de evidência por commit e CSP sem scripts inline. Markdown é exibido por um renderizador deliberadamente limitado; HTML do repositório nunca é interpretado. O SVG usa somente texto e nós criados pela aplicação.

A biblioteca http.server destina-se ao protótipo local, não a produção. Permanecem as limitações de isolamento de parser, CPU/memória e deadline global já descritas. Não crie túneis nem exponha este servidor na rede. A análise por URL usa o GitHub; nenhuma integração com Google Drive faz parte do aplicativo. As entregas são publicadas no GitHub.

## IA configurável (0.6.0)

Chave por POST com token/Host/Origin ou ambiente; mantida apenas na memória do servidor. Não aparece em GET, logs, histórico, ZIP ou ai-settings.json. O arquivo de preferências guarda somente provedor/modelo/endereço. HTTPS obrigatório, exceto loopback para APIs locais. URLs com credenciais/query/fragment são rejeitadas; redirects HTTP não são seguidos. Credenciais são enviadas em headers. Erros não incluem corpo bruto; respostas que refletem a própria chave são rejeitadas. Troca de destino limpa a chave, e jobs em andamento mantêm a configuração capturada no início.

A chamada é opt-in e pode consumir cota. O teste de conexão envia somente fatos sintéticos. O usuário escolhe o destino confiável e suas políticas de retenção; não prometemos retenção zero do provedor.

Validação aceita somente um contrato JSON pequeno e IDs de fatos selecionados existentes. HTML/Markdown gerados não são executados; textos são escapados na exportação e exibidos por nós DOM. A validação de referência não comprova a semântica do texto nem elimina todo risco de alucinação. Contexto continua parcial e filtragem de dados sensíveis permanece heurística.

## Histórico e relatórios (0.5.0)

A pedido do usuário, SQLite local persiste resultados e trechos de código já filtrados. O filtro de segredos continua heurístico; não promete capturar toda credencial. O banco não armazena chaves de IA nem o snapshot completo. A pasta de dados é escolhida no início do processo, nunca por requisições do navegador. SQL usa parâmetros e os IDs só consultam artefatos salvos.

Snippets e mapas ficam apenas no computador do usuário e nos arquivos que ele exportar. A opção IA continua enviando apenas fatos da IR, nunca snippets de código. Para excluir o histórico, fechar o aplicativo e remover o SQLite da pasta escolhida. Arquivos de dados não entram no ZIP do programa.

Relatório HTML não contém scripts, carregamentos externos ou handlers. Todos os nomes/códigos são escapados; SVG usa formas/textos controlados pelo gerador. O relatório recebe CSP distinta que permite apenas seu CSS inline e framing pela própria origem; a aplicação principal continua sem scripts inline. A impressão para PDF é manual no navegador.
