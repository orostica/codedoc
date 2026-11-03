import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codedoc.cli import app
from codedoc.comparison import compare_required_fields
from codedoc.config import Destination, load_config
from codedoc.models import Analysis, Context, Relation
from codedoc.parsing import Extractor
from codedoc.syntax import stable_id
from codedoc.validation import validate_document
from codedoc.workflow import analyze, create_plan, export_context, read_model, select_analysis
from test_scan import configuration, git, repository


FIXTURE = Path(__file__).parent / "fixtures/required-field"
CASES = json.loads((FIXTURE / "cases.json").read_text(encoding="utf-8"))


def frontend(body):
    return (FIXTURE / "portal/client.ts").read_text(encoding="utf-8").replace("JSON.stringify({ age: 18 })", body)


def backend(kind="required"):
    source = (FIXTURE / "api/PeopleController.cs").read_text(encoding="utf-8")
    condition = 'if (!body.TryGetProperty("name", out var name))'
    if kind == "conditional":
        source = source.replace(condition, 'if (RequiresName && !body.TryGetProperty("name", out var name))')
        source = source.replace("    [HttpPost]", "    public bool RequiresName { get; set; }\n    [HttpPost]")
    elif kind == "not_rejecting":
        source = source.replace("return BadRequest();", "return Ok();")
    elif kind == "early_success":
        source = source.replace(condition, "if (SkipValidation) return Ok();\n        " + condition)
        source = source.replace("    [HttpPost]", "    public bool SkipValidation { get; set; }\n    [HttpPost]")
    elif kind == "dto":
        source = source.replace("JsonElement body", "PersonInput body").replace(condition, "if (body.Name == null)")
        source += '\npublic class PersonInput { [System.ComponentModel.DataAnnotations.Required] public string? Name { get; set; } }\n'
    elif kind == "two_required":
        source = source.replace("        return Ok();", '        if (!body.TryGetProperty("email", out var email)) return BadRequest();\n        return Ok();')
    return source


def extracted(frontend_source, backend_source=None, *, status="confirmed"):
    client = Extractor("portal", "a" * 40, "client.ts", frontend_source.encode()).parse()
    server = Extractor("api", "b" * 40, "PeopleController.cs", (backend_source or backend()).encode()).parse()
    assert len(client.calls) == 1
    assert len(server.endpoints) == 1
    relation = Relation(id=stable_id("rel-", client.calls[0].id, server.endpoints[0].id), call_id=client.calls[0].id,
                        endpoint_id=server.endpoints[0].id, status=status, reason="fixture")
    comparisons, findings, gaps = compare_required_fields(client.calls, server.endpoints, [relation], client.symbols + server.symbols)
    return comparisons, findings, gaps, client, server


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_predefined_matrix(case):
    comparisons, findings, gaps, client, server = extracted(frontend(case["body"]), backend(case["backend"]))
    assert comparisons[0].status == case["expected"]
    assert [finding.field for finding in findings] == case["fields"]
    if case["expected"] == "unknown":
        assert gaps
        assert not findings
    else:
        assert not gaps
    proof = {client.calls[0].evidence_id, next(symbol.evidence_id for symbol in server.symbols if symbol.id == server.endpoints[0].symbol_id)}
    assert all(set(finding.evidence_ids) == proof for finding in findings)


@pytest.mark.parametrize("body", [
    "JSON.stringify({age: 18})",
    "JSON.stringify({name: 'Ana'})",
])
def test_candidates_never_support_findings(body):
    comparisons, findings, gaps, _, _ = extracted(frontend(body), status="candidate")
    assert comparisons[0].status == "unknown"
    assert not findings
    assert gaps[0].code == "required_fields_relation_unconfirmed"


@pytest.mark.parametrize("change", ["missing_content_type", "dynamic_headers", "shadowed_json", "overwritten_stringify", "custom_to_json"])
def test_unresolved_serialization_never_supports_findings(change):
    source = frontend("JSON.stringify({age: 18})")
    if change == "missing_content_type":
        source = source.replace('headers: { "Content-Type": "application/json" },', "")
    elif change == "dynamic_headers":
        source = source.replace('{ "Content-Type": "application/json" }', "input.headers")
    elif change == "shadowed_json":
        source = source.replace("input: PersonInput", "input: PersonInput, JSON: any")
    elif change == "overwritten_stringify":
        source = "JSON.stringify = customSerializer;\n" + source
    else:
        source = source.replace("JSON.stringify({age: 18})", "JSON.stringify({ toJSON() { return {name: 'Ana'}; } })")
    comparisons, findings, gaps, _, _ = extracted(source)
    assert comparisons[0].status == "unknown"
    assert not findings
    assert gaps


