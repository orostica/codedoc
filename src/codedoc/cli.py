from pathlib import Path

import typer

from codedoc.config import ScanError, load_config
from codedoc.scanner import scan, write_inventory

app = typer.Typer(no_args_is_help=True, help="Documentação rastreável de ecossistemas locais.")


@app.callback()
def main():
    """Ferramentas locais de documentação."""


@app.command("scan")
def scan_command(config: Path = typer.Option(..., "--config", help="Arquivo YAML do ecossistema.")):
    """Inventariar repositórios Git limpos sem executar o código analisado."""
    try:
        settings = load_config(config)
        inventory = scan(settings)
        write_inventory(settings.output, inventory)
    except ScanError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Inventário gravado: {len(inventory['repositories'])} repositório(s).")


if __name__ == "__main__":
    app()
