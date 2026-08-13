# Workflow — PIA-OS Backend

Fluxo básico de branch/PR já está em
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) ("Fluxo de trabalho"). Este
documento cobre o que acontece *depois* que uma mudança é aberta —
verificação automática, e o processo de entrega em etapas seguido desde
o Módulo 2.1.

## Verificação automática (o que o CI roda)

```
git push
  → .github/workflows/ci.yml (ou qualquer CI que rode scripts/run_ci_checks.sh)
      → make install-dev
      → make check
          → ruff check .
          → black --check .
          → pytest (com cobertura — falha se < 95%)
```

Local, antes de abrir um PR:

```bash
make check           # espelha o CI
make check-api-docs  # se mexeu em endpoint/schema
```

## Processo de entrega por módulo (histórico deste projeto)

Cada módulo (2.1 a 2.12) seguiu o mesmo ciclo:

1. Especificação recebida (objetivo, estrutura, critérios de aceitação).
2. Implementação, com validação real a cada passo (não só "parece
   certo" — testes rodados, lint/format aplicados, comportamento
   verificado manualmente quando possível).
3. Entrega com relatório (arquitetural, de impacto, checklist).
4. Auditoria/code review — correções aplicadas quando um apontamento
   era válido; imprecisões da auditoria sinalizadas explicitamente, não
   aceitas por concordância automática.
5. Aprovação → próximo módulo.

Esse ciclo é o que gerou a trilha de decisões documentada em
[`docs/adr/`](../adr/) — cada ADR corresponde a algo descoberto ou
decidido durante o passo 2 ou 4 de algum módulo.

## Branches e commits

Convenção de nome de branch e mensagens de commit: ver
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#fluxo-de-trabalho) — não
duplicado aqui.
