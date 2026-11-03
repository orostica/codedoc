# 11: Exportar contexto com orçamento e cobertura explícitos

**What to build:** Preparar pacotes por módulo que respeitem um orçamento aproximado e mantenham as evidências necessárias para interpretar e comparar cada fluxo.

**Blocked by:** 07: Rastrear transformações nas rotas API do Next.js; 08: Tratar destinos ambíguos e obrigatoriedade condicional; 10: Revisar e reutilizar o plano de módulos.

**Status:** ready-for-agent

- [ ] O seletor prioriza funcionalidade, dependências diretas relevantes, validadores, contratos e pontos de entrada.
- [ ] O pacote inclui contexto estruturado, fontes, tarefa e relatório de cobertura com relações confirmadas, candidatas, chamadas não resolvidas e motivos.
- [ ] Módulos grandes são divididos em tarefas preservando comparações completas entre chamada, intermediários e endpoint, sem truncamento arbitrário de métodos.
- [ ] Se uma comparação indivisível exceder o orçamento, a exportação solicita aumento do limite ou redução do escopo.
- [ ] A estimativa informa o método e suas limitações; exclusões são explícitas e o plano revisado é respeitado.
- [ ] Pacotes usam instruções universais e template de módulo, separando fatos, inferências, regras, restrições de interface e pontos para revisão.
- [ ] Testes verificam orçamento suficiente, divisão, insuficiência indivisível e ausência de exclusões silenciosas.

