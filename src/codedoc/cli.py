from pathlib import Path

import typer
import yaml

from codedoc.config import ScanError, load_config
from codedoc.scanner import scan, write_inventory
from codedoc.workflow import analyze, create_plan, export_context
from codedoc.validation import validate_document

app = typer.Typer(no_args_is_help=True, help="Documentação rastreável de ecossistemas locais.")


@app.callback()
def main():
    """Ferramentas locais de documentação."""


@app.command("init")
def init_command():
    """Criar ecosystem.yaml com os repositórios da pasta atual."""
    root = Path.cwd()
    target = root / "ecosystem.yaml"
    if target.exists():
        typer.echo("ecosystem.yaml já existe; configuração preservada.", err=True)
        raise typer.Exit(1)
    try:
        roots = ([root] if (root / ".git").exists() else sorted(
            (child for child in root.iterdir()
             if child.is_dir() and not child.is_symlink()
             and not child.is_junction() and (child / ".git").exists()),
            key=lambda child: child.name.casefold(),
        ))
        if not roots:
            typer.echo("Nenhum repositório Git encontrado na pasta atual ou nas subpastas imediatas.", err=True)
            raise typer.Exit(1)
        data = {
            "repositories": [{"id": f"repo-{index}", "path": path.relative_to(root).as_posix()}
                             for index, path in enumerate(roots, start=1)],
            "destinations": [],
            "exclude": [],
            "output": ("../.codedoc-" + root.name + "/inventory.json"
                       if roots == [root] else ".codedoc/inventory.json"),
        }
        with target.open("x", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False)
    except OSError:
        typer.echo("Não foi possível criar ecosystem.yaml. Confira as permissões da pasta.", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Configuração criada em {target} com {len(roots)} repositório(s).")
    typer.echo("Revise os caminhos, exclusões e destinations antes de analisar.")
    if roots == [root]:
        typer.echo("A saída fica na pasta pai. Faça commit do YAML ou ignore-o no Git para manter a árvore limpa.")


@app.command("scan")
def scan_command(config: Path = typer.Option(Path("ecosystem.yaml"), "--config", help="Arquivo YAML do ecossistema.")):
    """Inventariar repositórios Git limpos sem executar o código analisado."""
    try:
        settings = load_config(config)
        inventory = scan(settings)
        write_inventory(settings.output, inventory)
    except ScanError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Inventário gravado: {len(inventory['repositories'])} repositório(s).")


@app.command("analyze")
def analyze_command(config: Path = typer.Option(Path("ecosystem.yaml"), "--config")):
    """Analisar fetch direto e Controllers com rotas literais."""
    try:
        result = analyze(load_config(config))
    except ScanError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Análise gravada: {len(result.coverage.confirmed)} relação(ões) confirmada(s), {len(result.findings)} achado(s), {len(result.coverage.gaps)} lacuna(s).")


@app.command("plan")
def plan_command(config: Path = typer.Option(Path("ecosystem.yaml"), "--config")):
    """Sugerir módulos em plan.json para revisão manual."""
    try:
        plan = create_plan(load_config(config))
    except ScanError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Plano criado com {len(plan.modules)} módulo(s). Revise plan.json e marque reviewed como true.")


@app.command("context")
def context_command(config: Path = typer.Option(Path("ecosystem.yaml"), "--config"), module: str = typer.Option(..., "--module")):
    """Exportar pacote de um módulo revisado, sem invocar agentes."""
    try:
        export_context(load_config(config), module)
    except ScanError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo("Pacote exportado: context.json, sources/, task.md e coverage.json.")


@app.command("validate")
def validate_command(document: Path, config: Path = typer.Option(Path("ecosystem.yaml"), "--config"),
                     context: Path = typer.Option(..., "--context", help="Diretório do pacote exportado.")):
    """Verificar estrutura, citações e evidências originais do Markdown."""
    try:
        errors = validate_document(load_config(config), document, context)
        if errors:
            for error in errors:
                typer.echo(error, err=True)
            raise typer.Exit(1)
    except ScanError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo("Estrutura e evidências válidas. Conteúdo aguarda revisão humana.")


if __name__ == "__main__":
    app()
