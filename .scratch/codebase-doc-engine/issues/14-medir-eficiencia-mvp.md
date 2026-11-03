# 14: Medir eficiência e qualidade do MVP

**What to build:** Medir o ganho de consumo de tokens e a qualidade da documentação ao comparar acesso direto aos repositórios com o pacote de contexto.

**Blocked by:** 13: Documentar e revisar o piloto MSSUPERA.

**Status:** ready-for-agent

- [ ] Antes das sessões, fixar protocolo, casos esperados, avaliação de qualidade, método de contagem de tokens e limitações da medição.
- [ ] Executar baseline e abordagem híbrida em sessões separadas com mesmo agente, módulo, objetivo e commits.
- [ ] Registrar tokens, tempo, cobertura, precisão de referências, omissões relevantes e correções humanas; incluir tempo de análise e preparação da CLI.
- [ ] Verificar todos os casos de divergência previamente definidos e a ausência de afirmações de divergência nos casos ambíguos.
- [ ] Publicar resultados observados e materiais necessários para reprodução, sem presumir ganho nem ajustar o protocolo retroativamente.
- [ ] Declarar se tokens_hibrido <= 0,80 × tokens_baseline sem aumento de omissões relevantes ou correções humanas; se falhar, registrar a meta não atingida e os limites encontrados.

