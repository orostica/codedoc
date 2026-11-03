"""Análise, revisão explícita e exportação do primeiro fluxo documentável."""

from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

from pydantic import ValidationError

from codedoc.config import Configuration, ScanError
from codedoc.models import Analysis, Context, Coverage, Gap, Module, Plan, Relation, Source
from codedoc.parsing import Extractor, stable_id
from codedoc.scanner import git, revision, scan, write_inventory


MAX_SOURCE_BYTES = 2_000_000


def digest(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def config_hash(config: Configuration) -> str:
    return digest(config.model_dump(mode="json"))


def analysis_hash(analysis: Analysis) -> str:
    return digest(analysis.model_dump(mode="json", exclude={"analysis_id"}))


def read_model(path: Path, model):
    try:
        return model.model_validate_json(path.read_bytes())
    except (OSError, ValueError, ValidationError):
        raise ScanError("Artefato ausente ou inválido. Refaça a análise ou confira o arquivo informado.") from None


def read_analysis(config: Configuration) -> Analysis:
    analysis = read_model(config.output.parent / "analysis.json", Analysis)
    if analysis.analysis_id != analysis_hash(analysis) or analysis.config_hash != config_hash(config):
        raise ScanError("Análise alterada ou configuração incompatível. Execute analyze novamente.")
    return analysis


def ensure_output(config: Configuration, path: Path):
    if any(path.resolve().is_relative_to(repo.path) for repo in config.repositories):
        raise ScanError("Artefatos devem ficar fora dos repositórios analisados.")


def check_revisions(config: Configuration, analysis: Analysis):
    expected = {repo.id: repo.revision for repo in analysis.repositories}
    if set(expected) != {repo.id for repo in config.repositories}:
        raise ScanError("Repositórios incompatíveis. Execute analyze novamente.")
    for repo in config.repositories:
        if revision(repo) != expected[repo.id]:
            raise ScanError("Revisão mudou após a análise. Execute analyze novamente.")


def coverage(calls, relations, gaps) -> Coverage:
    return Coverage(
        confirmed=[rel.id for rel in relations if rel.status == "confirmed"],
        candidates=[rel.id for rel in relations if rel.status == "candidate"],
        unresolved_calls=[call.id for call in calls if not any(rel.call_id == call.id and rel.status == "confirmed" for rel in relations)],
        gaps=gaps,
    )


def destination_routes(url: str, config: Configuration) -> list[tuple[str, str]]:
    parsed = urlsplit(url)
    matches = []
    for destination in config.destinations:
        base = urlsplit(destination.url)
        base_path = base.path.rstrip("/")
        if (parsed.scheme.lower(), parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)) != (
            base.scheme.lower(), base.hostname, base.port or (443 if base.scheme == "https" else 80)
        ):
            continue
        if parsed.path != base_path and not parsed.path.startswith(base_path + "/"):
            continue
        matches.append((len(base_path), destination.repository_id, "/" + parsed.path[len(base_path):].strip("/")))
    longest = max((item[0] for item in matches), default=-1)
    return sorted({(repo, route) for length, repo, route in matches if length == longest})


