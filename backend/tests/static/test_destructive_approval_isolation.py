"""
Guardas de **isolamento** da aprovação destrutiva (`E4.9.8`).

```text
APPROVAL != EXECUTION != RECEIPT
```

Esta fatia materializa contratos e nada mais. As guardas provam o *nada
mais* por AST, `tokenize` e reflexão — nunca por busca textual frágil,
que acusaria as docstrings destes módulos, escritas justamente para
nomear o que eles **não** fazem.

`test_s99_*` no fim demonstra que cada mecanismo de guarda **consegue
falhar**, conforme o §11.5 do prompt: guarda que só pode passar não
protege nada.
"""

import ast
import dataclasses
import io
import pathlib
import tokenize

import pytest

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

CAMINHOS_NOVOS = (
    APP / "memory" / "models" / "approval_enums.py",
    APP / "memory" / "schemas" / "destructive_approval.py",
)

MODULOS_NOVOS = {
    "app.memory.models.approval_enums",
    "app.memory.schemas.destructive_approval",
}


def _executavel(arquivo: pathlib.Path) -> str:
    """Código sem docstrings, via AST."""
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


def _comentarios(arquivo: pathlib.Path) -> list[str]:
    fonte = arquivo.read_text(encoding="utf-8")
    return [
        token.string
        for token in tokenize.generate_tokens(io.StringIO(fonte).readline)
        if token.type == tokenize.COMMENT
    ]


# ======================================================================
# Escopo negativo
# ======================================================================


