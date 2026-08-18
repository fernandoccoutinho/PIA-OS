"""
Guardas de **isolamento** da resolução de alvo (`E4.9.7`).

```text
RESOLUTION_IS_OBSERVATIONAL = TRUE
TARGET_RESOLUTION != DELETION_AUTHORITY
DELETION_AUTHORITY != EFFECT
```

Esta fatia materializa contratos e nada mais. Estas guardas protegem o
*nada mais* por AST e por estrutura, nunca por leitura de docstring — as
docstrings destes módulos citam nominalmente o que eles **não** fazem, e
comparar texto bruto acusaria justamente as declarações de ausência.

É o quinto módulo do projeto a aprender isso da mesma forma (`gv16` na
E4.3.1, `s02`/`s11` na E4.9.6, `s15` na E4.9.6.1, `u76` na E4.9.6.3), e
por isso aqui a comparação por AST é o padrão desde o primeiro teste.

Arquivo próprio, pela lição da E4.6.3: prova estática em arquivo vizinho
muda a contagem de um módulo congelado por vizinhança.
"""

import ast
import pathlib

import pytest

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

NOVOS_MODULOS = {
    "app.memory.models.target_resolution_enums",
    "app.memory.schemas.erasure_target",
    "app.memory.ports.erasure_target",
}

CAMINHOS_NOVOS = (
    APP / "memory" / "models" / "target_resolution_enums.py",
    APP / "memory" / "schemas" / "erasure_target.py",
    APP / "memory" / "ports" / "erasure_target.py",
)


def _executavel(arquivo: pathlib.Path) -> str:
    """Código sem docstrings, via AST."""
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if isinstance(corpo, list):
            novo_corpo = [
                filho
                for filho in corpo
                if not (
                    isinstance(filho, ast.Expr)
                    and isinstance(filho.value, ast.Constant)
                    and isinstance(filho.value.value, str)
                )
            ] or [ast.Pass()]
            setattr(no, "body", novo_corpo)  # noqa: B010
    return ast.unparse(arvore)


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


def test_s01_nenhum_import_de_app_cognitive() -> None:
    """Fronteira G17/MD6 — a E4 não conhece patrimônio da E3."""
    for caminho in CAMINHOS_NOVOS:
        importados = _modulos_importados(caminho)
        assert not any(m.startswith("app.cognitive") for m in importados), caminho.name


