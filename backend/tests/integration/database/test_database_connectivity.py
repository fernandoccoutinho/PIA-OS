"""
Teste de integração de conectividade real com o banco.

Nenhum PostgreSQL real está disponível neste ambiente de sandbox/CI —
por isso este teste verifica o estado observável (`check_database_health`)
em vez de assumir sucesso ou falha, e documenta explicitamente por que
não força uma conexão real. Em um ambiente com `DATABASE_URL` apontando
para um Postgres de fato acessível (ex.: `docker compose up db` local),
este mesmo teste validaria a conexão de ponta a ponta.
"""

from app.database.health import check_database_health


def test_database_health_check_reports_a_consistent_status():
    """Não assume que o banco está disponível (não está, neste ambiente)
    — verifica que o resultado é internamente consistente: indisponível
    implica tempo de resposta ausente; disponível implica tempo presente."""
    result = check_database_health()

    if result.available:
        assert result.status == "healthy"
        assert result.response_time_ms is not None
        assert result.response_time_ms >= 0
    else:
        assert result.status == "unavailable"
        assert result.response_time_ms is None
