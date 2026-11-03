# Codebase Documentation Engine

CLI local para inventariar e documentar um fluxo mínimo entre repositórios
Next.js e C#/.NET. Comandos disponíveis: `scan`, `analyze`, `plan`, `context`
e `validate`. A CLI não invoca agentes nem executa os projetos analisados.

## Passo a passo de uso

### Executar diretamente na pasta dos projetos

Após instalar a ferramenta uma vez conforme a etapa 1, abra o PowerShell na
pasta que reúne os repositórios. O script usa o ambiente virtual da instalação
do CodeDoc, sem precisar ativá-lo ou configurar variáveis:

```powershell
cd C:\MeuEcossistema
& C:\SETDIG\codedoc\codedoc.cmd init
```

Substitua `C:\SETDIG\codedoc` pelo local da sua instalação. O comando `init`
cria `ecosystem.yaml` com os repositórios Git encontrados nas subpastas
imediatas, em ordem de nome, com IDs `repo-1`, `repo-2` etc. Pastas comuns e
links de diretórios não são incluídos. A busca não é recursiva.
Uma configuração existente é preservada.

Revise o YAML gerado, acrescente exclusões necessárias e preencha
`destinations` com as URLs-base e os IDs dos backends correspondentes, como
no exemplo da etapa 2. URLs não são inferidas automaticamente. Em seguida:

```powershell
& C:\SETDIG\codedoc\codedoc.cmd scan
& C:\SETDIG\codedoc\codedoc.cmd analyze
& C:\SETDIG\codedoc\codedoc.cmd plan
# Revise .codedoc\plan.json e marque reviewed como true.
& C:\SETDIG\codedoc\codedoc.cmd context --module ID_DO_MODULO
# Produza module.md com o pacote exportado e o agente escolhido.
& C:\SETDIG\codedoc\codedoc.cmd validate .\module.md --context .\.codedoc\contexts\ID_DO_MODULO
```

Todos os comandos procuram `ecosystem.yaml` no diretório atual quando
`--config` é omitido. Você ainda pode informar `--config` para usar outro
arquivo. Caminhos dentro do YAML continuam relativos ao próprio arquivo.
O script mantém o diretório atual da execução.

Se executar `init` na raiz de um repositório Git, ele configura apenas esse
repositório e coloca a saída em `../.codedoc-NOME-DA-PASTA/`, fora da árvore
analisada. Faça commit do YAML gerado ou ignore-o no Git antes de analisar;
salve também o Markdown fora do repositório para manter a árvore limpa.
Para analisar frontend e backend juntos, prefira executar na pasta pai de ambos.

O fluxo completo é: instalar → configurar → inventariar → analisar → revisar
o plano → exportar o contexto → produzir o Markdown → validar e revisar.

Execute os comandos no PowerShell, na raiz deste projeto. Substitua
`C:\MeuEcossistema` pela pasta que contém os repositórios a documentar.
A instalação da ferramenta fica separada dos repositórios analisados.

### 1. Instalar a ferramenta

Requer Python 3.12+ e Git no PATH. Confira com `python --version` e
`git --version`. Crie o ambiente virtual e instale a CLI:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\codedoc.exe --help
```

Os comandos usam o ambiente virtual diretamente; não é necessário ativá-lo.
O extra `[test]` instala também as dependências de testes.

### 2. Preparar os repositórios e a configuração

Neste exemplo, coloque o backend em `C:\MeuEcossistema\backend` e o frontend
em `C:\MeuEcossistema\frontend`. Confira cada repositório com
`git -C C:\MeuEcossistema\backend status --short` e repita para o frontend.
A saída deve estar vazia e cada repositório deve ter pelo menos um commit.

Crie `C:\MeuEcossistema\ecosystem.yaml`, fora dos repositórios analisados:

```yaml
repositories:
  - id: api
    path: ./backend
  - id: portal
    path: ./frontend
destinations:
  - url: https://api.example.invalid/v1
    repository_id: api
exclude:
  - generated/
  - '**/*.generated.ts'
output: ./.codedoc/inventory.json
```

Os caminhos são relativos ao arquivo YAML, independentemente do diretório
de execução. IDs são únicos. Destinos aceitam HTTP/HTTPS sem credenciais,
query ou fragmento; use somente endereços públicos de configuração, sem
segredos em qualquer segmento. Cada destino associa uma URL-base a um backend.
O caminho dessa URL-base representa o prefixo de montagem: por exemplo,
`https://example.invalid/service` mapeia `/service/api/items` para a rota
`/api/items` do backend. O mapeamento mais específico prevalece; destinos
igualmente específicos e ambíguos não geram confirmação.