def test_s02_nenhuma_persistencia_nos_contratos_transitorios() -> None:
    """Descritor é capacidade contextual transitória, não entidade."""
    proibidos = (
        "BaseModel",
        "mapped_column",
        "Mapped",
        "Session",
        "UnitOfWork",
        "Repository",
        "sqlalchemy",
        "alembic",
        "declarative",
        "__tablename__",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s03_nenhum_efeito_destrutivo_nem_escritor_de_recibo() -> None:
    """`EFFECT != ERASURE_RECORD`, e nenhum dos dois existe aqui."""
    proibidos = (
        "ErasureRecord",
        "ErasureRecordRepository",
        "append_observed",
        "delete",
        "unlink",
        "remove",
        "purge",
        "trash",
        "execute_effect",
        "ErasureEffectPort",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s04_nenhum_storage_conector_ou_cliente_externo() -> None:
    # ATUALIZADA NA E4.9.7.1, deliberadamente. A versão da cadeia 80
    # proibia `urllib` inteiro — grosso demais, pela mesma razão que
    # proibir `unicodedata` inteiro foi grosso demais na E4.9.6.2:
    # `urllib.parse.urlsplit` é decomposição de string, sem rede. O que
    # não pode aparecer é o que ABRE CONEXÃO.
    proibidos = (
        "requests",
        "httpx",
        "urllib.request",
        "urlopen",
        "urlretrieve",
        "boto3",
        "aiohttp",
        "socket",
        "subprocess",
        "open(",
        "pathlib",
        "os.remove",
        "shutil",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s05_nenhum_parser_de_texto_ou_voz() -> None:
    """Texto e voz convergirão a um envelope futuro; não são desta camada."""
    proibidos = ("parse_command", "transcribe", "ASR", "speech", "def parse", "microphone")
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s06_nenhuma_supressao_de_tipo_nova() -> None:
    """Supressão vive em COMENTÁRIO; `Any` e `cast` vivem em CÓDIGO.

    São duas buscas diferentes de propósito, e a primeira versão desta
    guarda errou por não distingui-las: procurou o marcador no texto
    bruto e acusou a docstring que **declara** que nenhuma supressão é
    usada. Sexta vez que este projeto vê o mesmo falso positivo.

    A AST não serve para a supressão, porque `ast.unparse` descarta
    comentários — uma supressão real ficaria invisível. `tokenize` lê
    exatamente os comentários e nada mais.

    O marcador é montado em pedaços para que a própria guarda não se
    conte.
    """
    import io
    import tokenize

    marcador = "type:" + " ignore"
    for caminho in CAMINHOS_NOVOS:
        fonte = caminho.read_text(encoding="utf-8")
        comentarios = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(fonte).readline)
            if token.type == tokenize.COMMENT
        ]
        assert not any(marcador in c for c in comentarios), caminho.name

        executavel = _executavel(caminho)
        assert "cast(" not in executavel, caminho.name
        assert ": Any" not in executavel, caminho.name


def test_s07_nenhuma_migration_nova() -> None:
    """`MIGRATION_DELTA = 0` — descritores são transitórios."""
    versoes = APP.parent / "alembic" / "versions"
    revisoes = {p.name.split("_")[0] for p in versoes.glob("*.py")}
    assert "c8a3f5017e94" in revisoes
    for arquivo in versoes.glob("*.py"):
        if arquivo.name.startswith("c8a3f5017e94"):
            continue
        texto = arquivo.read_text(encoding="utf-8")
        assert 'down_revision: str | None = "c8a3f5017e94"' not in texto, arquivo.name


def test_s08_nenhuma_classe_de_alvo_foi_reeditada() -> None:
    """Uma fonte da verdade sobre classificação, não duas.

    `ErasureTargetClass` é da E4.9.5 e continua sendo a única. Se alguém
    declarar um segundo enum com os mesmos membros, esta guarda cai.
    """
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        assert "class ErasureTargetClass" not in executavel, caminho.name
        for token in (
            "pia_managed_artifact",
            "authorized_connector_referent",
            "cognitive_metadata_record",
        ):
            assert token not in executavel, f"{caminho.name}: {token} reescrito"


def test_s09_o_efeito_nao_foi_materializado() -> None:
    """A E4.9.1 autorizou duas portas; esta fatia entrega uma."""
    infratores = [
        str(p.relative_to(APP)) for p in _fontes() if "ErasureEffectPort" in _executavel(p)
    ]
    assert infratores == []


def test_s10_nenhum_consumidor_runtime_da_porta_apareceu() -> None:
    """Contrato sem adaptador é o estado correto desta fatia.

    ATUALIZADA NA E4.9.8, e a atualização SEPARA duas coisas que a
    versão anterior tratava como uma só:

    ```text
    CONSUMIR A PORTA        != CONSUMIR OS VALUE OBJECTS
    ```

    `ErasureTargetResolverPort` continua **sem nenhum** consumidor — é
    o que prova que não há adaptador. Já `schemas.erasure_target` passou
    a ter um consumidor autorizado: a proposta destrutiva da E4.9.8
    reutiliza `ControlScope`, `CustodyNamespace`, `ReferenceProvenance`,
    `CLASSES_DE_CONTEUDO` e `TEXTO_OCULTO`.

    Colapsar os dois faria a guarda cair a cada fatia que reutilize um
    value object, e o que ela existe para proteger — a ausência de
    adaptador — deixaria de ser o que ela mede.
    """
    porta = {"app.memory.ports.erasure_target"}
    permitidos_porta = {
        APP / "memory" / "ports" / "erasure_target.py",
        APP / "memory" / "ports" / "__init__.py",
    }
    consumidores_da_porta = [
        str(p.relative_to(APP))
        for p in _fontes()
        if p not in permitidos_porta and porta & _modulos_importados(p)
    ]
    assert consumidores_da_porta == []

    permitidos_vo = set(CAMINHOS_NOVOS) | {
        APP / "memory" / "ports" / "__init__.py",
        APP / "memory" / "models" / "__init__.py",
        APP / "memory" / "schemas" / "__init__.py",
        # Consumidor AUTORIZADO pela E4.9.8.
        APP / "memory" / "schemas" / "destructive_approval.py",
    }
    consumidores_dos_vo = [
        str(p.relative_to(APP))
        for p in _fontes()
        if p not in permitidos_vo and NOVOS_MODULOS & _modulos_importados(p)
    ]
    assert consumidores_dos_vo == []


def test_s11_o_localizador_nao_tem_caminho_de_saida() -> None:
    """`MUST_NOT_PERSIST` e `MUST_NOT_BE_LOGGED_BY_THIS_MODULE`."""
    executavel = _executavel(APP / "memory" / "schemas" / "erasure_target.py")
    for termo in ("get_logger", "log_event", "logging", "print(", "to_dict", "model_dump"):
        assert termo not in executavel, termo


def test_s12_a_redacao_do_localizador_vive_no_codigo_executavel() -> None:
    """Se alguém remover o `__repr__`, esta guarda cai.

    A dataclass já oculta o campo por `repr=False`, mas um argumento é
    fácil de apagar sem perceber. A redação explícita é a segunda camada.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "ErasureTargetDescriptor"
    ]
    metodos = {no.name for no in classe.body if isinstance(no, ast.FunctionDef)}
    assert {"__repr__", "__str__"} <= metodos
    corpo = ast.unparse(classe)
    assert "LOCALIZADOR_OCULTO" in corpo


def test_s13_todos_os_value_objects_sao_frozen() -> None:
    """Congelamento declarado no decorador, não prometido em docstring."""
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    )
    # 6 → 7 na E4.9.7.2: `ReferenceProvenance` substituiu `origin: str`.
    classes = [no for no in ast.walk(arvore) if isinstance(no, ast.ClassDef)]
    assert len(classes) == 7
    for classe in classes:
        congelada = any(
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "dataclass"
            and any(
                kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in dec.keywords
            )
            for dec in classe.decorator_list
        )
        assert congelada, classe.name


def test_s14_a_porta_nao_recebe_sessao_repositorio_nem_efeito() -> None:
    """A assinatura é a garantia, provada na AST."""
    arvore = ast.parse((APP / "memory" / "ports" / "erasure_target.py").read_text(encoding="utf-8"))
    (metodo,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "resolve_target"
    ]
    parametros = [arg.arg for arg in metodo.args.args]
    assert parametros == ["self", "reference"]
    assert metodo.args.vararg is None
    assert metodo.args.kwarg is None
    assert metodo.args.kwonlyargs == []


def test_s15_nenhum_relogio_implicito_nos_contratos() -> None:
    """`resolved_at` chega por argumento, como na E4.9.6."""
    for caminho in CAMINHOS_NOVOS:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        chamadas = {
            no.func.attr
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        }
        assert "now" not in chamadas, caminho.name
        assert "utcnow" not in chamadas, caminho.name
        assert "today" not in chamadas, caminho.name


def test_s16_enums_e_policies_anteriores_intocados() -> None:
    """Escopo confinado: nada da E4.9.5/E4.9.6 foi editado."""
    erasure_enums = (APP / "memory" / "models" / "erasure_enums.py").read_text(encoding="utf-8")
    assert "TargetResolutionRefusalReason" not in erasure_enums
    assert "ErasureTargetDescriptor" not in erasure_enums

    retention = (APP / "memory" / "schemas" / "retention.py").read_text(encoding="utf-8")
    assert "ErasureTarget" not in retention


# ======================================================================
# E4.9.7.1 — guardas do corretivo de alvo exato e confidencialidade
# ======================================================================


def test_s17_o_localizador_de_sucesso_passa_pelo_validador_exato() -> None:
    """`FIELD_COUNT = 1 DOES_NOT_PROVE TARGET_CARDINALITY = 1`.

    Se alguém devolver `transient_locator` ao validador de texto opaco
    genérico, wildcard e URL assinada voltam a entrar. A guarda prova na
    AST qual função é chamada para aquele campo.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "ErasureTargetDescriptor"
    ]
    chamadas = [
        no
        for no in ast.walk(classe)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Name)
        and no.args
        and isinstance(no.args[0], ast.Constant)
        and no.args[0].value == "transient_locator"
    ]
    assert [no.func.id for no in chamadas if isinstance(no.func, ast.Name)] == [
        "validar_localizador_sem_expansao_literal"
    ]


