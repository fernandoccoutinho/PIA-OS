"""
Camada de memória e governança do PIA-OS — Entrega 4.

Pacote **irmão** de `app.cognitive`, nunca subpacote dele. A separação
é estrutural e não decorativa:

    E3 OWNS COGNITIVE PATRIMONY.
    E4 OPERATES OVER COGNITIVE PATRIMONY.

Consequência prática, verificada por teste (`MD6`) e imposta pelo gate
`G17` da E3.12: **nenhum módulo deste pacote importa `app.cognitive`**.
Referências ao patrimônio viajam como `COID` (`uuid.UUID`) e como
`ForeignKey("cognitive_objects.id")` — resolvida por nome no
`MetaData` compartilhado, sem import Python.
"""