Cada caminho deve apontar para a raiz de um repositório Git com commit e
árvore limpa, incluindo arquivos não rastreados não ignorados. Salve alterações
em commit ou informe uma cópia limpa antes de executar; o scanner preserva
os arquivos existentes. A saída fica fora dos repositórios analisados.

O inventário JSON registra versão do schema, commits completos, caminhos
relativos de arquivos elegíveis, linguagens por extensão e projetos por
manifests. Next.js é identificado pela dependência `next` em package.json;
projetos .NET são identificados por manifests csproj XML válidos. Manifests
inválidos ou maiores que 2 MB geram avisos sem incluir seu conteúdo.

O scanner consulta Git sem fsmonitor e lê somente os manifests elegíveis.
Respeita .gitignore (inclusive para arquivos rastreados) e exclusões configuradas
no formato gitignore. Bloqueia nomes usuais de arquivos sensíveis, configurações
de credenciais, dumps, diretórios gerados e dependências vendorizadas; ignora
symlinks e junctions. Não executa scripts de projetos nem faz chamadas de rede.
Exclusões por nome não reconhecem todo segredo possível: configure exclusões
adicionais para convenções específicas do ecossistema. O inventário não contém
trechos de código ou valores dos manifests, apenas os metadados descritos.

### 3. Conferir o inventário

```powershell
.\.venv\Scripts\codedoc.exe scan --config C:\MeuEcossistema\ecosystem.yaml
```

Abra `C:\MeuEcossistema\.codedoc\inventory.json` e confira os repositórios,
commits, arquivos, projetos e avisos antes de continuar.

### 4. Analisar e gerar o plano

O comando `analyze` faz uma nova varredura; executar `scan` antes é útil para
conferência, mas não é obrigatório. Ao terminar, a CLI informa as quantidades
de relações confirmadas, achados e lacunas. Confira esses resultados em
`analysis.json`. Lacunas indicam partes que a ferramenta não conseguiu resolver.

```powershell
.\.venv\Scripts\codedoc.exe analyze --config C:\MeuEcossistema\ecosystem.yaml
.\.venv\Scripts\codedoc.exe plan --config C:\MeuEcossistema\ecosystem.yaml
```

Os artefatos ficam ao lado do inventário configurado: `analysis.json` contém
símbolos, dependências sintáticas, chamadas, endpoints, relações, evidências,
comparações, achados e cobertura. `plan.json` sugere um módulo por relação confirmada. Revise os
nomes, o escopo e as relações e altere `reviewed` de `false` para `true`.
### 5. Revisar o plano e escolher um módulo

Abra `C:\MeuEcossistema\.codedoc\plan.json` em um editor. Confira os módulos
e as relações sugeridas com base em `analysis.json`, preservando os IDs e
as referências aos artefatos. O campo `reviewed` pertence ao plano: marque-o
como `true` somente depois de revisar e salve o arquivo.

Copie o `id` de um módulo da lista `modules`. Se ela estiver vazia, confira
`destinations`, as lacunas da análise e os padrões suportados descritos adiante.

### 6. Exportar o contexto do módulo

Substitua `ID_DO_MODULO` pelo identificador copiado do plano:

```powershell
.\.venv\Scripts\codedoc.exe context --config C:\MeuEcossistema\ecosystem.yaml --module ID_DO_MODULO
```

A exportação exige plano revisado da análise atual, configuração compatível,
mesmos commits e árvores limpas em todos os repositórios. Planos e pacotes
existentes são preservados: mova-os antes de gerar novamente.

O diretório `contexts/<id-do-modulo>/` contém:

- `context.json`: módulo selecionado, símbolos, contratos, achados e evidências.
- `sources/`: trechos dos arquivos na revisão Git original, sem normalizar bytes.
- `task.md`: instruções independentes do agente e seções obrigatórias do documento.
- `coverage.json`: relações do módulo e lacunas da análise global, que podem
  incluir outros arquivos e chamadas fora do recorte.

### 7. Produzir o documento com um agente

Entregue o diretório completo do pacote ao agente de sua preferência, incluindo
`sources/`. A redação acontece nessa etapa, fora da CLI. Exemplo de solicitação:

```text
Leia task.md e os arquivos deste pacote. Produza module.md com as seções
exigidas, usando as evidências de context.json. Registre os achados e
as lacunas e use os IDs exatos nas citações.
```

Salve o documento em `C:\MeuEcossistema\module.md`, fora dos repositórios
analisados. Use citações `[@ev-<24 caracteres hexadecimais>]`, copiando os IDs
exatos de `context.json`. Cada evidência identifica repositório, commit,
arquivo relativo, símbolo, linhas inclusivas e SHA-256 do arquivo inteiro.
O pacote também registra SHA-256 dos trechos exportados. Os hashes são
verificados contra os blobs Git, independentemente de CRLF da cópia local.

