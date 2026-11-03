"""Criar dois repositórios de demonstração sem executar frontend ou backend."""

import argparse
from pathlib import Path
import shutil
import subprocess


def prepare(destination: Path):
    if destination.exists():
        raise SystemExit("O destino já existe. Escolha um diretório novo.")
    fixture = Path(__file__).resolve().parents[2] / "tests/fixtures/minimal"
    destination.mkdir(parents=True)
    for name in ("api", "portal"):
        root = destination / name
        shutil.copytree(fixture / name, root)
        commands = [
            ["init"], ["config", "user.name", "CodeDoc Demo"],
            ["config", "user.email", "codedoc@example.invalid"],
            ["config", "commit.gpgsign", "false"],
            ["config", "core.hooksPath", ".disabled-hooks"],
            ["add", "--all"], ["commit", "-m", "Minimal documentation fixture"],
        ]
        for args in commands:
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    (destination / "ecosystem.yaml").write_text(
        "repositories:\n  - id: api\n    path: ./api\n  - id: portal\n    path: ./portal\n"
        "destinations:\n  - url: https://api.example.invalid\n    repository_id: api\n"
        "output: ./.codedoc/inventory.json\n", encoding="utf-8",
    )
    shutil.copyfile(fixture / "document.md", destination / "module.example.md")
    print("Demonstração criada. Execute analyze e plan com o ecosystem.yaml gerado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    prepare(parser.parse_args().destination.resolve())
