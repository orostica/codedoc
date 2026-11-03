# 12: Validar integridade, atualização e revisão separadamente

**What to build:** Informar separadamente se a documentação possui evidências íntegras, se suas fontes continuam atuais e se o conteúdo recebeu revisão humana.

**Blocked by:** 11: Exportar contexto com orçamento e cobertura explícitos.

**Status:** ready-for-agent

- [ ] A validação verifica schemas, seções obrigatórias, citações, links locais, arquivos, símbolos, intervalos, commits e hashes.
- [ ] Testes com artefatos adulterados detectam cada falha e identificam a evidência afetada.
- [ ] Alteração de commit ou árvore suja em qualquer repositório participante após a análise bloqueia a exportação e exige nova análise.
- [ ] Documentos existentes têm evidências conferidas na revisão original e atualização comparada às fontes atuais, sem confundir essas dimensões.
- [ ] Fontes ou revisões inacessíveis geram resultado indeterminado explícito, sem aprovação automática.
- [ ] A revisão humana registra pendência ou resultado informado; validação estrutural não aprova a semântica.
- [ ] Um caso demonstra simultaneamente evidências íntegras, fontes desatualizadas e revisão humana pendente.