@pytest.mark.parametrize("change", ["missing_return", "else_branch", "out_overwrites_body", "partial_controller", "custom_bad_request", "unknown_type"])
def test_ambiguous_backend_never_supports_findings(change):
    source = backend()
    if change == "missing_return":
        source = source.replace("return BadRequest();", "BadRequest();")
    elif change == "else_branch":
        source = source.replace("        return Ok();", "        else { return Ok(); }\n        return Ok();")
    elif change == "out_overwrites_body":
        source = source.replace("out var name", "out body")
    elif change == "partial_controller":
        source = source.replace("public class PeopleController", "public partial class PeopleController")
    elif change == "custom_bad_request":
        source = source.replace("    [HttpPost]", "    private IActionResult BadRequest() { return Ok(); }\n    [HttpPost]")
    else:
        source = source.replace("JsonElement body", "UnknownBody body")
    comparisons, findings, gaps, _, _ = extracted(frontend("JSON.stringify({age: 18})"), source)
    assert comparisons[0].status == "unknown"
    assert not findings
    assert gaps


def required_ecosystem(tmp_path):
    api = repository(tmp_path / "api", {"PeopleController.cs": backend()})
    portal = repository(tmp_path / "portal", {"client.ts": frontend("JSON.stringify({age: 18})")})
    path = configuration(tmp_path, [api, portal], destinations=[{"url": "https://api.example.invalid", "repository_id": "api"}])
    return path, load_config(path)


def package_and_document(tmp_path):
    path, config = required_ecosystem(tmp_path)
    runner = CliRunner()
    for command in ("analyze", "plan"):
        result = runner.invoke(app, [command, "--config", str(path)])
        assert result.exit_code == 0, (result.output, result.exception)
    plan_path = config.output.parent / "plan.json"
    plan = json.loads(plan_path.read_text())
    plan["reviewed"] = True
    plan_path.write_text(json.dumps(plan))
    module_id = plan["modules"][0]["id"]
    result = runner.invoke(app, ["context", "--config", str(path), "--module", module_id])
    assert result.exit_code == 0, (result.output, result.exception)
    package = config.output.parent / "contexts" / module_id
    context = read_model(package / "context.json", Context)
    assert len(context.analysis.findings) == 1
    finding = context.analysis.findings[0]
    content = (FIXTURE / "document.md").read_text(encoding="utf-8")
    values = {
        "frontend_evidence": finding.evidence_ids[0], "backend_evidence": finding.evidence_ids[1], "finding_id": finding.id,
        "frontend_revision": next(item.revision for item in context.analysis.repositories if item.id == "portal"),
        "backend_revision": next(item.revision for item in context.analysis.repositories if item.id == "api"),
    }
    for key, value in values.items():
        content = content.replace("{{" + key + "}}", value)
    document = config.output.parent / "module.md"
    document.write_text(content, encoding="utf-8")
    return path, config, package, document


