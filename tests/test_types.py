import json
from pathlib import Path

import pytest

from codedoc.models import Analysis, Context, Relation
from codedoc.parsing import Extractor
from codedoc.type_comparison import compare_types
from codedoc.validation import validate_document
from codedoc.workflow import analyze, create_plan, export_context, read_model, select_analysis
from codedoc.config import load_config
from test_scan import configuration, git, repository


FIXTURE = Path(__file__).parent / "fixtures/types"
CASES = json.loads((FIXTURE / "cases.json").read_text())


def server(expression, parameters="", verb="HttpGet"):
    return f'''using Microsoft.AspNetCore.Mvc;
using System.Text.Json;
[ApiController]
[Route("api/items")]
public class ItemsController : ControllerBase {{
    [{verb}]
    public IActionResult Load({parameters}) {{ return {expression}; }}
}}'''


def client(body=None, query="", operation="trim", response=False):
    options = '' if body is None else ', {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({value: ' + body + '})}'
    fetch = 'fetch("https://api.example.invalid/api/items' + query + '"' + options + ')'
    if response:
        return f'export async function load() {{ const response = await {fetch}; const data = await response.json(); return data.value.{operation}(); }}'
    return f'export async function load() {{ return {fetch}; }}'


def response_server(value):
    if value == "dynamic":
        return server("Ok(GetData())")
    payload = {} if value == "missing" else {"value": json.loads(value)}
    return server('Content(' + json.dumps(json.dumps(payload)) + ', "application/json")')


def compare(frontend, backend, status="confirmed"):
    portal = Extractor("portal", "a" * 40, "client.ts", frontend.encode()).parse()
    api = Extractor("api", "b" * 40, "ItemsController.cs", backend.encode()).parse()
    assert len(portal.calls) == len(api.endpoints) == 1
    relation = Relation(id="relation", call_id=portal.calls[0].id, endpoint_id=api.endpoints[0].id,
                        status=status, reason="test")
    comparisons, findings, gaps = compare_types(portal.calls, api.endpoints, [relation], portal.symbols + api.symbols,
                                               portal.gaps + api.gaps)
    return comparisons, findings, gaps


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_predefined_type_matrix(case):
    location = case["location"]
    if location == "body":
        frontend = client(body=case["value"])
        backend = server(f'Ok(body.GetProperty("value").{case["operation"]}())', '[FromBody] JsonElement body', "HttpPost")
    elif location == "response":
        frontend = client(response=True, operation=case["operation"])
        backend = response_server(case["value"])
    else:
        frontend = client(query="?age=" + case["value"])
        backend = server("Ok(int.Parse(age))", "[FromQuery] string age")
    comparisons, findings, gaps = compare(frontend, backend)
    relevant = [row for row in comparisons if row.location == location]
    assert relevant and {row.status for row in relevant} == {case["expected"]}
    assert bool([finding for finding in findings if finding.field.startswith(location + ":")]) == (case["expected"] == "incompatible")
    assert all(len(set(row.evidence_ids)) == 2 for row in comparisons)
    if case["expected"] == "unknown":
        assert any(gap.code == location + "_type_unresolved" for gap in gaps)


def test_candidate_types_are_only_gaps():
    rows, findings, gaps = compare(client(response=True), response_server("18"), "candidate")
    assert not findings and gaps
    assert all(row.status == "unknown" for row in rows)


@pytest.mark.parametrize("change", [
    lambda source: source.replace('data.value.trim()', '(data as {value: string}).value.trim()'),
    lambda source: source.replace('const data', 'let data'),
    lambda source: source.replace('return data', 'data.value = "ok"; return data'),
    lambda source: source.replace('data.value.trim()', 'data?.value?.trim()'),
    lambda source: source.replace('return data', 'if (flag) return "ok"; return data'),
])
def test_dynamic_response_or_assertion_does_not_prove_incompatibility(change):
    rows, findings, _ = compare(change(client(response=True)), response_server("18"))
    assert not findings
    assert all(row.status == "unknown" for row in rows)