def test_s01_nenhuma_persistencia_orm_ou_repository() -> None:
    """Contratos transitórios — sem tabela, sessão ou writer."""
    proibidos = (
        "BaseModel",
        "mapped_column",
        "Mapped",
        "Session",
        "UnitOfWork",
        "Repository",
        "sqlalchemy",
        "alembic",
        "__tablename__",
        "commit",
        "flush",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s02_nenhum_efeito_destrutivo_nem_writer_de_recibo() -> None:
    """`APPROVAL_RECORD != ERASURE_RECORD`."""
    proibidos = (
        "ErasureRecord",
        "ErasureRecordRepository",
        "append_observed",
        "ErasureEffectPort",
        "execute_effect",
        "purge",
        "unlink",
        "shutil",
        "os.remove",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s03_nenhuma_rede_io_ou_cliente_externo() -> None:
    proibidos = (
        "requests",
        "httpx",
        "urllib.request",
        "urlopen",
        "boto3",
        "aiohttp",
        "socket",
        "subprocess",
        "open(",
        "pathlib",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s04_nenhuma_autenticacao_idp_ou_step_up_implementado() -> None:
    """`TYPED_ASSURANCE_CLAIM != AUTHENTICATION_PERFORMED`.

    `AssuranceLevel` e `IdentityEvidence` **representam** evidência; não
    há verificação, e estes nomes provam que nada foi construído.
    """
    proibidos = (
        "jwt",
        "oauth",
        "OAuth",
        "login",
        "authenticate(",
        "verify_password",
        "hashlib",
        "hmac",
        "bcrypt",
        "secrets",
        "IdentityProvider",
        "session_token",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s05_nenhum_parser_de_texto_ou_voz() -> None:
    proibidos = ("parse_command", "transcribe", "ASR", "speech", "def parse", "intent")
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s06_nenhum_relogio_implicito() -> None:
    """`datetime.now()` escondido é proibido — instante vem por argumento."""
    for caminho in CAMINHOS_NOVOS:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        atributos = {
            no.func.attr
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        }
        for termo in ("now", "utcnow", "today", "time", "monotonic"):
            assert termo not in atributos, f"{caminho.name}: {termo}"


def test_s07_nenhum_hash_ou_digest_de_escopo() -> None:
    """`PROPOSAL_DIGEST = NOT_USED`.

    O binding é estrutural. Um digest sobre dados de custódia poderia
    virar chave de relocalização sem canonicalização provada.
    """
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in ("sha256", "md5", "blake2", "digest", "hexdigest", "hash("):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s08_nenhum_serializer_logger_ou_dump() -> None:
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in ("to_dict", "model_dump", "json", "get_logger", "logging", "print("):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s09_nenhuma_supressao_de_tipo_nova() -> None:
    """Supressão vive em COMENTÁRIO; `Any` e `cast` vivem em CÓDIGO."""
    marcador = "type:" + " ignore"
    for caminho in CAMINHOS_NOVOS:
        assert not any(marcador in c for c in _comentarios(caminho)), caminho.name
        executavel = _executavel(caminho)
        assert "cast(" not in executavel, caminho.name
        assert ": Any" not in executavel, caminho.name


def test_s10_nenhum_import_de_app_cognitive() -> None:
    for caminho in CAMINHOS_NOVOS:
        importados = _modulos_importados(caminho)
        assert not any(m.startswith("app.cognitive") for m in importados), caminho.name


def test_s11_nenhuma_migration_nova() -> None:
    versoes = APP.parent / "alembic" / "versions"
    revisoes = {p.name.split("_")[0] for p in versoes.glob("*.py")}
    assert "c8a3f5017e94" in revisoes
    for arquivo in versoes.glob("*.py"):
        # E4.9.9.a: `a1f7c2d40e93` é a sucessora AUTORIZADA do head
        # anterior. A guarda continua provando que nenhuma OUTRA nasceu.
        if arquivo.name.startswith(("c8a3f5017e94", "a1f7c2d40e93")):
            continue
        texto = arquivo.read_text(encoding="utf-8")
        assert 'down_revision: str | None = "c8a3f5017e94"' not in texto, arquivo.name


def test_s12_nenhum_consumidor_de_producao_fora_dos_exports() -> None:
    """Contrato sem consumidor é o estado correto desta fatia."""
    # ATUALIZADO PELA E4.9.9.a: a persistência de aprovação é o primeiro
    # consumidor AUTORIZADO destes contratos — foi para isso que a
    # E4.9.8 os criou.
    #
    # O que a guarda continua provando, e é o que importa: nenhum
    # consumidor DESTRUTIVO apareceu. `test_approval_record_isolation`
    # prova pelo outro lado que a persistência não executa, não compõe
    # writer de recibo e não conhece efeito.
    permitidos = set(CAMINHOS_NOVOS) | {
        APP / "memory" / "models" / "__init__.py",
        APP / "memory" / "schemas" / "__init__.py",
        APP / "memory" / "models" / "approval_record.py",
        APP / "memory" / "repositories" / "approval_record_repository.py",
    }
    infratores = [
        str(p.relative_to(APP))
        for p in _fontes()
        if p not in permitidos and MODULOS_NOVOS & _modulos_importados(p)
    ]
    assert infratores == []


def test_s13_o_efeito_continua_sem_existir() -> None:
    infratores = [
        str(p.relative_to(APP)) for p in _fontes() if "ErasureEffectPort" in _executavel(p)
    ]
    assert infratores == []


# ======================================================================
# Contratos e assinaturas
# ======================================================================


def test_s14_todos_os_value_objects_sao_frozen() -> None:
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "destructive_approval.py").read_text(encoding="utf-8")
    )
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


def test_s15_os_sete_contratos_da_e4_9_7_nao_mudaram() -> None:
    """Retrato congelado — o A6 entrou por uma assinatura alterada sem intenção.

    Uma mudança de assinatura pública existente é Stop Condition mesmo
    que a suíte passe. Esta guarda a torna visível.
    """
    import inspect

    from app.memory.schemas import erasure_target as et

    retrato = {
        nome: (
            str(inspect.signature(getattr(et, nome))),
            tuple(
                (
                    c.name,
                    c.default is dataclasses.MISSING,
                    c.default_factory is dataclasses.MISSING,
                    c.repr,
                )
                for c in dataclasses.fields(getattr(et, nome))
            ),
        )
        for nome in (
            "ControlScope",
            "CustodyNamespace",
            "VerifiedDeletionCapability",
            "ReferenceProvenance",
            "ErasureTargetReference",
            "ErasureTargetDescriptor",
            "TargetResolutionRefusal",
        )
    }

    assert retrato["VerifiedDeletionCapability"][0] == (
        "(operation: str, scope: str, verified: bool) -> None"
    )
    assert retrato["ControlScope"][0] == (
        "(workspace_id: uuid.UUID, tenant_id: uuid.UUID, control_principal_ref: str) -> None"
    )
    assert retrato["CustodyNamespace"][0] == "(provider: str, namespace: str) -> None"

    # Campos sem default, por contrato — o inventário do A6.
    sem_default = {
        nome: tuple(campo for campo, sem, _, _ in campos if sem)
        for nome, (_, campos) in retrato.items()
    }
    assert sem_default["VerifiedDeletionCapability"] == ("operation", "scope", "verified")
    assert sem_default["ReferenceProvenance"] == ("origin",)
    # ATUALIZADO NA E4.9.8.3: `legacy_protection_state` é campo novo
    # OBRIGATÓRIO, quebra pública deliberada e autorizada. Continua sem
    # default — é a razão de existir da fatia.
    assert sem_default["ErasureTargetDescriptor"] == (
        "target_class",
        "subject_coid",
        "control_scope",
        "custody_namespace",
        "capability",
        "resolved_at",
        "origin",
        "legacy_protection_state",
        "transient_locator",
    )

    # Campos redigidos continuam redigidos.
    redigidos = {
        nome: {campo for campo, _, _, r in campos if r is False}
        for nome, (_, campos) in retrato.items()
    }
    assert redigidos["ControlScope"] == {"control_principal_ref"}
    assert redigidos["CustodyNamespace"] == {"provider", "namespace"}
    assert redigidos["VerifiedDeletionCapability"] == {"operation", "scope"}
    assert redigidos["ErasureTargetReference"] == {"opaque_reference"}
    assert redigidos["ErasureTargetDescriptor"] == {"transient_locator", "version_etag"}


def test_s16_a_resolucao_de_governanca_nao_e_delegada_no_repr() -> None:
    """O caso descoberto no preflight, fixado na AST.

    `GovernanceResolution` é da E4.3 e expõe onze campos `str` livres.
    Se alguém trocar `RESOLUCAO_OCULTA` por `{self.governance_resolution!r}`,
    os onze voltam a vazar pela composição.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "destructive_approval.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "DestructiveApprovalProposal"
    ]
    (repr_,) = [
        no for no in classe.body if isinstance(no, ast.FunctionDef) and no.name == "__repr__"
    ]
    corpo = ast.unparse(repr_)
    assert "RESOLUCAO_OCULTA" in corpo
    assert "governance_resolution!r" not in corpo
    assert "self.governance_resolution." not in corpo


AUTORIZADOS_NO_SNAPSHOT = {
    "target_class",
    "subject_coid",
    "control_scope",
    "custody_namespace",
    "origin",
    "legacy_protection_state",
    "version_etag",
}

PROPAGACAO_AUTOMATICA = ("asdict(", "**descriptor", "getattr(", "vars(", "fields(")


def _copia_do_materializador(fonte: str) -> tuple[set[str], set[str], bool]:
    """`(copiados, atributos_de_origem, usa_propagacao_automatica)`.

    Helper COMPARTILHADO entre `s17_1` e a demonstração `s99_18`
    (`E4.9.8.3.1`). Se a demonstração reimplementasse esta análise, provaria
    apenas que um mutante cai numa lógica escrita para o teste.

    ```text
    MUTANT_REJECTED_BY_PARALLEL_LOGIC != GUARD_CAN_FAIL
    ```
    """
    (metodo,) = [
        no
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.FunctionDef) and no.name == "from_descriptor"
    ]
    corpo = ast.unparse(metodo)
    automatica = any(forma in corpo for forma in PROPAGACAO_AUTOMATICA)

    (retorno,) = [no for no in ast.walk(metodo) if isinstance(no, ast.Return)]
    if not isinstance(retorno.value, ast.Call):
        return set(), set(), automatica

    copiados: set[str] = set()
    origens: set[str] = set()
    for kw in retorno.value.keywords:
        if kw.arg is None:
            automatica = True
            continue
        copiados.add(kw.arg)
        if (
            isinstance(kw.value, ast.Attribute)
            and isinstance(kw.value.value, ast.Name)
            and kw.value.value.id == "descriptor"
        ):
            origens.add(kw.value.attr)
    return copiados, origens, automatica


def test_s17_o_snapshot_nao_reutiliza_o_descritor() -> None:
    """`SNAPSHOT != ErasureTargetDescriptor` — o descritor tem localizador.

    ATUALIZADA NA E4.9.8.3, deliberadamente. A versão anterior proibia o
    **nome** `ErasureTargetDescriptor` no código executável, o que era
    exato enquanto não havia conversão alguma. `from_descriptor` precisa
    do tipo para recusar entrada errada, então a proibição por nome
    passaria a impedir a própria fronteira que ela protege.

    ```text
    NAME_MENTIONED != FIELD_REUSED
    ```

    O que continua provado, e é o que importa: o snapshot **não tem** campo
    de localizador, e `from_descriptor` **não copia** nenhum dos três
    campos excluídos.
    """
    import dataclasses

    from app.memory.schemas.destructive_approval import SafeTargetSnapshot

    campos = {c.name for c in dataclasses.fields(SafeTargetSnapshot)}
    for proibido in ("transient_locator", "capability", "resolved_at"):
        assert proibido not in campos, proibido

    arvore = ast.parse(
        (APP / "memory" / "schemas" / "destructive_approval.py").read_text(encoding="utf-8")
    )
    (metodo,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "from_descriptor"
    ]
    corpo = ast.unparse(metodo)
    for proibido in (
        "descriptor.transient_locator",
        "descriptor.capability",
        "descriptor.resolved_at",
    ):
        assert proibido not in corpo, proibido


def test_s17_1_o_materializador_copia_campo_a_campo() -> None:
    """Cópia explícita, nunca reflexão (`E4.9.8.3`).

    ```text
    EXPLICIT_COPY != AUTOMATIC_PROPAGATION
    ```

    Com `asdict`, `**` ou reflexão, um campo novo no descritor entraria no
    snapshot **sozinho**, sem ninguém decidir — e é exatamente assim que
    `transient_locator` atravessaria a fronteira que a E4.9.7 gastou dois
    corretivos para estabelecer.

    Esta guarda fixa na AST os sete copiados. Um oitavo campo copiado, ou
    qualquer forma automática, derruba o teste.
    """
    copiados, origens, automatica = _copia_do_materializador(
        (APP / "memory" / "schemas" / "destructive_approval.py").read_text(encoding="utf-8")
    )
    assert not automatica, "propagação automática"
    assert copiados == AUTORIZADOS_NO_SNAPSHOT, copiados
    assert origens == AUTORIZADOS_NO_SNAPSHOT, origens
    assert origens.isdisjoint({"transient_locator", "capability", "resolved_at"})


def test_s18_enums_novos_nao_duplicam_fonte_da_verdade() -> None:
    executavel = _executavel(APP / "memory" / "models" / "approval_enums.py")
    for proibido in (
        "class ErasureTargetClass",
        "class ErasureOutcome",
        "class RetentionExpiryAction",
        "class RefusalDimension",
        "pia_managed_artifact",
        "assess_and_inform",
    ):
        assert proibido not in executavel, proibido


# ======================================================================
# §11.5 — cada mecanismo de guarda consegue falhar
# ======================================================================


def test_s99_1_a_busca_por_ast_acusa_termo_realmente_presente() -> None:
    """Mutante local: um módulo com o termo proibido derruba a guarda.

    Sem esta demonstração, `test_s01`–`s08` poderiam estar passando por
    olharem no lugar errado, e ninguém saberia.
    """
    mutante = pathlib.Path("/tmp/_e498_mutante.py")
    mutante.write_text('"""ErasureEffectPort só aqui."""\nx = "ErasureEffectPort"\n')
    try:
        assert "ErasureEffectPort" in _executavel(mutante)
        limpo = pathlib.Path("/tmp/_e498_limpo.py")
        limpo.write_text('"""ErasureEffectPort só na docstring."""\nx = 1\n')
        assert "ErasureEffectPort" not in _executavel(limpo)
        limpo.unlink()
    finally:
        mutante.unlink(missing_ok=True)


def test_s99_2_a_busca_por_tokenize_acusa_supressao_real() -> None:
    """E ignora a docstring que apenas a menciona."""
    marcador = "type:" + " ignore"
    mutante = pathlib.Path("/tmp/_e498_supressao.py")
    mutante.write_text(f'"""fala de {marcador} na docstring."""\nx = 1  # {marcador}[arg-type]\n')
    try:
        assert any(marcador in c for c in _comentarios(mutante))
    finally:
        mutante.unlink(missing_ok=True)

    so_docstring = pathlib.Path("/tmp/_e498_docstring.py")
    so_docstring.write_text(f'"""menciona {marcador} e nada mais."""\nx = 1\n')
    try:
        assert not any(marcador in c for c in _comentarios(so_docstring))
    finally:
        so_docstring.unlink(missing_ok=True)


def test_s99_3_o_retrato_de_assinatura_detecta_default_novo() -> None:
    """Prova que `s15` cairia se um default fosse acrescentado."""

    @dataclasses.dataclass(frozen=True)
    class _Antes:
        obrigatorio: bool

    @dataclasses.dataclass(frozen=True)
    class _Depois:
        obrigatorio: bool = True

    def sem_default(classe: type) -> tuple[str, ...]:
        return tuple(
            c.name
            for c in dataclasses.fields(classe)
            if c.default is dataclasses.MISSING and c.default_factory is dataclasses.MISSING
        )

    assert sem_default(_Antes) == ("obrigatorio",)
    assert sem_default(_Depois) == ()


def test_s99_4_a_prova_de_confidencialidade_detecta_vazamento_real() -> None:
    """Um objeto que delega `!r` a um campo livre vaza — e é detectado."""
    marcador = "https://user:password@example.invalid/o?token=S99"

    @dataclasses.dataclass(frozen=True)
    class _Vazando:
        campo: str

    @dataclasses.dataclass(frozen=True)
    class _Redigido:
        campo: str = dataclasses.field(repr=False)

        def __repr__(self) -> str:
            return "_Redigido(campo=<text:redacted>)"

    assert marcador in repr(_Vazando(marcador))
    assert marcador not in repr(_Redigido(marcador))


def test_s99_5_os_quatro_scripts_externos_continuam_intocados() -> None:
    """Nenhum arquivo de caracterização vive no repositório.

    Os scripts são externos por desenho: se algum fosse copiado para
    dentro, poderia ser editado junto com o código que ele mede.
    """
    with pytest.raises(StopIteration):
        next(iter(sorted((APP.parent).rglob("reproduce_e49*.py"))))


# ======================================================================
# E4.9.8.1 — guardas do binding
# ======================================================================


def test_s19_a_matriz_de_operacao_e_fonte_unica() -> None:
    """`WRONG_OPERATION != APPROVABLE`, com uma só fonte.

    Se alguém escrever a correspondência em linha dentro do
    `__post_init__`, passa a haver duas verdades sobre qual pergunta a
    governança precisa ter respondido.
    """
    fonte = (APP / "memory" / "schemas" / "destructive_approval.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    definicoes = [
        no
        for no in arvore.body
        if isinstance(no, ast.AnnAssign)
        and isinstance(no.target, ast.Name)
        and no.target.id == "OPERACAO_DE_GOVERNANCA"
    ]
    assert len(definicoes) == 1

    executavel = _executavel(APP / "memory" / "schemas" / "destructive_approval.py")
    assert executavel.count("CognitiveOperation.LEGAL_ERASURE") == 1
    assert executavel.count("CognitiveOperation.RETENTION_DISPOSITION") == 1


def test_s20_o_binding_de_governanca_vive_no_construtor() -> None:
    """As quatro verificações da proposta, provadas na AST.

    A cadeia 85 tinha apenas `isinstance`. Se alguém remover qualquer uma
    destas, o EDR volta a afirmar um binding que o runtime não faz.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "destructive_approval.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "DestructiveApprovalProposal"
    ]
    (post_init,) = [
        no for no in classe.body if isinstance(no, ast.FunctionDef) and no.name == "__post_init__"
    ]
    corpo = ast.unparse(post_init)
    for exigido in (
        "GovernanceOutcome.ADMISSIBLE",
        "execution_authorized",
        "OPERACAO_DE_GOVERNANCA",
        "context_domain_ids",
        "context_purpose",
    ):
        assert exigido in corpo, exigido


def test_s21_o_binding_de_identidade_vive_no_envelope() -> None:
    """Ator, principal de controle e frescor temporal."""
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "destructive_approval.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "DestructiveApprovalEnvelope"
    ]
    (post_init,) = [
        no for no in classe.body if isinstance(no, ast.FunctionDef) and no.name == "__post_init__"
    ]
    corpo = ast.unparse(post_init)
    for exigido in ("context_actor_ref", "control_principal_ref", "authenticated_at"):
        assert exigido in corpo, exigido