def test_s18_a_verificacao_de_alvo_exato_e_estrutural() -> None:
    """Não é lista de substrings apresentada como segurança.

    O validador decompõe a URL e recusa por estrutura — userinfo, query,
    fragmento, metacaractere e barra final. Se alguém trocar isso por uma
    lista de palavras proibidas, esta guarda cai.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    )
    (validador,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "validar_localizador_sem_expansao_literal"
    ]
    executavel = [linha for linha in validador.body if not isinstance(linha, ast.Expr)]
    corpo = "\n".join(ast.unparse(linha) for linha in executavel)
    assert "urlsplit" in corpo
    assert "username" in corpo
    assert "password" in corpo
    assert "METACARACTERES_DE_EXPANSAO" in corpo
    # Devolve o valor recebido, sem normalizar.
    for proibido in ("normalize", "casefold", "lower()", "upper()", "replace("):
        assert proibido not in corpo, proibido


def test_s19_a_recusa_nao_tem_campo_de_texto_livre() -> None:
    """`SAFE_DIAGNOSTIC != FREE_TEXT`.

    Um campo `str` livre na recusa é onde o localizador coube na cadeia
    80. `origin` continua sendo `str` porque é a referência que motivou
    a tentativa, e não contexto de diagnóstico.
    """
    import dataclasses

    from app.memory.models.target_resolution_enums import RefusalDimension
    from app.memory.schemas.erasure_target import TargetResolutionRefusal

    campos = {campo.name: campo.type for campo in dataclasses.fields(TargetResolutionRefusal)}
    assert "diagnostic" not in campos
    assert "observed_dimension" in campos
    assert campos["observed_dimension"] == (RefusalDimension | None)
    assert len(RefusalDimension) == 8

    # ATUALIZADO NA E4.9.7.2, e a mudança é um endurecimento. A cadeia 81
    # isentava `origin` por ser "dado do pedido" — a auditoria mostrou que
    # a intenção do nome não vale como garantia do tipo, e o campo aceitava
    # o localizador. Agora a recusa não tem NENHUM campo `str`.
    de_texto = {nome for nome, tipo in campos.items() if tipo is str}
    assert de_texto == set()


def test_s20_nenhum_bool_declarativo_de_exatidao() -> None:
    """Exatidão é verificada, não declarada pelo chamador.

    Um `exact=True` que qualquer chamador pudesse afirmar seria o mesmo
    defeito com outro nome — o §2.1 do prompt proíbe explicitamente.
    """
    import dataclasses

    from app.memory.schemas.erasure_target import ErasureTargetDescriptor

    nomes = {campo.name for campo in dataclasses.fields(ErasureTargetDescriptor)}
    for proibido in ("exact", "is_exact", "exato", "single_target", "verified_exact"):
        assert proibido not in nomes, proibido


def test_s21_o_dubl_observacional_verifica_todas_as_dimensoes() -> None:
    """A prova comportamental do §11.3, que a cadeia 80 não tinha.

    O dublê vive nos testes, mas a auditoria mediu justamente que ele
    comparava só `workspace_id` enquanto o EDR afirmava mais. Esta guarda
    fixa as cinco dimensões na AST do dublê.
    """
    testes = pathlib.Path(__file__).resolve().parents[1]
    arvore = ast.parse(
        (testes / "unit" / "memory" / "test_erasure_target.py").read_text(encoding="utf-8")
    )
    (metodo,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "resolve_target"
    ]
    corpo = ast.unparse(metodo)
    for dimensao in (
        "WORKSPACE",
        "TENANT",
        "CONTROL_PRINCIPAL",
        "PROVIDER",
        "NAMESPACE",
    ):
        assert f"RefusalDimension.{dimensao}" in corpo, dimensao


def test_s22_o_corretivo_nao_criou_capability_nova() -> None:
    """Reafirmação após a E4.9.7.2 — nenhuma capacidade nova entrou.

    Corrigido na E4.9.7.2: a formulação anterior dizia "o escopo continua
    fechado", que se confundia com o fechamento de cross-tenant em
    runtime — esse continua DEFERRED. Aqui o que se prova é a ausência de
    capability nova nos módulos da fatia.
    """
    proibidos = (
        "ErasureRecordRepository",
        "append_observed",
        "ErasureEffectPort",
        "evaluate",
        "assess(",
        "trash",
        "purge",
        "scheduler",
        "requests",
        "httpx",
        "boto3",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


# ======================================================================
# E4.9.7.2 — origem tipada, referência sensível e alegações alinhadas
# ======================================================================


def test_s23_origin_e_tipado_nos_tres_value_objects() -> None:
    """`FREE_TEXT_ORIGIN = CONFIDENTIALITY_CHANNEL`.

    Se alguém devolver `origin` a `str`, o canal livre volta e o
    localizador entra por ele de novo.
    """
    import dataclasses

    from app.memory.schemas.erasure_target import (
        ErasureTargetDescriptor,
        ErasureTargetReference,
        ReferenceProvenance,
        TargetResolutionRefusal,
    )

    for classe in (ErasureTargetReference, ErasureTargetDescriptor, TargetResolutionRefusal):
        campos = {c.name: c.type for c in dataclasses.fields(classe)}
        assert campos["origin"] is ReferenceProvenance, classe.__name__


def test_s24_inventario_dos_campos_textuais_publicos() -> None:
    """Nenhum campo `str` novo entrou sem inventário.

    O §3.3 do prompt exige inventariar todos os campos textuais antes de
    fazer a quinta alegação absoluta. Esta guarda congela o conjunto: um
    campo `str` novo em qualquer contrato da fatia derruba o teste e
    obriga a decidir explicitamente se ele é canal de confidencialidade.
    """
    import dataclasses

    from app.memory.schemas.erasure_target import (
        ControlScope,
        CustodyNamespace,
        ErasureTargetDescriptor,
        ErasureTargetReference,
        ReferenceProvenance,
        TargetResolutionRefusal,
        VerifiedDeletionCapability,
    )

    textuais = {
        classe.__name__: sorted(c.name for c in dataclasses.fields(classe) if c.type is str)
        for classe in (
            ControlScope,
            CustodyNamespace,
            VerifiedDeletionCapability,
            ReferenceProvenance,
            ErasureTargetReference,
            ErasureTargetDescriptor,
            TargetResolutionRefusal,
        )
    }
    assert textuais == {
        "ControlScope": ["control_principal_ref"],
        "CustodyNamespace": ["namespace", "provider"],
        "VerifiedDeletionCapability": ["operation", "scope"],
        "ReferenceProvenance": [],
        "ErasureTargetReference": ["opaque_reference"],
        "ErasureTargetDescriptor": ["transient_locator"],
        "TargetResolutionRefusal": [],
    }


MARCADOR_SENSIVEL = "https://user:password@example.invalid/object?token=S25_SECRET"

CAMPOS_TEXTUAIS_LIVRES: tuple[tuple[str, str], ...] = (
    ("ControlScope", "control_principal_ref"),
    ("CustodyNamespace", "provider"),
    ("CustodyNamespace", "namespace"),
    ("VerifiedDeletionCapability", "operation"),
    ("VerifiedDeletionCapability", "scope"),
    ("ErasureTargetReference", "opaque_reference"),
    ("ErasureTargetDescriptor", "transient_locator"),
    ("ErasureTargetDescriptor", "version_etag"),
)
"""Todo campo `str` público que aceita texto arbitrário.

