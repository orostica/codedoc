# 04: Comparar tipos de entrada e formatos de resposta

**What to build:** Apresentar incompatibilidades demonstráveis entre dados enviados ou consumidos pelo frontend e entradas ou respostas do backend.

**Blocked by:** 02: Documentar um fluxo mínimo entre frontend e backend.

**Status:** resolved

- [x] Fixtures com resultados definidos previamente cobrem tipos compatíveis, incompatíveis e não resolvidos em entrada e resposta.
- [x] A comparação considera parâmetros e corpos, dados enviados e acessos à resposta, conforme evidências disponíveis na implementação.
- [x] Tipos declarados e descrições de contrato são evidências adicionais, sem substituir silenciosamente a implementação.
- [x] Tipos, serializações ou respostas não resolvidos são reportados como lacunas, sem afirmar incompatibilidade.
- [x] Cada achado explica os valores comparados e referencia evidências dos dois lados; pacote e documento de exemplo preservam esses vínculos.

## Answer

Implementado em 2026-11-12. A matriz em `tests/fixtures/types/cases.json`
fixa 24 resultados esperados antes da execução dos testes, cobrindo corpo,
parâmetros e resposta compatíveis, incompatíveis e indeterminados. Testes
adicionais cobrem declarações divergentes, caminhos aninhados, serialização,
relações candidatas e casos dinâmicos.

Os contratos extraídos registram fatos de tipo da implementação. Corpos JSON
literais ou JSON.stringify resolvidos são comparados com getters diretos de
JsonElement em uma ação com retorno único. Parâmetros FromQuery string são
comparados quando o retorno executa int.Parse; valores repetidos ficam como
lacunas. Respostas Content com JSON e media type literais são comparadas com
acessos diretos de string ou número após await fetch e await response.json.
Tipos declarados e ProducesResponseType permanecem nos trechos como contexto;
não sobrescrevem os valores construídos ou retornados.

`analysis.type_comparisons` registra caminho, tipos fornecido e esperado,
resultado, explicação e evidências do frontend e backend. Incompatibilidades
geram achados `incompatible_type`; tipos ou operações indeterminados geram
lacunas. Compatibilidade vale apenas para a operação registrada, sem aprovar
o fluxo completo. JSON null é aceito por GetString; GetInt32 distingue frações
e inteiros fora do intervalo. Valores de campos não são registrados nos fatos.

DTOs, respostas Ok com objetos, negociação de conteúdo, aliases, condicionais,
mutações, casts e acessos opcionais fora do recorte permanecem não resolvidos.
Sinais reconhecidos de serialização customizada em outros arquivos elegíveis
do repositório bloqueiam conclusões. Não há resolução semântica completa,
execução dos projetos analisados ou inferência sobre filtros externos.

Comparações e achados são filtrados por módulo e acompanham a exportação.
O documento de exemplo preserva ID do achado e citações dos dois lados no
mesmo parágrafo. A validação reextrai os contratos nas fontes Git originais
e refaz a comparação; testes rejeitam citações ausentes, contratos adulterados
e explicações inconsistentes. Análise/contexto passam a schema 1.2; artefatos
anteriores precisam ser regenerados. Schemas JSON e README foram atualizados.

Verificação: 149 testes aprovados e 1 ignorado pela restrição do Windows à
criação de symlinks. `git diff --check` sem erros. Dois caches de build já
alterados durante a sessão foram preservados fora do escopo do ticket.

