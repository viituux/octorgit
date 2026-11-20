# Configurar a IA — Windows e Linux

1. Inicie o aplicativo e abra **Administração de IA** no menu.
2. Escolha API compatível com OpenAI, Google ou Anthropic.
3. Informe um modelo disponível na sua conta e o endereço base correspondente.
4. Cole a chave no campo de senha e salve. O teste de conexão faz uma chamada pequena e pode consumir cota.
5. Marque **Usar IA** antes de analisar. Veja o resultado em **Documentação → IA**.

A chave fica só na memória do servidor; reiniciar exige informá-la novamente. Modelo, provedor e endereço são salvos sem a chave. Trocar o provedor ou endereço limpa a chave anterior. Nunca coloque a chave na URL. HTTPS é obrigatório, exceto para APIs locais em loopback. Uma API proprietária exige adaptador próprio; qualquer chave não significa qualquer protocolo.

Para CLI ou configuração por ambiente, defina `AI_PROVIDER` (`openai-compatible`, `google` ou `anthropic`), `AI_BASE_URL`, `AI_MODEL` e `AI_API_KEY`. Use o gerenciador de segredos ou a configuração de ambiente da sua máquina; não grave credenciais no código. A CLI usa `--ia`. As variáveis legadas `GEMINI_API_KEY` e `GEMINI_MODEL` permanecem aceitas por compatibilidade.

Sem IA, a análise estática e todas as imagens continuam funcionando. Falhas de chave, cota, modelo ou resposta inválida não removem os documentos estáticos.

## Custos e consumo

Na mesma tela, informe as tarifas oficiais de entrada e saída em USD por milhão de tokens. Deixe vazio se não souber; zero só deve ser usado quando a tarifa for realmente gratuita. O orçamento mensal é um aviso, e a pausa é manual. Tarifas só afetam chamadas futuras. O painel não consulta o saldo ou fatura do provedor e não registra chamadas da CLI. Testes de conexão também entram no consumo.
