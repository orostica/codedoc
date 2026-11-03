# Codebase Documentation Engine

CLI local para inventariar e documentar um fluxo mínimo entre repositórios
Next.js e C#/.NET. Comandos disponíveis: `scan`, `analyze`, `plan`, `context`
e `validate`. A CLI não invoca agentes nem executa os projetos analisados.

Requer Python 3.12+ e Git no PATH.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\codedoc.exe scan --config C:\MeuEcossistema\ecosystem.yaml
.\.venv\Scripts\python.exe -m pytest
```

Exemplo de configuração YAML, mantida fora dos repositórios analisados:

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

## Fluxo mínimo de documentação

```powershell
.\.venv\Scripts\codedoc.exe analyze --config C:\MeuEcossistema\ecosystem.yaml
.\.venv\Scripts\codedoc.exe plan --config C:\MeuEcossistema\ecosystem.yaml
```

Os artefatos ficam ao lado do inventário configurado: `analysis.json` contém
símbolos, dependências sintáticas, chamadas, endpoints, relações, evidências e
cobertura. `plan.json` sugere um módulo por relação confirmada. Revise os
nomes, o escopo e as relações e altere `reviewed` de `false` para `true`.
Copie o `id` do módulo desejado para o próximo comando:

```powershell
.\.venv\Scripts\codedoc.exe context --config C:\MeuEcossistema\ecosystem.yaml --module ID_DO_MODULO
```

A exportação exige plano revisado da análise atual, configuração compatível,
mesmos commits e árvores limpas em todos os repositórios. Planos e pacotes
existentes são preservados: mova-os antes de gerar novamente.

O diretório `contexts/<id-do-modulo>/` contém:

- `context.json`: módulo selecionado, símbolos, contratos mínimos e evidências.
- `sources/`: trechos dos arquivos na revisão Git original, sem normalizar bytes.
- `task.md`: instruções independentes do agente e seções obrigatórias do documento.
- `coverage.json`: relações do módulo e lacunas da análise global, que podem
  incluir outros arquivos e chamadas fora do recorte.

Entregue o pacote ao agente de sua preferência e peça Markdown conforme a
tarefa. Use citações `[@ev-<24 caracteres hexadecimais>]`, copiando os IDs
exatos de `context.json`. Cada evidência identifica repositório, commit,
arquivo relativo, símbolo, linhas inclusivas e SHA-256 do arquivo inteiro.
O pacote também registra SHA-256 dos trechos exportados. Os hashes são
verificados contra os blobs Git, independentemente de CRLF da cópia local.

```powershell
.\.venv\Scripts\codedoc.exe validate C:\MeuEcossistema\module.md --config C:\MeuEcossistema\ecosystem.yaml --context C:\MeuEcossistema\.codedoc\contexts\ID_DO_MODULO
```

O validador exige seções Objetivo, Fluxo, Evidências, Lacunas e Revisão,
commits participantes e citações conhecidas. Confere os símbolos, intervalos,
hashes e trechos na revisão original. Parágrafos de Objetivo e Fluxo devem
conter citações; a interpretação semântica e a associação de cada afirmação
à evidência adequada continuam dependendo de revisão humana.
As três dimensões de validação e a comparação com fontes atuais serão
ampliadas no ticket 12.

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
de tipos, campos obrigatórios e resolução semântica ficam para os próximos
tickets. As dependências import/using são sintáticas. Não há comprovação
do comportamento em execução nem de configuração global do servidor.

Arquivos com erro sintático, codificação diferente de UTF-8 ou mais de 2 MB
geram lacunas. O orçamento e a divisão dos pacotes serão implementados no
ticket 11; neste recorte pequeno, módulos de arquivo e classes podem levar
ao pacote trechos além da ação específica. A ausência de achados não indica
cobertura completa. A análise lê código elegível e exporta trechos: adicione
às exclusões quaisquer fontes sensíveis específicas do seu ecossistema.

Os schemas JSON versionados estão em `schemas/`, gerados dos modelos
Pydantic usados para validar artefatos em execução. O identificador da análise
é o hash de seu conteúdo completo; no pacote ele preserva a referência à
análise original, enquanto o conteúdo é filtrado para o módulo selecionado.

## Demonstração reproduzível

```powershell
.\.venv\Scripts\python.exe examples\minimal-flow\prepare.py .scratch\minimal-demo
.\.venv\Scripts\codedoc.exe analyze --config .scratch\minimal-demo\ecosystem.yaml
.\.venv\Scripts\codedoc.exe plan --config .scratch\minimal-demo\ecosystem.yaml
```

O preparador copia a fixture mantida no projeto para dois repositórios Git
novos e cria commits locais. Não instala nem executa os projetos de exemplo.
Revise `.scratch/minimal-demo/.codedoc/plan.json`, marque `reviewed: true` e
execute `context` com o ID escolhido. O arquivo `module.example.md` contém
um documento de exemplo: substitua os marcadores de evidências e commits
pelos valores exatos do pacote e execute `validate`.

O teste de integração automatiza esse percurso, incluindo a revisão simulada,
validação do exemplo e rejeição de uma citação desconhecida. As fixtures
estão em `tests/fixtures/minimal/`. APIs e agentes externos não são invocados.
