"""
Carregador central de configuração.

Responsabilidades (e apenas estas):
1. Identificar o ambiente de execução (variável ENVIRONMENT/APP_ENV do
   processo, antes de qualquer .env ser lido).
2. Localizar o arquivo .env apropriado para esse ambiente.
3. Construir e validar a instância de `Settings` a partir dele.

Este módulo é o único ponto do sistema que decide *qual* arquivo .env
carregar. `Settings` (Pydantic) continua sendo o único ponto que decide
*como* interpretar e validar cada variável.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.environment import Environment, parse_environment

if TYPE_CHECKING:
    from app.config.settings import Settings

# Variáveis aceitas para declarar o ambiente antes do .env ser carregado.
# ENVIRONMENT é o nome canônico; APP_ENV é aceito por compatibilidade com
# convenções comuns em outras plataformas.
_ENVIRONMENT_VARS = ("ENVIRONMENT", "APP_ENV")

# Diretório onde os arquivos .env residem — raiz do backend (mesmo nível
# de main.py e docker-compose.yml).
_CONFIG_ROOT = Path(__file__).resolve().parents[2]


def detect_environment() -> Environment:
    """Determina o ambiente de execução a partir do processo, antes do .env.

    Necessário porque o arquivo .env correto (ex.: `.env.testing`) só pode
    ser escolhido se já soubermos qual ambiente está ativo — não podemos
    descobrir o ambiente lendo o próprio arquivo que estamos escolhendo.
    """
    for var in _ENVIRONMENT_VARS:
        raw = os.environ.get(var)
        if raw:
            return parse_environment(raw)
    return Environment.DEVELOPMENT


def resolve_env_file(environment: Environment, root: Path = _CONFIG_ROOT) -> Path | None:
    """Retorna o caminho do .env a usar para o ambiente informado.

    Ordem de precedência (o primeiro arquivo existente vence):
    1. `.env.<ambiente>.local` — overrides locais, não versionados.
    2. `.env.<ambiente>` — configuração específica do ambiente.
    3. `.env` — arquivo padrão (usado pela Entrega 2.1).

    Retorna None se nenhum arquivo existir (válido: variáveis de ambiente
    reais do processo/container ainda são lidas normalmente pelo Pydantic).
    """
    candidates = [
        root / f".env.{environment.value}.local",
        root / f".env.{environment.value}",
        root / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def build_settings() -> "Settings":
    """Constrói a instância de `Settings` usando o .env resolvido para o ambiente ativo.

    Chamada exclusivamente por `app.config.settings.get_settings` (que a
    envolve em `lru_cache` para garantir carregamento único por processo).
    """
    from app.config.settings import Settings

    # Nota: ENVIRONMENT precisa vir de uma variável de processo real (shell,
    # Docker) para ser usada na *escolha* do arquivo .env — não pode vir de
    # dentro do próprio arquivo que ainda não sabemos qual é. Se só existir
    # dentro do .env, `Settings` a lerá normalmente após o arquivo ser
    # carregado (caindo no arquivo `.env` padrão, como na Entrega 2.1).
    environment = detect_environment()
    env_file = resolve_env_file(environment)

    if env_file is not None:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    return Settings()
