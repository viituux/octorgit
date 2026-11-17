# ADR 006 — Tecnologias visuais e IA configurável

Substitui a restrição de provedor único do ADR 004. Solicitação do usuário: remover Primeiro contato, desenhar arquitetura com linguagem/banco/infra e permitir configurar a própria IA.

Gerar SVG determinístico de evidências estáticas, sem inventar serviços ou relações por estética. Separar imports de tecnologias e distinguir configuração de execução. Oferecer adaptadores explícitos OpenAI compatível, Google e Anthropic. A chave da tela permanece só em RAM; persistir apenas preferências sem segredo. A análise estática continua independente da IA.
