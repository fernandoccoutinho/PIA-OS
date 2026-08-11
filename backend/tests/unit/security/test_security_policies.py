from app.config.settings import Settings
from app.security.policies import SecurityPolicy, get_security_policy


def test_production_policy_is_strict():
    settings = Settings(environment="production", debug=False, secret_key="real-key")
    policy = get_security_policy(settings)
    assert isinstance(policy, SecurityPolicy)
    assert policy.enforce_https is True
    assert policy.expose_error_details is False
    assert policy.strict_cors is True


def test_development_policy_is_permissive():
    settings = Settings(environment="development", debug=True)
    policy = get_security_policy(settings)
    assert policy.enforce_https is False
    assert policy.expose_error_details is True
    assert policy.strict_cors is False


def test_expose_error_details_follows_debug_flag_not_environment_alone():
    # Mesmo em produção, se debug estiver ligado (caso raro, investigação
    # pontual), expose_error_details reflete isso — fonte única de verdade.
    settings = Settings(environment="production", debug=True, secret_key="real-key")
    policy = get_security_policy(settings)
    assert policy.expose_error_details is True


def test_csp_enabled_requires_both_production_like_and_policy_set():
    settings_without_csp = Settings(environment="production", secret_key="real-key")
    assert get_security_policy(settings_without_csp).csp_enabled is False

    settings_with_csp = Settings(
        environment="production", secret_key="real-key", csp_policy="default-src 'self'"
    )
    assert get_security_policy(settings_with_csp).csp_enabled is True


def test_staging_behaves_like_production_for_strictness():
    settings = Settings(environment="staging", debug=False)
    policy = get_security_policy(settings)
    assert policy.enforce_https is True
    assert policy.strict_cors is True
