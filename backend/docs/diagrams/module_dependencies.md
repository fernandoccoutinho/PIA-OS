# Diagrama — Dependência entre Módulos

Versão textual (Mermaid) de `module_dependencies.drawio`. Seta A --> B
significa "A depende de B" (importa/usa).

```mermaid
graph LR
    M21["2.1 Arquitetura"]
    M22["2.2 Configuracao Central"]
    M23["2.3 Persistencia"]
    M24["2.4 ORM"]
    M25["2.5 APIs REST"]
    M26["2.6 Logging"]
    M27["2.7 Erros"]
    M28["2.8 Seguranca"]
    M29["2.9 Doc OpenAPI"]
    M210["2.10 Testes"]
    M211["2.11 Deploy"]
    M212["2.12 Doc Tecnica"]

    M22 --> M21
    M23 --> M22
    M24 --> M23
    M25 --> M24
    M25 --> M22
    M26 --> M22
    M27 --> M25
    M27 --> M26
    M28 --> M27
    M28 --> M26
    M28 --> M22
    M29 --> M25
    M29 --> M27
    M210 -.testa.-> M22
    M210 -.testa.-> M23
    M210 -.testa.-> M24
    M210 -.testa.-> M25
    M210 -.testa.-> M26
    M210 -.testa.-> M27
    M210 -.testa.-> M28
    M211 -.empacota.-> M25
    M211 -.empacota.-> M22
    M212 -.documenta.-> M21
    M212 -.documenta.-> M211
```

## Regra de dependência observada

Nenhum módulo posterior altera a API pública dos anteriores sem uma
razão explícita e documentada (ver `docs/adr/`). A direção das setas é
estritamente "de trás para frente" — 2.2 nunca depende de 2.5, por
exemplo. Isso é o que permitiu implementar 2.1–2.11 sequencialmente sem
retrabalho estrutural.

## Como manter atualizado

Ao criar um módulo novo, adicione o nó e as arestas reais de import —
não presuma a partir do número do módulo. Se um módulo futuro
introduzir uma dependência "para trás" (algo cedo passando a depender de
algo tardio), isso é um sinal de possível problema arquitetural — vale
um ADR explicando a exceção.
