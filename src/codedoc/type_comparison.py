"""Comparação de tipos observados; declarações não substituem operações executadas."""

from codedoc.models import Finding, Gap, TypeComparison
from codedoc.syntax import stable_id


def compare_types(calls, endpoints, relations, symbols, serialization_gaps=()):
    calls = {item.id: item for item in calls}
    endpoints = {item.id: item for item in endpoints}
    symbols = {item.id: item for item in symbols}
    comparisons, findings, gaps = [], [], []
    for relation in relations:
        call, endpoint = calls[relation.call_id], endpoints[relation.endpoint_id]
        frontend, backend = symbols[call.symbol_id], symbols[endpoint.symbol_id]
        proof = [call.evidence_id, backend.evidence_id]
        environment_unknown = any(
            (gap.repository_id == endpoint.repository_id and gap.code == "dotnet_serialization_unresolved") or
            (gap.repository_id == call.repository_id and gap.code == "javascript_serialization_unresolved")
            for gap in serialization_gaps)
        for location in ("body", "query", "response"):
            actual_contract, expected_contract = ((endpoint.types, call.types) if location == "response"
                                                  else (call.types, endpoint.types))
            actuals = {fact.path: fact.kind for fact in actual_contract.facts if fact.location == location}
            expected = [fact for fact in expected_contract.facts if fact.location == location]
            unresolved = location in call.types.unresolved or location in endpoint.types.unresolved
            def observed(path):
                if path in actuals:
                    return actuals[path]
                if location in {"body", "response"}:
                    parts = path.split("/")
                    for index in range(1, len(parts)):
                        parent = "/".join(parts[:index])
                        child = "/".join(parts[:index + 1])
                        if child not in actuals and actuals.get(parent) == "object":
                            if parts[index] in {"constructor", "__proto__", "toString", "valueOf", "hasOwnProperty"}:
                                return "unknown"
                            return "absent"
                return "unknown"
            rows = [(fact.path, observed(fact.path), fact.kind) for fact in expected]
            if unresolved or (location == "response" and not expected):
                rows.append(("*", "unknown", "unknown"))
            for path, actual, wanted in rows:
                status, reason = "unknown", "type_or_access_unresolved"
                if relation.status != "confirmed":
                    reason = "relation_unconfirmed"
                elif environment_unknown:
                    reason = "serialization_environment_unresolved"
                elif "unknown" not in (actual, wanted):
                    compatible = (actual == wanted or
                                  (wanted == "number" and actual in {"int32", "integer"}) or
                                  (wanted == "integer" and actual == "int32") or
                                  (wanted == "string" and actual == "null" and location == "body"))
                    status = "compatible" if compatible else "incompatible"
                    reason = "observed_types_match" if compatible else "observed_types_conflict"
                explanation = (f"{location} {path!r}: a implementação fornece {actual}; "
                               f"a operação consumidora exige {wanted}. Resultado: {status} ({reason}).")
                finding_id = None
                if status == "incompatible":
                    finding_id = stable_id("finding-", relation.id, "type", location, path, actual, wanted)
                    findings.append(Finding(id=finding_id, code="incompatible_type", relation_id=relation.id,
                                            field=f"{location}:{path}", explanation=explanation, evidence_ids=proof))
                if status == "unknown":
                    gaps.append(Gap(repository_id=frontend.repository_id, file=frontend.file,
                                    code=f"{location}_type_unresolved", call_id=call.id))
                comparisons.append(TypeComparison(relation_id=relation.id, location=location, path=path,
                                                  actual=actual, expected=wanted, status=status, reason=reason,
                                                  evidence_ids=proof, finding_id=finding_id, explanation=explanation))
    return comparisons, findings, gaps
