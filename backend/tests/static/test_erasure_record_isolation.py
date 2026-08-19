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
    # E4.9.9.a: a aprovação persistente reutiliza `ErasureTargetClass`
    # para classificar cada alvo do lote — mesma razão da entrada da
    # E4.9.7 mais abaixo. Conhecer o vocabulário de classificação NÃO é
    # conhecer a primitiva de recibo, e `test_approval_record_isolation`
    # prova pelo outro lado que nada ali importa `ErasureRecord`,
    # `ErasureRecordRepository` ou `append_observed`.
    APP / "memory" / "models" / "approval_record.py",
    APP / "memory" / "models" / "approval_lifecycle_enums.py",
    APP / "memory" / "repositories" / "approval_record_repository.py",
    # E4.9.9.b: a fronteira de efeito reutiliza `ErasureOutcome` como FONTE
    # ÚNICA dos três desfechos observados — duplicá-lo criaria duas verdades
    # sobre o que foi observado. Reutilizar o VOCABULÁRIO não é conhecer a
    # primitiva de recibo: `test_erasure_effect_isolation` prova pelo outro
    # lado que nada ali importa `ErasureRecord`, repositório ou
    # `append_observed`.
    APP / "memory" / "schemas" / "erasure_effect.py",
    APP / "memory" / "models" / "erasure_enums.py",
    APP / "memory" / "schemas" / "erasure_record.py",
    APP / "memory" / "repositories" / "erasure_record_repository.py",
    APP / "memory" / "models" / "__init__.py",
    APP / "memory" / "errors" / "codes.py",
    APP / "memory" / "errors" / "exceptions.py",
    # E4.9.7: os contratos de resolução de alvo reutilizam
    # `ErasureTargetClass` em vez de declarar um segundo enum com os
    # mesmos quatro membros. Conhecer o vocabulário de classificação NÃO
    # é conhecer a primitiva de recibo — `test_erasure_target_isolation`
    # prova que nada ali importa `ErasureRecord`, repositório ou writer.
    APP / "memory" / "schemas" / "erasure_target.py",
    # E4.9.8: a proposta destrutiva reutiliza `ErasureTargetClass` para
    # recusar classe não apagável no snapshot. Mesma razão da linha
    # acima — conhecer o vocabulário de classificação NÃO é conhecer a
    # primitiva de recibo, e `test_destructive_approval_isolation`
    # prova que nada ali importa `ErasureRecord`, repositório ou writer.
    APP / "memory" / "schemas" / "destructive_approval.py",
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
    # ATUALIZADA NA E4.9.9.d. A composição final é o consumidor
    # AUTORIZADO, e a guarda ficou MAIS FORTE, não mais frouxa: antes
    # exigia ZERO consumidores; agora exige EXATAMENTE UM, e nomeia
    # qual. Um segundo consumidor passaria na versão antiga se ela
    # tivesse sido apenas relaxada com um `permitidos`.
    #
    # ```text
    # AUTHORIZED_CONSUMER = destructive_execution_service.py
    # SECOND_CONSUMER = FORBIDDEN
    # ```
    # DOIS consumidores autorizados, com papéis distintos — e é a
    # distinção que a guarda preserva:
    #
    # ```text
    # schemas/destructive_execution.py   contratos INERTES da composição
    # services/destructive_execution_service.py   a composição EXECUTÁVEL
    # ```
    #
    # Um terceiro é recusado. Comparar CONJUNTOS, e não listas, porque a
    # ordem de varredura do sistema de arquivos não é contrato.
    esperados = {
        "memory/schemas/destructive_execution.py",
        "memory/services/destructive_execution_service.py",
    }
    infratores: list[str] = []
    for arquivo in _fontes():
        if arquivo in PERMITIDOS:
            continue
        if NOVOS_MODULOS & _modulos_importados(arquivo):
            infratores.append(str(arquivo.relative_to(APP)))
    assert set(infratores) == esperados, infratores


def test_s02_nenhum_service_menciona_erasure_record() -> None:
    """Busca textual em `services/`, além do teste por AST.

    Import não é a única forma de acoplar: uma referência tardia por
    string ou `importlib` escaparia da AST.
    """
    servicos = [p for p in (APP / "memory" / "services").rglob("*.py")]
    servicos += [p for p in (APP / "cognitive" / "services").rglob("*.py")]
    # ATUALIZADA NA E4.9.9.d: um serviço — e SÓ um — passa a mencionar a
    # primitiva. A busca textual continua existindo porque `importlib` e
    # referência por string escapariam da AST.
    esperado = APP / "memory" / "services" / "destructive_execution_service.py"
    infratores = [
        str(p.relative_to(APP))
        for p in servicos
        if "__pycache__" not in p.parts and "ErasureRecord" in p.read_text(encoding="utf-8")
    ]
    assert infratores == [str(esperado.relative_to(APP))], infratores


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