Se um destes deixar de ser livre — por tipo fechado ou gramática aplicada —
mova-o daqui e prove a rejeição. Enquanto aceitar texto arbitrário, vale
`UNRESTRICTED_PUBLIC_STR = MAY_CONTAIN_SENSITIVE_VALUE`.
"""


def _fabricas_com_marcador() -> dict[str, object]:
    """Um objeto por canal, com o marcador sensível naquele campo."""
    import uuid
    from datetime import UTC, datetime

    from app.memory.models.erasure_enums import ErasureTargetClass
    from app.memory.models.target_resolution_enums import (
        LegacyProtectionState,
        ReferenceOrigin,
    )
    from app.memory.schemas.erasure_target import (
        ControlScope,
        CustodyNamespace,
        ErasureTargetDescriptor,
        ErasureTargetReference,
        ReferenceProvenance,
        VerifiedDeletionCapability,
    )

    w, n, s = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    prov = ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF)
    escopo_ok = ControlScope(w, n, "principal:controle-1")
    custodia_ok = CustodyNamespace("pia-storage", "workspace/w1")
    cap_ok = VerifiedDeletionCapability("delete_object", "workspace/w1/*", True)
    quando = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    M = MARCADOR_SENSIVEL

    def descritor(**kw: object) -> ErasureTargetDescriptor:
        base: dict[str, object] = {
            "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
            "subject_coid": s,
            "control_scope": escopo_ok,
            "custody_namespace": custodia_ok,
            "capability": cap_ok,
            "resolved_at": quando,
            "origin": prov,
            "legacy_protection_state": LegacyProtectionState.NOT_PROTECTED,
            "transient_locator": "s3://bucket/exact-object",
        }
        base.update(kw)
        construtor: object = ErasureTargetDescriptor
        assert callable(construtor)
        return construtor(**base)

    def referencia(**kw: object) -> ErasureTargetReference:
        base: dict[str, object] = {
            "subject_coid": s,
            "opaque_reference": "payload://safe",
            "origin": prov,
            "control_scope": escopo_ok,
        }
        base.update(kw)
        construtor: object = ErasureTargetReference
        assert callable(construtor)
        return construtor(**base)

    escopo_sensivel = ControlScope(w, n, M)
    custodia_provider = CustodyNamespace(M, "workspace/w1")
    custodia_namespace = CustodyNamespace("pia-storage", M)

    return {
        # diretos
        "ControlScope.control_principal_ref": escopo_sensivel,
        "CustodyNamespace.provider": custodia_provider,
        "CustodyNamespace.namespace": custodia_namespace,
        "VerifiedDeletionCapability.operation": VerifiedDeletionCapability(
            M, "workspace/w1/*", True
        ),
        "VerifiedDeletionCapability.scope": VerifiedDeletionCapability("delete_object", M, True),
        "ErasureTargetReference.opaque_reference": referencia(opaque_reference=M),
        "ErasureTargetDescriptor.version_etag": descritor(version_etag=M),
        # compostos — uma classe interna segura não prova a externa
        "Reference→control_scope": referencia(control_scope=escopo_sensivel),
        "Reference→expected_namespace": referencia(expected_namespace=custodia_namespace),
        "Descriptor→control_scope": descritor(control_scope=escopo_sensivel),
        "Descriptor→custody_namespace.provider": descritor(custody_namespace=custodia_provider),
        "Descriptor→custody_namespace.namespace": descritor(custody_namespace=custodia_namespace),
        "Descriptor→capability.operation": descritor(
            capability=VerifiedDeletionCapability(M, "workspace/w1/*", True)
        ),
        "Descriptor→capability.scope": descritor(
            capability=VerifiedDeletionCapability("delete_object", M, True)
        ),
    }


def test_s25_nenhum_canal_textual_revela_marcador_sensivel() -> None:
    """SUBSTITUI a guarda da cadeia 82, que fixava "exatamente dois".

    ```text
    UNRESTRICTED_PUBLIC_STR = MAY_CONTAIN_SENSITIVE_VALUE
    DIRECT_REDACTION != COMPOSITE_REDACTION
    INVENTORY_OF_NAMES != CONFIDENTIALITY_PROOF
    ```

    A versão anterior contava nomes e protegia dois campos, e passava
    **porque não exercitava os demais** com o mesmo marcador. Esta
    exercita cada canal livre, direto e composto, com o valor sensível
    real — que é a única forma de a guarda poder falhar.

    `transient_locator` não aparece na lista de fábricas porque o
    validador de expansão literal já **rejeita** a URL com userinfo e
    query: rejeição também é fechamento, e `u53`/`u55` cobrem esse caso.
    """
    for canal, objeto in _fabricas_com_marcador().items():
        assert MARCADOR_SENSIVEL not in repr(objeto), f"{canal}: repr"
        assert MARCADOR_SENSIVEL not in str(objeto), f"{canal}: str"
        assert MARCADOR_SENSIVEL not in f"{objeto}", f"{canal}: f-string"
        assert MARCADOR_SENSIVEL not in "{}".format(objeto), f"{canal}: format"  # noqa: UP032


def test_s25_1_todo_campo_textual_livre_esta_coberto() -> None:
    """A lista de canais é derivada por reflexão, não escrita à mão.

    Um campo `str` novo em qualquer contrato da fatia derruba esta guarda
    até ser classificado e coberto — que é exatamente o que faltou na
    cadeia 82.
    """
    import dataclasses

    from app.memory.schemas import erasure_target

    descobertos: set[tuple[str, str]] = set()
    for nome in dir(erasure_target):
        obj = getattr(erasure_target, nome)
        if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
            continue
        for campo in dataclasses.fields(obj):
            if campo.type is str or campo.type == (str | None):
                descobertos.add((obj.__name__, campo.name))

    assert descobertos == set(CAMPOS_TEXTUAIS_LIVRES)


def test_s25_2_os_campos_livres_continuam_acessiveis_e_imutaveis() -> None:
    """Redigir a representação não pode inutilizar nem normalizar o valor."""
    from dataclasses import FrozenInstanceError

    from app.memory.schemas.erasure_target import ControlScope, CustodyNamespace

    objetos = _fabricas_com_marcador()
    escopo = objetos["ControlScope.control_principal_ref"]
    assert isinstance(escopo, ControlScope)
    assert escopo.control_principal_ref == MARCADOR_SENSIVEL

    custodia = objetos["CustodyNamespace.provider"]
    assert isinstance(custodia, CustodyNamespace)
    assert custodia.provider == MARCADOR_SENSIVEL
    assert custodia == CustodyNamespace(MARCADOR_SENSIVEL, "workspace/w1")

    with pytest.raises(FrozenInstanceError):
        escopo.control_principal_ref = "outro"


def test_s25_3_a_redacao_tem_duas_camadas_em_cada_classe() -> None:
    """`repr=False` no campo E `__repr__` próprio na classe.

    Uma camada só é frágil: um argumento é fácil de apagar sem perceber.
    """
    import dataclasses

    from app.memory.schemas import erasure_target

    por_classe: dict[str, set[str]] = {}
    for classe, campo in CAMPOS_TEXTUAIS_LIVRES:
        por_classe.setdefault(classe, set()).add(campo)

    for nome, campos in por_classe.items():
        classe = getattr(erasure_target, nome)
        assert {"__repr__", "__str__"} <= set(vars(classe)), nome
        ocultos = {c.name for c in dataclasses.fields(classe) if c.repr is False}
        assert campos <= ocultos, f"{nome}: {campos - ocultos}"


def test_s26_o_vocabulario_de_origem_veio_do_repositorio_real() -> None:
    """Os cinco nomes existem de fato na E3, e não foram presumidos."""
    from app.memory.models.target_resolution_enums import ORIGENS_PLURAIS, ReferenceOrigin

    modelos = {
        "payload_ref": APP / "cognitive" / "models" / "causal_history.py",
        "source_ref": APP / "cognitive" / "models" / "provenance_record.py",
        "evidence_refs": APP / "cognitive" / "models" / "provenance_record.py",
        "input_refs": APP / "cognitive" / "models" / "transformation_record.py",
        "output_refs": APP / "cognitive" / "models" / "transformation_record.py",
    }
    assert {o.value for o in ReferenceOrigin} == set(modelos)
    for campo, caminho in modelos.items():
        texto = caminho.read_text(encoding="utf-8")
        assert f"{campo}: Mapped[" in texto, campo

    # As três plurais são exatamente as colunas JSON de lista.
    assert {o.value for o in ORIGENS_PLURAIS} == {
        "evidence_refs",
        "input_refs",
        "output_refs",
    }


def test_s27_nenhuma_alegacao_de_fechamento_externo_permanece() -> None:
    """`EXTERNAL_RUNTIME_CROSS_TENANT_CLOSURE = DEFERRED`.

    Busca semântica pelas formulações que a auditoria apontou. Ler o
    texto bruto é correto aqui: o alvo É o texto das docstrings, não o
    código executável.
    """
    alvos = (
        APP / "memory" / "schemas" / "erasure_target.py",
        APP / "memory" / "models" / "target_resolution_enums.py",
        APP / "memory" / "ports" / "erasure_target.py",
    )
    for caminho in alvos:
        texto = caminho.read_text(encoding="utf-8")
        for frase in ("Fecha o *cross-tenant*", "fecham a *credential confusion*"):
            assert frase not in texto, f"{caminho.name}: {frase}"
        # As formulações corretas têm de estar presentes, não só as erradas ausentes.
    schemas = (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    enums = (APP / "memory" / "models" / "target_resolution_enums.py").read_text(encoding="utf-8")
    assert "CREDENTIAL_CONFUSION_RUNTIME_CLOSURE = DEFERRED" in schemas
    assert "EXTERNAL_RUNTIME_CROSS_TENANT_CLOSURE = DEFERRED" in enums


def test_s28_o_nome_do_validador_nao_promete_exatidao_material() -> None:
    """`RAW_PATTERN_SYNTAX_REJECTION != MATERIAL_TARGET_CARDINALITY_PROOF`."""
    fonte = (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    assert "def validar_localizador_sem_expansao_literal(" in fonte
    assert "def validar_localizador_exato(" not in fonte
    assert "MATERIAL_EXACT_TARGET_PROOF = DEFERRED" in fonte


def test_s29_verified_e_obrigatorio_na_ast() -> None:
    """`DEFAULT_TRUE = IMPLICIT_AUTHORITY`, provado no código-fonte.

    Prova na AST, e não só por reflexão, porque o defeito da cadeia 83
    entrou como uma linha de anotação com valor — e é exatamente essa
    linha que esta guarda inspeciona.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "VerifiedDeletionCapability"
    ]
    (anotacao,) = [
        no
        for no in classe.body
        if isinstance(no, ast.AnnAssign)
        and isinstance(no.target, ast.Name)
        and no.target.id == "verified"
    ]
    assert anotacao.value is None, "verified não pode ter default de espécie alguma"
    assert isinstance(anotacao.annotation, ast.Name)
    assert anotacao.annotation.id == "bool"


