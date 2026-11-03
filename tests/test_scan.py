import json
from pathlib import Path
import subprocess

import pytest
from typer.testing import CliRunner
import yaml

from codedoc.cli import app
from codedoc.config import ScanError, load_config
from codedoc.scanner import scan
import codedoc.scanner as scanner


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def repository(root, files):
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "Scanner Test")
    git(root, "config", "user.email", "scanner@example.invalid")
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-m", "fixture")
    return root


def configuration(tmp_path, roots, **extra):
    path = tmp_path / "ecosystem.yaml"
    data = {"repositories": [{"id": root.name, "path": root.name} for root in roots],
            "output": "output/inventory.json", **extra}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_cli_multiple_repositories_from_another_directory(tmp_path, monkeypatch):
    api = repository(tmp_path / "api", {"App.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"/>',
                                        "Program.cs": "class Program {}"})
    web = repository(tmp_path / "web", {"package.json": json.dumps({"dependencies": {"next": "1", "axios": "1"}}),
                                        "src/index.tsx": "export default 1"})
    config = configuration(tmp_path, [api, web], destinations=[{"url": "https://api.example.invalid/v1", "repository_id": "api"}])
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    result = CliRunner().invoke(app, ["scan", "--config", str(config)])
    assert result.exit_code == 0, result.output
    inventory = json.loads((tmp_path / "output/inventory.json").read_text())
    assert [item["id"] for item in inventory["repositories"]] == ["api", "web"]
    for item, root in zip(inventory["repositories"], [api, web]):
        assert item["revision"] == git(root, "rev-parse", "HEAD")
        assert git(root, "status", "--porcelain") == ""
    assert inventory["repositories"][0]["projects"][0]["technologies"] == ["csharp", "dotnet"]
    assert inventory["repositories"][1]["projects"][0]["technologies"] == ["axios", "next", "nodejs"]
    assert inventory["repositories"][1]["languages"] == ["typescript"]
    assert inventory["destinations"][0]["repository_id"] == "api"


@pytest.mark.parametrize("dirty_kind", ["modified", "staged", "untracked"])
def test_dirty_repositories_are_preserved(tmp_path, dirty_kind):
    root = repository(tmp_path / "api", {"Program.cs": "original"})
    changed = root / ("new.cs" if dirty_kind == "untracked" else "Program.cs")
    changed.write_text("private-content", encoding="utf-8")
    if dirty_kind == "staged":
        git(root, "add", "--all")
    before = git(root, "status", "--porcelain")
    result = CliRunner().invoke(app, ["scan", "--config", str(configuration(tmp_path, [root]))])
    assert result.exit_code == 1
    assert "alterações pendentes" in result.output
    assert "private-content" not in result.output
    assert changed.read_text() == "private-content"
    assert git(root, "status", "--porcelain") == before
    assert not (tmp_path / "output").exists()


def test_requires_repository_root_with_commit(tmp_path):
    root = tmp_path / "api"
    root.mkdir()
    config = configuration(tmp_path, [root])
    with pytest.raises(ScanError, match="raiz Git"):
        scan(load_config(config))
    git(root, "init")
    with pytest.raises(ScanError, match="commit"):
        scan(load_config(config))


def test_exclusions_block_sensitive_and_ignored_content_before_read(tmp_path, monkeypatch):
    root = repository(tmp_path / "api", {
        "package.json": '{"scripts":{"postinstall":"do-not-run"},"dependencies":{"next":"1"}}',
        ".gitignore": "ignored/\n",
        ".env": "PRIVATE_SECRET",
        "credentials/package.json": "PRIVATE_SECRET",
        "node_modules/pkg/package.json": "PRIVATE_SECRET",
        "excluded/package.json": "PRIVATE_SECRET",
        "generated/package.json": "PRIVATE_SECRET",
        "keep.ts": "PRIVATE_SOURCE_NOT_READ",
        "private.pem": "PRIVATE_SECRET",
        "appsettings.json": "PRIVATE_SECRET",
    })
    # Também excluir arquivo rastreado que passou a ser ignorado.
    ignored = root / "ignored"
    ignored.mkdir()
    (ignored / "package.json").write_text("PRIVATE_SECRET")
    git(root, "add", "--force", "ignored/package.json")
    git(root, "commit", "-m", "tracked ignored file")
    config = configuration(tmp_path, [root], exclude=["excluded/", "generated/**"])
    reads = []
    original = scanner.read_manifest

    def audited_read(path):
        reads.append(path.relative_to(root).as_posix())
        return original(path)

    monkeypatch.setattr(scanner, "read_manifest", audited_read)
    inventory = scan(load_config(config))
    assert reads == ["package.json"]
    assert inventory["repositories"][0]["files"] == [".gitignore", "keep.ts", "package.json"]
    assert "PRIVATE" not in json.dumps(inventory)