def test_finding_reaches_package_and_validated_document(tmp_path):
    path, config, package, document = package_and_document(tmp_path)
    assert validate_document(config, document, package) == []
    result = CliRunner().invoke(app, ["validate", str(document), "--config", str(path), "--context", str(package)])
    assert result.exit_code == 0, (result.output, result.exception)
    context = read_model(package / "context.json", Context)
    assert context.analysis.comparisons[0].status == "missing"
    assert context.analysis.findings[0].field == "name"
    assert context.analysis.calls[0].body.fields == ["age"]
    assert context.analysis.endpoints[0].request.fields == ["name"]
    assert "analysis.findings" in (package / "task.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("change", ["omit_finding", "omit_backend_citation", "alter_contract", "alter_explanation"])
def test_validation_protects_finding_and_both_evidence_sources(tmp_path, change):
    _, config, package, document = package_and_document(tmp_path)
    context_path = package / "context.json"
    data = json.loads(context_path.read_text())
    finding = data["analysis"]["findings"][0]
    if change in {"omit_finding", "omit_backend_citation"}:
        content = document.read_text(encoding="utf-8")
        content = content.replace(finding["id"] if change == "omit_finding" else f'[@{finding["evidence_ids"][1]}]', "")
        document.write_text(content, encoding="utf-8")
    else:
        if change == "alter_contract":
            # Referências internas continuam consistentes, mas divergem da fonte.
            data["analysis"]["endpoints"][0]["request"]["fields"] = ["email"]
            finding["field"] = "email"
        else:
            finding["explanation"] = "Afirmação adulterada."
        context_path.write_text(json.dumps(data))
    assert validate_document(config, document, package)


def test_unmapped_or_ambiguous_destinations_do_not_produce_findings(tmp_path):
    _, config = required_ecosystem(tmp_path)
    config.destinations.clear()
    unmapped = analyze(config)
    assert unmapped.findings == []
    config.destinations = [Destination(url="https://api.example.invalid", repository_id=repo) for repo in ("api", "portal")]
    ambiguous = analyze(config)
    assert ambiguous.findings == []
    assert ambiguous.coverage.candidates


@pytest.mark.parametrize("repo,file,source,code", [
    ("portal", "setup.ts", "JSON.stringify = customSerializer;", "javascript_serialization_unresolved"),
    ("api", "Program.cs", "builder.Services.AddControllers().AddNewtonsoftJson();", "dotnet_serialization_unresolved"),
])
def test_repository_serialization_changes_prevent_unsupported_findings(tmp_path, repo, file, source, code):
    _, config = required_ecosystem(tmp_path)
    root = next(item.path for item in config.repositories if item.id == repo)
    (root / file).write_text(source, encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-m", "custom serialization")
    result = analyze(config)
    assert result.findings == []
    assert result.comparisons[0].status == "unknown"
    assert any(gap.code == code for gap in result.coverage.gaps)
    assert any(gap.code == "serialization_environment_unresolved" for gap in result.coverage.gaps)


def test_known_guard_survives_unresolved_additional_conditional_rule():
    source = backend().replace("        return Ok();", '        if (RequiresEmail && !body.TryGetProperty("email", out var email)) return BadRequest();\n        return Ok();')
    source = source.replace("    [HttpPost]", "    public bool RequiresEmail { get; set; }\n    [HttpPost]")
    comparisons, findings, gaps, _, _ = extracted(frontend("JSON.stringify({ age: 18 })"), source)
    assert comparisons[0].status == "missing"
    assert [finding.field for finding in findings] == ["name"]
    assert gaps[0].code == "additional_backend_checks_unresolved"


def test_module_export_filters_unrelated_findings(tmp_path):
    _, config = required_ecosystem(tmp_path)
    api, portal = (next(item.path for item in config.repositories if item.id == name) for name in ("api", "portal"))
    source = backend()
    method = source[source.index("    [HttpPost]"):source.rfind("\n}")]
    other = method.replace("[HttpPost]", '[HttpPost("extra")]').replace(" Create(", " CreateExtra(")
    source = source[:source.rfind("\n}")] + "\n" + other + "\n}\n"
    (api / "PeopleController.cs").write_text(source, encoding="utf-8")
    (portal / "extra.ts").write_text(frontend("JSON.stringify({age: 18})").replace("/api/people", "/api/people/extra"), encoding="utf-8")
    for root in (api, portal):
        git(root, "add", "--all")
        git(root, "commit", "-m", "second flow")
    analysis = analyze(config)
    plan = create_plan(config)
    assert len(analysis.findings) == 2
    assert len(plan.modules) == 2
    selected = select_analysis(analysis, plan.modules[0])
    assert len(selected.findings) == len(selected.comparisons) == 1
    assert selected.findings[0].relation_id == plan.modules[0].relation_ids[0]
    assert selected.findings[0] in analysis.findings


def test_corrupt_finding_cannot_be_read_as_valid_analysis(tmp_path):
    from pydantic import ValidationError
    _, config = required_ecosystem(tmp_path)
    analysis = analyze(config)
    data = analysis.model_dump()
    data["findings"][0]["evidence_ids"] = [analysis.calls[0].evidence_id] * 2
    with pytest.raises(ValidationError, match="Achado sem provas"):
        Analysis.model_validate(data)
