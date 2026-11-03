# 10: Revisar e reutilizar o plano de módulos

**What to build:** Permitir ao desenvolvedor revisar os módulos sugeridos, ajustar seus limites e reutilizar o plano aprovado na exportação de contexto.

**Blocked by:** 02: Documentar um fluxo mínimo entre frontend e backend.

**Status:** ready-for-agent

- [ ] Módulos são sugeridos a partir de rotas e dependências e representam funcionalidades de negócio que podem atravessar repositórios.
- [ ] O desenvolvedor pode ajustar nomes, agrupamentos e escopo e persistir a revisão sem editar código analisado.
- [ ] O plano identifica a análise e o conjunto de commits que o sustentam.
- [ ] Exportação exige plano revisado e compatível com a análise; plano não revisado ou incompatível recebe diagnóstico acionável.
- [ ] Um teste de fluxo altera agrupamentos, persiste a revisão, recarrega o plano e exporta somente o módulo selecionado.

