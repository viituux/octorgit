# ADR 001 — CLI estática antes da plataforma

Status: adotada nesta base inicial.

Começar com Python 3.11+, biblioteca padrão e módulos de aquisição, parsing e documentação. Usar `ast` para Python; Tree-sitter fica para uma segunda linguagem. Não adicionar Django como dependência: ele é o framework analisado, não necessário para executar a ferramenta.

Resolver repositórios públicos para SHA e ler snapshots sem executar Git ou código do alvo. O modo local é explicitamente fixture e não possui rastreabilidade por commit.

Exportar inventário determinístico antes de integrar IA. Isso permite verificar evidências e limitações sem custo de tokens. O parser inicial não equivale à cobertura de Django/DRF exigida pelo gate do MVP.
