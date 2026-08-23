"""
Guarda estática da fronteira da orquestração `E7.1`, com mutantes.

```text
E7_NEVER ciência (E5), DTO público (E6.1), identidade humana (E8),
         efeito externo (E9), aprovação destrutiva (E4.9)
PERSISTENCE_ONLY_THROUGH_REPOSITORY = TRUE
SINGLE_PRODUCER_PER_OBJECT = TRUE
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
```

Tudo por AST e por leitura de arquivo. Docstring não é símbolo de
runtime, e por isso os invariantes que citam nomes proibidos são medidos
sobre a árvore sintática, não sobre o texto — exceto onde o alvo é
justamente o texto de um arquivo de requisitos.
"""

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

BACKEND = pathlib.Path(__file__).resolve().parents[2]
ORQUESTRACAO = BACKEND / "app" / "orchestration"
SERVICOS = ORQUESTRACAO / "services"
SCHEMAS = ORQUESTRACAO / "schemas"
REPOSITORIOS = ORQUESTRACAO / "repositories"
ENVELOPE = SCHEMAS / "envelope.py"
HANDOFF = SERVICOS / "handoff_service.py"
SCHEDULE = SERVICOS / "schedule_service.py"
COMANDO = SERVICOS / "command_receipt_service.py"
BASE_REQUIREMENTS = BACKEND / "requirements" / "base.txt"

#: Escopo negativo absoluto do prompt ativo da E7.1.
SIMBOLOS_PROIBIDOS = frozenset(
    {
        "ProvenanceRecord",
        "ProvenanceManager",
        "provenance_records",
        "CognitiveObject",
        "ApprovalRecord",
        "approval_records",
        "DestructiveOperation",
        "PiapEnvelope",
    }
)

#: Dependências de runtime que a E7.1 não pode introduzir (Stop Condition S17).
DEPENDENCIAS_PROIBIDAS = frozenset(
    {"httpx", "requests", "aiohttp", "celery", "rq", "arq", "kafka", "redis", "apscheduler"}
)

#: Camadas que a E7 nunca importa.
PACOTES_PROIBIDOS = (
    "app.predictive_accessibility",
    "app.memory",
    "app.cognitive",
    "app.routers",
    "app.api",
    "fastapi",
)


def _arquivos_de_producao() -> list[pathlib.Path]:
    return sorted(p for p in ORQUESTRACAO.rglob("*.py"))


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _imports(caminho: pathlib.Path) -> list[str]:
    modulos: list[str] = []
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Import):
            modulos.extend(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    return modulos


def _nomes(caminho: pathlib.Path) -> set[str]:
    """Todo identificador, atributo e literal de string da árvore."""
    encontrados: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Name):
            encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            encontrados.add(no.attr)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            encontrados.add(no.value)
        elif isinstance(no, ast.alias):
            encontrados.add(no.name.split(".")[-1])
    return encontrados


def _chamados(caminho: pathlib.Path) -> set[str]:
    return {
        no.func.id if isinstance(no.func, ast.Name) else no.func.attr
        for no in ast.walk(_arvore(caminho))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name | ast.Attribute)
    }


def _construidos(caminho: pathlib.Path) -> set[str]:
    return {
        no.func.id
        for no in ast.walk(_arvore(caminho))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }


def _chamadas_qualificadas(caminho: pathlib.Path) -> set[str]:
    """Chamadas com o receptor, ex. `self._repository.create_schedule`.

    Distinguir receptor é o que separa **produzir** de **delegar**: o
    `CommandReceiptService` chama `create_schedule` no `ScheduleService`,
    que é composição legítima; produzir seria chamá-la no repositório.
    """
    qualificadas: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
            qualificadas.add(ast.unparse(no.func))
    return qualificadas


