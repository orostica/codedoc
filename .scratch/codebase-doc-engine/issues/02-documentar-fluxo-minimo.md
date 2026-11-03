# 02: Documentar um fluxo mínimo entre frontend e backend

**What to build:** Documentar um fluxo simples de fetch até um Controller C#, desde a análise local até um pacote para agente externo e a validação básica do documento produzido.

**Blocked by:** 01: Inventariar um ecossistema local com segurança.

**Status:** resolved

- [x] Uma fixture versionada cobre fetch direto e Controller com destino seguro configurado; destino, método e rota sustentam a ligação confirmada.
- [x] A análise extrai símbolos e dependências básicos com identificadores qualificados por repositório e localizações rastreáveis.
- [x] O desenvolvedor revisa um módulo antes da exportação; o pacote contém contexto estruturado, fontes, tarefa e cobertura.
- [x] Schemas executáveis versionados e sintaxe de citações vinculam evidências a repositório, commit, arquivo relativo, símbolo, linhas e hash.
- [x] Um documento de exemplo com citações válidas passa na validação básica; referência desconhecida falha.
- [x] A CLI usa Python 3.12+, Typer, Pydantic, Tree-sitter e Pytest, permanece local e não invoca agentes; o fluxo demonstrável tem instruções de uso.

## Answer

Implementado em 2026-11-03. A CLI agora oferece analyze, plan, context e validate.
A análise usa Tree-sitter para extrair símbolos, imports/using, fetch direto e
Controllers com rotas literais. Confirmações exigem destino configurado, método,
rota e um único endpoint compatível; ambiguidades permanecem como candidatas.

O plano identifica a análise, nasce com revisão pendente e precisa ser revisado
explicitamente antes da exportação. Alterações de configuração, análise, commits
ou árvores de trabalho bloqueiam exportações incompatíveis. Planos e pacotes
existentes são preservados.

Pacotes incluem contexto, fontes, tarefa e cobertura. Evidências identificam
repositório, commit, arquivo relativo, símbolo, linhas inclusivas e hash SHA-256
do blob Git. Schemas JSON 1.0 acompanham os modelos executáveis Pydantic.
O Markdown usa citações no formato [@ev-IDENTIFICADOR]; a validação básica
confere seções, commits, citações, símbolos, intervalos, hashes e trechos.
Uma citação válida não comprova a correção semântica da afirmação.

Validação final: 53 testes aprovados e 1 ignorado por restrição do Windows à
criação de symlinks. A integração exercita a revisão simulada do plano, exporta
o pacote, valida o documento de exemplo e rejeita referências desconhecidas,
citações incompletas, evidências adulteradas e entradas desatualizadas.

A execução manual do preparador e dos comandos instalados analyze/plan gerou
uma relação confirmada sem lacunas na fixture mínima. O plano da demonstração
permanece com revisão pendente. As APIs de exemplo e agentes não foram executados.

O README descreve instalação, demonstração, revisão e limites do recorte.
Comparação de tipos, obrigatoriedade, proxies, Axios, Minimal APIs e orçamento
de contexto continuam nos tickets posteriores; padrões reconhecidos mas não
resolvidos são apresentados como lacunas.
