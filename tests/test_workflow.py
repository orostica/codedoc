import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codedoc.cli import app
from codedoc.config import ScanError, load_config
from codedoc.models import Analysis, Context, Coverage, Plan
from codedoc.parsing import Extractor
from codedoc.validation import validate_document
from codedoc.workflow import analyze, create_plan, destination_routes, export_context, read_model
from test_scan import configuration, git, repository


FIXTURE = Path(__file__).parent / "fixtures/minimal"


def fixture_sources(fixture, name):
    manifest = json.loads((fixture / "files.json").read_text(encoding="utf-8"))
    return {relative: (fixture / name / relative).read_text(encoding="utf-8") for relative in manifest[name]}


@pytest.fixture
def ecosystem(tmp_path):
    roots = []
    for name in ("api", "portal"):
        files = fixture_sources(FIXTURE, name)
        roots.append(repository(tmp_path / name, files))
    path = configuration(tmp_path, roots,
                         destinations=[{"url": "https://api.example.invalid", "repository_id": "api"}])
    return path, load_config(path), roots


def test_fixture_loader_ignores_generated_binaries(tmp_path):
    (tmp_path / "api/obj").mkdir(parents=True)
    (tmp_path / "api/ItemsController.cs").write_text("class ItemsController {}", encoding="utf-8")
    (tmp_path / "api/obj/Demo.assets.cache").write_bytes(b"\xff\x00generated")
    (tmp_path / "files.json").write_text(json.dumps({"api": ["ItemsController.cs"]}), encoding="utf-8")
    assert fixture_sources(tmp_path, "api") == {"ItemsController.cs": "class ItemsController {}"}


