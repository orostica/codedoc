"""Comparação determinística de presença de campos em relações confirmadas."""

from codedoc.models import Comparison, Finding, Gap
from codedoc.syntax import stable_id


def compare_required_fields(calls, endpoints, relations, symbols, serialization_gaps=()):
    calls = {item.id: item for item in calls}
    endpoints = {item.id: item for item in endpoints}
    symbols = {item.id: item for item in symbols}
    comparisons, findings, gaps = [], [], []
    for relation in relations:
        call, endpoint = calls[relation.call_id], endpoints[relation.endpoint_id]
        frontend, backend = symbols[call.symbol_id], symbols[endpoint.symbol_id]
        proof = [call.evidence_id, backend.evidence_id]
        result, reason, ids = "unknown", "relation_unconfirmed", []
        if relation.status != "confirmed":
            gaps.append(Gap(repository_id=frontend.repository_id, file=frontend.file,
                            code="required_fields_relation_unconfirmed", call_id=call.id))
        elif endpoint.request.status == "none":
            result, reason = "not_applicable", "no_proven_body_requirement"
        elif any((gap.repository_id == endpoint.repository_id and gap.code == "dotnet_serialization_unresolved")
                 or (gap.repository_id == call.repository_id and gap.code == "javascript_serialization_unresolved"
                     and call.body.reason == "inline_json_stringify_object") for gap in serialization_gaps):
            reason = "serialization_environment_unresolved"
            gaps.append(Gap(repository_id=frontend.repository_id, file=frontend.file, code=reason, call_id=call.id))
        elif endpoint.request.status != "known":
            reason = "backend_requirement_unresolved"
            gaps.append(Gap(repository_id=backend.repository_id, file=backend.file, code=reason, call_id=call.id))
        elif call.body.status != "object":
            reason = "request_body_unresolved"
            gaps.append(Gap(repository_id=frontend.repository_id, file=frontend.file, code=reason, call_id=call.id))
        else:
            missing = [field for field in endpoint.request.fields if field not in call.body.fields]
            result = "missing" if missing else "no_omission"
            reason = "proven_required_keys_omitted" if missing else "proven_required_keys_present"
            for field in missing:
                finding = Finding(id=stable_id("finding-", relation.id, field), relation_id=relation.id,
                                  field=field, evidence_ids=proof,
                                  explanation=f"O corpo JSON enviado omite a chave {field!r}; a guarda inicial do backend retorna BadRequest quando essa chave está ausente.")
                findings.append(finding)
                ids.append(finding.id)
        if endpoint.request.reason == "additional_checks_unresolved":
            gaps.append(Gap(repository_id=backend.repository_id, file=backend.file,
                            code="additional_backend_checks_unresolved", call_id=call.id))
        comparisons.append(Comparison(relation_id=relation.id, status=result, reason=reason, finding_ids=ids))
    return comparisons, findings, gaps
