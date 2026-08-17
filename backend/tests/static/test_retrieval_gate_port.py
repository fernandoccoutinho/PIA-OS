"""
Prova **estática** da porta de composição da E4.6.3.

Arquivo próprio, e não um apêndice de `test_port_assignment.py`: aquele
seletor pertence à contagem congelada da E4.7, e uma prova da E4.6.3
morando lá faria um módulo congelado mudar de número sem ter mudado de
comportamento.

    FROZEN MODULE COUNT != NEIGHBOURING FILE

Quase não há asserção de runtime aqui: o valor do arquivo é ser
verificado pelo mypy.

    RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY
"""

from app.cognitive.models.cognitive_object import CognitiveObject
from app.memory.ports.retrieval import CognitiveObjectView, RetrievalCandidateGatePort


class GateConcreto:
    """Implementação real e mínima, sem herdar do Protocol."""

    def allows(self, candidate: CognitiveObjectView) -> bool:
        return candidate.deleted_at is None


def prova_de_atribuicao_do_gate() -> RetrievalCandidateGatePort:
    """`GateConcreto` satisfaz a porta por **atribuição verificada**.

    Um gate que devolvesse `int`, aceitasse outro parâmetro ou omitisse
    o retorno faria o mypy recusar aqui — que é exatamente o ponto.
    """
    gate: RetrievalCandidateGatePort = GateConcreto()
    return gate


def prova_de_que_o_objeto_real_da_e3_atravessa_o_gate(
    objeto: CognitiveObject,
) -> bool:
    """O `CognitiveObject` REAL atravessa o gate, tipado ponta a ponta.

    A atribuição direta `vista: CognitiveObjectView = objeto` **não**
    compila, e o motivo é o achado já registrado pela E4.7.1: os modelos
    da E3 declaram `Mapped[...]`, e o mypy compara a **anotação
    declarada**, não o tipo que o descritor devolve em runtime.

    ```text
    Mapped[AccessibilityState] != str   (para o mypy)
    ```

    A saída sem `Any`, `cast` ou `type: ignore` é a mesma de lá:
    narrowing por `isinstance`, que **tipa** o objeto para o mypy porque
    `CognitiveObjectView` é `runtime_checkable`. O `else` não é defensivo
    — é o que torna a função total sem mentir sobre o caso.
    """
    if isinstance(objeto, CognitiveObjectView):
        return prova_de_atribuicao_do_gate().allows(objeto)
    return False


def test_static_retrieval_candidate_gate_port_is_type_checked() -> None:
    """Marcador de runtime: a prova real é o mypy sobre este arquivo."""
    assert prova_de_atribuicao_do_gate.__doc__
    assert prova_de_que_o_objeto_real_da_e3_atravessa_o_gate.__doc__
