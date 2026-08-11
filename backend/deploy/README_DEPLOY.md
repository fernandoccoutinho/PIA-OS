# Guia de Deploy — PIA-OS Backend

Containerização, deploy e operação (Módulo 2.11). Reutiliza integralmente
a infraestrutura dos Módulos 2.1–2.10 — nenhuma funcionalidade da
aplicação muda; isto é só a camada de implantação.

## Estrutura

```
deploy/
├── docker/
│   ├── Dockerfile        # padrão — paridade de produção, self-hosted "just funciona"
│   ├── Dockerfile.dev      # hot reload, deps de dev
│   ├── Dockerfile.prod       # multi-stage, gunicorn+uvicorn, imagem enxuta
│   └── .dockerignore           # cópia documentada — a funcional é backend/.dockerignore
├── compose/
│   ├── docker-compose.yml    # base self-hosted (api + db; redis/nginx via profile)
│   ├── docker-compose.dev.yml  # hot reload, bind mount
│   ├── docker-compose.test.yml   # banco descartável (tmpfs), roda a suíte automaticamente
│   └── docker-compose.prod.yml     # stack completa: limites de recursos, nginx sempre ativo
├── nginx/
│   ├── nginx.conf              # config principal (gzip, includes)
│   └── default.conf              # proxy reverso, headers, HTTPS comentado (sem cert real)
├── scripts/
│   ├── start.sh / stop.sh          # sobe/derruba um ambiente
│   ├── healthcheck.sh                # verifica GET /health de fora do container
│   ├── wait_for_db.sh                  # aguarda o Postgres aceitar conexões
│   ├── backup.sh / restore.sh            # dump/restore versionado do banco
├── env/
│   ├── .env.example                     # ponteiro — a fonte real é backend/.env.example
│   ├── .env.development / .env.test / .env.production  # overlays por ambiente
└── backups/                                # gerado em runtime, fora do controle de versão
```

## Instalação

```bash
cd backend
bash deploy/scripts/start.sh dev
```

Isso: copia `deploy/env/.env.example` (ponteiro) para `.env` se ainda não
existir, builda a imagem de dev, sobe `api` + `db` com hot reload.
Acesse `http://localhost:8000/docs`.

Para configurar de verdade (não usar só os defaults de dev):

```bash
cp .env.example .env                        # base completa (Módulo 2.2)
cat deploy/env/.env.development >> .env       # overlay de dev (opcional, já é o default)
```

## Ambientes

| Ambiente | Compose | Dockerfile | Características |
|---|---|---|---|
| `dev` | `docker-compose.dev.yml` | `Dockerfile.dev` | hot reload, bind mount, deps de dev |
| `test` | `docker-compose.test.yml` | `Dockerfile.dev` | banco `tmpfs` descartável, roda `pytest` sozinho |
| `base` | `docker-compose.yml` | `Dockerfile` | self-hosted simples, sem nginx/redis por padrão |
| `prod` | `docker-compose.prod.yml` | `Dockerfile.prod` | multi-stage, nginx sempre ativo, limites de recursos, sem portas expostas direto de `api`/`db` |

```bash
bash deploy/scripts/start.sh dev
bash deploy/scripts/start.sh test    # roda a suíte e sai (--abort-on-container-exit)
bash deploy/scripts/start.sh prod
bash deploy/scripts/start.sh base -- --profile with-proxy --profile with-redis
```

## Guia Docker — decisões técnicas

- **Três Dockerfiles autocontidos** (não uma cadeia de imagens-base):
  cada um builda isoladamente sem precisar de uma imagem intermediária
  pré-construída. Custo: ~8 linhas de setup (`apt-get`/`pip install`
  base) repetidas entre eles — aceito deliberadamente pela simplicidade
  e robustez (nenhum passo de orquestração extra para buildar), não é o
  tipo de "duplicação de configuração" que o módulo pede para evitar
  (isso se refere a não redefinir valores de `Settings`, não a
  boilerplate de Dockerfile).
- **`Dockerfile.prod` é multi-stage de verdade**: estágio `builder`
  instala toolchain de compilação (`gcc`, headers do `libpq`) num venv;
  estágio final copia só o venv pronto — a imagem final não carrega
  compilador nenhum, reduzindo tamanho e superfície de ataque.
- **`.dockerignore` funcional vive em `backend/.dockerignore`**, não em
  `deploy/docker/` — o Docker só lê `.dockerignore` na raiz do contexto
  de build. A cópia em `deploy/docker/.dockerignore` é só documentação
  visual da estrutura pedida.
- **`gunicorn` novo em produção** (`requirements/prod.txt`): supervisor
  de múltiplos workers `uvicorn` — `uvicorn` sozinho não gerencia
  múltiplos processos.

## Guia de Operação

### Logs

