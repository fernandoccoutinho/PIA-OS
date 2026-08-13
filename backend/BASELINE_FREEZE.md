# Congelamento da Baseline — PIA-OS Backend v1.0

**Data:** 2026-08-05

## Encerramento oficial

A **Entrega 2 — Infraestrutura do Backend** (Módulos 2.1 a 2.13) está
**oficialmente encerrada** a partir deste documento. Esta baseline
(`BASELINE.md`) é a referência congelada da versão v1.0 da
infraestrutura.

## Regras do congelamento

1. **Nenhuma funcionalidade nova entra nesta baseline.** O escopo de
   2.1–2.13 está fechado.
2. **Correções futuras à infraestrutura existente ocorrem apenas por
   patches** — bugs reais encontrados em produção, não novos recursos.
   Um patch não abre uma nova numeração de módulo de entrega; é uma
   correção pontual, documentada como tal.
3. **A Entrega 3 inicia em nova linha de desenvolvimento** — domínio da
   plataforma (Objetos Cognitivos, IA), autenticação, interface Web,
   Desktop e SDKs. Constrói sobre esta baseline sem modificá-la
   retroativamente, exceto onde um ADR novo explicitamente revisar uma
   decisão anterior (ver `docs/adr/index.md` — nenhum ADR foi
   revogado até este ponto).

## O que isso significa na prática

- Qualquer mudança em `app/config/`, `app/database/`, `app/logging/`,
  etc. depois deste ponto é, por definição, uma mudança **pós-baseline**
  — deve ser tratada com o mesmo rigor de revisão que uma mudança em
  produção real teria.
- Novos módulos da Entrega 3 devem **consumir** esta infraestrutura
  (Configuration Manager, Logger Central, hierarquia de exceções,
  Repository Pattern), não reimplementá-la.

## Referência

`BASELINE.md` — dados técnicos da versão congelada.