def _literais_de_codigo(caminho: pathlib.Path) -> set[str]:
    """Strings do código EXCLUINDO docstrings — texto não é comportamento."""
    arvore = _arvore(caminho)
    docstrings: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            corpo = getattr(no, "body", [])
            if (
                corpo
                and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)
                and isinstance(corpo[0].value.value, str)
            ):
                docstrings.add(id(corpo[0].value))
        # Docstrings de atributo (a linha logo após uma anotação) seguem o
        # mesmo padrão `Expr(Constant(str))` e são excluídas junto. Nem todo
        # nó com `body` tem lista: `ListComp.body` é uma expressão.
        corpo = getattr(no, "body", None)
        if not isinstance(corpo, list):
            continue
        for filho in corpo:
            if (
                isinstance(filho, ast.Expr)
                and isinstance(filho.value, ast.Constant)
                and isinstance(filho.value.value, str)
            ):
                docstrings.add(id(filho.value))
    return {
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docstrings
    }


# --- escopo negativo --------------------------------------------------------


def test_e71b01_nenhum_arquivo_da_e7_referencia_simbolo_proibido() -> None:
    """`D1 = REFERENCE_ONLY`; `S18`/`S20`; sem `approval_records` (C1)."""
    for caminho in _arquivos_de_producao():
        encontrados = _nomes(caminho) & SIMBOLOS_PROIBIDOS
        assert not encontrados, f"{caminho.name}: {sorted(encontrados)}"


def test_e71b02_a_e7_nao_importa_ciencia_memoria_cognicao_nem_api() -> None:
    for caminho in _arquivos_de_producao():
        for modulo in _imports(caminho):
            for proibido in PACOTES_PROIBIDOS:
                assert not modulo.startswith(proibido), f"{caminho.name} importa {modulo}"


def test_e71b03_a_e7_nao_importa_rede_fila_worker_nem_scheduler() -> None:
    """Stop Condition S17 medida no import, não na intenção."""
    for caminho in _arquivos_de_producao():
        for modulo in _imports(caminho):
            raiz = modulo.split(".")[0]
            assert raiz not in DEPENDENCIAS_PROIBIDAS, f"{caminho.name} importa {modulo}"
            assert raiz not in {"socket", "urllib", "http"}, f"{caminho.name} importa {modulo}"


def test_e71b04_nenhuma_dependencia_de_runtime_nova_em_base_txt() -> None:
    conteudo = BASE_REQUIREMENTS.read_text(encoding="utf-8").lower()
    for pacote in DEPENDENCIAS_PROIBIDAS:
        assert pacote not in conteudo, f"base.txt passou a conter {pacote}"


def test_e71b05_o_dominio_da_orquestracao_nao_cria_rota() -> None:
    """O DOMÍNIO segue sem API; a rota vive em `app/routers/`.

    ```text
    DOMAIN_PACKAGE != TRANSPORT_LAYER
    ```

    ATUALIZADO PELA E7.2: a versão anterior exigia que `api/router.py`
    sequer mencionasse orquestração, porque na E7.1 **nenhuma** rota
    existia. A E7.2 criou cinco, autorizadas por plano próprio. O que esta
    guarda protege continua valendo e ficou mais preciso: nenhum arquivo
    de `app/orchestration/**` declara rota ou dependency — se declarasse,
    o domínio passaria a conhecer FastAPI e a fronteira se dissolveria.
    """
    for caminho in _arquivos_de_producao():
        chamados = _chamados(caminho)
        assert "APIRouter" not in chamados, caminho.name
        assert "Depends" not in chamados, caminho.name
        for modulo in _imports(caminho):
            assert not modulo.startswith("fastapi"), f"{caminho.name} importa {modulo}"


# --- fronteira de persistência ----------------------------------------------


def test_e71b06_apenas_o_repositorio_fala_sqlalchemy() -> None:
    """`RAW_SQL_IN_SERVICE = FORBIDDEN`; `SESSION_OUTSIDE_REPOSITORY = FORBIDDEN`."""
    for caminho in sorted(SERVICOS.glob("*.py")) + sorted(SCHEMAS.glob("*.py")):
        for modulo in _imports(caminho):
            assert not modulo.startswith("sqlalchemy"), f"{caminho.name} importa {modulo}"
        assert "text" not in _construidos(caminho), caminho.name
        assert "session" not in {
            no.attr for no in ast.walk(_arvore(caminho)) if isinstance(no, ast.Attribute)
        }, caminho.name