### 8. Validar e revisar o documento

```powershell
.\.venv\Scripts\codedoc.exe validate C:\MeuEcossistema\module.md --config C:\MeuEcossistema\ecosystem.yaml --context C:\MeuEcossistema\.codedoc\contexts\ID_DO_MODULO
```

O validador exige seções Objetivo, Fluxo, Evidências, Lacunas e Revisão,
commits participantes e citações conhecidas. Confere os símbolos, intervalos,
hashes e trechos na revisão original. Parágrafos de Objetivo e Fluxo devem
conter citações; a interpretação semântica e a associação de cada afirmação
à evidência adequada continuam dependendo de revisão humana.
Cada achado do pacote deve aparecer no documento com seu ID e as citações
do frontend e do backend no mesmo parágrafo. O validador reextrai os contratos
das fontes originais e refaz a comparação determinística para detectar
adulterações no corpo, na exigência ou na explicação registrada.
As três dimensões de validação e a comparação com fontes atuais serão
ampliadas no ticket 12.

Quando a validação passa, a CLI informa: `Estrutura e evidências válidas.
Conteúdo aguarda revisão humana.` Se falhar, corrija os problemas listados e
execute o comando novamente. Revise se as afirmações são sustentadas pelas
evidências e se as lacunas estão claras.

### 9. Atualizar após mudanças nos repositórios

Faça os commits das mudanças e deixe as árvores limpas. Preserve os artefatos
anteriores em outra pasta, execute `analyze`, gere e revise um novo plano e
exporte o contexto atualizado. Produza e valide o documento com esse pacote.

### Problemas comuns

| Situação | Como prosseguir |
| --- | --- |
| Repositório sem commit ou com alterações | Confira `git status --short`, revise e faça commit ou use uma cópia limpa. |
| Nenhum módulo sugerido | Confira destinos, métodos, rotas e lacunas em `analysis.json`. |
| Plano não revisado ou incompatível | Use o plano da análise atual e marque `reviewed` como `true` após revisá-lo. |
| Plano ou pacote já existente | Mova o artefato anterior para preservá-lo antes de gerar outro. |
| Documento rejeitado | Confira seções, commits, IDs de achados e citações contra o pacote usado. |

Para consultar opções de um comando, execute, por exemplo:

```powershell
.\.venv\Scripts\codedoc.exe context --help
```

## Padrões cobertos nesta entrega

A análise usa Tree-sitter para TypeScript/TSX e C#. Aceita chamadas ao
`fetch` global com URL HTTP/HTTPS literal, método padrão GET ou `method`
literal em objeto inline. No backend, aceita classes com nome terminado em
Controller que derivam diretamente de ControllerBase ou Controller, com um
atributo Route literal e ações públicas com um atributo HttpGet/HttpPost/etc.
Rotas literais aceitam substituição de `[controller]`. Confirmação exige
destino configurado, método e rota compatíveis e um único endpoint candidato.

URLs relativas ou dinâmicas, fetch sombreado, opções dinâmicas, spreads,
rotas parametrizadas, Controllers com base não resolvida, Axios e Minimal
APIs detectados são registrados como lacunas. Proxies Next.js, comparação
de tipos e resolução semântica ficam para os próximos
tickets. As dependências import/using são sintáticas. Não há comprovação
do comportamento em execução nem de configuração global do servidor.

Arquivos com erro sintático, codificação diferente de UTF-8 ou mais de 2 MB
geram lacunas. O orçamento e a divisão dos pacotes serão implementados no
ticket 11; neste recorte pequeno, módulos de arquivo e classes podem levar
ao pacote trechos além da ação específica. A ausência de achados não indica
cobertura completa. A análise lê código elegível e exporta trechos: adicione
às exclusões quaisquer fontes sensíveis específicas do seu ecossistema.

Os schemas JSON versionados estão em `schemas/`, gerados dos modelos
Pydantic usados para validar artefatos em execução. Análise e contexto usam
a versão 1.1; plano e cobertura permanecem em 1.0. Artefatos de análise e
contexto 1.0 precisam ser regenerados: preserve os anteriores, execute analyze
e gere/revise um novo plano antes de exportar novamente.
O identificador da análise
é o hash de seu conteúdo completo; no pacote ele preserva a referência à
análise original, enquanto o conteúdo é filtrado para o módulo selecionado.

## Demonstração reproduzível

