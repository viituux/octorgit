# ADR 003 — Interface local por solicitação do usuário

Status: adotada na versão 0.3.0.

O usuário pediu explicitamente telas após experimentar a CLI no Windows. Adicionar uma interface local antes da validação completa; isso não significa que o gate de qualidade foi alcançado.

Reusar parser/exportador por um servidor loopback da biblioteca padrão e HTML/CSS/JavaScript empacotados. Evitar Node, banco, serviços externos e setup adicional para o usuário Windows. O launcher .bat abre o navegador usando o código da própria pasta.

Consequências: demo offline, progresso por etapas, evidências, exportação e histórico temporário. Sem persistência entre reinicializações, contas, deploy ou múltiplas análises simultâneas. Django/DRF + React permanecem opções para uma plataforma hospedada futura.