def analyze(config: Configuration) -> Analysis:
    if config.output.name in {"analysis.json", "plan.json"}:
        raise ScanError("Reserve analysis.json e plan.json para os artefatos; use inventory.json como saída do inventário.")
    inventory = scan(config)
    symbols, evidence, dependencies, endpoints, calls, gaps = [], [], [], [], [], []
    roots = {repo.id: repo.path for repo in config.repositories}
    for repo in inventory["repositories"]:
        for file in repo["files"]:
            if Path(file).suffix.lower() not in {".cs", ".ts", ".tsx", ".js", ".jsx"}:
                continue
            raw = git(roots[repo["id"]], "show", f"{repo['revision']}:{file}")
            try:
                raw.decode("utf-8")
            except UnicodeError:
                gaps.append(Gap(repository_id=repo["id"], file=file, code="source_not_utf8"))
                continue
            if len(raw) > MAX_SOURCE_BYTES:
                gaps.append(Gap(repository_id=repo["id"], file=file, code="source_too_large"))
                continue
            extracted = Extractor(repo["id"], repo["revision"], file, raw).parse()
            symbols.extend(extracted.symbols)
            evidence.extend(extracted.evidence)
            dependencies.extend(extracted.dependencies)
            endpoints.extend(extracted.endpoints)
            calls.extend(extracted.calls)
            gaps.extend(extracted.gaps)
    relations = []
    for call in calls:
        if call.url is None or call.method is None:
            continue
        destinations = destination_routes(call.url, config)
        matching = [endpoint for endpoint in endpoints
                    if endpoint.method == call.method and any(
                        repo == endpoint.repository_id and route.casefold() == endpoint.route.casefold()
                        for repo, route in destinations)]
        confirmed = len(destinations) == 1 and len(matching) == 1
        for endpoint in matching:
            relations.append(Relation(id=stable_id("rel-", call.id, endpoint.id), call_id=call.id,
                                      endpoint_id=endpoint.id, status="confirmed" if confirmed else "candidate",
                                      reason="destination_method_route" if confirmed else "ambiguous_destination_or_endpoint"))
        if not confirmed:
            gaps.append(Gap(repository_id=call.repository_id,
                            file=next(item.file for item in symbols if item.id == call.symbol_id),
                            code="destination_unmapped" if not destinations else "endpoint_unresolved_or_ambiguous", call_id=call.id))
    analysis = Analysis(analysis_id="pending", config_hash=config_hash(config),
                        repositories=[{"id": repo["id"], "revision": repo["revision"]} for repo in inventory["repositories"]],
                        symbols=symbols, evidence=evidence, dependencies=dependencies,
                        calls=calls, endpoints=endpoints, relations=relations,
                        coverage=coverage(calls, relations, gaps))
    analysis.analysis_id = analysis_hash(analysis)
    check_revisions(config, analysis)
    target = config.output.parent / "analysis.json"
    ensure_output(config, target)
    write_inventory(config.output, inventory)
    write_inventory(target, analysis.model_dump(mode="json"))
    return analysis


def create_plan(config: Configuration) -> Plan:
    analysis = read_analysis(config)
    check_revisions(config, analysis)
    target = config.output.parent / "plan.json"
    ensure_output(config, target)
    if target.exists():
        raise ScanError("Já existe plan.json. Preserve sua revisão; mova o plano anterior antes de gerar outro.")
    modules = []
    endpoints = {item.id: item for item in analysis.endpoints}
    for relation in analysis.relations:
        if relation.status != "confirmed":
            continue
        endpoint = endpoints[relation.endpoint_id]
        slug = re.sub(r"[^a-z0-9]+", "-", endpoint.route.lower()).strip("-") or "root"
        module_id = f"{endpoint.method.lower()}-{slug}-{relation.id[-8:]}"
        modules.append(Module(id=module_id, title=f"{endpoint.method} {endpoint.route}", relation_ids=[relation.id]))
    if not modules:
        raise ScanError("Nenhum fluxo confirmado para planejar. Confira a cobertura e os mapeamentos de destino.")
    plan = Plan(analysis_id=analysis.analysis_id, modules=modules)
    write_inventory(target, plan.model_dump(mode="json"))
    return plan


def select_analysis(analysis: Analysis, module: Module) -> Analysis:
    relations = [item for item in analysis.relations if item.id in module.relation_ids]
    if len({item.id for item in relations}) != len(module.relation_ids):
        raise ScanError("Plano referencia relações desconhecidas ou duplicadas.")
    call_ids, endpoint_ids = {item.call_id for item in relations}, {item.endpoint_id for item in relations}
    calls = [item for item in analysis.calls if item.id in call_ids]
    endpoints = [item for item in analysis.endpoints if item.id in endpoint_ids]
    symbol_ids = {item.symbol_id for item in calls + endpoints}
    evidence_ids = {item.evidence_id for item in calls}
    for endpoint in endpoints:
        evidence_ids.update(endpoint.evidence_ids)
    symbol_ids.update(item.symbol for item in analysis.evidence if item.id in evidence_ids)
    files = {(item.repository_id, item.file) for item in analysis.symbols if item.id in symbol_ids}
    # Imports básicos são evidências do módulo de arquivo, sem presumir resolução semântica.
    module_symbols = {item.id for item in analysis.symbols if item.kind == "module" and (item.repository_id, item.file) in files}
    symbol_ids.update(module_symbols)
    symbols = [item for item in analysis.symbols if item.id in symbol_ids]
    evidence_ids.update(item.evidence_id for item in symbols)
    evidence = [item for item in analysis.evidence if item.id in evidence_ids]
    dependencies = [item for item in analysis.dependencies if item.from_symbol in symbol_ids]
    # Cobertura global de lacunas acompanha o módulo para evitar sugerir completude.
    return Analysis(analysis_id=analysis.analysis_id, config_hash=analysis.config_hash,
                    repositories=analysis.repositories, symbols=symbols, evidence=evidence,
                    dependencies=dependencies, calls=calls, endpoints=endpoints, relations=relations,
                    coverage=coverage(calls, relations, analysis.coverage.gaps))


