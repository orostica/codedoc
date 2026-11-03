# 03: Detectar campo obrigatório ausente na requisição

**What to build:** Mostrar ao desenvolvedor quando uma chamada omite um campo demonstravelmente exigido pelo backend, com explicação e evidências no pacote documentável.

**Blocked by:** 02: Documentar um fluxo mínimo entre frontend e backend.

**Status:** resolved

- [x] Resultados esperados de casos positivos, negativos e ambíguos são registrados antes da implementação do detector.
- [x] A comparação considera o corpo efetivamente construído na chamada e a exigência demonstrada na implementação do backend.
- [x] O caso de campo opcional no frontend e exigido no backend produz achado quando a omissão for demonstrável.
- [x] Campo enviado corretamente não produz achado; obrigatoriedade ou envio indeterminados produzem lacuna.
- [x] O achado chega ao pacote e ao documento de exemplo validado com evidências dos dois lados; todos os casos definidos passam.

## Answer

Implementado em 2026-11-03. Uma matriz de 19 casos positivos, negativos e
ambíguos foi registrada antes da implementação do detector. O cenário principal
declara name opcional no frontend, constrói um JSON sem essa chave e encontra
uma guarda inicial no Controller que retorna BadRequest quando ela falta.

A análise compara strings JSON literais contendo objetos ou JSON.stringify de
objetos inline determináveis, com Content-Type JSON explícito. A exigência inicial
suportada usa um único parâmetro FromBody JsonElement e guardas sequenciais de
TryGetProperty com rejeição explícita. Cada campo omitido gera um achado com
explicação, relação confirmada e evidências do frontend e do backend.

Campos enviados não geram achados de omissão. Null conta como chave presente;
tipos e valores permanecem fora desta comparação. Valores dinâmicos, spreads,
replacers, DTOs, validações condicionais e serializações não resolvidas geram
lacunas. Relações candidatas não sustentam achados. Sinais reconhecidos de
customização de serialização em outros arquivos elegíveis do repositório também
bloqueiam conclusões que dependam dela.

Comparações e achados acompanham o módulo exportado. O validador exige o ID de
cada achado no documento e as citações dos dois lados no mesmo parágrafo,
reextrai contratos das fontes originais e refaz as verificações determinísticas.
Análise e contexto usam schema 1.1; artefatos 1.0 precisam ser regenerados.

Verificação final: 97 testes aprovados e 1 ignorado por restrição do Windows à
criação de symlinks. A integração cobre exportação, documento de exemplo válido,
citações incompletas, contratos e explicações adulterados e filtragem dos achados
por módulo. A execução manual do preparador e de analyze/plan confirmou uma
relação, um achado para name e nenhuma lacuna no cenário mínimo. O plano manual
permanece com revisão pendente; APIs e agentes externos não foram executados.

Durante a regressão foi corrigida a preparação das fixtures: uma cópia recursiva
incluía caches binários de build em obj e falhava ao ler UTF-8. Um teste isolado
reproduziu a falha antes da correção. Agora testes e preparador usam uma lista
explícita de fontes, e os repositórios de exemplo ignoram arquivos de build.
Arquivos gerados existentes foram preservados. O README documenta demonstração,
escopo, limites e migração dos artefatos.