def test_s30_nenhuma_fabrica_de_producao_injeta_verificacao() -> None:
    """Nenhum construtor auxiliar pode devolver a autoridade implícita.

    Um `classmethod` ou função de módulo que montasse a capacidade com
    `verified=True` embutido recriaria o defeito com outro nome.
    """
    fonte = (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    chamadas = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Name)
        and no.func.id == "VerifiedDeletionCapability"
    ]
    assert chamadas == [], "produção não constrói capacidade em lugar algum"


# ======================================================================
# E4.9.8.3 — guardas da proteção de legado
# ======================================================================


def test_s31_fonte_unica_do_vocabulario_de_protecao() -> None:
    """Um só `LegacyProtectionState` em todo `app/`.

    Um segundo enum com os mesmos membros criaria duas verdades sobre o
    que foi apresentado ao usuário, e a divergência apareceria no dia em
    que a re-resolução comparasse contra a fonte errada.
    """
    definicoes: list[str] = []
    for caminho in _fontes():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ClassDef) and no.name == "LegacyProtectionState":
                definicoes.append(str(caminho.relative_to(APP)))
    assert definicoes == ["memory/models/target_resolution_enums.py"]


def test_s32_o_vocabulario_tem_dois_membros_e_nenhum_generico() -> None:
    """`ABSENCE_OF_INFORMATION != NOT_PROTECTED`."""
    arvore = ast.parse(
        (APP / "memory" / "models" / "target_resolution_enums.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "LegacyProtectionState"
    ]
    membros = [
        no.target.id
        for no in classe.body
        if isinstance(no, ast.Assign | ast.AnnAssign)
        and isinstance(getattr(no, "target", None), ast.Name)
    ]
    membros += [
        no.targets[0].id
        for no in classe.body
        if isinstance(no, ast.Assign) and isinstance(no.targets[0], ast.Name)
    ]
    assert set(membros) == {"PROTECTED", "NOT_PROTECTED"}
    for proibido in ("UNKNOWN", "OTHER", "UNSPECIFIED", "DEFAULT", "INHERITED", "AUTO"):
        assert proibido not in membros


def test_s33_campo_obrigatorio_e_anotacao_fechada_nas_duas_classes() -> None:
    """`DEFAULT_LEGACY_PROTECTION_STATE = FORBIDDEN`.

    Reflexão para default — é onde a propriedade vive —, AST para a
    anotação, porque `str | bool | object | Any` seria erro de contrato
    estático que a reflexão sozinha não distingue de um enum.
    """
    import dataclasses
    import typing

    from app.memory.models.target_resolution_enums import LegacyProtectionState
    from app.memory.schemas.destructive_approval import SafeTargetSnapshot
    from app.memory.schemas.erasure_target import ErasureTargetDescriptor

    for classe in (ErasureTargetDescriptor, SafeTargetSnapshot):
        (campo,) = [c for c in dataclasses.fields(classe) if c.name == "legacy_protection_state"]
        assert campo.default is dataclasses.MISSING, classe.__name__
        assert campo.default_factory is dataclasses.MISSING, classe.__name__
        assert typing.get_type_hints(classe)["legacy_protection_state"] is (
            LegacyProtectionState
        ), classe.__name__

    for arquivo, nome in (
        ("erasure_target.py", "ErasureTargetDescriptor"),
        ("destructive_approval.py", "SafeTargetSnapshot"),
    ):
        arvore = ast.parse((APP / "memory" / "schemas" / arquivo).read_text(encoding="utf-8"))
        (classe_ast,) = [
            no for no in ast.walk(arvore) if isinstance(no, ast.ClassDef) and no.name == nome
        ]
        (anotacao,) = [
            no
            for no in classe_ast.body
            if isinstance(no, ast.AnnAssign)
            and isinstance(no.target, ast.Name)
            and no.target.id == "legacy_protection_state"
        ]
        assert anotacao.value is None, f"{nome}: default proibido"
        assert isinstance(anotacao.annotation, ast.Name)
        assert anotacao.annotation.id == "LegacyProtectionState", nome


def test_s34_validacao_de_membro_real_nos_dois_construtores() -> None:
    """Anotação sozinha não recusa nada em runtime — lição do A19/A20."""
    for arquivo, nome in (
        ("erasure_target.py", "ErasureTargetDescriptor"),
        ("destructive_approval.py", "SafeTargetSnapshot"),
    ):
        arvore = ast.parse((APP / "memory" / "schemas" / arquivo).read_text(encoding="utf-8"))
        (classe,) = [
            no for no in ast.walk(arvore) if isinstance(no, ast.ClassDef) and no.name == nome
        ]
        (post_init,) = [
            no
            for no in classe.body
            if isinstance(no, ast.FunctionDef) and no.name == "__post_init__"
        ]
        corpo = ast.unparse(post_init)
        assert "isinstance(self.legacy_protection_state, LegacyProtectionState)" in corpo, nome
        assert "raise TypeError" in corpo, nome


def test_s35_nenhuma_inferencia_de_protecao_no_codigo() -> None:
    """O estado vem da fronteira; não é derivado de nada.

    Busca por IDENTIFICADOR na AST, não substring — `protection` aparece
    legitimamente em docstring e nome de campo.
    """
    proibidos = {
        "infer_legacy_protection",
        "guess_protection",
        "derive_protection",
        "is_legacy",
        "looks_legacy",
        "default_protection",
    }
    for caminho in (
        APP / "memory" / "schemas" / "erasure_target.py",
        APP / "memory" / "schemas" / "destructive_approval.py",
        APP / "memory" / "models" / "target_resolution_enums.py",
    ):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        identificadores = {
            no.name for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef)
        } | {no.attr for no in ast.walk(arvore) if isinstance(no, ast.Attribute)}
        assert identificadores.isdisjoint(proibidos), identificadores & proibidos