def test_e71b07_o_contrato_do_envelope_nao_depende_de_persistencia() -> None:
    for modulo in _imports(ENVELOPE):
        assert not modulo.startswith(("sqlalchemy", "app.models", "app.orchestration.models"))


def test_e71b08_todo_sql_cru_da_e7_vive_no_repositorio() -> None:
    """Medido sobre literais de CÓDIGO, não sobre docstrings.

    Um comentário que explica por que o `DO UPDATE` existe não executa
    SQL; medir o texto bruto confundiria documentação com comportamento.
    """
    for caminho in _arquivos_de_producao():
        if caminho.parent == REPOSITORIOS:
            continue
        for literal in _literais_de_codigo(caminho):
            maiusculo = literal.upper()
            for verbo in ("INSERT INTO", "UPDATE ", "DELETE FROM", "SELECT "):
                assert verbo not in maiusculo, f"{caminho.name} contém SQL cru: {literal!r}"


# --- produtor único (MAI §21) -----------------------------------------------


def test_e71b09_apenas_o_handoff_service_produz_tentativa_e_recibo_de_selamento() -> None:
    """`HandoffService -> ENVELOPE_CONTENT, SealReceipt, Attempt`."""
    produtores = {"create_attempt", "create_seal_receipt"}
    for caminho in sorted(SERVICOS.glob("*.py")):
        chamados = _chamados(caminho) & produtores
        if caminho == HANDOFF:
            assert chamados == produtores, f"{caminho.name}: {sorted(chamados)}"
        else:
            assert not chamados, f"{caminho.name} produz selamento: {sorted(chamados)}"


def test_e71b10_apenas_o_schedule_service_produz_schedule_no_repositorio() -> None:
    """Produzir é chamar o repositório; delegar ao produtor não é produzir."""
    for caminho in sorted(SERVICOS.glob("*.py")):
        produz = "self._repository.create_schedule" in _chamadas_qualificadas(caminho)
        assert produz is (caminho == SCHEDULE), caminho.name
    # O serviço de comando compõe o produtor, nunca o repositório de escrita.
    qualificadas = _chamadas_qualificadas(COMANDO)
    assert "self._schedule_service.create_schedule" in qualificadas
    assert not {c for c in qualificadas if c.startswith("self._repository.create_")}


def test_e71b11_apenas_o_command_receipt_service_reivindica_comando() -> None:
    for caminho in sorted(SERVICOS.glob("*.py")):
        reivindica = "claim_command" in _chamados(caminho)
        assert reivindica is (caminho == COMANDO), caminho.name


def test_e71b12_nenhum_servico_constroi_modelo_orm_diretamente() -> None:
    modelos = {"Schedule", "ScheduleStep", "HandoffAttempt", "SealReceipt", "CommandReceipt"}
    for caminho in sorted(SERVICOS.glob("*.py")):
        assert not (_construidos(caminho) & modelos), caminho.name


# --- regra temporal do conteúdo (MAI §3 e §21) ------------------------------


def test_e71b13_o_conteudo_nao_declara_campo_do_recibo() -> None:
    """`NO_COMPOSITE_DEPENDS_ON_DOWNSTREAM_COMPONENT`."""
    classes = {no.name: no for no in _arvore(ENVELOPE).body if isinstance(no, ast.ClassDef)}
    campos = {
        alvo.target.id
        for alvo in classes["EnvelopeContent"].body
        if isinstance(alvo, ast.AnnAssign) and isinstance(alvo.target, ast.Name)
    }
    assert campos == {
        "envelope_version",
        "schedule_id",
        "step_id",
        "role",
        "instruction_ref",
        "context_refs",
        "expected_output_contract",
        "constraints",
    }
    assert not (campos & {"sealed_at", "attempt_id", "sealer_ref"})


