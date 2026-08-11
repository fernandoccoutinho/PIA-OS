#!/usr/bin/env python3
"""
Roda o verificador de consistência da documentação da API e imprime o
relatório. Sai com código 1 se algum problema for encontrado — útil no
CI, além dos testes automatizados (`test_api_documentation.py`).

Rodar a partir da raiz de `backend/` (mesma convenção dos demais
scripts do projeto):

    PYTHONPATH=. python scripts/check_api_docs.py
"""

import sys

from app.api.documentation import check_endpoint_documentation

if __name__ == "__main__":
    from main import app

    report = check_endpoint_documentation(app)
    print(report.render())
    sys.exit(0 if report.is_clean else 1)