def test_s36_protecao_nao_virou_blocker_nem_dimensao() -> None:
    """`PROTECTED` não é bloqueio automático nesta fatia.

    E a dimensão de recusa **não** foi ampliada: o motivo fechado já
    identifica a recusa, e ampliar `observed_dimension` seria delta
    público redundante.
    """
    from app.memory.models.approval_enums import ApprovalBlockerKind
    from app.memory.models.target_resolution_enums import RefusalDimension

    for membro in ApprovalBlockerKind.__members__:
        assert "LEGACY" not in membro
    for membro in RefusalDimension.__members__:
        assert "LEGACY" not in membro
    assert len(RefusalDimension) == 8


def test_s37_nenhuma_migration_orm_ou_repository_nesta_fatia() -> None:
    """`PERSISTENCE_DELTA = 0` e `MIGRATION_DELTA = 0`."""
    versoes = APP.parent / "alembic" / "versions"
    revisoes = {p.name.split("_")[0] for p in versoes.glob("*.py")}
    assert "c8a3f5017e94" in revisoes
    for arquivo in versoes.glob("*.py"):
        if arquivo.name.startswith("c8a3f5017e94"):
            continue
        texto = arquivo.read_text(encoding="utf-8")
        assert 'down_revision: str | None = "c8a3f5017e94"' not in texto, arquivo.name

    for caminho in (
        APP / "memory" / "schemas" / "erasure_target.py",
        APP / "memory" / "schemas" / "destructive_approval.py",
        APP / "memory" / "models" / "target_resolution_enums.py",
    ):
        executavel = _executavel(caminho)
        for proibido in ("mapped_column", "Mapped", "Session", "Repository", "sqlalchemy"):
            assert proibido not in executavel, f"{caminho.name}: {proibido}"