def test_declared_frontend_type_does_not_replace_constructed_body():
    frontend = 'type Input = {value: string};\n' + client(body="18")
    backend = server('Ok(body.GetProperty("value").GetString())', '[FromBody] JsonElement body', "HttpPost")
    rows, findings, _ = compare(frontend, backend)
    assert next(row for row in rows if row.location == "body").actual == "int32"
    assert len(findings) == 1


def test_backend_declared_return_and_contract_do_not_replace_content():
    backend = response_server("18").replace('[HttpGet]', '[HttpGet]\n[ProducesResponseType(typeof(string), 200)]')
    rows, findings, _ = compare(client(response=True), backend)
    assert rows[0].actual == "int32" and findings


@pytest.mark.parametrize("expression", [
    'Ok(flag ? body.GetProperty("value").GetString() : "ok")',
    'Ok(() => body.GetProperty("value").GetString())',
])
def test_conditional_or_deferred_backend_access_is_unknown(expression):
    rows, findings, _ = compare(client(body="18"), server(expression, '[FromBody] JsonElement body', "HttpPost"))
    assert not findings
    assert all(row.status == "unknown" for row in rows)


def test_literal_request_json_and_nested_response_paths():
    frontend = client(body="18").replace('JSON.stringify({value: 18})', "'{\"value\": 18}'")
    rows, findings, _ = compare(frontend, server('Ok(body.GetProperty("value").GetString())',
                                               '[FromBody] JsonElement body', "HttpPost"))
    assert any(row.status == "incompatible" and row.location == "body" for row in rows)
    assert findings
    frontend = client(response=True).replace("data.value.trim()", "data.value.name.trim()")
    rows, findings, _ = compare(frontend, response_server('{"name": "Ana"}'))
    assert not findings and rows[0].status == "compatible" and rows[0].path == "$/value/name"


@pytest.mark.parametrize("value", ['{"value": 1, "value": "Ana"}', 'NaN', 'dynamic'])
def test_unresolved_response_json_does_not_produce_findings(value):
    backend = server('Content(' + json.dumps(value) + ', "application/json")')
    rows, findings, gaps = compare(client(response=True), backend)
    assert not findings and gaps
    assert all(row.status == "unknown" for row in rows)


def test_optional_invocation_and_array_length_are_not_assumed_missing():
    frontend = client(response=True).replace("data.value.trim()", "data.value.trim?.()")
    rows, findings, _ = compare(frontend, response_server("18"))
    assert not findings and rows[0].status == "unknown"
    frontend = client(response=True).replace("data.value.trim()", "data.value.length.toFixed()")
    rows, findings, _ = compare(frontend, response_server("[]"))
    assert not findings and rows[0].status == "unknown"


def test_query_numeric_text_normalization():
    for query in ("?age=00000000000000018", "?age=%2B18", "?age=%20-18%20", "?age=-2147483648"):
        rows, findings, _ = compare(client(query=query), server("Ok(int.Parse(age))", "[FromQuery] string age"))
        assert not findings
        assert next(row.status for row in rows if row.location == "query") == "compatible"