@pytest.mark.parametrize("url", ["https://user:PRIVATE_SECRET@example.invalid", "https://example.invalid?token=PRIVATE_SECRET", "file:///private", "https://example.invalid/#PRIVATE_SECRET"])
def test_invalid_destinations_do_not_leak_values(tmp_path, url):
    config = configuration(tmp_path, [tmp_path / "api"], destinations=[{"url": url, "repository_id": "api"}])
    result = CliRunner().invoke(app, ["scan", "--config", str(config)])
    assert result.exit_code == 1
    assert "Configuração inválida" in result.output
    assert "PRIVATE_SECRET" not in result.output


def test_manifest_parse_errors_do_not_leak_content(tmp_path):
    root = repository(tmp_path / "api", {"package.json": "PRIVATE_SECRET", "App.csproj": "<!DOCTYPE secret>PRIVATE_SECRET"})
    inventory = scan(load_config(configuration(tmp_path, [root])))
    assert "PRIVATE_SECRET" not in json.dumps(inventory)
    assert all(project["warning"] == "manifest_unreadable" for project in inventory["repositories"][0]["projects"])


def test_revision_change_during_scan_is_rejected(tmp_path, monkeypatch):
    root = repository(tmp_path / "api", {"Program.cs": "original"})
    original = scanner.scan_repository

    def changing_scan(*args):
        result = original(*args)
        (root / "Program.cs").write_text("changed")
        git(root, "add", "--all")
        git(root, "commit", "-m", "new revision")
        return result

    monkeypatch.setattr(scanner, "scan_repository", changing_scan)
    with pytest.raises(ScanError, match="revisão mudou"):
        scan(load_config(configuration(tmp_path, [root])))


def test_output_cannot_dirty_analyzed_repository(tmp_path):
    root = repository(tmp_path / "api", {"Program.cs": "original"})
    config = configuration(tmp_path, [root], output="api/inventory.json")
    result = CliRunner().invoke(app, ["scan", "--config", str(config)])
    assert result.exit_code == 1
    assert "saída deve ficar fora" in result.output
    assert git(root, "status", "--porcelain") == ""


@pytest.mark.parametrize("extra", [
    {"repositories": [{"id": "same", "path": "api"}, {"id": "same", "path": "web"}]},
    {"destinations": [{"url": "https://api.example.invalid", "repository_id": "unknown"}]},
    {"output": "ecosystem.yaml"},
    {"repositories": [{"id": "api", "path": "invalid\x00path"}]},
])
def test_invalid_configuration_preserves_input_and_has_safe_diagnostic(tmp_path, extra):
    config = configuration(tmp_path, [tmp_path / "api"], **extra)
    before = config.read_bytes()
    result = CliRunner().invoke(app, ["scan", "--config", str(config)])
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert config.read_bytes() == before
    assert not (tmp_path / "output").exists()


def test_symlink_manifest_is_not_read(tmp_path):
    root = repository(tmp_path / "api", {"Program.cs": "original"})
    target = tmp_path / "private.json"
    target.write_text("PRIVATE_SECRET")
    try:
        (root / "package.json").symlink_to(target)
    except OSError:
        pytest.skip("Criação de symlink indisponível neste ambiente")
    git(root, "add", "--all")
    git(root, "commit", "-m", "link")
    inventory = scan(load_config(configuration(tmp_path, [root])))
    assert inventory["repositories"][0]["projects"] == []