```powershell
.\.venv\Scripts\python.exe examples\minimal-flow\prepare.py .scratch\minimal-demo
.\.venv\Scripts\codedoc.exe analyze --config .scratch\minimal-demo\ecosystem.yaml
.\.venv\Scripts\codedoc.exe plan --config .scratch\minimal-demo\ecosystem.yaml
```

O preparador copia a fixture mantida no projeto para dois repositórios Git
novos e cria commits locais. Copia somente as fontes listadas em files.json,
preservando a demonstração mesmo que um editor gere caches de build na fixture.
Não instala nem executa os projetos de exemplo.
Revise `.scratch/minimal-demo/.codedoc/plan.json`, marque `reviewed: true` e
execute `context` com o ID escolhido. O arquivo `module.example.md` contém
um documento de exemplo: substitua os marcadores de evidências e commits
pelos valores exatos do pacote e execute `validate`.

O teste de integração automatiza esse percurso, incluindo a revisão simulada,
validação do exemplo e rejeição de uma citação desconhecida. As fixtures
estão em `tests/fixtures/minimal/`. APIs e agentes externos não são invocados.

## Campos obrigatórios ausentes

O comando analyze compara presença de chaves JSON apenas em relações
confirmadas. A chamada precisa usar Content-Type application/json explícito,
com cabeçalhos inline. O corpo pode ser uma string JSON literal contendo
objeto ou `JSON.stringify` de objeto inline com chaves estáticas e valores
primitivos determináveis. A análise considera o corpo efetivamente construído;
um campo opcional no tipo TypeScript, sozinho, não demonstra omissão.

No backend, a cobertura inicial é uma ação com um único parâmetro
`[FromBody] JsonElement`, com import explícito System.Text.Json ou tipo
qualificado. A guarda inicial `if (!body.TryGetProperty("name", out var name))
return BadRequest();` comprova a rejeição de objetos sem a chave name.
São aceitas guardas sequenciais, com bloco opcional, `out _` e retorno
`base.BadRequest()`. Retornos de sucesso anteriores, regras condicionais,
tipos/aliases não resolvidos e Controllers parciais produzem lacunas.

TryGetProperty distingue maiúsculas de minúsculas; null continua sendo uma
chave presente, e seu valor não é validado por esse teste de presença.
Veja a [documentação oficial de TryGetProperty](https://learn.microsoft.com/en-us/dotnet/api/system.text.json.jsonelement.trygetproperty?view=net-10.0).

Spreads, chaves computadas, valores dinâmicos ou undefined, replacers e toJSON
ficam como lacunas. Esses mecanismos podem alterar o resultado da serialização;
veja a [especificação ECMAScript de JSON.stringify](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.stringify).
Sinais reconhecidos de customização de serialização, como redefinição de
JSON.stringify ou configuração de conversores .NET em outro arquivo elegível
do mesmo repositório, bloqueiam conclusões dependentes dessa serialização.
Isso não substitui resolução semântica de bibliotecas ou execução do sistema.

DTOs, Required, nullability e convenções de validação sem binding/serialização
resolvidos são reportados como lacunas. Uma restrição de interface não comprova
rejeição pelo servidor. A análise preserva exigências incondicionais já
demonstradas e sinaliza validações adicionais não resolvidas.

`analysis.findings` registra um achado por campo omitido, com ID, relação,
explicação e evidências dos dois lados. `analysis.comparisons` distingue:

- `missing`: chave comprovadamente exigida e omitida.
- `no_omission`: todas as chaves comprovadamente exigidas estão presentes;
  isso não aprova tipos, valores nem regras não resolvidas.
- `unknown`: corpo, exigência, relação ou serialização não resolvidos.
- `not_applicable`: nenhum parâmetro de corpo identificado neste recorte.

As chaves são listadas nos contratos sem registrar seus valores. Os achados
acompanham o módulo exportado, e as lacunas aparecem em coverage.json.

Para reproduzir o cenário de campo opcional omitido:

```powershell
.\.venv\Scripts\python.exe examples\minimal-flow\prepare.py .scratch\required-field-demo --fixture required-field
.\.venv\Scripts\codedoc.exe analyze --config .scratch\required-field-demo\ecosystem.yaml
.\.venv\Scripts\codedoc.exe plan --config .scratch\required-field-demo\ecosystem.yaml
```

Revise o plano e siga os mesmos comandos context/validate do fluxo mínimo.
O documento de exemplo inclui marcadores para ID do achado, evidências e
commits. A matriz de resultados esperados foi fixada antes do detector em
`tests/fixtures/required-field/cases.json`; a integração valida o documento
e rejeita a omissão do achado ou de uma das citações exigidas.
