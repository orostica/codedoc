# 08: Tratar destinos ambíguos e obrigatoriedade condicional

**What to build:** Distinguir relações confirmadas, relações candidatas e chamadas não resolvidas, afirmando divergências condicionais somente quando sustentadas pelo código.

**Blocked by:** 03: Detectar campo obrigatório ausente na requisição.

**Status:** ready-for-agent

- [ ] Casos previamente definidos incluem serviços com mesmo método e rota, destino ausente, destino confirmado e condições verdadeiras, falsas e indeterminadas.
- [ ] Confirmação exige destino mapeado, método e rota compatíveis; coincidência de método e rota entre serviços não basta.
- [ ] Relações candidatas registram evidências e motivo da incerteza e não sustentam afirmação de divergência.
- [ ] Ausência de campo condicional gera achado somente quando a chamada satisfaz a condição demonstrada e omite o campo.
- [ ] Condições ou destinos não resolvidos aparecem na cobertura; ausência de achados não é apresentada como cobertura completa.
- [ ] O pacote e o documento de exemplo preservam as distinções e passam nas verificações dos casos definidos.