def test_s38_e4_9_9_a_nao_foi_iniciada() -> None:
    """A E4.9.9.a permanece bloqueada até `PASS_FINAL` independente."""
    ausentes = (
        "ApprovalRecord",
        "ApprovalRecordRepository",
        "ErasureEffectPort",
        "RetentionEvaluator",
        "DestructiveExecutionService",
    )
    infratores: list[str] = []
    for caminho in _fontes():
        executavel = _executavel(caminho)
        for simbolo in ausentes:
            if f"class {simbolo}" in executavel:
                infratores.append(f"{caminho.name}:{simbolo}")
    assert infratores == []


# --- §7.2: cada guarda consegue falhar -----------------------------------


def test_s99_9_a_guarda_de_default_detecta_default_acrescentado() -> None:
    """Reflexão distingue campo obrigatório de campo com default."""
    import dataclasses
    from enum import StrEnum

    class _E(StrEnum):
        A = "a"

    @dataclasses.dataclass(frozen=True)
    class _Obrigatorio:
        estado: _E

    @dataclasses.dataclass(frozen=True)
    class _ComDefault:
        estado: _E = _E.A

    def sem_default(classe: type) -> bool:
        (campo,) = [c for c in dataclasses.fields(classe) if c.name == "estado"]
        return campo.default is dataclasses.MISSING and campo.default_factory is dataclasses.MISSING

    assert sem_default(_Obrigatorio)
    assert not sem_default(_ComDefault)


