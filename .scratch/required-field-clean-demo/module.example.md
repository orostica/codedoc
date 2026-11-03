# Cadastro de pessoa

## Objetivo

A função createPerson envia um objeto JSON ao backend. [@{{frontend_evidence}}]

## Fluxo

O corpo construído contém age e omite name, embora o tipo frontend permita name opcional. [@{{frontend_evidence}}]

A guarda inicial de Create retorna BadRequest quando a chave name está ausente. [@{{backend_evidence}}]

O achado {{finding_id}} compara essa omissão com a exigência explícita do backend. [@{{frontend_evidence}}] [@{{backend_evidence}}]

## Evidências

Frontend: {{frontend_revision}}.
Backend: {{backend_revision}}.

As evidências preservam símbolos, linhas e hashes das fontes na revisão original.

## Lacunas

A análise compara presença de chaves em JSON, sem validar tipos, valores ou execução.
DTOs e serializações não resolvidos exigem revisão e não fundamentam divergências.

## Revisão

Revisão humana pendente.
