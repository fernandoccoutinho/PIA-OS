# Diagrama — Fluxo de Requisição (incluindo tratamento de exceção e logging)

Versão textual (Mermaid) de `request_flow.drawio`. Cobre o caminho feliz
e o de erro no mesmo diagrama (o de erro é o desvio a partir de
"Endpoint" quando uma exceção é levantada).

```mermaid
sequenceDiagram
    participant C as Cliente
    participant CORS as CORSMiddleware
    participant RID as RequestIDMiddleware
    participant SEC as SecurityMiddleware
    participant TIM as TimingMiddleware
    participant LOG as LoggingMiddleware
    participant EP as Endpoint (routers/*)
    participant HAND as Handler Global (2.7)
    participant LGR as Logger Central (2.6)

    C->>CORS: Requisicao HTTP
    CORS->>RID: (preflight OK / headers CORS)
    RID->>RID: gera/propaga X-Request-ID
    RID->>SEC: request.state.request_id setado
    SEC->>SEC: valida host, tamanho, Content-Type
    alt violacao de seguranca
        SEC->>LGR: log security_violation
        SEC->>HAND: PIAOSException (chamado direto - ver docs/backend/security.md)
        HAND-->>C: 400/413/415/429 (envelope padrao)
    else requisicao valida
        SEC->>TIM: segue
        TIM->>LOG: mede tempo
        LOG->>LGR: log request_received (com request_id no contexto)
        LOG->>EP: chama o endpoint
        alt endpoint ok
            EP-->>LOG: resposta 2xx
            LOG->>LGR: log request_completed
            LOG-->>C: resposta + X-Request-ID + X-Response-Time-Ms
        else endpoint levanta excecao
            EP->>HAND: PIAOSException / HTTPException / ValidationError / SQLAlchemyError
            HAND->>LGR: log do erro (code, category, severity, request_id)
            HAND-->>C: envelope de erro padrao (nunca stack trace, exceto log em dev)
        end
    end
```

## Como manter atualizado

Se um middleware novo for inserido na cadeia, adicione o participante e
reordene conforme `main.py::create_app()` (a ordem real dos
`add_middleware` — documentada em `deploy/README_DEPLOY.md` e
`docs/backend/security.md`).