def test_e71b14_o_calculo_do_hash_nao_le_relogio() -> None:
    """Nenhuma chamada temporal no módulo de contrato."""
    temporais = {"now", "utcnow", "today", "time", "monotonic", "database_now"}
    assert not (_chamados(ENVELOPE) & temporais)
    for modulo in _imports(ENVELOPE):
        assert modulo not in {"datetime", "time"}, modulo


def test_e71b15_o_content_hash_nunca_e_usado_como_chave_de_comando() -> None:
    """`M-c`: `COMMAND_IDEMPOTENCY_KEY` é do chamador, não do conteúdo.

    ```text
    SAME_CONTENT != SAME_ATTEMPT
    FINGERPRINT_INGREDIENT != IDEMPOTENCY_KEY
    ```

    ATUALIZADO PELO CORRETIVO R1: a versão anterior proibia a substring
    `content_sha256` no módulo inteiro. O corretivo passou a incluir o
    hash do conteúdo como **ingrediente** da impressão digital da
    requisição — uso legítimo e exigido, que a proibição textual
    confundiria com "usar o hash como chave".

    A guarda passa a medir o que importa: em toda chamada, o argumento
    `command_key` é literalmente a chave recebida do chamador, e nunca
    uma expressão derivada de conteúdo.
    """
    # Só as chamadas que ESCREVEM a chave: `claim_command` no repositório e
    # `_executar_uma_vez` no próprio serviço. Montar o DTO de saída a
    # partir do recibo (`command_key=recibo.command_key`) é leitura, não
    # escolha de chave.
    escritores = {"claim_command", "_executar_uma_vez"}
    conferidas = 0
    for no in ast.walk(_arvore(COMANDO)):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func.id if isinstance(no.func, ast.Name) else getattr(no.func, "attr", "")
        if alvo not in escritores:
            continue
        for argumento in no.keywords:
            if argumento.arg == "command_key":
                assert ast.unparse(argumento.value) == "command_key", ast.unparse(no)
                conferidas += 1
    assert conferidas >= 4, f"esperado ao menos 4 chamadas escritoras, achei {conferidas}"
    # O hash de conteúdo existe, e só como ingrediente da impressão digital.
    assert "_digest_de_conteudo" in _nomes(COMANDO)


def test_e71b16_o_selamento_nao_altera_estado_de_etapa() -> None:
    """`SEALED != DISPATCHED` — nenhuma transição de etapa na E7.1."""
    assert "DISPATCHED" not in _nomes(HANDOFF)
    atribuicoes = {
        ast.unparse(alvo)
        for no in ast.walk(_arvore(HANDOFF))
        if isinstance(no, ast.Assign)
        for alvo in no.targets
    }
    assert not {a for a in atribuicoes if a.endswith(".state")}, atribuicoes
    from app.orchestration.models.enums import E7_1_IMPLEMENTED_STEP_TRANSITIONS

    assert not E7_1_IMPLEMENTED_STEP_TRANSITIONS


def test_e71b17_a_orquestracao_nao_antecipa_a_e7_3() -> None:
    """Nada de delegação, gate, auditoria, cancelamento ou Stop Condition runtime."""
    # ATUALIZADO PELA E7.2: `HandoffResult`, `HandoffAttribution` e
    # `ReturnValidationService` saíram da lista porque deixaram de ser
    # antecipação e passaram a ser entrega autorizada. Os objetos da E7.3
    # permanecem proibidos — a lista mede o que ainda NÃO foi autorizado,
    # não o que um dia esteve fora do escopo.
    # ATUALIZADO PELA E7.3 — mesma razão de sempre: a lista mede o que
    # ainda NÃO foi autorizado, não o que um dia esteve fora do escopo.
    proibidos = {
        "StopConditionRuntime",
        "HardCancelService",
        "TimeoutWorker",
        "BudgetEnforcer",
        "GovernedSynthesis",
        "auto_advance",
    }
    for caminho in _arquivos_de_producao():
        assert not (_nomes(caminho) & proibidos), caminho.name