def test_s22_nenhuma_delegacao_foi_inventada() -> None:
    """Limite declarado: só o caso direto é representado.

    A busca é por IDENTIFICADOR, não por substring. A primeira versão
    desta guarda procurava `"role"` e `"acl"` no texto e acusava
    "cont**role**" e "dat**acl**ass" — o mesmo falso positivo de
    substring que já custou correções nas fatias anteriores. Nomes de
    variável, atributo, campo e função são o lugar onde delegação
    apareceria de fato.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "destructive_approval.py").read_text(encoding="utf-8")
    )
    identificadores: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            identificadores.add(no.id)
        elif isinstance(no, ast.Attribute):
            identificadores.add(no.attr)
        elif isinstance(no, ast.FunctionDef | ast.ClassDef):
            identificadores.add(no.name)
        elif isinstance(no, ast.arg):
            identificadores.add(no.arg)

    proibidos = {
        "delegate",
        "delegation",
        "delegated_by",
        "on_behalf_of",
        "impersonate",
        "admin_override",
        "role",
        "role_id",
        "group",
        "group_id",
        "acl",
        "proxy",
        "power_of_attorney",
    }
    assert identificadores.isdisjoint(proibidos), identificadores & proibidos


def test_s23_os_helpers_publicos_sao_estritos() -> None:
    """`ANNOTATION != ENFORCED_TYPE`.

    A anotação sozinha não recusa nada em runtime — foi exatamente assim
    que A15/A16 passaram. A guarda exige o `isinstance` explícito.
    """
    arvore = ast.parse(
        (APP / "memory" / "models" / "approval_enums.py").read_text(encoding="utf-8")
    )
    for nome, tipo in (
        ("satisfies", "DestructiveOperation"),
        ("permite_proposta", "InputChannel"),
    ):
        (metodo,) = [
            no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef) and no.name == nome
        ]
        corpo = ast.unparse(metodo)
        assert f"isinstance(operacao, {tipo})" in corpo or f"isinstance(canal, {tipo})" in corpo
        assert "raise TypeError" in corpo


def test_s24_nenhum_relogio_entrou_com_o_frescor() -> None:
    """O frescor usa instantes RECEBIDOS, não um relógio interno."""
    for caminho in CAMINHOS_NOVOS:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        atributos = {
            no.func.attr
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        }
        for termo in ("now", "utcnow", "today"):
            assert termo not in atributos, f"{caminho.name}: {termo}"


def test_s99_6_a_guarda_de_binding_detecta_remocao_real() -> None:
    """§11.5 — o mecanismo de `s20`/`s21` consegue falhar.

    Um `__post_init__` sem a verificação é detectado; um com ela, não.
    """
    com = ast.parse(
        "class X:\n"
        "    def __post_init__(self):\n"
        "        if r.outcome is not GovernanceOutcome.ADMISSIBLE:\n"
        "            raise ValueError('x')\n"
    )
    sem = ast.parse("class X:\n    def __post_init__(self):\n        pass\n")

    def tem_binding(arvore: ast.Module) -> bool:
        (metodo,) = [
            no
            for no in ast.walk(arvore)
            if isinstance(no, ast.FunctionDef) and no.name == "__post_init__"
        ]
        return "GovernanceOutcome.ADMISSIBLE" in ast.unparse(metodo)

    assert tem_binding(com)
    assert not tem_binding(sem)


def test_s99_7_a_guarda_de_helper_exige_anotacao_E_runtime() -> None:
    """§11.5 — e CORRIGIDA na E4.9.8.2.

    A versão da cadeia 86 apresentava `operacao: object` como a versão
    **correta**, desde que houvesse `isinstance`. Minha própria
    demonstração sancionava a ampliação estática que a auditoria depois
    classificou como regressão de contrato público.

    ```text
    STATIC_TYPE_CONTRACT != RUNTIME_TYPE_ENFORCEMENT
    BOTH_REQUIRED = TRUE
    ```

    Os três mutantes cobrem as três combinações erradas.
    """
    so_anotacao = (
        "def satisfies(self, operacao: DestructiveOperation) -> bool:\n" "    return True\n"
    )
    so_runtime = (
        "def satisfies(self, operacao: object) -> bool:\n"
        "    if not isinstance(operacao, DestructiveOperation):\n"
        "        raise TypeError('x')\n"
        "    return True\n"
    )
    nenhum = "def satisfies(self, operacao: object) -> bool:\n    return True\n"
    correto = (
        "def satisfies(self, operacao: DestructiveOperation) -> bool:\n"
        "    if not isinstance(operacao, DestructiveOperation):\n"
        "        raise TypeError('x')\n"
        "    return True\n"
    )

    def conforme(fonte: str) -> bool:
        (metodo,) = [
            no
            for no in ast.walk(ast.parse(fonte))
            if isinstance(no, ast.FunctionDef) and no.name == "satisfies"
        ]
        (argumento,) = [a for a in metodo.args.args if a.arg == "operacao"]
        anotacao_exata = (
            isinstance(argumento.annotation, ast.Name)
            and argumento.annotation.id == "DestructiveOperation"
        )
        corpo = ast.unparse(metodo)
        runtime = (
            "isinstance(operacao, DestructiveOperation)" in corpo and "raise TypeError" in corpo
        )
        return anotacao_exata and runtime

    assert not conforme(so_anotacao), "anotação sem runtime não fecha"
    assert not conforme(so_runtime), "runtime com anotação ampliada não fecha"
    assert not conforme(nenhum)
    assert conforme(correto)


def test_s99_8_a_guarda_de_delegacao_distingue_identificador_de_substring() -> None:
    """§11.5 — e prova que o falso positivo de substring foi eliminado.

    `controle` contém `role` e `dataclass` contém `acl`. A guarda por
    identificador não os acusa; a busca por substring acusaria os dois.
    """
    inocente = ast.parse("from dataclasses import dataclass\ncontrole = 1\n")
    culpado = ast.parse("def resolver(role_id):\n    return role_id\n")

    def identificadores(arvore: ast.Module) -> set[str]:
        vistos: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Name):
                vistos.add(no.id)
            elif isinstance(no, ast.arg):
                vistos.add(no.arg)
        return vistos

    assert "role" not in identificadores(inocente)
    assert "acl" not in identificadores(inocente)
    assert "role_id" in identificadores(culpado)


def test_s99_18_a_guarda_do_materializador_detecta_as_tres_alteracoes() -> None:
    """`s17_1` — copiar excluído, omitir autorizado, propagar automático.

    §3.1 do corretivo da E4.9.8.3.1. A cadeia 88 publicou `s17_1` sem
    demonstração de falha; sem ela, "a guarda existe" e "a guarda pega o
    defeito" eram a mesma afirmação sem prova.
    """
    correto = (
        "def from_descriptor(cls, descriptor):\n"
        "    return cls(\n"
        "        target_class=descriptor.target_class,\n"
        "        subject_coid=descriptor.subject_coid,\n"
        "        control_scope=descriptor.control_scope,\n"
        "        custody_namespace=descriptor.custody_namespace,\n"
        "        origin=descriptor.origin,\n"
        "        legacy_protection_state=descriptor.legacy_protection_state,\n"
        "        version_etag=descriptor.version_etag,\n"
        "    )\n"
    )
    copia_localizador = correto.replace(
        "        version_etag=descriptor.version_etag,\n",
        "        version_etag=descriptor.transient_locator,\n",
    )
    omite_protecao = correto.replace(
        "        legacy_protection_state=descriptor.legacy_protection_state,\n", ""
    )
    propagacao = (
        "def from_descriptor(cls, descriptor):\n"
        "    return cls(**dataclasses.asdict(descriptor))\n"
    )

    copiados, origens, automatica = _copia_do_materializador(correto)
    assert not automatica
    assert copiados == AUTORIZADOS_NO_SNAPSHOT
    assert origens == AUTORIZADOS_NO_SNAPSHOT

    _, origens_mut, _ = _copia_do_materializador(copia_localizador)
    assert "transient_locator" in origens_mut, "campo excluído copiado"
    assert origens_mut != AUTORIZADOS_NO_SNAPSHOT

    copiados_mut, _, _ = _copia_do_materializador(omite_protecao)
    assert copiados_mut != AUTORIZADOS_NO_SNAPSHOT, "campo autorizado omitido"

    _, _, automatica_mut = _copia_do_materializador(propagacao)
    assert automatica_mut, "propagação automática detectada"
