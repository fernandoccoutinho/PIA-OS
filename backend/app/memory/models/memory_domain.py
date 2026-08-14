"""
`MemoryDomain` — segmentação lógica do patrimônio cognitivo (E4.1).

Um domínio é um **recorte**, não um continente. Ele não guarda
objetos: ele os classifica. A distinção não é sutil e determina todo o
resto do desenho —

```
DOMAIN MEMBERSHIP != COGNITIVE EXISTENCE
DOMAIN BOUNDARY   != COGNITIVE BOUNDARY
```

Um `CognitiveObject` sem nenhum domínio existe plenamente; um objeto
em dois domínios continua sendo **um** objeto com **um** COID.

O que um `MemoryDomain` explicitamente **não** é:

- pasta de filesystem — não tem `path`, não tem hierarquia, não tem
  aninhamento (`MEMORY_DOMAIN != FILESYSTEM_FOLDER`);
- container de storage — não guarda bytes nem referencia local algum;
- `CognitiveObject` — não tem COID, CLID, linhagem, proveniência,
  história causal, e não participa de transformações;
- contexto (E4.2) — domínio é estável; contexto é perspectiva
  operacional;
- policy, ACL ou autoridade (E4.3) — quem pode ver ou classificar não
  é decidido aqui;
- sessão, índice de busca ou evidência de persistência (E4.4).
"""

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel


class MemoryDomain(BaseModel):
    """Recorte lógico nomeado sobre o patrimônio cognitivo.

    Herda `BaseModel` (`id` UUID + `created_at`/`updated_at`), a mesma
    base declarativa de todo o projeto — não existe hierarquia
    paralela.

    **Contrato mínimo, deliberadamente.** Só `id` e `name`. Campos
    considerados e recusados por ausência de necessidade demonstrada
    (E4.1 §5): `description`, `metadata`/`arbitrary_json` (proibido
    desde E3.6.2), `owner` e `acl` (autoridade é E4.3), `policy_ref`
    (E4.3), `parent_domain_id`/`path` (hierarquia é `DEFERRED`),
    qualquer `*_score` (proibido por `COUT-P8`/`COUT-P9`), `provider`
    e `model` (`PROVIDER_NEUTRALITY = REQUIRED`).
    """

    __tablename__ = "memory_domains"

    name: Mapped[str] = mapped_column(nullable=False)
    """Nome legível por humano — **atributo, não identidade**.

    A identidade é `id` (`domain_id`). Consequências congeladas:

        rename != new domain
        same name != same domain

    Não há `UNIQUE(name)`: nenhum contrato do freeze da E4 estabelece
    unicidade de nome, e inventá-la seria decidir pelo usuário como
    ele organiza o próprio patrimônio (E4.1 §7/§28). Dois domínios
    homônimos são dois domínios.
    """

    @property
    def domain_id(self) -> object:
        """Alias de leitura para `id`, na linguagem ubíqua do módulo.

        Mesmo padrão de `CognitiveObject.coid` em E3.1: usar o termo do
        domínio sem duplicar a coluna. E, como lá, o alias existe para
        deixar explícito que `domain_id != COID` — são identidades de
        espécies diferentes, e um domínio nunca é um objeto cognitivo.
        """
        return self.id
