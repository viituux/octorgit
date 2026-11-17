# ADR 004 — Gemini opcional com referências por IDs

Status: adotada em 0.4.0 a pedido do usuário.

Usar um único provedor, Google Gemini, pela REST generateContent, ainda suportada oficialmente, mantendo a instalação sem dependências adicionais. Credencial somente por variável de ambiente do servidor, nunca hardcoded ou em arquivos de entrega.

Enviar fatos selecionados da IR, sem arquivos brutos. Exigir JSON, referências por IDs e separar inferred/unconfirmed. Enriquecer referências por código e preservar resultados estáticos se a IA falhar. Não alegar que a checagem de referência comprova a afirmação.

Limitar contexto, resposta e tokens; uma chamada, sem retries automáticos, e cache limitado à sessão. Tokens são medidos quando o provedor os informa; custo em moeda ainda não é calculado. Geração real autenticada depende de nova chave válida configurada pelo usuário.
