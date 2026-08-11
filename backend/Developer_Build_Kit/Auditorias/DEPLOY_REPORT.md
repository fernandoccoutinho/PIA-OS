# Relatório de Deploy — Módulo 2.13

## Limitação do ambiente (honesta, documentada desde o Módulo 2.11)

**Sem Docker disponível neste sandbox** — não foi possível rodar
`docker build`/`docker compose up` de ponta a ponta nesta sessão nem em
nenhuma das anteriores. Toda validação abaixo é o que É possível
verificar sem um daemon Docker: sintaxe, estrutura, e testes unitários
que leem o conteúdo dos arquivos.

## Validações realizadas

| Item | Método | Resultado |
|---|---|---|
| 4 `docker-compose.*.yml` | `yaml.safe_load()` | Todos válidos |
| 3 Dockerfiles | Leitura estrutural (`FROM`, `HEALTHCHECK`, `USER`, multi-stage) | Estrutura consistente com `docs/adr/ADR-008.md` |
| `.dockerignore` | Confirmado no contexto de build correto (`backend/.dockerignore`, não `deploy/docker/`) | Correto — ver `docs/adr` e `deploy/README_DEPLOY.md` |
| Nginx | Leitura estrutural (`default.conf`, `nginx.conf`) | Proxy reverso, gzip, headers de segurança, bloco HTTPS comentado (sem certificado real, por escopo) |
| 6 scripts operacionais | `bash -n` (sintaxe) | Todos válidos |
| Variáveis de ambiente | Overlays por ambiente lidos, grep por segredo real | Nenhum segredo real encontrado — só placeholders reconhecíveis |
| `tests/unit/deploy/` | Suíte dedicada (Módulo 2.11) | 100% passando — cobre Dockerfiles, Compose, scripts, env, Nginx |

## Suporte às três modalidades oficiais

- **Self-Hosted**: `docker compose -f deploy/compose/docker-compose.yml up`
  — sem dependência externa obrigatória (Redis/Nginx opcionais via
  `profiles:`). Confirmado por leitura do compose e teste dedicado
  (`test_base_compose_redis_and_nginx_are_profile_gated`).
- **Cloud**: `Dockerfile.prod` é uma imagem OCI padrão, sem acoplamento a
  nenhum provedor específico — documentado em
  `docs/backend/deployment.md`.
- **Desktop**: backend funciona localmente sem alteração (`uvicorn
  main:app`, sem Docker necessário) — pré-condição para Electron/Tauri
  embutirem o processo.

## README de Deploy

`deploy/README_DEPLOY.md` revisado — instalação, ambientes, guia Docker,
operação (logs/reinício/atualização/rollback), backup/restore,
recuperação de desastre, e as três modalidades, todos presentes e
consistentes com os arquivos reais de `deploy/`.

## Achados desta etapa

Nenhum. A estrutura de deploy criada no Módulo 2.11 permanece consistente
— nenhuma mudança foi necessária nesta auditoria.

## Conclusão

Deploy consistente e íntegro na medida do que é verificável sem um
ambiente Docker real. Recomendação para a Entrega 3: rodar
`docker compose up` de ponta a ponta em um ambiente com Docker
disponível antes do primeiro deploy real de produção — esta lacuna de
validação está documentada desde o Módulo 2.1 e não é nova aqui.
