"""
Camada de orquestração multi-IA (`E7`).

```text
E7_OWNS  trabalho, etapa, tentativa, repasse, resultado, modo de execução
E7_USES  erros PIA (E1), principal técnico (E6.2)
E7_NEVER ciência (E5), DTO público (E6.1), identidade e aprovação humanas
         (E8), efeito externo (E9), aprovação destrutiva (E4.9)
```

A E7 orquestra e registra: não avalia, não aprova, não age no mundo
(`MAI-001 R1` §1).

Esta fatia é a **E7.1** e entrega exatamente quatro coisas: um `Schedule`
governado com etapas e papéis, o `ENVELOPE_CONTENT_SHA256` determinístico,
o selamento por tentativa com recibo próprio e a idempotência de comando.

```text
E7_1_HAS  contrato, estado, content hash, recibo de selamento, idempotência
E7_1_LACKS transporte, retorno, validação de saída, atribuição, API,
           delegação, gate, auditoria, provedor, rede, fila, worker
```

O que falta acima não é omissão: pertence à E7.2 e à E7.3, e antecipá-lo
aqui afirmaria capacidade que esta entrega não tem.
"""
