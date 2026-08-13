"""
Fixtures de usuário — estrutura apenas.

Nenhum modelo de usuário existe ainda no PIA-OS — autenticação é um
módulo futuro (fora do escopo de todos os módulos 2.1-2.10). Este
arquivo existe para que, quando um modelo `Usuario` real for criado, os
testes já tenham um lugar padrão para fixtures de usuário, em vez de
cada teste futuro inventar sua própria forma de simular um.
"""

import pytest


@pytest.fixture
def fake_user_payload() -> dict[str, str]:
    """Payload mínimo plausível para "algum usuário" — uso apenas em
    testes que precisem de um valor de referência antes do módulo de
    autenticação existir (ex.: testar que um campo `user_id` de log
    aceita uma string). Não corresponde a nenhum schema real ainda."""
    return {
        "id": "00000000-0000-0000-0000-000000000000",
        "email": "test@example.com",
    }