TASK = """# Tarefa: documentar módulo

Use apenas context.json, coverage.json e os trechos de sources/ deste pacote.
A CLI não invoca agentes. Entregue este pacote ao agente de sua preferência.

Produza Markdown com as seções: ## Objetivo, ## Fluxo, ## Evidências,
## Lacunas e ## Revisão. Identifique os commits dos repositórios participantes.
Explique responsabilidades, pontos de entrada e dependências sustentadas pelas fontes.
Cada afirmação sobre comportamento ou contrato deve citar [@ev-IDENTIFICADOR],
substituindo pelo ID exato da evidência. Cada parágrafo de Objetivo e Fluxo
deve conter uma citação. Diferencie fatos de inferências e preserve lacunas.
Imports são dependências sintáticas, sem garantia de resolução semântica.
Não conclua divergências de contrato: este recorte apenas relaciona chamadas e endpoints.
Restrição de interface não comprova regra aplicada no servidor.
Registre revisão humana pendente; referências válidas não aprovam o conteúdo.
Preserve o código-fonte. A validação será executada separadamente.
"""


def export_context(config: Configuration, module_id: str) -> Path:
    analysis = read_analysis(config)
    check_revisions(config, analysis)
    plan = read_model(config.output.parent / "plan.json", Plan)
    if not plan.reviewed or plan.analysis_id != analysis.analysis_id:
        raise ScanError("Revise plan.json e marque reviewed como true para a análise atual.")
    if len({item.id for item in plan.modules}) != len(plan.modules):
        raise ScanError("Plano contém IDs de módulo duplicados.")
    module = next((item for item in plan.modules if item.id == module_id), None)
    if module is None:
        raise ScanError("Módulo desconhecido. Consulte plan.json.")
    selected = select_analysis(analysis, module)
    target = config.output.parent / "contexts" / module.id
    ensure_output(config, target)
    if target.exists():
        raise ScanError("Pacote já existe. Preserve o pacote anterior antes de exportar novamente.")
    repositories = {item.id: item for item in config.repositories}
    inventory = scan(config)
    eligible = {item["id"]: set(item["files"]) for item in inventory["repositories"]}
    contents, sources = {}, []
    for evidence in selected.evidence:
        if evidence.file not in eligible[evidence.repository_id]:
            raise ScanError("Fonte excluída ou indisponível. Execute analyze novamente.")
        raw = git(repositories[evidence.repository_id].path, "show", f"{evidence.revision}:{evidence.file}")
        lines = raw.splitlines(keepends=True)
        if sha256(raw).hexdigest() != evidence.source_hash or evidence.end_line > len(lines):
            raise ScanError("Fonte incompatível com a evidência. Execute analyze novamente.")
        snippet = b"".join(lines[evidence.start_line - 1:evidence.end_line])
        path = f"sources/{evidence.id}.txt"
        contents[path] = snippet
        sources.append(Source(evidence_id=evidence.id, path=path, snippet_hash=sha256(snippet).hexdigest()))
    context = Context(module=module, analysis=selected, sources=sources)
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".context-", dir=target.parent))
        (temporary / "sources").mkdir()
        for path, content in contents.items():
            (temporary / path).write_bytes(content)
        write_inventory(temporary / "context.json", context.model_dump(mode="json"))
        write_inventory(temporary / "coverage.json", selected.coverage.model_dump(mode="json"))
        (temporary / "task.md").write_text(TASK, encoding="utf-8")
        check_revisions(config, analysis)
        temporary.rename(target)
        temporary = None
    except OSError:
        raise ScanError("Falha ao exportar o pacote. Confira permissões e caminhos de saída.") from None
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
    return target
