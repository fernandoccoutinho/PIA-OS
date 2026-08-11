# Sistema Central de Configuração — PIA-OS Backend

> Movido de `docs/CONFIGURATION.md` para `docs/backend/configuration.md` no Módulo 2.12.


Fonte única de verdade para toda configuração da plataforma. Nenhum outro
módulo deve ler `os.environ` diretamente — sempre importar `settings`.

```python
from app.config.settings import settings

settings.app_name
settings.database.pool_size   # acesso agrupado
```

## Estrutura

| Arquivo                     | Responsabilidade                                            |
|------------------------------|----------------------------------------------------------------|
| `app/config/environment.py`  | Enum `Environment` e detecção do ambiente ativo                |
| `app/config/constants.py`    | Constantes fixas (não variam por ambiente, não são segredos)   |
| `app/config/validators.py`   | Validadores reutilizáveis (porta, log level, URL de banco, etc.)|
| `app/config/settings.py`     | Classe `Settings` (fonte única) + classes de grupo             |
| `app/config/loader.py`       | Seleciona o `.env` correto por ambiente e constrói `Settings`   |
| `app/config/config.py`       | `validate_environment` — falha o startup se algo crítico faltar|

## Ambientes suportados

`development`, `testing`, `staging`, `production` — definidos por
`ENVIRONMENT` (ou `APP_ENV`) como variável real de processo (shell/Docker),
**não** dentro do próprio `.env` — é o que permite escolher qual arquivo
`.env` carregar antes de lê-lo.

## Resolução do arquivo `.env`

Ordem de precedência (primeiro que existir é usado):

1. `.env.<ambiente>.local` — overrides locais, nunca commitados
2. `.env.<ambiente>` — ex.: `.env.testing`, `.env.staging`, `.env.production`
3. `.env` — padrão (compatível com a Entrega 2.1)

Variáveis já definidas no ambiente do processo (shell, Docker `environment:`)
sempre têm precedência sobre qualquer arquivo `.env`.

## Grupos de configuração

Cada domínio tem sua própria classe de leitura, todas derivadas dos mesmos
campos de `Settings` (não duplicam estado):

`settings.app` · `settings.database` · `settings.log` · `settings.api` ·
`settings.security` · `settings.docker`

## Banco de dados: duas formas de configurar

- **`DATABASE_URL`** (recomendado, compatível com a Entrega 2.1): URL completa.
- **`DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`**: partes
  discretas, montadas automaticamente em `DATABASE_URL` — usadas **somente**
  se `DATABASE_URL` não for definida explicitamente. Se ambas existirem,
  `DATABASE_URL` prevalece.

## Validação e falha rápida (fail-fast)

Em `staging` e `production`, a aplicação recusa iniciar se:

- `SECRET_KEY` estiver no valor padrão de desenvolvimento;
- `DEBUG` estiver ativado;
- `DATABASE_URL` contiver credenciais padrão de desenvolvimento.

Em `testing`, exige que `DATABASE_URL` pareça apontar para um banco de teste.
Todos os problemas são coletados e reportados juntos, em uma única mensagem.

## Cache / carregamento único

`get_settings()` é decorada com `functools.lru_cache` — `Settings` é
construída uma única vez por processo. `settings` (nível de módulo) é essa
instância cacheada; importar `settings` em qualquer lugar reaproveita o
mesmo objeto.

## Convenção de nomenclatura das variáveis de ambiente

- **Formato:** sempre `UPPER_SNAKE_CASE`.
- **Prefixo por domínio**, correspondendo à classe de grupo em `settings.py`:
  - `APP_*` — identidade/estado da aplicação (`APP_NAME`, `APP_VERSION`)
  - `DATABASE_*` — configuração de conexão/pool (`DATABASE_URL`, `DATABASE_POOL_SIZE`)
  - `DB_*` — partes discretas alternativas do banco (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`)
  - `LOG_*` — logging (`LOG_LEVEL`, `LOG_FORMAT`)
  - `JWT_*` / `SECRET_KEY` — segurança
  - `API_*` — metadados da API (`API_PREFIX`, `API_VERSION`)
  - `DOCKER_*` — sinalização de execução em container (`DOCKER_ENV`)
- **Sem abreviações ambíguas**: usar `DATABASE`, não `DB`, exceto no grupo de
  partes discretas (`DB_HOST` etc.), onde `DB_` já é o prefixo estabelecido.
- **Booleanos** usam `true`/`false` em minúsculas no `.env` (ex.: `DEBUG=true`).
- **Nunca reutilizar um prefixo de domínio para um campo de outro grupo** —
  evita ambiguidade ao ler o `.env.example` sem abrir o código.
- Variáveis novas seguem o prefixo do grupo ao qual pertencem — ver
  "Como adicionar uma nova configuração" abaixo.

## Como adicionar uma nova configuração

1. Adicione o campo em `Settings` (`app/config/settings.py`), com tipo e
   valor padrão explícitos.
2. Se precisar de validação além do tipo, adicione um validador em
   `validators.py` e um `field_validator` chamando-o.
3. Adicione a variável em `.env.example`, na seção correspondente.
4. Se pertencer a um grupo existente, exponha-a também na classe de grupo
   correspondente (`AppGroup`, `DatabaseGroup`, etc.).
5. Se for uma configuração crítica em produção, adicione a checagem em
   `config.py::validate_environment`.
