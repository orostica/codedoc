# 07: Rastrear transformações nas rotas API do Next.js

**What to build:** Explicar o fluxo navegador → rota API Next.js → backend levando em conta transformações intermediárias do pedido.

**Blocked by:** 06: Analisar chamadas Axios e wrappers locais.

**Status:** ready-for-agent

- [ ] Fixtures cobrem encaminhamento sem transformação, alterações de parâmetros e desembrulho de formData antes do envio ao backend.
- [ ] Cada etapa tem destino, método, rota e evidências; a comparação usa os dados que chegam ao backend após as transformações.
- [ ] Diferenças introduzidas ou corrigidas pelo proxy mudam corretamente o resultado da comparação.
- [ ] Transformações ou encaminhamentos não resolvidos produzem lacunas e impedem conclusões dependentes deles.
- [ ] O pacote e documento de exemplo mostram a cadeia completa e suas transformações, com cobertura e referências validáveis.

