"""
Testes de sanidade da configuração do Nginx (Módulo 2.11).

Sem um binário nginx neste ambiente para `nginx -t` de verdade — valida
estrutura e conteúdo esperado por leitura direta do arquivo.
"""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
NGINX_DIR = BACKEND_ROOT / "deploy" / "nginx"


def test_nginx_conf_exists_and_includes_conf_d():
    content = (NGINX_DIR / "nginx.conf").read_text()
    assert "include /etc/nginx/conf.d/*.conf;" in content


def test_nginx_conf_enables_gzip_compression():
    content = (NGINX_DIR / "nginx.conf").read_text()
    assert "gzip on;" in content


def test_default_conf_proxies_to_the_api_service():
    content = (NGINX_DIR / "default.conf").read_text()
    assert "server api:8000;" in content
    assert "proxy_pass http://pia_os_api;" in content


def test_default_conf_has_security_headers():
    content = (NGINX_DIR / "default.conf").read_text()
    assert "X-Content-Type-Options" in content
    assert "X-Frame-Options" in content


def test_default_conf_https_block_is_commented_out_no_real_certificates():
    content = (NGINX_DIR / "default.conf").read_text()
    # O bloco HTTPS existe como referência, mas comentado — sem
    # certificado real configurado (fora do escopo do Módulo 2.11).
    assert "# server {" in content
    assert "ssl_certificate" in content
    lines_with_ssl_cert = [line for line in content.splitlines() if "ssl_certificate " in line]
    assert all(line.strip().startswith("#") for line in lines_with_ssl_cert)


def test_default_conf_forwards_client_ip_headers():
    content = (NGINX_DIR / "default.conf").read_text()
    assert "X-Real-IP" in content
    assert "X-Forwarded-For" in content
