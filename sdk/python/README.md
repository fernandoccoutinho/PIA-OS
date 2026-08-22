# pia-os-sdk

SDK de **representação** do PIA-OS. Derivado do snapshot canônico do
OpenAPI da Chain107-R1.

```text
SDK_SOURCE_OF_TRUTH = FALSE
OPENAPI_SOURCE_OF_TRUTH = TRUE
E6_3 = REPRESENTATION_ONLY_SDK
```

O SDK envia o DTO público, recebe o envelope e preserva campos e ordem.
Não recalcula ciência, aprovação ou roteamento, não normaliza PIAP, não
acessa banco e **não tenta de novo**.

## Instalação

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install ./sdk/python
```

## Uso

```python
from pia_os_sdk import PiaClient, PiaApiError
from pia_os_sdk import models as m

with PiaClient("https://pia.example.com", credencial, timeout=30.0) as cliente:
    print(cliente.health().status)
    resposta = cliente.evaluate(m.PublicEvaluationRequest.model_validate(payload))
    print(resposta.data.request_length)
```

## A credencial

`Authorization: Bearer pia_<key_id>.<secret>`.

É uma credencial de **serviço**. Não representa usuário humano e nunca
concede, substitui ou amplia aprovação PIAP.

```text
SERVICE_PRINCIPAL != HUMAN_USER
SERVICE_SCOPE != PIAP_APPROVAL
```

O Bearer é enviado **apenas** em `evaluate()`. As três operações de
observabilidade são públicas no OpenAPI (`security` ausente) e não
recebem a credencial.

```text
PUBLIC_OPERATION_WITHOUT_SECURITY_REQUIREMENT
  -> MUST_NOT_RECEIVE_SERVICE_CREDENTIAL
SERVER_ACCEPTS_HEADER != CLIENT_SHOULD_SEND_HEADER
```

O servidor aceitar o header não torna necessário enviá-lo: cada ponto a
mais por onde o segredo passa é mais um lugar onde middleware, proxy ou
telemetria pode observá-lo.

Passe-a por variável de ambiente ou cofre — nunca em código versionado,
argumento de linha de comando ou log. O SDK não a imprime em `repr`, em
exceção nem em log, e não a persiste em lugar algum. Perdida a
credencial, revogue-a e emita outra pelo comando administrativo local do
backend; não existe recuperação.

## Erros

`PiaApiError` preserva `status_code`, `code` (`PIA-####`) e `detail`
públicos, sem reinterpretar. `503` continua `503`: cota excedida e
autoridade de cota indisponível são coisas diferentes, e o SDK não as
mistura.

```text
QUOTA_EXCEEDED != QUOTA_AUTHORITY_UNAVAILABLE
RETRY != DUPLICATE_EFFECT
```

Não há retry automático. Repetir uma avaliação é decisão de quem chama,
que sabe qual efeito pretende.

`PiaTransportError` cobre falhas anteriores à resposta (DNS, conexão,
timeout) — sem status nem código PIA, porque o servidor não respondeu.

## Modelos gerados

`pia_os_sdk/models.py` é **gerado**. Não edite à mão.

```bash
python -m tools.snapshot_openapi          # atualiza o snapshot (exige o backend)
python -m tools.generate_models           # regenera os modelos
python -m tools.generate_models --check   # exige REGENERATION_DIFF = 0
```

O snapshot remove um único campo volátil, `info.x-metadata.generated_at`,
que muda a cada processo e tornaria a regeneração não reprodutível. A
remoção é enumerada em `tools/snapshot_openapi.py`; nenhum campo de
contrato é tocado.

## Superfície

| método | rota | credencial |
|---|---|---|
| `evaluate` | `POST /api/v1/predictive-evaluations` | Bearer |
| `health` | `GET /api/v1/health` | nenhuma |
| `status` | `GET /api/v1/status` | nenhuma |
| `version` | `GET /api/v1/version` | nenhuma |

Não existe `get_capacity_limits()`: a Chain107-R1 não tem esse endpoint,
e o SDK não inventa rota para cumprir proposta anterior.

## Testes

```bash
pytest sdk/python/tests
python -m tools.mutation_evidence_e63
```
