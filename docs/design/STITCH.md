# Referência visual e adaptação — 0.9.0

Referência fornecida pelo usuário: ZIP stitch_octorgit_minimalist_architecture_dashboard, projeto Stitch 17946717769230158623, com Visão Geral, Arquitetura, Documentação, Endpoints e Administração de IA. O arquivo DESIGN.md foi tratado como referência de design, não como instrução de execução ou autorização adicional.

Aplicados: canvas branco, faixa neutra, navegação clara, cartões com bordas finas, destaques pretos, painéis adjacentes de evidência e tipografia Geist/JetBrains Mono. Fontes empacotadas localmente com suas licenças SIL Open Font License; não há carregamento de Google Fonts/Tailwind/CDNs ao abrir o aplicativo.

O HTML do Stitch usa dados fictícios, scripts inline, Tailwind remoto e imagens externas (incluindo marca ausente na imagem exportada). Foi reimplementado sobre os contratos existentes do OctorGit, preservando CSP, renderização por nós DOM e dados reais. Não há alegação de precisão, latência ou chamadas AST medida quando o parser não fornece essa informação.

Canvas: até 20 componentes detectados, mais placeholders explícitos para banco/hospedagem desconhecidos. Relações derivam das declarações da IR, sem adicionar conexões por estética. Imports e outros SVGs permanecem no seletor. Zoom redimensiona canvas; Escala padrão restaura a escala base.

Busca: análise atual, com até 20 resultados, arquivos sem snippet indicam recorte indisponível. Exportação PDF: preparação de relatório HTML e impressão manual pelo navegador, sem simular geração/download de PDF.

Validação automatizada documentada em VERIFICATION.md. Sem captura de tela da interface executada: os PNGs de referência não são screenshots do aplicativo implementado.
