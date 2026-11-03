# Rastreador: Markdown local

- Uma funcionalidade por diretório: `.scratch/<feature-slug>/`.
- Spec: `spec.md` no diretório da funcionalidade.
- Tickets: `issues/<NN>-<slug>.md`, um arquivo por ticket,
  numerados a partir de 01, com bloqueadores primeiro.
- Estado: linha `Status:` próxima ao início, usando os nomes
  definidos em `triage-labels.md`.
- Dependências: linha `Blocked by:` com números e títulos,
  ou `None (can start immediately)`.
- Comentários: acrescentar ao final, sob `## Comments`.

Publicar significa criar o arquivo local correspondente.
Consultar um ticket significa ler seu arquivo completo,
incluindo comentários.

Trabalhar nos tickets cujos bloqueadores estejam concluídos.
Registrar a conclusão com `Status: resolved`.

Para wayfinder:
- Mapa: `.scratch/<feature-slug>/map.md`.
- Cada ticket declara `Type: research|prototype|grilling|task`.
- Selecionar o primeiro por número que esteja desbloqueado
  e ainda não tenha sido assumido.
- Ao assumir, salvar `Status: claimed`.
- Ao concluir, acrescentar `## Answer`, salvar `Status: resolved`
  e adicionar uma síntese com link em Decisions-so-far do mapa.