REPOSITORIO = REPOSITORIOS / "orchestration_repository.py"

#: Classificação EXAUSTIVA dos métodos públicos do repositório.
#:
#: ```text
#: PARTIAL_ENUMERATION = GUARD_WITH_A_HOLE
#: ```
#:
#: A Chain110 listava cinco métodos escopados e nada dizia sobre os
#: demais — os cinco caminhos de tentativa e recibo passaram pelo gate
#: sem serem medidos. Agora todo método público cai em exatamente uma
#: categoria, e um método novo que não esteja classificado REPROVA o
#: gate em vez de ser ignorado por omissão.
CONTROL_BOUND = frozenset(
    {
        "create_schedule",
        "get_schedule",
        "lock_schedule",
        "set_schedule_state",
        "list_steps",
        "get_step",
        "next_attempt_number",
        "create_attempt",
        "create_seal_receipt",
        "get_attempt",
        "get_seal_receipt_by_attempt",
        "list_attempts",
        # --- E7.3 ---
        "expire_stale_delegations",
        "revoke_active_delegations",
        "create_delegation",
        "get_active_delegation",
        "get_delegation",
        "consume_delegation",
        "list_delegations",
        "create_control_event",
        "list_control_events",
        "count_open_pause_events",
        "list_open_attempts_of_schedule",
        "all_steps_returned",
        "get_last_attribution_before",
        "create_execution_observation",
        "list_execution_observations",
        "get_result_for_audit",
        "get_control_event",
        "get_audit_opinion",
        "create_audit_opinion",
        "list_audit_opinions",
        # --- E7.2 ---
        "lock_step",
        "set_step_state",
        "lock_attempt",
        "set_attempt_state",
        "get_open_attempt",
        "list_unreturned_predecessors",
        "create_handoff_result",
        "create_handoff_attribution",
        "get_handoff_result",
        "get_handoff_attribution",
    }
)
"""Exigem `control_principal_ref` na assinatura E o impõem no corpo.

ATUALIZADO PELA E7.2: dez métodos novos entraram, e a contagem total do
repositório subiu. Nenhum entrou por omissão — o teste de exaustividade
reprova qualquer método público sem categoria.
"""

PRINCIPAL_BOUND = frozenset({"claim_command", "get_command_receipt"})
"""Escopados pelo principal TÉCNICO do comando, não pelo de controle."""

REFUSAL_ONLY = frozenset(
    {
        "update_seal_receipt",
        "delete_seal_receipt",
        "update_handoff_record",
        "delete_handoff_record",
        "update_governance_record",
        "delete_governance_record",
    }
)
"""Recusam incondicionalmente; escopo é irrelevante porque nada executam."""

SCOPE_EXEMPT = frozenset({"database_now"})
"""Não tocam entidade alguma. Única isenção admitida."""


def _metodos_publicos_do_repositorio() -> dict[str, ast.FunctionDef]:
    arvore = _arvore(REPOSITORIO)
    classes = [no for no in arvore.body if isinstance(no, ast.ClassDef)]
    assert [c.name for c in classes] == ["OrchestrationRepository"]
    return {
        no.name: no
        for no in classes[0].body
        if isinstance(no, ast.FunctionDef) and not no.name.startswith("_")
    }


def test_e71b18_a_classificacao_dos_metodos_do_repositorio_e_exaustiva() -> None:
    """Nenhum método público escapa por omissão."""
    metodos = set(_metodos_publicos_do_repositorio())
    classificados = CONTROL_BOUND | PRINCIPAL_BOUND | REFUSAL_ONLY | SCOPE_EXEMPT
    nao_classificados = metodos - classificados
    fantasmas = classificados - metodos
    assert not nao_classificados, f"método público sem classificação: {sorted(nao_classificados)}"
    assert not fantasmas, f"classificação aponta para método inexistente: {sorted(fantasmas)}"
    todas = (CONTROL_BOUND, PRINCIPAL_BOUND, REFUSAL_ONLY, SCOPE_EXEMPT)
    assert sum(len(c) for c in todas) == len(classificados)


