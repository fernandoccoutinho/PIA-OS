"""
Guardas de **isolamento** da fundação `ErasureRecord` (`E4.9.5`).

Esta fatia cria a primitiva persistente e nada mais. O que estes testes
protegem é justamente o *nada mais*:

```text
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
ERASURE_EFFECT = NONE
```

A garantia é por AST, não por leitura de docstring. Um serviço que
importasse o repositório poderia, na próxima fatia, gravar um recibo
de um apagamento que nunca ocorreu — e um recibo falso é pior do que
recibo nenhum, porque parece prova.

Arquivo próprio, e não um acréscimo a `test_isolation_ports.py` ou
`test_port_assignment.py`: a lição da E4.6.3 foi que pôr prova estática
num arquivo vizinho muda a contagem de um módulo congelado por
vizinhança.

```text
FROZEN MODULE COUNT != NEIGHBOURING FILE
```
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

NOVOS_MODULOS = {
    "app.memory.models.erasure_record",
    "app.memory.models.erasure_enums",
    "app.memory.schemas.erasure_record",
    "app.memory.repositories.erasure_record_repository",
}

# Arquivos que legitimamente conhecem a primitiva: ela própria e o
# `__init__` de models, que existe para que `Base.metadata` a registre.
PERMITIDOS = {
    APP / "memory" / "models" / "erasure_record.py",
    APP / "memory" / "models" / "erasure_enums.py",
    APP / "memory" / "schemas" / "erasure_record.py",
    APP / "memory" / "repositories" / "erasure_record_repository.py",
    APP / "memory" / "models" / "__init__.py",
    APP / "memory" / "errors" / "codes.py",
    APP / "memory" / "errors" / "exceptions.py",
}


def _modulos_importados(arquivo: pathlib.Path) -> set[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module)
    return modulos


def _fontes() -> list[pathlib.Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def test_s01_nenhum_service_ou_manager_importa_a_primitiva() -> None:
    """Nenhum escritor runtime existe — e não pode passar a existir
    por acréscimo silencioso na próxima fatia."""
    infratores: list[str] = []
    for arquivo in _fontes():
        if arquivo in PERMITIDOS:
            continue
        if NOVOS_MODULOS & _modulos_importados(arquivo):
            infratores.append(str(arquivo.relative_to(APP)))
    assert infratores == [], f"importam a primitiva sem autorização: {infratores}"


def test_s02_nenhum_service_menciona_erasure_record() -> None:
    """Busca textual em `services/`, além do teste por AST.

    Import não é a única forma de acoplar: uma referência tardia por
    string ou `importlib` escaparia da AST.
    """
    servicos = [p for p in (APP / "memory" / "services").rglob("*.py")]
    servicos += [p for p in (APP / "cognitive" / "services").rglob("*.py")]
    infratores = [
        str(p.relative_to(APP))
        for p in servicos
        if "__pycache__" not in p.parts and "ErasureRecord" in p.read_text(encoding="utf-8")
    ]
    assert infratores == []


def test_s03_nenhuma_rota_ou_api_expoe_a_primitiva() -> None:
    """O registro de tudo que já foi destruído não é recurso consultável."""
    candidatos = [
        p
        for p in _fontes()
        if any(parte in {"api", "routers", "routes", "endpoints"} for parte in p.parts)
    ]
    for arquivo in candidatos:
        assert not (NOVOS_MODULOS & _modulos_importados(arquivo)), arquivo


def test_s04_sync_nao_inclui_erasure_records() -> None:
    """`SYNC_BOUNDARY = LOCAL_ONLY`.

    Um recibo exportado levaria, para outra instalação, a lista do que
    foi apagado aqui.
    """
    from app.cognitive.schemas.synchronization import SECTION_BY_TABLE

    assert "erasure_records" not in SECTION_BY_TABLE


def test_s05_causal_event_type_permanece_inalterado() -> None:
    """`CAUSAL_EVENT_TYPE = UNCHANGED` — a E3 não é tocada."""
    from app.cognitive.models.enums import CausalEventType

    assert [e.value for e in CausalEventType] == [
        "created",
        "transformed",
        "compared",
        "accessed",
    ]


def test_s06_cognitive_operation_permanece_com_onze_membros() -> None:
    """A E4.3.5 já nomeou `legal_erasure`; esta fatia não amplia nada."""
    from app.memory.models.governance_enums import CognitiveOperation

    assert len(CognitiveOperation) == 11
    assert CognitiveOperation.LEGAL_ERASURE.value == "legal_erasure"


def test_s07_a_primitiva_nao_menciona_efeito_destrutivo() -> None:
    """Nenhum callable de produção da fatia sabe apagar, resolver alvo,
    autenticar ou aprovar."""
    proibidos = (
        "def erase",
        "def delete_target",
        "def resolve_target",
        "def execute_erasure",
        "def authenticate",
        "def approve",
        "ErasureEffectPort",
        "ErasureTargetResolverPort",
    )
    for modulo in NOVOS_MODULOS:
        caminho = APP.parent / (modulo.replace(".", "/") + ".py")
        texto = caminho.read_text(encoding="utf-8")
        for termo in proibidos:
            assert termo not in texto, f"{modulo} menciona {termo}"


def test_s08_target_resolver_effect_approval_e_retention_continuam_ausentes() -> None:
    """A fatia não antecipou nenhuma das fundações seguintes."""
    ausentes = (
        "ErasureEffectPort",
        "ErasureTargetResolverPort",
        "ErasureTargetDescriptor",
        "DestructiveApprovalEnvelope",
        "ApprovalRecord",
        "RetentionPolicy",
    )
    encontrados: list[str] = []
    for arquivo in _fontes():
        texto = arquivo.read_text(encoding="utf-8")
        for termo in ausentes:
            # `class X` ou `X = ` seriam definição; menção em docstring
            # é legítima e existe de propósito nos contratos.
            if f"class {termo}" in texto:
                encontrados.append(f"{arquivo.relative_to(APP)}:{termo}")
    assert encontrados == []


def test_s09_nenhum_campo_proibido_no_schema() -> None:
    """Prova de lista proibida sobre as colunas reais da tabela."""
    from app.memory.models.erasure_record import ErasureRecord

    proibidos = {
        "metadata",
        "meta",
        "details",
        "detail",
        "payload",
        "message",
        "description",
        "notes",
        "content",
        "body",
        "prompt",
        "response",
        "locator",
        "uri",
        "url",
        "path",
        "bucket",
        "key",
        "payload_ref",
        "source_ref",
        "evidence_refs",
        "input_refs",
        "output_refs",
        "effect_digest",
        "digest",
        "hash",
        "credential",
        "token",
        "secret",
    }
    colunas = {c.name for c in ErasureRecord.__table__.columns}
    assert colunas & proibidos == set()
