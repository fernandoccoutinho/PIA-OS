# Diagrama — Deploy (Self-Hosted / Produção)

Versão textual (Mermaid) de `deployment.drawio` — topologia do
`docker-compose.prod.yml` (Módulo 2.11).

```mermaid
graph TB
    Client["Cliente / Navegador"]

    subgraph Host["Host Docker"]
        subgraph Network["pia_os_prod_network (bridge)"]
            Nginx["nginx:1.27-alpine<br/>proxy reverso, porta 80 exposta"]
            API["api (Dockerfile.prod)<br/>gunicorn + uvicorn workers<br/>sem porta exposta ao host"]
            DB[("db - postgres:16-alpine<br/>sem porta exposta ao host")]
            Redis[("redis - estrutura, profile with-redis<br/>nao usado ainda")]
        end
        Volume1[("volume: pia_os_prod_db_data")]
        Volume2[("volume: pia_os_prod_redis_data")]
    end

    Client -->|":80"| Nginx
    Nginx -->|proxy_pass| API
    API --> DB
    API -.nao conectado ainda.-> Redis
    DB --- Volume1
    Redis --- Volume2

    style Redis stroke-dasharray: 5 5
    style Volume2 stroke-dasharray: 5 5
```

## Como manter atualizado

Ao adicionar um serviço novo ao `docker-compose.prod.yml`, adicione o nó
correspondente aqui — a topologia deste diagrama deve sempre ser
derivável 1:1 do arquivo de compose real, nunca divergir dele.
