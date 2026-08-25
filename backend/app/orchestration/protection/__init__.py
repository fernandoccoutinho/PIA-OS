"""
Ponte de enforcement da Governança — proteção humana (`E7.4-1 B1a`).

```text
NORMATIVE_PROHIBITION_OWNER = E4 GOVERNANCE
SEMANTIC_DESCRIPTOR_OWNER   = E8 IAB
EFFECT_ENFORCEMENT_OWNER    = E7.4-1
```

Sem reexportação deliberada: `ports/governance.py` importa
`protection/binding.py`, e um `__init__` que importasse `bridge` fecharia o
ciclo na primeira linha. O precedente é o próprio `ports/__init__.py`, que
também só documenta.
"""