def package_and_document(tmp_path):
    roots = [repository(tmp_path / "api", {"ItemsController.cs": response_server("18")}),
             repository(tmp_path / "portal", {"client.ts": client(response=True)})]
    path = configuration(tmp_path, roots, destinations=[{"url": "https://api.example.invalid", "repository_id": "api"}])
    config = load_config(path)
    analysis = analyze(config)
    plan = create_plan(config)
    plan.reviewed = True
    (config.output.parent / "plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    package = export_context(config, plan.modules[0].id)
    context = read_model(package / "context.json", Context)
    finding = context.analysis.findings[0]
    values = {"finding_id": finding.id, "explanation": finding.explanation,
              "frontend_evidence": finding.evidence_ids[0], "backend_evidence": finding.evidence_ids[1]}
    for repo in context.analysis.repositories:
        values[repo.id + "_revision"] = repo.revision
    content = (FIXTURE / "document.md").read_text(encoding="utf-8")
    for key, value in values.items():
        content = content.replace("{{" + key + "}}", value)
    document = config.output.parent / "module.md"
    document.write_text(content, encoding="utf-8")
    return config, package, document, analysis, plan


def test_type_finding_export_document_and_module_selection(tmp_path):
    config, package, document, analysis, plan = package_and_document(tmp_path)
    assert validate_document(config, document, package) == []
    selected = select_analysis(analysis, plan.modules[0])
    assert selected.type_comparisons == analysis.type_comparisons
    assert len(selected.findings) == 1
    assert selected.findings[0].code == "incompatible_type"


@pytest.mark.parametrize("change", ["citation", "finding", "contract", "explanation"])
def test_type_finding_validation_rejects_tampering(tmp_path, change):
    config, package, document, _, _ = package_and_document(tmp_path)
    context_path = package / "context.json"
    data = json.loads(context_path.read_text())
    finding = data["analysis"]["findings"][0]
    if change in {"citation", "finding"}:
        token = finding["id"] if change == "finding" else "[@" + finding["evidence_ids"][1] + "]"
        document.write_text(document.read_text(encoding="utf-8").replace(token, ""), encoding="utf-8")
    elif change == "explanation":
        # O modelo também rejeita explicações sem correspondência determinística.
        finding["explanation"] = "alterada"
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Analysis.model_validate(data["analysis"])
        return
    else:
        # Contrato e comparação adulterados de modo consistente ainda divergem da fonte Git.
        for fact in data["analysis"]["endpoints"][0]["types"]["facts"]:
            if fact["path"] == "$/value":
                fact["kind"] = "boolean"
        analysis = data["analysis"]
        from codedoc.models import Call, Endpoint, Symbol
        rows, findings, _ = compare_types([Call.model_validate(x) for x in analysis["calls"]],
                                          [Endpoint.model_validate(x) for x in analysis["endpoints"]],
                                          [Relation.model_validate(x) for x in analysis["relations"]],
                                          [Symbol.model_validate(x) for x in analysis["symbols"]])
        analysis["type_comparisons"] = [row.model_dump() for row in rows]
        analysis["findings"] = [item.model_dump() for item in findings]
        context_path.write_text(json.dumps(data), encoding="utf-8")
    assert validate_document(config, document, package)


@pytest.mark.parametrize("repo,file,source", [
    ("api", "Program.cs", "builder.Services.AddControllers().AddNewtonsoftJson();"),
    ("portal", "setup.ts", "JSON.stringify = customSerializer;"),
])
def test_serialization_risk_in_other_file_prevents_type_findings(tmp_path, repo, file, source):
    config, _, _, _, _ = package_and_document(tmp_path)
    root = next(item.path for item in config.repositories if item.id == repo)
    (root / file).write_text(source, encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-m", "serialization risk")
    analysis = analyze(config)
    assert not analysis.findings
    assert all(row.status == "unknown" for row in analysis.type_comparisons)


def test_multiple_modules_keep_only_their_type_findings(tmp_path):
    config, _, _, _, _ = package_and_document(tmp_path)
    for repo in config.repositories:
        if repo.id == "api":
            source = response_server("18").replace("ItemsController", "OtherController").replace('api/items', 'api/other')
            filename = "OtherController.cs"
        else:
            source = client(response=True).replace("api/items", "api/other")
            filename = "other.ts"
        (repo.path / filename).write_text(source, encoding="utf-8")
        git(repo.path, "add", "--all")
        git(repo.path, "commit", "-m", "second module")
    analysis = analyze(config)
    assert len(analysis.findings) == 2
    from codedoc.models import Module
    selected = select_analysis(analysis, Module(id="one", title="One", relation_ids=[analysis.relations[0].id]))
    assert len(selected.type_comparisons) == len(selected.findings) == 1
    assert selected.findings[0].relation_id == analysis.relations[0].id
