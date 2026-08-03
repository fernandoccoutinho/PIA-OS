# PIA-OS

**Plataforma de nova geração para gerenciamento de conhecimento e integração com Inteligências Artificiais.**

O PIA-OS funciona como um "sistema operacional" de conhecimento: a **memória persiste no próprio sistema**, e os diferentes modelos de IA acessam essa memória — que vive no computador do usuário — de forma **governada e controlada**. Há uma camada de governança que define **até onde cada IA pode acessar** determinada memória.

---

## Visão

- **Memória persistente e local** — o contexto de trabalho é preservado entre sessões e permanece no sistema, não no provedor de IA.
- **Integração multi-modelo** — diferentes provedores/modelos de IA acessam a mesma base de conhecimento por meio de uma interface comum.
- **Arquitetura modular e extensível** — componentes desacoplados (backend, drivers de IA, SDK, interface web).
- **Governança de acesso** — controle granular sobre quais memórias cada IA pode ler/usar.

---

## Arquitetura (visão geral)

```
+---------------------+        +----------------------+
|     Interface Web   |        |      SDK Python      |
|  (dashboard, console)|       |  (integração externa)|
+----------+----------+        +----------+-----------+
           |                              |
           +--------------+---------------+
                          |
                   +------v------+
                   |   Backend   |  APIs, sessões, logs, governança
                   +------+------+
                          |
              +-----------+-----------+
              |                       |
      +-------v-------+       +-------v--------+
      |  Persistência |       | Drivers de IA  |
      | (memória local|       | (provedores,   |
      |  + metadados) |       |  streaming)    |
      +---------------+       +----------------+
```

---

## Roadmap

O desenvolvimento está organizado em 8 entregas incrementais.

| # | Entrega | Prazo | Objetivo de aceite |
|---|---------|-------|--------------------|
| 1 | **Infraestrutura de Engenharia** | 1 semana | Projeto pronto para desenvolvimento |
| 2 | **Backend Base** | 1 semana | Backend operacional |
| 3 | **Persistência de Dados** | 1 semana | Dados persistidos corretamente |
| 4 | **Sessões e Integração com IA** | 2 semanas | Primeira integração funcional com um provedor de IA |
| 5 | **SDK Python** | 1 semana | SDK funcionando em projeto externo |
| 6 | **Interface Web** | 1 semana | Interface integrada ao backend |
| 7 | **Qualidade e Estabilização** | 1 semana | Todos os testes aprovados |
| 8 | **Release 1.0** | 1 semana | Versão 1.0 instalada em ambiente limpo |

<details>
<summary>Detalhamento das entregas</summary>

### Entrega 1 – Infraestrutura de Engenharia
Repositório Git organizado · estrutura inicial do projeto · Docker · ambiente reproduzível · GitHub Actions · framework de testes · padronização de código · documentação inicial.

### Entrega 2 – Backend Base
Estrutura do backend · APIs básicas · configuração da aplicação · sistema de logs · tratamento de erros · banco de dados configurado · migrações.

### Entrega 3 – Persistência de Dados
Modelos de dados · CRUD completo · versionamento · pesquisa básica · metadados.

### Entrega 4 – Sessões e Integração com IA
Gerenciamento de sessões · interface de integração com IA · drivers iniciais · streaming de respostas · registro de eventos.

### Entrega 5 – SDK Python
SDK Python · APIs documentadas · exemplos de uso · pacote instalável.

### Entrega 6 – Interface Web
Login · dashboard · área de trabalho · pesquisa · gerenciamento de objetos · console de IA.

### Entrega 7 – Qualidade e Estabilização
Testes automatizados · correções · cobertura mínima definida · documentação técnica · guia de instalação.

### Entrega 8 – Release 1.0
Build oficial · Docker funcional · documentação consolidada · Release Candidate · versão 1.0 em ambiente limpo.

</details>

---

## Status

🚧 **Em desenvolvimento** — Entrega 1 (Infraestrutura de Engenharia).

---

## Como começar

> A estrutura de desenvolvimento (backend, Docker, testes) está sendo montada na Entrega 1. As instruções de instalação e execução serão adicionadas conforme os componentes forem entregues.

---

## Licença

A definir.