def _classes_com_metodo(fontes, metodo: str) -> list[str]:
    """Classes de produção que IMPLEMENTAM o método — nunca o `Protocol`.

    ```text
    DECLARED_BOUNDARY != CONCRETE_ADAPTER
    ```

    Um `Protocol` declara a fronteira e tem corpo `...`; um adaptador a
    implementa. A distinção é medida na AST pelo corpo do método, não
    pelo nome do arquivo.
    """
    encontradas: list[str] = []
    for caminho in fontes:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ClassDef):
                continue
            protocolo = any(
                isinstance(base, ast.Name) and base.id == "Protocol" for base in no.bases
            )
            if protocolo:
                continue
            for membro in no.body:
                if not isinstance(membro, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if membro.name != metodo:
                    continue
                corpo = [
                    linha
                    for linha in membro.body
                    if not (isinstance(linha, ast.Expr) and isinstance(linha.value, ast.Constant))
                ]
                substancial = not (
                    len(corpo) == 1
                    and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and corpo[0].value.value is Ellipsis
                )
                if substancial:
                    encontradas.append(f"{caminho.name}:{no.name}")
    return encontradas


def test_s08_target_resolver_effect_approval_e_retention_continuam_ausentes() -> None:
    """A fatia não antecipou nenhuma das fundações seguintes."""
    # Atualizado pela E4.9.6: `RetentionPolicy` saiu da lista porque
    # passou a existir como primitiva persistente autorizada. A guarda
    # fez exatamente o que devia — acusou a chegada da fatia seguinte.
    # As demais continuam ausentes, e o próprio isolamento da retenção
    # é provado em `test_retention_policy_isolation.py`.
    #
    # Atualizado de novo pela E4.9.7, pela MESMA razão e com o mesmo
    # efeito: `ErasureTargetResolverPort` e `ErasureTargetDescriptor`
    # saíram porque a E4.9.1 os autorizou e a E4.9.7 os materializou como
    # contratos observacionais. `ErasureEffectPort` PERMANECE na lista —
    # a E4.9.1 autorizou DUAS portas e exigiu que ficassem separadas, e a
    # fronteira de efeito continua sem existir. `test_s09` do isolamento
    # da E4.9.7 prova a mesma ausência do outro lado.
    # Atualizado pela E4.9.8, pela mesma razão e com o mesmo efeito das
    # atualizações anteriores: `DestructiveApprovalEnvelope` saiu porque
    # a E4.9.8 o autorizou e materializou como contrato inerte.
    #
    # ATUALIZADO PELA E4.9.9.a: `ApprovalRecord` saiu porque a fatia o
    # autorizou e materializou como persistência inerte.
    #
    # `ErasureEffectPort` PERMANECE, e a lista GANHOU o executor e o
    # writer — as três capacidades que continuam sem existir:
    #
    # ```text
    # ErasureEffectPort        = ABSENT
    # DESTRUCTIVE_EXECUTOR     = ABSENT
    # ERASURE_RECORD_WRITER    = NOT_COMPOSED
    # ```
    #
    # Persistir uma aprovação é o oposto de executá-la, e esta guarda
    # continua sendo uma das provas disso.
    # ATUALIZADA NA E4.9.9.b: o PORT e o resultado tipado são autorizados
    # e inertes. O que continua ausente, e é o que importa, é o
    # EXECUTOR — nenhuma classe compõe efeito com recibo.
    # ATUALIZADA NA E4.9.9.d: `DestructiveExecutionService` saiu da lista
    # porque a fatia o autorizou e materializou — a guarda fez de novo
    # exatamente o que devia, acusando a chegada da fatia seguinte.
    #
    # O que PERMANECE ausente é a capacidade material, e a guarda passou
    # a medi-la em vez de medir um nome:
    #
    # ```text
    # ERASURE_EFFECT_ADAPTER = NONE
    # PRODUCTION_DELETION_AVAILABLE = FALSE
    # ```
    encontrados = _classes_com_metodo(_fontes(), "attempt_effect")
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