def reviewed_package(config):
    analysis = analyze(config)
    plan = create_plan(config)
    plan.reviewed = True
    (config.output.parent / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    package = export_context(config, plan.modules[0].id)
    return analysis, plan, package


def sample_document(config, package):
    context = read_model(package / "context.json", Context)
    call = context.analysis.calls[0]
    endpoint = context.analysis.endpoints[0]
    symbols = {item.id: item for item in context.analysis.symbols}
    values = {
        "frontend_evidence": call.evidence_id,
        "backend_evidence": symbols[endpoint.symbol_id].evidence_id,
        "frontend_revision": next(repo.revision for repo in context.analysis.repositories if repo.id == "portal"),
        "backend_revision": next(repo.revision for repo in context.analysis.repositories if repo.id == "api"),
    }
    content = (FIXTURE / "document.md").read_text(encoding="utf-8")
    for key, value in values.items():
        content = content.replace("{{" + key + "}}", value)
    document = config.output.parent / "module.md"
    document.write_text(content, encoding="utf-8")
    return document


def test_cli_full_workflow_and_unknown_citation(ecosystem, tmp_path, monkeypatch):
    config_path, config, roots = ecosystem
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    runner = CliRunner()
    for command in ("analyze", "plan"):
        result = runner.invoke(app, [command, "--config", str(config_path)])
        assert result.exit_code == 0, (result.output, result.exception)
    analysis = read_model(config.output.parent / "analysis.json", Analysis)
    assert len(analysis.relations) == 1
    assert analysis.relations[0].status == "confirmed"
    assert analysis.coverage.unresolved_calls == []
    assert analysis.coverage.gaps == []
    assert {item.kind for item in analysis.dependencies} == {"import", "using"}
    assert all(item.id.startswith(item.repository_id + ":") for item in analysis.symbols)
    plan = read_model(config.output.parent / "plan.json", Plan)
    args = ["context", "--config", str(config_path), "--module", plan.modules[0].id]
    blocked = runner.invoke(app, args)
    assert blocked.exit_code == 1
    assert "Revise plan.json" in blocked.output
    plan.reviewed = True
    (config.output.parent / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    exported = runner.invoke(app, args)
    assert exported.exit_code == 0, (exported.output, exported.exception)
    package = config.output.parent / "contexts" / plan.modules[0].id
    context = read_model(package / "context.json", Context)
    assert (package / "task.md").exists()
    assert json.loads((package / "coverage.json").read_text()) == context.analysis.coverage.model_dump()
    for evidence in context.analysis.evidence:
        root = next(root for root in roots if root.name == evidence.repository_id)
        blob = git(root, "show", f"{evidence.revision}:{evidence.file}")
        assert evidence.start_line <= evidence.end_line
        assert evidence.symbol.startswith(evidence.repository_id + ":")
        # git helper strips trailing newline; source hash uses exact Git blob bytes.
        assert len(evidence.source_hash) == 64
        assert blob
    document = sample_document(config, package)
    validate_args = ["validate", str(document), "--config", str(config_path), "--context", str(package)]
    valid = runner.invoke(app, validate_args)
    assert valid.exit_code == 0, (valid.output, valid.exception)
    assert "revisão humana" in valid.output
    document.write_text(document.read_text(encoding="utf-8") + "\n[@ev-unknown]\n", encoding="utf-8")
    invalid = runner.invoke(app, validate_args)
    assert invalid.exit_code == 1
    assert "desconhecida" in invalid.output
    assert all(git(root, "status", "--porcelain") == "" for root in roots)


@pytest.mark.parametrize("change", ["dirty", "commit", "config", "analysis", "plan"])
def test_export_rejects_stale_or_modified_inputs(ecosystem, change):
    _, config, roots = ecosystem
    analyze(config)
    plan = create_plan(config)
    plan.reviewed = True
    if change == "dirty":
        (roots[1] / "client.ts").write_text("changed")
    elif change == "commit":
        (roots[1] / "client.ts").write_text("changed")
        git(roots[1], "add", "--all")
        git(roots[1], "commit", "-m", "changed")
    elif change == "config":
        config.destinations.clear()
    elif change == "analysis":
        path = config.output.parent / "analysis.json"
        data = json.loads(path.read_text())
        data["config_hash"] = "changed"
        path.write_text(json.dumps(data))
    elif change == "plan":
        plan.analysis_id = "outdated"
    (config.output.parent / "plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    with pytest.raises(ScanError):
        export_context(config, plan.modules[0].id)
    assert not (config.output.parent / "contexts").exists()


@pytest.mark.parametrize("mutation", ["snippet", "hash", "range", "coverage", "no_citation", "no_section", "malformed_citation"])
def test_validator_detects_corrupted_sources_and_markdown(ecosystem, mutation):
    _, config, _ = ecosystem
    _, _, package = reviewed_package(config)
    document = sample_document(config, package)
    if mutation in {"hash", "range"}:
        path = package / "context.json"
        data = json.loads(path.read_text())
        if mutation == "hash":
            data["analysis"]["evidence"][0]["source_hash"] = "0" * 64
        else:
            evidence = data["analysis"]["evidence"][0]
            evidence["end_line"] += 1
            symbol = next(item for item in data["analysis"]["symbols"] if item["id"] == evidence["symbol"])
            symbol["end_line"] += 1
        path.write_text(json.dumps(data))
    elif mutation == "snippet":
        next((package / "sources").iterdir()).write_text("changed")
    elif mutation == "coverage":
        path = package / "coverage.json"
        data = json.loads(path.read_text())
        data["unresolved_calls"] = ["unknown"]
        path.write_text(json.dumps(data))
    else:
        content = document.read_text(encoding="utf-8")
        if mutation == "no_citation":
            content = content.replace("## Fluxo", "## Fluxo\n\nAfirmação sem evidência.\n")
        elif mutation == "no_section":
            content = content.replace("## Revisão", "## Outra seção")
        else:
            content += "\n[@ev-incompleta\n"
        document.write_text(content, encoding="utf-8")
    try:
        errors = validate_document(config, document, package)
    except ScanError:
        assert mutation == "coverage"
    else:
        assert errors


def test_matching_requires_destination_method_and_route(ecosystem):
    _, config, _ = ecosystem
    config.destinations.clear()
    no_destination = analyze(config)
    assert no_destination.coverage.confirmed == []
    assert no_destination.coverage.unresolved_calls
    assert no_destination.coverage.gaps[0].code == "destination_unmapped"


@pytest.mark.parametrize("url,method", [
    ("https://api.example.invalid/api/different", "GET"),
    ("https://api.example.invalid/api/items", "POST"),
    ("https://other.example.invalid/api/items", "GET"),
])
def test_different_route_method_or_host_never_confirms(ecosystem, url, method):
    _, config, roots = ecosystem
    client = roots[1] / "client.ts"
    client.write_text(f'export async function load() {{ return fetch("{url}", {{method: "{method}"}}); }}')
    git(roots[1], "add", "--all")
    git(roots[1], "commit", "-m", "different target")
    result = analyze(config)
    assert result.coverage.confirmed == []
    assert result.coverage.unresolved_calls


@pytest.mark.parametrize("source", [
    'export function load(url: string) { return fetch(url); }',
    'export function load() { return fetch("/api/items"); }',
    'export function load(options: RequestInit) { return fetch("https://api.example.invalid/api/items", options); }',
    'export function load(fetch: any) { return fetch("https://api.example.invalid/api/items"); }',
    'export function load() { return fetch("https://api.example.invalid/api/items", { ...options }); }',
])
def test_unsupported_fetch_patterns_are_explicit_gaps(source):
    parsed = Extractor("portal", "a" * 40, "client.ts", source.encode()).parse()
    assert parsed.calls
    assert parsed.gaps[0].code == "fetch_unresolved"
    assert parsed.calls[0].url is None or parsed.calls[0].method is None


def test_invalid_syntax_does_not_create_confirmed_contracts():
    parsed = Extractor("portal", "a" * 40, "client.ts", b'function broken( { fetch("x")').parse()
    assert parsed.calls == []
    assert parsed.gaps[0].code == "syntax_error"


def test_module_and_function_with_identical_extent_keep_distinct_symbols():
    parsed = Extractor("portal", "a" * 40, "client.ts",
                       b'function load() { return fetch("https://api.example.invalid/api/items"); }').parse()
    assert {symbol.kind for symbol in parsed.symbols} == {"module", "function"}
    function = next(symbol for symbol in parsed.symbols if symbol.kind == "function")
    assert parsed.calls[0].symbol_id == function.id


@pytest.mark.parametrize("filename", ["ItemsController.cs", "ItemsController.CS"])
def test_controller_base_is_parsed_independently_of_whitespace(filename):
    source = b'[Route("api/items")]public class ItemsController:ControllerBase{[HttpGet]public object List(){return null;}}'
    parsed = Extractor("api", "a" * 40, filename, source).parse()
    assert len(parsed.endpoints) == 1
    assert parsed.endpoints[0].route == "/api/items"
    assert {symbol.kind for symbol in parsed.symbols} == {"module", "class", "method"}


def test_fetch_options_cannot_hide_method_in_prototype_or_escaped_key():
    prototype = Extractor("portal", "a" * 40, "client.ts",
                          b'fetch("https://api.example.invalid/api/items", {__proto__: {method: "POST"}})').parse()
    assert prototype.calls[0].method is None
    escaped = Extractor("portal", "a" * 40, "client.ts",
                        b'fetch("https://api.example.invalid/api/items", {"metho\\u0064": "POST"})').parse()
    assert escaped.calls[0].method == "POST"


def test_destination_prefix_uses_segment_boundary_and_longest_match(ecosystem):
    _, config, _ = ecosystem
    from codedoc.config import Destination
    config.destinations.append(Destination(url="https://api.example.invalid/service", repository_id="portal"))
    assert destination_routes("https://api.example.invalid/service/api/items", config) == [("portal", "/api/items")]
    assert destination_routes("https://api.example.invalid/services/api/items", config) == [("api", "/services/api/items")]


def test_equally_specific_destinations_remain_candidates(ecosystem):
    _, config, _ = ecosystem
    from codedoc.config import Destination
    config.destinations.append(Destination(url="https://api.example.invalid", repository_id="portal"))
    result = analyze(config)
    assert result.coverage.confirmed == []
    assert len(result.coverage.candidates) == 1


@pytest.mark.parametrize("route", ["[HttpGet(\"{id}\")]", "[HttpGet] [HttpPost]", "[HttpGet] [Route(\"other\")]"])
def test_unsupported_controller_routes_never_create_endpoint(route):
    source = f'[Route("api/items")] public class ItemsController : ControllerBase {{ {route} public object List() {{ return null; }} }}'
    parsed = Extractor("api", "a" * 40, "ItemsController.cs", source.encode()).parse()
    assert parsed.endpoints == []
    assert parsed.gaps


def test_known_unsupported_api_patterns_are_reported():
    typescript = Extractor("portal", "a" * 40, "client.ts", b'window.fetch("/api/items"); axios.get("/api/items");').parse()
    assert {gap.code for gap in typescript.gaps} == {"member_fetch_not_supported", "axios_not_supported"}
    csharp = Extractor("api", "a" * 40, "Program.cs", b'app.MapGet("/api/items", () => "ok");').parse()
    assert csharp.gaps[0].code == "minimal_api_not_supported"


def test_analyze_respects_scanner_exclusions(ecosystem):
    _, config, _ = ecosystem
    config.exclude = ["client.ts"]
    result = analyze(config)
    assert result.calls == []
    assert all(item.file != "client.ts" for item in result.evidence)


def test_plan_and_package_are_not_silently_overwritten(ecosystem):
    _, config, _ = ecosystem
    _, plan, package = reviewed_package(config)
    before = (package / "context.json").read_bytes()
    with pytest.raises(ScanError, match="Já existe"):
        create_plan(config)
    with pytest.raises(ScanError, match="Pacote já existe"):
        export_context(config, plan.modules[0].id)
    assert (package / "context.json").read_bytes() == before


def test_schemas_match_runtime_contracts():
    for model, filename in ((Analysis, "analysis"), (Plan, "plan"), (Context, "context"), (Coverage, "coverage")):
        stored = json.loads((Path(__file__).parents[1] / "schemas" / f"{filename}.schema.json").read_text())
        assert stored == model.model_json_schema()
