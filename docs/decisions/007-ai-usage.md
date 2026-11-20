# ADR 007 — Administração local de consumo de IA

O usuário solicitou administrar a API e acompanhar tokens/custos. Medir cada chamada externa por wrapper de provedor, incluindo testes de conexão, em ledger separado persistente. Cache local não gera novo evento de chamada. Registrar tentativa antes da rede e preservar desconhecidos em falhas/interrupções.

Preços em USD por milhão de tokens são informados pelo usuário por perfil; não consultar APIs de faturamento ou prometer saldo universal. Capturar tarifas no início e preservar histórico. Orçamento mensal UTC é aviso global; pausa manual impede novas chamadas externas. Guardar somente metadados de consumo, sem chaves/prompts/respostas. Manter análise estática disponível.
