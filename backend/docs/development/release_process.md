# Processo de Release — PIA-OS Backend

Nenhum conteúdo anterior cobria isso — primeira vez que o processo de
release é documentado explicitamente.

## Versionamento

`settings.app_version` (`app/config/settings.py`) é a fonte única da
versão do backend — aparece em `GET /`, `GET /api/v1/version`, no schema
OpenAPI (`info.version` e `info.x-metadata.backend_version`, Módulo
2.9) e nas imagens Docker. Versionamento semântico (`MAJOR.MINOR.PATCH`)
— hoje em `0.1.0` (fase de infraestrutura, pré-primeira versão estável
com funcionalidade de domínio).

`PIA_OS_VERSION` (`app/config/constants.py`) é a versão da *plataforma*
PIA-OS como um todo — distinta da versão do componente backend
(`app_version`), já que o PIA-OS terá outros componentes (frontend,
desktop) versionados independentemente no futuro.

## Changelog

`CHANGELOG_API.md` (raiz do repositório) documenta mudanças que afetam o
contrato da API — gerado a partir de `app/docs/changelog.py::API_CHANGELOG`
(fonte única de código, Módulo 2.9):

```bash
make generate-changelog
```

Mudanças que **não** afetam a API pública (refatoração interna,
documentação, testes) não entram no changelog da API — só no histórico
do controle de versão.

## Passos de um release

1. Todos os módulos/mudanças planejados para a versão passam por
   `make check` limpo.
2. Atualizar `app_version` em `.env`/configuração de deploy (via
   `APP_VERSION`, Módulo 2.2) se for uma mudança de versão do backend.
3. Adicionar a entrada correspondente em
   `app/docs/changelog.py::API_CHANGELOG` se a mudança afeta a API.
4. `make generate-changelog` — regenera `CHANGELOG_API.md`.
5. Tag do commit (`git tag vX.Y.Z`).
6. Deploy — ver [`deploy/README_DEPLOY.md`](../../deploy/README_DEPLOY.md#atualização-rollout-de-uma-nova-versão).

## Rollback

Não há registry de imagens versionadas nesta etapa (ver ADR-008,
"Alternativas consideradas") — rollback é `git checkout <tag/commit
anterior>` + rebuild, documentado em
[`deploy/README_DEPLOY.md`](../../deploy/README_DEPLOY.md#rollback).

## Compatibilidade retroativa

Toda mudança em um módulo posterior precisou preservar o comportamento
observável dos módulos anteriores (critério de aceitação repetido em
todas as especificações, 2.2 a 2.12) — quando uma mudança de fato alterou
algo observável (ex.: hierarquia de exceções no Módulo 2.7 — ver
ADR-004), isso foi documentado explicitamente como uma exceção
deliberada, não uma quebra silenciosa.

## Melhorias futuras (não implementadas)

Registry de imagens Docker versionadas, pipeline de release automatizado
(tag → build → push → deploy), notas de release geradas automaticamente
a partir de Pull Requests mergeados.
