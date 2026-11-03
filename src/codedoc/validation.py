"""Validação básica de Markdown e das evidências na revisão original."""

from hashlib import sha256
from pathlib import Path
import re

from pathspec import GitIgnoreSpec

from codedoc.config import Configuration, ScanError
from codedoc.comparison import compare_required_fields
from codedoc.models import Context, Coverage
from codedoc.parsing import Extractor
from codedoc.scanner import eligible_name, git
from codedoc.workflow import destination_routes, read_model


REQUIRED_SECTIONS = ("Objetivo", "Fluxo", "Evidências", "Lacunas", "Revisão")


def validate_document(config: Configuration, document: Path, package: Path) -> list[str]:
    context = read_model(package / "context.json", Context)
    coverage = read_model(package / "coverage.json", Coverage)
    if coverage != context.analysis.coverage:
        raise ScanError("Relatório de cobertura diverge do contexto.")
    try:
        markdown = document.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ScanError("Não foi possível ler o documento Markdown.") from None
    errors = []
    evidence = {item.id: item for item in context.analysis.evidence}
    citations = re.findall(r"\[@([^\]\s]+)\]", markdown)
    if markdown.count("[@") != len(citations):
        errors.append("Documento contém sintaxe de citação inválida.")
    if not citations:
        errors.append("Documento sem citações de evidência.")
    if any(citation not in evidence for citation in citations):
        errors.append("Documento contém referência de evidência desconhecida.")
    paragraphs = re.split(r"\n\s*\n", markdown)
    for finding in context.analysis.findings:
        if not any(finding.id in paragraph and all(f"[@{item}]" in paragraph for item in finding.evidence_ids)
                   for paragraph in paragraphs):
            errors.append("Achado ausente ou sem citações dos dois lados no mesmo parágrafo.")
    sections = {}
    current = None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    for section in REQUIRED_SECTIONS:
        if section not in sections or not "\n".join(sections[section]).strip():
            errors.append(f"Seção obrigatória ausente ou vazia: {section}.")
    for section in ("Objetivo", "Fluxo"):
        for paragraph in re.split(r"\n\s*\n", "\n".join(sections.get(section, []))):
            if paragraph.strip() and not re.search(r"\[@[^\]]+\]", paragraph):
                errors.append(f"Parágrafo sem citação em {section}.")
    for repo in context.analysis.repositories:
        if repo.revision not in markdown:
            errors.append("Documento não identifica todos os commits participantes.")
            break
    roots = {repo.id: repo.path for repo in config.repositories}
    exclusions = GitIgnoreSpec.from_lines(config.exclude)
    originals = {}
    for item in evidence.values():
        if item.repository_id not in roots:
            errors.append("Repositório de evidência indisponível na configuração.")
            continue
        if not eligible_name(item.file, exclusions):
            errors.append("Fonte bloqueada pela política de exclusões.")
            continue
        key = (item.repository_id, item.revision, item.file)
        if key not in originals:
            try:
                ignored = git(roots[item.repository_id], "check-ignore", "--no-index", "--stdin", "-z",
                              data=item.file.encode("utf-8") + b"\0", allowed=(0, 1))
                if ignored:
                    errors.append("Fonte bloqueada por .gitignore.")
                    continue
                raw = git(roots[item.repository_id], "show", f"{item.revision}:{item.file}")
                parsed = Extractor(item.repository_id, item.revision, item.file, raw).parse()
                originals[key] = (raw, {ev.id: ev for ev in parsed.evidence},
                                  {call.id: call for call in parsed.calls}, {endpoint.id: endpoint for endpoint in parsed.endpoints})
            except (ScanError, UnicodeError):
                errors.append("Fonte original indisponível ou ilegível.")
                continue
        raw, parsed_evidence, _, _ = originals[key]
        if parsed_evidence.get(item.id) != item or sha256(raw).hexdigest() != item.source_hash:
            errors.append("Evidência não corresponde ao símbolo, intervalo ou hash da fonte original.")
    symbols = {item.id: item for item in context.analysis.symbols}
    for items, position in ((context.analysis.calls, 2), (context.analysis.endpoints, 3)):
        for item in items:
            symbol = symbols[item.symbol_id]
            ev = evidence[symbol.evidence_id]
            original = originals.get((ev.repository_id, ev.revision, ev.file))
            if original is None or original[position].get(item.id) != item:
                errors.append("Contrato extraído diverge da implementação na revisão original.")
    calls = {item.id: item for item in context.analysis.calls}
    endpoints = {item.id: item for item in context.analysis.endpoints}
    for relation in context.analysis.relations:
        if relation.status != "confirmed":
            continue
        call, endpoint = calls[relation.call_id], endpoints[relation.endpoint_id]
        destinations = destination_routes(call.url, config) if call.url else []
        if (len(destinations) != 1 or destinations[0][0] != endpoint.repository_id
                or destinations[0][1].casefold() != endpoint.route.casefold() or call.method != endpoint.method):
            errors.append("Relação confirmada sem destino, método e rota correspondentes.")
    comparisons, findings, _ = compare_required_fields(context.analysis.calls, context.analysis.endpoints,
                                                      context.analysis.relations, context.analysis.symbols,
                                                      context.analysis.coverage.gaps)
    if comparisons != context.analysis.comparisons or findings != context.analysis.findings:
        errors.append("Achados ou comparações divergem das verificações determinísticas.")
    for source in context.sources:
        path = package / source.path
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(package.resolve()):
                raise OSError
            snippet = path.read_bytes()
            item = evidence[source.evidence_id]
            original = originals.get((item.repository_id, item.revision, item.file))
            expected = b"".join(original[0].splitlines(keepends=True)[item.start_line - 1:item.end_line]) if original else None
            if sha256(snippet).hexdigest() != source.snippet_hash or snippet != expected:
                errors.append("Trecho exportado diverge da evidência original.")
        except OSError:
            errors.append("Trecho exportado indisponível ou caminho inseguro.")
    return sorted(set(errors))
