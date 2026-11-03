# 03: Detectar campo obrigatório ausente na requisição

**What to build:** Mostrar ao desenvolvedor quando uma chamada omite um campo demonstravelmente exigido pelo backend, com explicação e evidências no pacote documentável.

**Blocked by:** 02: Documentar um fluxo mínimo entre frontend e backend.

**Status:** ready-for-agent

- [ ] Resultados esperados de casos positivos, negativos e ambíguos são registrados antes da implementação do detector.
- [ ] A comparação considera o corpo efetivamente construído na chamada e a exigência demonstrada na implementação do backend.
- [ ] O caso de campo opcional no frontend e exigido no backend produz achado quando a omissão for demonstrável.
- [ ] Campo enviado corretamente não produz achado; obrigatoriedade ou envio indeterminados produzem lacuna.
- [ ] O achado chega ao pacote e ao documento de exemplo validado com evidências dos dois lados; todos os casos definidos passam.

