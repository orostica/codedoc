import json

from typer.testing import CliRunner

from codedoc.cli import app
from codedoc.config import load_config
from test_scan import repository, git


def test_init_and_scan_use_current_directory(tmp_path, monkeypatch):
    api = repository(tmp_path / "api", {"App.csproj": "<Project/>"})
    repository(tmp_path / "portal", {"package.json": '{"dependencies":{"next":"1"}}'})
    (tmp_path / "ordinary-folder").mkdir()
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    config = load_config(tmp_path / "ecosystem.yaml")
    assert [repo.path.name for repo in config.repositories] == ["api", "portal"]
    assert config.destinations == []
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0, result.output
    inventory = json.loads((tmp_path / ".codedoc/inventory.json").read_text())
    assert len(inventory["repositories"]) == 2
    assert git(api, "status", "--porcelain") == ""


def test_init_preserves_existing_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "ecosystem.yaml"
    target.write_text("original", encoding="utf-8")
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 1
    assert target.read_text() == "original"


def test_init_without_repositories_does_not_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 1
    assert not (tmp_path / "ecosystem.yaml").exists()


def test_init_inside_repository_places_output_outside(tmp_path, monkeypatch):
    root = repository(tmp_path / "api", {"App.csproj": "<Project/>"})
    monkeypatch.chdir(root)
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    config = load_config(root / "ecosystem.yaml")
    assert config.repositories[0].path == root
    assert not config.output.is_relative_to(root)
    git(root, "add", "ecosystem.yaml")
    git(root, "commit", "-m", "configuration")
    result = CliRunner().invoke(app, ["scan"])
    assert result.exit_code == 0, result.output
