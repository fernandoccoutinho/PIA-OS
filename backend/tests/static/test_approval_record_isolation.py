"""
Guardas de **isolamento** da aprovação persistente (`E4.9.9.a`).

```text
PERSISTED_APPROVAL != EXECUTION
APPROVAL_RECORD    != ERASURE_RECORD
```

Esta fatia persiste uma decisão e nada mais. As guardas provam o *nada
mais* por AST, reflexão e schema real — e preferem **comportamento** a
guarda textual sempre que a propriedade puder ser exercida.

Mutante só acompanha a guarda quando ela é a **única** prova de uma
propriedade material.
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

NOVOS = (
    APP / "memory" / "models" / "approval_lifecycle_enums.py",
    APP / "memory" / "models" / "approval_record.py",
    APP / "memory" / "repositories" / "approval_record_repository.py",
)


def _executavel(arquivo: pathlib.Path) -> str:
    """Código sem docstrings — as desta fatia nomeiam o que ela não faz."""
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if isinstance(corpo, list):
            novo = [
                filho
                for filho in corpo
                if not (
                    isinstance(filho, ast.Expr)
                    and isinstance(filho.value, ast.Constant)
                    and isinstance(filho.value.value, str)
                )
            ] or [ast.Pass()]
            setattr(no, "body", novo)  # noqa: B010
    return ast.unparse(arvore)


def _fontes() -> list[pathlib.Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def test_s01_nenhum_efeito_destrutivo_nesta_fatia() -> None:
    """Zero import ou uso de efeito, storage, rede ou shell."""
    proibidos = (
        "ErasureEffectPort",
        "shutil",
        "subprocess",
        "os.remove",
        "unlink",
        "boto3",
        "requests",
        "httpx",
        "socket",
        "open(",
    )
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s02_nenhum_escritor_de_recibo_foi_composto() -> None:
    """`ERASURE_RECORD_WRITER = NOT_COMPOSED`."""
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in ("append_observed", "ErasureRecordRepository", "ErasureRecord"):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s03_nenhuma_autenticacao_api_parser_ou_agendador() -> None:
    proibidos = (
        "jwt",
        "oauth",
        "OAuth",
        "login",
        "authenticate(",
        "hashlib",
        "hmac",
        "bcrypt",
        "APIRouter",
        "FastAPI",
        "transcribe",
        "Celery",
        "scheduler",
        "BackgroundTasks",
    )
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s04_nenhuma_serializacao_opaca() -> None:
    """`pickle`, `__dict__`, `asdict` e `cast` fora."""
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in ("pickle", "__dict__", "asdict(", "cast(", "object.__new__"):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s05_nenhuma_supressao_de_tipo_nova() -> None:
    import io
    import tokenize

    marcador = "type:" + " ignore"
    for caminho in NOVOS:
        fonte = caminho.read_text(encoding="utf-8")
        comentarios = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(fonte).readline)
            if token.type == tokenize.COMMENT
        ]
        assert not any(marcador in c for c in comentarios), caminho.name


def test_s06_nenhum_consumidor_de_producao_fora_do_repositorio() -> None:
    """EXATAMENTE um consumidor de produção, e ele é a composição final.

    ATUALIZADA NA E4.9.9.d. A composição final é o consumidor
    # AUTORIZADO, e a guarda ficou MAIS FORTE, não mais frouxa: antes
    # exigia ZERO consumidores; agora exige EXATAMENTE UM, e nomeia
    # qual. Um segundo consumidor passaria na versão antiga se ela
    # tivesse sido apenas relaxada com um `permitidos`.
    #
    # ```text
    # AUTHORIZED_CONSUMER = destructive_execution_service.py
    # SECOND_CONSUMER = FORBIDDEN
    # ```
    """
    permitidos = {
        APP / "memory" / "models" / "__init__.py",
        APP / "memory" / "repositories" / "approval_record_repository.py",
    } | set(NOVOS)
    esperado = APP / "memory" / "services" / "destructive_execution_service.py"
    modulos = {
        "app.memory.models.approval_record",
        "app.memory.repositories.approval_record_repository",
    }
    infratores: list[str] = []
    for caminho in _fontes():
        if caminho in permitidos:
            continue
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        importados: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module)
            elif isinstance(no, ast.Import):
                importados.update(a.name for a in no.names)
        if modulos & importados:
            infratores.append(str(caminho.relative_to(APP)))
    assert infratores == [str(esperado.relative_to(APP))], infratores


def test_s07_o_instante_decisorio_e_do_banco() -> None:
    """`clock_timestamp()`, nunca `now()` nem relógio da aplicação.

    `now()` é o instante de INÍCIO da transação: duas sessões abertas
    antes do vencimento poderiam consumir depois dele.
    """
    executavel = _executavel(APP / "memory" / "repositories" / "approval_record_repository.py")
    assert "clock_timestamp" in executavel
    assert "func.now()" not in executavel
    assert "datetime.now" not in executavel
    assert "utcnow" not in executavel


def test_s08_o_consumo_e_um_unico_update_condicional() -> None:
    """`SELECT`-depois-`UPDATE` deixaria as duas sessões vencerem.

    Esta guarda é a única prova ESTÁTICA da forma do comando; o
    comportamento concorrente é provado por `i19`–`i21`, com barreira
    real e duas sessões.
    """
    arvore = ast.parse(
        (APP / "memory" / "repositories" / "approval_record_repository.py").read_text(
            encoding="utf-8"
        )
    )
    (metodo,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "_transicionar"
    ]
    corpo = ast.unparse(metodo)
    assert "update(ApprovalRecord)" in corpo
    assert ".returning(" in corpo
    assert "clock_timestamp" in corpo
    # nenhuma leitura de estado ANTES da decisão dentro do método
    assert "select(ApprovalRecord)" not in corpo


def test_s09_o_binding_completo_entra_na_condicao() -> None:
    """`PARTIAL_BINDING_MATCH = FORBIDDEN`.

    Guarda estática sobre a forma; a prova de comportamento está em
    `i13`–`i18`, com envelopes alternativos integralmente válidos.
    """
    arvore = ast.parse(
        (APP / "memory" / "repositories" / "approval_record_repository.py").read_text(
            encoding="utf-8"
        )
    )
    (metodo,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "_condicoes_de_binding"
    ]
    corpo = ast.unparse(metodo)
    for exigido in (
        "operation",
        "purpose_ref",
        "principal_ref",
        "assurance_level",
        "authenticated_at",
        "channel",
        "voice_review",
        "impact_item_count",
        "impact_volume_kind",
        "impact_bytes_total",
        "governance_outcome",
        "governance_policy_rationale",
        "materialized_at",
        "expires_at",
    ):
        assert exigido in corpo, exigido

    (filhas,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "_condicoes_das_filhas"
    ]
    corpo_filhas = ast.unparse(filhas)
    assert "exists()" in corpo_filhas
    assert "func.count()" in corpo_filhas, "cardinalidade é metade da prova"
    assert "legacy_protection_state" in corpo_filhas
    assert "version_etag" in corpo_filhas


def test_s10_nenhum_digest_ou_hash_de_binding() -> None:
    """`APPROVAL_SCOPE_DIGEST = NOT_USED`."""
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in ("sha256", "md5", "blake2", "hexdigest", "digest", "fingerprint"):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s11_nenhuma_coluna_json_nas_tres_tabelas() -> None:
    """`JSON_STORAGE = FORBIDDEN` — medido no schema real."""
    import sqlalchemy as sa

    from app.memory.models.approval_record import (
        ApprovalRecord,
        ApprovalRecordGovernanceItem,
        ApprovalRecordTarget,
    )

    for modelo in (ApprovalRecord, ApprovalRecordTarget, ApprovalRecordGovernanceItem):
        for coluna in modelo.__table__.columns:
            assert not isinstance(coluna.type, sa.JSON)


def test_s12_uma_unica_migration_sucessora_do_head_anterior() -> None:
    """E nenhuma branch criada sobre revisão antiga."""
    versoes = APP.parent / "alembic" / "versions"
    grafo: dict[str, str | None] = {}
    for arquivo in versoes.glob("*.py"):
        revisao = descendente = None
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
                if no.target.id == "revision" and isinstance(no.value, ast.Constant):
                    revisao = no.value.value
                elif no.target.id == "down_revision" and isinstance(no.value, ast.Constant):
                    descendente = no.value.value
        if revisao:
            grafo[revisao] = descendente

    filhos_do_head_anterior = [r for r, p in grafo.items() if p == "c8a3f5017e94"]
    assert filhos_do_head_anterior == ["a1f7c2d40e93"]
    # E4.9.9.d: a migration textual de `governance_rule_id` é a ÚNICA
    # sucessora autorizada de `a1f7c2d40e93`. A guarda ganhou um degrau:
    # antes só media a folha, agora também prova que nenhuma BRANCH
    # nasceu da revisão desta fatia.
    netos = [r for r, p in grafo.items() if p == "a1f7c2d40e93"]
    assert netos == ["d5b31f7a08c4"], netos
    # ATUALIZADO PELA E4.11: `e7c25a91f4b3` (validated_experiences) é a
    # sucessora AUTORIZADA. A guarda desce mais um degrau e continua
    # medindo o mesmo: nenhuma OUTRA migration nasceu, e o head é folha.
    bisnetos = [r for r, p in grafo.items() if p == "d5b31f7a08c4"]
    assert bisnetos == ["e7c25a91f4b3"], bisnetos
    sucessoras_e5 = [r for r, p in grafo.items() if p == "e7c25a91f4b3"]
    assert sucessoras_e5 == ["f8a91c2d4e60"], sucessoras_e5
    pais = {p for p in grafo.values() if p}
    folhas = [r for r in grafo if r not in pais]
    # ATUALIZADO PELA E7.4-1: a folha passou a ser `b47e9c05d3fa`
    # (kernel de conexões); antes `a91d3f7c26be`
    # (orquestração). A guarda continua medindo folha ÚNICA — não
    # imobilidade da cadeia.
    assert folhas == ["b47e9c05d3fa"], folhas


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


def test_s13_nenhum_adaptador_concreto_de_efeito_ou_resolucao() -> None:
    """RENOMEADA NA E4.9.9.d — `GUARD_NAME != GUARD_MEASUREMENT`.

    O nome antigo prometia que as fatias `b`, `c` e `d` não tinham
    começado. As três foram autorizadas e implementadas, e manter o nome
    faria a guarda prometer uma ausência que deixou de existir.

    O que **permanece** ausente é a capacidade material, e é isso que a
    guarda passou a medir:

    ```text
    ERASURE_EFFECT_ADAPTER = NONE
    TARGET_RESOLVER_ADAPTER = NONE
    PRODUCTION_DELETION_AVAILABLE = FALSE
    ```

    Medir adaptador concreto é mais forte do que medir nome de classe:
    um adaptador chamado qualquer outra coisa passaria na versão antiga.
    """
    infratores = _classes_com_metodo(_fontes(), "attempt_effect")
    infratores += _classes_com_metodo(_fontes(), "resolve_target")
    assert infratores == []


def test_s14_e3_e_modulos_congelados_sem_import_novo() -> None:
    for caminho in NOVOS:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                assert not no.module.startswith("app.cognitive"), caminho.name


def test_s99_1_a_guarda_do_instante_decisorio_detecta_now() -> None:
    """§ mutante — `s07` é a única prova estática desta propriedade.

    A prova de comportamento exigiria duas transações abertas em ordem
    controlada; a guarda estática é o que impede a regressão barata.
    """
    correto = "def _transicionar(self):\n    agora = func.clock_timestamp()\n"
    com_now = "def _transicionar(self):\n    agora = func.now()\n"
    com_python = "def _transicionar(self):\n    agora = datetime.now(UTC)\n"

    def conforme(fonte: str) -> bool:
        corpo = ast.unparse(ast.parse(fonte))
        return (
            "clock_timestamp" in corpo and "func.now()" not in corpo and "datetime.now" not in corpo
        )

    assert conforme(correto)
    assert not conforme(com_now)
    assert not conforme(com_python)


def test_s99_2_a_guarda_do_comando_unico_detecta_select_antes_do_update() -> None:
    """§ mutante — `s08` é a única prova estática da forma do comando."""
    correto = (
        "def _transicionar(self):\n"
        "    return self._session.execute(update(ApprovalRecord)"
        ".where(x).values(y).returning(ApprovalRecord.id))\n"
    )
    dois_passos = (
        "def _transicionar(self):\n"
        "    atual = self._session.execute(select(ApprovalRecord).where(x))\n"
        "    return self._session.execute(update(ApprovalRecord).values(y))\n"
    )

    def conforme(fonte: str) -> bool:
        corpo = ast.unparse(ast.parse(fonte))
        return (
            "update(ApprovalRecord)" in corpo
            and ".returning(" in corpo
            and "select(ApprovalRecord)" not in corpo
        )

    assert conforme(correto)
    assert not conforme(dois_passos)
