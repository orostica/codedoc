# Codebase Documentation Engine

CLI local para inventariar um ecossistema de repositórios Next.js e C#/.NET.
O comando disponível nesta entrega é `scan`; análise de contratos e geração
de contexto pertencem aos próximos tickets.

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
segredos em qualquer segmento. Destinos são registrados, ainda sem confirmar
ligações entre chamadas e endpoints.

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