def test_e71b19_todo_metodo_control_bound_exige_e_impoe_o_vinculo() -> None:
    """Assinatura **e** corpo. Receber o parâmetro e ignorá-lo é pior que não recebê-lo."""
    metodos = _metodos_publicos_do_repositorio()
    for nome in sorted(CONTROL_BOUND):
        no = metodos[nome]
        argumentos = {arg.arg for arg in no.args.kwonlyargs} | {arg.arg for arg in no.args.args}
        assert "control_principal_ref" in argumentos, f"{nome}: assinatura sem o vínculo"
        corpo = ast.unparse(no)
        impoe = (
            "control_principal_ref ==" in corpo
            or "control_principal_ref=control_principal_ref" in corpo
        )
        assert impoe, f"{nome}: recebe o vínculo e não o usa"


def test_e71b20_todo_caminho_de_escrita_recusa_em_vez_de_devolver_none() -> None:
    """Escritor que devolve `None` convida a tratar recusa como ausência."""
    escritores = (
        "set_schedule_state",
        "next_attempt_number",
        "create_attempt",
        "create_seal_receipt",
    )
    metodos = _metodos_publicos_do_repositorio()
    for nome in escritores:
        corpo = ast.unparse(metodos[nome])
        assert "OrchestrationScopeViolationError" in corpo, nome


def test_e71b21_os_metodos_de_recusa_levantam_incondicionalmente() -> None:
    metodos = _metodos_publicos_do_repositorio()
    imutaveis = {
        "SealReceiptImmutableError",
        "HandoffRecordImmutableError",
        "GovernanceRecordImmutableError",
    }
    for nome in sorted(REFUSAL_ONLY):
        corpo = ast.unparse(metodos[nome])
        assert any(erro in corpo for erro in imutaveis), nome
        assert "if " not in corpo, f"{nome}: recusa condicional não é recusa"


#: Caminhos que tocam `HandoffAttempt` ou `SealReceipt`. Além do dono,
#: exigem o Schedule **declarado pelo chamador**.
#:
#: ```text
#: OWNER_BINDING != SCHEDULE_BINDING
#: DERIVED_SCHEDULE != CALLER_EXPECTED_SCHEDULE
#: ```
ATTEMPT_SCOPED = frozenset(
    {
        "next_attempt_number",
        "create_attempt",
        "create_seal_receipt",
        "get_attempt",
        "get_seal_receipt_by_attempt",
        "list_attempts",
        # --- E7.3 ---
        "expire_stale_delegations",
        "revoke_active_delegations",
        "create_delegation",
        "get_active_delegation",
        "get_delegation",
        "consume_delegation",
        "list_delegations",
        "create_control_event",
        "list_control_events",
        "count_open_pause_events",
        "list_open_attempts_of_schedule",
        "all_steps_returned",
        "get_last_attribution_before",
        "create_execution_observation",
        "list_execution_observations",
        "get_result_for_audit",
        "get_control_event",
        "get_audit_opinion",
        "create_audit_opinion",
        "list_audit_opinions",
    }
)

#: Helper privado — verificado explicitamente porque é o ponto único de
#: travessia e porque foi exatamente onde o defeito R2 se escondeu.
HELPER_DE_ESCOPO = "_attempt_under_scope"


def _metodo_do_repositorio(nome: str) -> ast.FunctionDef:
    arvore = _arvore(REPOSITORIO)
    encontrados = [
        no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef) and no.name == nome
    ]
    assert len(encontrados) == 1, f"{nome}: esperado exatamente um método, achei {len(encontrados)}"
    return encontrados[0]


