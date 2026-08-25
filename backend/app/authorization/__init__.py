"""
`app.authorization` — E8 IAB, produtor autorizado do descritor semântico.

```text
E4 = autoridade classificatória   (app.memory, fronteira pura)
E8 = produtor do descritor        (este pacote)
E7 = consumidor e executor        (app.orchestration)
```

A E4 avalia um descritor **tipado** e não lê texto livre. Alguém precisa
produzir esse descritor a partir do objetivo real, e até aqui ninguém o
fazia: era exatamente o vão registrado como
`BRIDGE_READY != OPERATIONAL_PROTECTION`.

Este pacote fecha o vão e nada além disso:

    PRODUCER != CLASSIFIER
    PRODUCER != BOUNDARY

O broker não classifica. Ele **exige** classificação de uma porta
semântica autorizada, verifica que o que voltou é tipado nos valores
canônicos, vincula o resultado ao objetivo por hash e à versão do
classificador, e recusa tecnicamente quando não pode fazer isso.

O que este pacote **não** faz, por contrato:

- não cria catálogo local de tópicos;
- não usa regex, lista lexical ou palavra-chave;
- não decide por forma estrutural da requisição;
- não devolve `NOT_APPLICABLE` na ausência de descritor.

A última linha é a mais consequente:

    MISSING DESCRIPTOR != NOT_APPLICABLE
    ABSENCE -> TECHNICAL UNAVAILABILITY

Ausência de classificação produz indisponibilidade técnica tipada, com
zero efeito. Tratá-la como "nada a ver aqui" converteria toda falha do
classificador em permissão silenciosa — que é a forma que este subsistema
existe para tornar impossível.
"""

from app.authorization.broker import (
    IntentAuthorizationBroker,
    IntentAuthorizationUnavailableError,
)
from app.authorization.descriptor import AuthorizedCapabilityDescriptor
from app.authorization.ports import (
    SemanticCapabilityClassifierPort,
    SemanticClassification,
)

__all__ = [
    "AuthorizedCapabilityDescriptor",
    "IntentAuthorizationBroker",
    "IntentAuthorizationUnavailableError",
    "SemanticCapabilityClassifierPort",
    "SemanticClassification",
]
