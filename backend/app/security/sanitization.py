"""
Utilitários de sanitização.

Funções genéricas de tratamento de string — sem regra de negócio
específica. Endpoints funcionais futuros as usam conforme necessário;
nenhuma é aplicada automaticamente a toda entrada (isso pertence à
validação de schema Pydantic de cada endpoint — Módulo 2.5).
"""

import unicodedata

# Caracteres de controle sempre removidos: todo o intervalo C0 (0x00-0x1F)
# e DEL (0x7F), exceto tab/newline/carriage-return, que são whitespace
# legítimo em texto livre.
_ALLOWED_CONTROL_CHARS = frozenset({"\t", "\n", "\r"})


def remove_control_characters(value: str) -> str:
    """Remove caracteres de controle (incluindo NUL) que não têm função
    em texto — comum em payloads malformados ou tentativas de injeção
    de bytes de controle em logs/terminais."""
    return "".join(
        ch for ch in value if ch in _ALLOWED_CONTROL_CHARS or unicodedata.category(ch) != "Cc"
    )


def normalize_unicode(value: str) -> str:
    """Normaliza para a forma NFKC — reduz variantes visuais/de largura
    do mesmo caractere lógico a uma representação canônica única, o que
    ajuda a evitar bypasses de filtros baseados em comparação textual."""
    return unicodedata.normalize("NFKC", value)


def sanitize_string(value: str) -> str:
    """Combina remoção de caracteres de controle + normalização Unicode
    + limpeza de espaços nas bordas — o tratamento padrão recomendado
    para texto livre vindo de fora da aplicação."""
    return normalize_unicode(remove_control_characters(value)).strip()


def mask_sensitive_value(value: str, *, visible_chars: int = 4) -> str:
    """Mascara um valor sensível para exibição/log — mantém apenas os
    últimos `visible_chars` caracteres visíveis (útil, por exemplo, para
    confirmar visualmente qual chave está em uso sem expô-la por
    completo). Não usar para armazenamento — apenas para exibição."""
    if len(value) <= visible_chars:
        return "*" * len(value)
    return "*" * (len(value) - visible_chars) + value[-visible_chars:]
