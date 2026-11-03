"""Contratos executáveis: análise/contexto 1.1, plano/cobertura 1.0."""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepositoryRevision(Model):
    id: str
    revision: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")


class Location(Model):
    repository_id: str
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @field_validator("file")
    @classmethod
    def relative_file(cls, value: str) -> str:
        if (not value or PurePosixPath(value).is_absolute() or "\\" in value
                or ":" in value or ".." in PurePosixPath(value).parts):
            raise ValueError("Caminho relativo inválido")
        return value

    @model_validator(mode="after")
    def ordered_lines(self):
        if self.end_line < self.start_line:
            raise ValueError("Intervalo inválido")
        return self


class Evidence(Location):
    id: str = Field(pattern=r"^ev-[a-f0-9]{24}$")
    revision: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    symbol: str


class Symbol(Location):
    id: str
    name: str
    kind: Literal["module", "class", "method", "function"]
    evidence_id: str


class Dependency(Model):
    from_symbol: str
    target: str
    kind: Literal["import", "using"]
    evidence_id: str


class RequestBody(Model):
    status: Literal["object", "unknown", "none"]
    fields: list[str] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def shape(self):
        if len(set(self.fields)) != len(self.fields) or (self.status != "object" and self.fields):
            raise ValueError("Formato JSON inconsistente")
        return self


class BodyRequirement(Model):
    status: Literal["known", "unknown", "none"]
    fields: list[str] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def shape(self):
        if (len(set(self.fields)) != len(self.fields)
                or (self.status == "known") != bool(self.fields)):
            raise ValueError("Obrigatoriedade inconsistente")
        return self


class Endpoint(Model):
    id: str
    symbol_id: str
    repository_id: str
    method: str
    route: str
    evidence_ids: list[str]
    request: BodyRequirement


class Call(Model):
    id: str
    symbol_id: str
    repository_id: str
    method: str | None
    url: str | None
    evidence_id: str
    body: RequestBody


class Relation(Model):
    id: str
    call_id: str
    endpoint_id: str
    status: Literal["confirmed", "candidate"]
    reason: str


class Gap(Model):
    repository_id: str
    file: str
    code: str
    call_id: str | None = None


class Finding(Model):
    id: str = Field(pattern=r"^finding-[a-f0-9]{24}$")
    code: Literal["missing_required_field"] = "missing_required_field"
    relation_id: str
    field: str
    explanation: str
    evidence_ids: list[str] = Field(min_length=2)


class Comparison(Model):
    relation_id: str
    status: Literal["missing", "no_omission", "unknown", "not_applicable"]
    reason: str
    finding_ids: list[str] = Field(default_factory=list)


class Coverage(Model):
    schema_version: Literal["1.0"] = "1.0"
    confirmed: list[str]
    candidates: list[str]
    unresolved_calls: list[str]
    gaps: list[Gap]