def test_e71b22_tentativa_e_recibo_alcancam_o_schedule_por_join_ou_helper() -> None:
    """Nenhum caminho de tentativa/recibo lê a tabela sem atravessar o Schedule."""
    metodos = _metodos_publicos_do_repositorio()
    for nome in ("get_attempt", "get_seal_receipt_by_attempt", "list_attempts"):
        corpo = ast.unparse(metodos[nome])
        assert ".join(Schedule" in corpo, f"{nome}: não atravessa Schedule"
    assert HELPER_DE_ESCOPO in ast.unparse(metodos["create_seal_receipt"])


def test_e71b24_todo_caminho_de_tentativa_exige_dono_e_schedule() -> None:
    """Assinatura: os dois parâmetros, nunca só um.

    Exigir o dono e derivar o Schedule responde "é seu", que não é a
    pergunta. A pergunta é "é seu **e** é deste trabalho".
    """
    metodos = _metodos_publicos_do_repositorio()
    assert ATTEMPT_SCOPED <= CONTROL_BOUND, sorted(ATTEMPT_SCOPED - CONTROL_BOUND)
    for nome in sorted(ATTEMPT_SCOPED):
        no = metodos[nome]
        argumentos = {arg.arg for arg in no.args.kwonlyargs} | {arg.arg for arg in no.args.args}
        assert "control_principal_ref" in argumentos, f"{nome}: sem o dono"
        assert "schedule_id" in argumentos, f"{nome}: sem o Schedule declarado"


def test_e71b25_o_corpo_usa_os_dois_vinculos_e_nao_apenas_os_recebe() -> None:
    """Receber `schedule_id` e não filtrar por ele é o defeito R2 de volta."""
    metodos = _metodos_publicos_do_repositorio()
    for nome in sorted(ATTEMPT_SCOPED):
        corpo = ast.unparse(metodos[nome])
        usa_dono = (
            "control_principal_ref ==" in corpo
            or "control_principal_ref=control_principal_ref" in corpo
        )
        usa_schedule = "schedule_id ==" in corpo or "schedule_id=schedule_id" in corpo
        assert usa_dono, f"{nome}: recebe o dono e não o usa"
        assert usa_schedule, f"{nome}: recebe o Schedule e não o usa"


def test_e71b26_o_helper_de_escopo_impoe_as_quatro_condicoes() -> None:
    """`_attempt_under_scope` verificado explicitamente, predicado a predicado."""
    no = _metodo_do_repositorio(HELPER_DE_ESCOPO)
    argumentos = {arg.arg for arg in no.args.kwonlyargs} | {arg.arg for arg in no.args.args}
    assert {"control_principal_ref", "schedule_id", "attempt_id"} <= argumentos
    corpo = ast.unparse(no)
    for predicado in (
        "HandoffAttempt.id == attempt_id",
        "HandoffAttempt.schedule_id == schedule_id",
        "Schedule.id == schedule_id",
        "Schedule.control_principal_ref == control_principal_ref",
    ):
        assert predicado in corpo, f"{HELPER_DE_ESCOPO}: falta `{predicado}`"


def test_e71b27_as_consultas_de_tentativa_impoem_as_quatro_condicoes() -> None:
    """Os dois getters repetem o mesmo conjunto — nenhum deriva o Schedule."""
    metodos = _metodos_publicos_do_repositorio()
    for nome in ("get_attempt", "get_seal_receipt_by_attempt"):
        corpo = ast.unparse(metodos[nome])
        assert "HandoffAttempt.schedule_id == schedule_id" in corpo, nome
        assert "Schedule.id == schedule_id" in corpo, nome
        assert "Schedule.control_principal_ref == control_principal_ref" in corpo, nome


def test_e71b23_a_integridade_schedule_step_vive_no_schema() -> None:
    """FK composta declarada no modelo, e não só na migration."""
    modelo = (ORQUESTRACAO / "models" / "attempt.py").read_text(encoding="utf-8")
    assert "ForeignKeyConstraint" in modelo
    assert "fk_handoff_attempts_step_within_schedule" in modelo
    alvo = (ORQUESTRACAO / "models" / "step.py").read_text(encoding="utf-8")
    assert "uq_schedule_steps_id_schedule" in alvo
