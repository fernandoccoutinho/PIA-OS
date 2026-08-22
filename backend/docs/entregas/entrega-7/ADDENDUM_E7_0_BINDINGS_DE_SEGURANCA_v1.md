# Addendum E7.0 — bindings de segurança da API e idempotência

Este addendum complementa o `MAI-001 R1` e o plano E7.0 R1 sem alterar sua decomposição.

```text
SCHEDULE_CONTROL_BINDING = TECHNICAL_PRINCIPAL_REF
API_READ_WRITE_WITHOUT_CONTROL_BINDING = FORBIDDEN
COMMAND_IDEMPOTENCY_SCOPE = (technical_principal_ref, operation, command_key)
GLOBAL_COMMAND_KEY_ALONE = INSUFFICIENT
```

## 1. Controle do Schedule

Todo Schedule criado pela API recebe `control_principal_ref`, referência opaca ao principal técnico autenticado. Repositórios e serviços devem exigir esse vínculo em toda leitura, exportação, importação, consulta de tentativa e mudança de estado.

Ter o escopo E7 autoriza usar a operação; não concede acesso aos Schedules de outro principal.

```text
SAME_SCOPE != SAME_WORK_OWNERSHIP
CROSS_PRINCIPAL_SCHEDULE_READ = FORBIDDEN
```

## 2. Idempotência

A mesma `command_key` pode ser escolhida por clientes diferentes. Portanto, a unicidade e a recuperação de recibo usam a composição:

```text
(technical_principal_ref, operation, command_key)
```

Mesma tripla devolve o mesmo recibo sem novo efeito. Outro principal ou outra operação não colide. Retry legítimo usa nova `command_key` e cria nova tentativa, mesmo com o mesmo `ENVELOPE_CONTENT_SHA256`.

## 3. Provas obrigatórias

- principal B não lê, exporta, importa nem altera Schedule do principal A;
- mesma chave no mesmo principal/operação é idempotente;
- mesma chave em principais diferentes não colide;
- mesma chave em operações diferentes não colide;
- mutante que remove `control_principal_ref` da consulta deve morrer;
- mutante que torna `command_key` global deve morrer.