def test_s99_10_a_guarda_de_anotacao_detecta_tipo_aberto() -> None:
    """`str | bool | object | Any` não é anotação fechada."""
    fechada = "class X:\n    legacy_protection_state: LegacyProtectionState\n"
    aberta = "class X:\n    legacy_protection_state: object\n"
    uniao = "class X:\n    legacy_protection_state: str | bool\n"

    def conforme(fonte: str) -> bool:
        arvore = ast.parse(fonte)
        (anotacao,) = [
            no
            for no in ast.walk(arvore)
            if isinstance(no, ast.AnnAssign)
            and isinstance(no.target, ast.Name)
            and no.target.id == "legacy_protection_state"
        ]
        return (
            isinstance(anotacao.annotation, ast.Name)
            and anotacao.annotation.id == "LegacyProtectionState"
        )

    assert conforme(fechada)
    assert not conforme(aberta)
    assert not conforme(uniao)


def test_s99_11_a_guarda_de_fonte_unica_detecta_enum_duplicado() -> None:
    """Um segundo enum em outro módulo é detectado pela contagem na AST."""
    um = "class LegacyProtectionState:\n    pass\n"
    dois = "class LegacyProtectionState:\n    pass\n\n\nclass Outro:\n    pass\n"
    tres = "class LegacyProtectionState:\n    pass\n\n\n" "class LegacyProtectionState:\n    pass\n"

    def quantas(fonte: str) -> int:
        return sum(
            1
            for no in ast.walk(ast.parse(fonte))
            if isinstance(no, ast.ClassDef) and no.name == "LegacyProtectionState"
        )

    assert quantas(um) == 1
    assert quantas(dois) == 1
    assert quantas(tres) == 2
