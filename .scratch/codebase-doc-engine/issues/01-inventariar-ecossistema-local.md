# 01: Inventariar um ecossistema local com segurança

**What to build:** Executar a CLI com uma configuração comum para vários repositórios locais e obter um inventário confiável do ecossistema analisado.

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] A configuração identifica repositórios, destinos HTTP sem credenciais, exclusões e saída; funciona também fora das raízes analisadas.
- [x] O inventário identifica projetos, tecnologias e commits completos por repositório, incluindo Next.js e C#/.NET.
- [x] Repositórios sem Git ou com alterações pendentes são recusados com diagnóstico acionável, preservando as alterações existentes.
- [x] O scanner respeita .gitignore e exclusões e bloqueia arquivos sensíveis por padrão; não executa código analisado nem faz chamadas de rede.
- [x] Testes com repositórios temporários verificam inventário, árvores sujas e exclusões; logs não expõem conteúdo sensível.

## Answer

Implementado em 2026-11-03. CLI `codedoc scan --config` com configuração YAML validada,
caminhos relativos à configuração e inventário JSON de vários repositórios.
Detecta projetos Next.js e C#/.NET, registra commits completos, linguagens e arquivos
elegíveis. Preserva árvores de trabalho e rejeita saída dentro dos repositórios analisados.

Consulta Git com fsmonitor desabilitado, aplica .gitignore inclusive a arquivos rastreados,
exclusões configuráveis e bloqueios de arquivos sensíveis. Lê somente manifests elegíveis,
sem executar scripts ou acessar a rede. Erros de configuração e manifests não expõem valores.
Verifica novamente commits e limpeza das árvores antes de retornar o inventário.

Validação: `python -m pytest -q` — 17 testes aprovados, 1 ignorado por falta de permissão
para criar symlink neste Windows. O comando instalado `codedoc scan --help` funciona.
README contém instalação, execução, exemplo de configuração e limites da detecção.

Arquivos sensíveis são bloqueados por padrões de nomes; convenções próprias devem ser
adicionadas às exclusões. O piloto MSSUPERA não foi executado nesta entrega.
