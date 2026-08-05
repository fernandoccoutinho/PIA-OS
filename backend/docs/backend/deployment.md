# Deploy — PIA-OS Backend

Documentação técnica da camada de implantação (Módulo 2.11). O guia
operacional completo (comandos de instalação, backup/restore, rollback,
recuperação de desastre) vive em
[`deploy/README_DEPLOY.md`](../../deploy/README_DEPLOY.md) — este
documento não o duplica, apenas descreve a arquitetura por trás dele.

## Finalidade

Empacotar o backend de forma reproduzível (Docker), configurável por
ambiente (dev/test/prod) sem hardcode, e implantável em três
modalidades sem alteração de código: Cloud, Desktop (backend local) e
Self-Hosted.

## Componentes

| Componente | Local | Papel |
|---|---|---|
| `Dockerfile` / `.dev` / `.prod` | `deploy/docker/` | 3 imagens autocontidas — paridade de produção, hot reload, multi-stage enxuta |
| `docker-compose.{yml,dev,test,prod}.yml` | `deploy/compose/` | Orquestração por ambiente |
| `nginx.conf` / `default.conf` | `deploy/nginx/` | Proxy reverso, compressão, headers de segurança na borda |
| `start.sh`, `stop.sh`, `healthcheck.sh`, `wait_for_db.sh`, `backup.sh`, `restore.sh` | `deploy/scripts/` | Operação (ver guia completo) |
| `.env.example` + overlays por ambiente | `deploy/env/` | Configuração — nunca segredo real versionado |

## Fluxo interno

```
deploy/scripts/start.sh <ambiente>
  → resolve o docker-compose.<ambiente>.yml correto
  → garante .env presente (copia deploy/env/.env.example se ausente)
  → docker compose up -d
       → build da imagem (Dockerfile correspondente ao ambiente)
       → sobe `db` (Postgres), aguarda healthcheck
       → sobe `api` (Sistema Central de Configuração — Módulo 2.2 — lê
         as variáveis de ambiente do container, valida em
         app.core.lifespan; falha rápido se algo crítico faltar em
         produção)
       → (prod) sobe `nginx`, único ponto exposto ao host
```

## Pontos de extensão

- **Novo ambiente:** novo `docker-compose.<nome>.yml` em
  `deploy/compose/` + tratamento em `deploy/scripts/*.sh` (`case`
  statements já centralizados, um lugar só para adicionar o caso novo).
- **Novo destino de log:** já resolvido pelo Módulo 2.6
  (`LOG_DESTINATION`) — o Docker só precisa capturar stdout/stderr,
  nenhuma mudança na camada de deploy.
- **Redis/cache real:** o serviço já existe nos Compose (atrás de
  `profiles: with-redis`) — ativar de verdade é conectar a aplicação a
  ele num módulo futuro, sem mudar a infraestrutura de deploy.
- **HTTPS real:** o bloco `server` comentado em `deploy/nginx/default.conf`
  já está pronto para receber `ssl_certificate`/`ssl_certificate_key`
  reais.
- **Cloud (AWS/Azure/GCP/DO):** a imagem `Dockerfile.prod` é OCI padrão
  — nenhuma mudança de código para rodar em ECS, Cloud Run, Container
  Apps, App Platform, etc.; só como os segredos chegam ao container muda
  por provedor (todos compatíveis com o Módulo 2.2, que só exige que a
  variável exista no ambiente do processo).

## Ver também

[`deploy/README_DEPLOY.md`](../../deploy/README_DEPLOY.md) — instalação,
ambientes, guia Docker, guia de operação (logs, reinício, atualização,
rollback), guia de backup, recuperação de desastre, Cloud/Desktop/
Self-Hosted em detalhe.
