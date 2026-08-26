#!/usr/bin/env bash
#
# run_e742_closure.sh — fechamento mecanico da E7.4-2.
#
#     ONE_HARNESS_AT_A_TIME · NEVER_TWO_ON_ONE_DATABASE
#
# Sequencial do inicio ao fim, sem background e sem paralelismo. Duas
# rodadas anteriores desta cadeia foram invalidadas por concorrencia
# entre arneses destrutivos sobre o mesmo banco de mutacao:
#
#     CONCURRENT_HARNESSES_ON_ONE_MUTATION_DB = VERDICT_VOID
#
# Uso:
#     bash run_e742_closure.sh /caminho/do/clone
#
set -Eeuo pipefail

CLONE="${1:?informe o diretorio do clone}"
BACKEND="$CLONE/backend"
LOGS="$CLONE/e742-closure-logs"
mkdir -p "$LOGS"

: "${DATABASE_URL:?exporte DATABASE_URL}"
: "${MUTANT_DATABASE_URL:?exporte MUTANT_DATABASE_URL}"
# Os arneses divergem no nome da variavel: e741_hp_mutants.py le
# MUTANT_DATABASE_URL, mutation_evidence_e7*.py leem
# PIA_MUTATION_DATABASE_URL. Exportar as duas evita baseline vermelha
# por banco errado.
export PIA_MUTATION_DATABASE_URL="${PIA_MUTATION_DATABASE_URL:-$MUTANT_DATABASE_URL}"
export ENVIRONMENT="${ENVIRONMENT:-testing}"

if [ "$DATABASE_URL" = "$MUTANT_DATABASE_URL" ]; then
  echo "M0: banco de teste e de mutacao sao o mesmo. Abortando." >&2
  exit 2
fi

cd "$BACKEND"

executar() {
  local nome="$1"; shift
  echo "[RUN] $nome"
  if ! "$@" > "$LOGS/$nome.log" 2>&1; then
    echo "[FAIL] $nome — ver $LOGS/$nome.log" >&2
    tail -25 "$LOGS/$nome.log" >&2
    exit 1
  fi
  echo "[OK]  $nome"
}

# --- 1. instalacao LIMPA ----------------------------------------------------
#
# Recriada, nunca reaproveitada. Trocar versao de dependencia num venv
# existente deixa residuo que falseia gate — foi o que fez o snapshot
# OpenAPI parecer divergente quando o codigo estava correto:
#
#     ENV_CONTAMINATION != CODE_DIVERGENCE
#
# `cp -a` tambem nao serve: quebra os caminhos absolutos do venv.
rm -rf .venv
executar 00_venv python3 -m venv .venv
export PATH="$BACKEND/.venv/bin:$PATH"
executar 01_install pip install -q -r requirements/dev.txt -r requirements/mcp.txt

# `python` nu: os arneses e71/e72/e73 invocam o interpretador pelo nome,
# sem sys.executable. Sem o venv no PATH a baseline sai vermelha em tudo.
command -v python | grep -q "$BACKEND/.venv" || {
  echo "M0: 'python' nao resolve para o venv do backend." >&2; exit 2; }

# --- 2. migrations ----------------------------------------------------------
executar 02_alembic python -m alembic upgrade head
FOLHA="$(python -m alembic current 2>/dev/null | awk '{print $1}' | tail -1)"
[ "$FOLHA" = "f4c8b0d51e73" ] || {
  echo "M0: folha de migration inesperada: $FOLHA" >&2; exit 2; }

# --- 3. integracao MCP real -------------------------------------------------
executar 03_mcp_integracao python -m pytest tests/integration/mcp/ -q --no-cov -p no:cacheprovider
executar 04_mcp_unitarias  python -m pytest tests/unit/mcp/ -q --no-cov -p no:cacheprovider

# --- 4. concorrencia --------------------------------------------------------
executar 05_concorrencia python -m pytest -q --no-cov -p no:cacheprovider -k concorrencia

# --- 5. mutantes: UM POR VEZ ------------------------------------------------
[ -f scripts/e742_mcp_mutants.py ] || {
  echo "M0: arnês obrigatório E7.4-2 ausente." >&2; exit 2; }

# Prova NEGATIVA do guard de identidade de banco, ANTES de qualquer arnes
# destrutivo. Se o guard nao recusa o banco de teste disfarcado de banco de
# mutacao, nenhum veredito adiante vale: o passo seguinte derruba schema.
#
#     A GUARD NEVER SEEN REFUSING IS AN UNPROVEN GUARD
#
executar 06_prova_guard_banco python scripts/e742_mutation_guard_proof.py
grep -qx "GUARD_PROOF=PASS" "$LOGS/06_prova_guard_banco.log" || {
  echo "M0: prova do guard de banco sem veredito PASS." >&2; exit 1; }

executar 06_mutantes_e742 python scripts/e742_mcp_mutants.py
executar 07_mutantes_b3free python scripts/e741_b3free_mutants.py
executar 08_mutantes_novos  python scripts/e741_hp_mutants.py
executar 09_mutantes_e71    python scripts/mutation_evidence_e71.py
executar 10_mutantes_e72    python scripts/mutation_evidence_e72.py
executar 11_mutantes_e73    python scripts/mutation_evidence_e73.py
executar 12_mutantes_kernel python scripts/e741_mutants.py
executar 13_mutantes_e62    python scripts/mutation_evidence_e62.py

# Baseline vermelha invalida a contagem inteira, mesmo com KILLED alto.
if grep -qE "baseline *: *exit [1-9]" "$LOGS"/*mutantes*.log; then
  echo "M0: baseline vermelha em algum arnes — veredito invalido." >&2
  exit 1
fi
if grep -qE "SURVIVED" "$LOGS"/*mutantes*.log; then
  echo "M0: mutante sobrevivente." >&2
  grep -B4 "SURVIVED" "$LOGS"/*mutantes*.log >&2
  exit 1
fi

# --- 6. qualidade -----------------------------------------------------------
executar 14_ruff  python -m ruff check .
executar 15_black python -m black --check .
python -m mypy app > "$LOGS/16_mypy.log" 2>&1 || true
NOVOS="$(grep -c ' error: ' "$LOGS/16_mypy.log" || true)"
[ "$NOVOS" -le 7 ] || {
  echo "M0: mypy regrediu — $NOVOS erros, divida historica e 7." >&2; exit 1; }

# --- 7. suite integral, UMA vez --------------------------------------------
executar 17_suite_integral python -m pytest

# --- 8. identidade final ----------------------------------------------------
cd "$CLONE"
{
  echo "HEAD      = $(git rev-parse HEAD)"
  echo "TREE      = $(git rev-parse HEAD^{tree})"
  echo "PARENT    = $(git rev-parse HEAD^)"
  echo "COUNT     = $(git rev-list --count HEAD)"
  echo "ROOT      = $(git rev-list --max-parents=0 HEAD)"
  echo "SDK_TREE  = $(git rev-parse HEAD:sdk)"
  echo "MIGRATION = $FOLHA"
  echo "STATUS    = [$(git status --porcelain --untracked-files=no)]"
} > "$LOGS/18_identidade.log"
cat "$LOGS/18_identidade.log"

[ -z "$(git status --porcelain --untracked-files=no)" ] || {
  echo "M0: worktree suja no fim do fechamento." >&2; exit 1; }

echo
echo "E742_CLOSURE=PASS"