`LOG_DESTINATION=console` (padrão, Módulo 2.6) — todo log vai para
stdout/stderr do container, capturado pelo driver `json-file` do Docker
(configurado em `docker-compose.prod.yml` com rotação: `max-size: 10m`,
`max-file: 5`). Ver logs:

```bash
docker compose -f deploy/compose/docker-compose.prod.yml logs -f api
```

### Reiniciar

```bash
bash deploy/scripts/stop.sh prod && bash deploy/scripts/start.sh prod
# ou, sem recriar containers:
docker compose -f deploy/compose/docker-compose.prod.yml restart api
```

### Limpeza de volumes

```bash
bash deploy/scripts/stop.sh dev --volumes   # remove também os dados do banco — destrutivo
```

### Atualização (rollout de uma nova versão)

```bash
git pull
bash deploy/scripts/stop.sh prod
docker compose -f deploy/compose/docker-compose.prod.yml build api
bash deploy/scripts/start.sh prod
bash deploy/scripts/healthcheck.sh localhost 80   # via nginx
```

### Rollback

```bash
git checkout <tag-ou-commit-anterior>
docker compose -f deploy/compose/docker-compose.prod.yml build api
bash deploy/scripts/start.sh prod
```

Sem builds versionados/imutáveis por tag de imagem nesta etapa (fica
para quando houver um registry de imagens no pipeline de CI/CD) — o
rollback aqui é via `git checkout` + rebuild, não via troca de tag de
imagem já publicada.

## Guia de Backup

```bash
bash deploy/scripts/backup.sh prod
# gera deploy/backups/prod/pia_os_prod_<timestamp>.sql.gz
```

Cada execução cria um arquivo novo (nunca sobrescreve) — versionamento
por timestamp UTC. Restauração:

```bash
bash deploy/scripts/restore.sh prod deploy/backups/prod/pia_os_prod_20260101T000000Z.sql.gz
```

Pede confirmação interativa (`digite 'sim'`) antes de sobrescrever o
banco — para automação não-interativa, defina `CONFIRM=yes`.

**Sem armazenamento externo** (S3, GCS, etc.) nesta etapa, conforme o
escopo do módulo — os backups ficam em `deploy/backups/` no host, fora
do controle de versão (`.gitignore`). Copiar para um destino externo é
responsabilidade de quem opera o ambiente, por enquanto.

## Recuperação de desastre

1. Provisione um host novo com Docker + Docker Compose.
2. Clone o repositório, configure `.env` (a partir de
   `deploy/env/.env.production`, com segredos reais).
3. `bash deploy/scripts/start.sh prod` — sobe API + banco vazio.
4. `bash deploy/scripts/restore.sh prod <último-backup>` — restaura os
   dados do backup mais recente disponível.
5. `bash deploy/scripts/healthcheck.sh` — confirma que voltou ao ar.

## Cloud (AWS / Azure / GCP / DigitalOcean)

Nenhuma configuração específica de provedor nesta etapa (conforme o
escopo do Módulo 2.11) — a imagem `Dockerfile.prod` é um container OCI
padrão, executável em qualquer serviço de container gerenciado (ECS,
Azure Container Apps, Cloud Run, App Platform) sem alteração. O que
muda por provedor: como `DATABASE_URL`/`SECRET_KEY` chegam ao container
(Secrets Manager, Key Vault, Secret Manager — todos compatíveis, já que
o Módulo 2.2 só exige que as variáveis existam no ambiente do processo)
e como o load balancer do provedor substitui o `nginx` deste módulo (ou
convive com ele).

## Desktop (Electron / Tauri)

O backend roda localmente sem nenhuma alteração — Electron/Tauri
empacotam o binário/processo Python (ou o container, se o runtime alvo
tiver Docker) e apontam o frontend para `http://localhost:8000`. Como
não há autenticação ainda (módulos futuros), a superfície local não
precisa de nenhum ajuste de CORS/trusted hosts além do que já é padrão
de desenvolvimento (`TRUSTED_HOSTS=*`, já é o default). Documentação de
empacotamento específica do Electron/Tauri (empacotar o Python, gerenciar
o ciclo de vida do processo filho) fica para quando o frontend desktop
existir — aqui só se garante que o backend não impõe nenhuma barreira.

## Self-Hosted

```bash
git clone <repo> && cd backend
bash deploy/scripts/start.sh base
```

Sem nenhuma dependência externa obrigatória — `docker compose up` (via
`start.sh base`) sobe tudo que é necessário (API + PostgreSQL). Redis e
Nginx são opcionais (`--profile with-redis --profile with-proxy`).

## O que NÃO foi implementado nesta etapa (conforme o escopo)

Kubernetes, Helm, Terraform, certificados HTTPS reais, balanceamento de
carga, monitoramento externo — pertencem a versões futuras.