class Analysis(Model):
    schema_version: Literal["1.1"] = "1.1"
    analysis_id: str
    config_hash: str
    repositories: list[RepositoryRevision]
    symbols: list[Symbol]
    evidence: list[Evidence]
    dependencies: list[Dependency]
    endpoints: list[Endpoint]
    calls: list[Call]
    relations: list[Relation]
    findings: list[Finding]
    comparisons: list[Comparison]
    coverage: Coverage

    @model_validator(mode="after")
    def references(self):
        groups = (self.repositories, self.symbols, self.evidence, self.calls, self.endpoints, self.relations, self.findings)
        for group in groups:
            if len({item.id for item in group}) != len(group):
                raise ValueError("Identificador duplicado")
        repos = {item.id: item.revision for item in self.repositories}
        symbols = {item.id: item for item in self.symbols}
        evidence = {item.id: item for item in self.evidence}
        calls = {item.id: item for item in self.calls}
        endpoints = {item.id: item for item in self.endpoints}
        relations = {item.id: item for item in self.relations}
        for item in self.evidence:
            if item.symbol not in symbols or repos.get(item.repository_id) != item.revision:
                raise ValueError("Evidência sem origem")
        for item in self.symbols:
            ev = evidence.get(item.evidence_id)
            if ev is None or ev.symbol != item.id or any(
                getattr(ev, field) != getattr(item, field)
                for field in ("repository_id", "file", "start_line", "end_line")
            ):
                raise ValueError("Símbolo sem evidência correspondente")
        for item in self.calls:
            if item.symbol_id not in symbols or item.evidence_id not in evidence or item.repository_id not in repos:
                raise ValueError("Chamada sem origem")
        for item in self.endpoints:
            if item.symbol_id not in symbols or item.repository_id not in repos or not item.evidence_ids or any(ev not in evidence for ev in item.evidence_ids):
                raise ValueError("Endpoint sem origem")
        for item in self.dependencies:
            if item.from_symbol not in symbols or item.evidence_id not in evidence:
                raise ValueError("Dependência sem origem")
        for item in self.relations:
            if item.call_id not in calls or item.endpoint_id not in endpoints:
                raise ValueError("Relação sem origem")
        for item in self.findings:
            rel = relations.get(item.relation_id)
            if rel is None or rel.status != "confirmed":
                raise ValueError("Achado exige relação confirmada")
            call, endpoint = calls[rel.call_id], endpoints[rel.endpoint_id]
            if (call.body.status != "object" or endpoint.request.status != "known"
                    or item.field not in endpoint.request.fields or item.field in call.body.fields
                    or set(item.evidence_ids) != {call.evidence_id, symbols[endpoint.symbol_id].evidence_id}):
                raise ValueError("Achado sem provas correspondentes")
        if {item.relation_id for item in self.comparisons} != set(relations) or len(self.comparisons) != len(relations):
            raise ValueError("Comparações incompletas ou duplicadas")
        for item in self.comparisons:
            linked = [finding for finding in self.findings if finding.relation_id == item.relation_id]
            if set(item.finding_ids) != {finding.id for finding in linked} or len(set(item.finding_ids)) != len(item.finding_ids):
                raise ValueError("Comparação referencia achados inconsistentes")
            rel = relations[item.relation_id]
            call, endpoint = calls[rel.call_id], endpoints[rel.endpoint_id]
            missing = set(endpoint.request.fields) - set(call.body.fields)
            serialization_unknown = any(
                (gap.repository_id == endpoint.repository_id and gap.code == "dotnet_serialization_unresolved")
                or (gap.repository_id == call.repository_id and gap.code == "javascript_serialization_unresolved"
                    and call.body.reason == "inline_json_stringify_object") for gap in self.coverage.gaps
            )
            expected = ("unknown" if rel.status != "confirmed" else
                        "not_applicable" if endpoint.request.status == "none" else
                        "unknown" if serialization_unknown else
                        "unknown" if endpoint.request.status != "known" or call.body.status != "object" else
                        "missing" if missing else "no_omission")
            if item.status != expected or {finding.field for finding in linked} != (missing if expected == "missing" else set()):
                raise ValueError("Resultado de comparação inconsistente")
        confirmed = [item.id for item in self.relations if item.status == "confirmed"]
        candidates = [item.id for item in self.relations if item.status == "candidate"]
        unresolved = [item.id for item in self.calls if not any(rel.call_id == item.id and rel.status == "confirmed" for rel in self.relations)]
        if (self.coverage.confirmed != confirmed or self.coverage.candidates != candidates
                or self.coverage.unresolved_calls != unresolved):
            raise ValueError("Cobertura inconsistente")
        return self


class Module(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1)
    relation_ids: list[str] = Field(min_length=1)


class Plan(Model):
    schema_version: Literal["1.0"] = "1.0"
    analysis_id: str
    reviewed: bool = False
    modules: list[Module]


class Source(Model):
    evidence_id: str
    path: str = Field(pattern=r"^sources/ev-[a-f0-9]{24}\.txt$")
    snippet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class Context(Model):
    schema_version: Literal["1.1"] = "1.1"
    module: Module
    analysis: Analysis
    sources: list[Source]

    @model_validator(mode="after")
    def references(self):
        if set(self.module.relation_ids) != {item.id for item in self.analysis.relations}:
            raise ValueError("Módulo inconsistente")
        if len({item.evidence_id for item in self.sources}) != len(self.sources):
            raise ValueError("Fonte duplicada")
        if {item.evidence_id for item in self.sources} != {item.id for item in self.analysis.evidence}:
            raise ValueError("Fontes incompletas")
        if any(item.path != f"sources/{item.evidence_id}.txt" for item in self.sources):
            raise ValueError("Nome de fonte inconsistente")
        return self
