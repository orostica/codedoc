"""Recorte sintático de tipos: JSON literal, getters e acessos diretos à resposta.

Não resolve aliases, fluxo condicional, DTOs, wrappers ou serializadores externos.
"""

import json
import math
import re
from urllib.parse import parse_qs, urlsplit

from codedoc.contracts import children, object_pairs, primitive, request_body
from codedoc.models import TypeContract, TypeFact
from codedoc.syntax import attributes, literal, text, walk


def fact(location, path, kind):
    return TypeFact(location=location, path=path, kind=kind)


def json_kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, int):
        return "int32" if -(2**31) <= value < 2**31 else "integer"
    return "number"


def json_facts(value, location, path="$"):
    result = [fact(location, path, json_kind(value))]
    if isinstance(value, dict):
        for key, child in value.items():
            # JSON Pointer evita colisões de chaves contendo pontos ou barras.
            result.extend(json_facts(child, location, path + "/" + key.replace("~", "~0").replace("/", "~1")))
    return result


def decode_json(encoded):
    def invalid(_):
        raise ValueError
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    return json.loads(encoded, parse_constant=invalid, object_pairs_hook=unique)


def frontend_types(call, root):
    result = TypeContract()
    args = children(call.child_by_field_name("arguments"))
    body = request_body(call, root)
    if body.status == "object":
        options = object_pairs(args[1])
        node = options["body"]
        encoded = literal(node)
        try:
            if encoded is not None:
                result.facts.extend(json_facts(decode_json(encoded), "body"))
            else:
                pairs = object_pairs(children(node.child_by_field_name("arguments"))[0])
                value = {}
                for key, item in pairs.items():
                    if not primitive(item):
                        raise ValueError
                    if item.type == "string":
                        value[key] = literal(item)
                    else:
                        # JSON.stringify normaliza números JS; só inteiros seguros aqui.
                        number = decode_json(text(item))
                        if isinstance(number, (int, float)) and not isinstance(number, bool):
                            if not math.isfinite(number) or abs(number) > 2**53 - 1:
                                raise ValueError
                            if isinstance(number, float) and number.is_integer():
                                number = int(number)
                        value[key] = number
                result.facts.extend(json_facts(value, "body"))
        except (ValueError, RecursionError):
            result.unresolved.append("body")
    elif body.status == "unknown":
        result.unresolved.append("body")
    url = literal(args[0]) if args else None
    if url:
        try:
            for key, values in parse_qs(urlsplit(url).query, keep_blank_values=True).items():
                value = values[0]
                digits = value.strip().lstrip("+-").lstrip("0") or "0"
                normalized = ("-" if value.strip().startswith("-") else "") + digits
                integer = (len(values) == 1 and re.fullmatch(r"\s*[+-]?[0-9]+\s*", value)
                           and len(digits) <= 10 and -(2**31) <= int(normalized) < 2**31)
                kind = "integer_text" if integer else "invalid_integer_text"
                result.facts.append(fact("query", key, kind if len(values) == 1 else "unknown"))
        except ValueError:
            result.unresolved.append("query")
    response_accesses(call, result)
    return result


def response_accesses(call, result):
    """Reconhece const response=await fetch; const data=await response.json()."""
    scope = call.parent
    while scope and scope.type not in {"function_declaration", "arrow_function", "function_expression"}:
        scope = scope.parent
    if scope is None:
        result.unresolved.append("response")
        return
    block = scope.child_by_field_name("body")
    statements = children(block)
    if (block.type != "statement_block" or len(statements) != 3 or
            any(node.type in {"assignment_expression", "update_expression"} for node in walk(block))):
        result.unresolved.append("response")
        return
    bindings = []
    for statement in statements[:2]:
        decls = children(statement)
        if statement.type != "lexical_declaration" or not text(statement).startswith("const ") or len(decls) != 1:
            result.unresolved.append("response")
            return
        decl = decls[0]
        name, value = decl.child_by_field_name("name"), decl.child_by_field_name("value")
        if name.type != "identifier" or value is None:
            result.unresolved.append("response")
            return
        bindings.append((text(name), value))
    response, fetch_value = bindings[0]
    data, json_value = bindings[1]
    if (fetch_value.type != "await_expression" or children(fetch_value) != [call] or
            json_value.type != "await_expression" or
            text(children(json_value)[0]) != response + ".json()" or response == data):
        result.unresolved.append("response")
        return
    returned = children(statements[2])
    if (statements[2].type != "return_statement" or len(returned) != 1 or
            any(child.type in {"optional_chain", "?."} for node in walk(statements[2]) for child in node.children)):
        result.unresolved.append("response")
        return
    expression = returned[0]
    if expression.type != "call_expression" or children(expression.child_by_field_name("arguments")):
        result.unresolved.append("response")
        return
    function = expression.child_by_field_name("function")
    if function.type != "member_expression":
        result.unresolved.append("response")
        return
    operation = text(function.child_by_field_name("property"))
    expected = {"toUpperCase": "string", "toLowerCase": "string", "trim": "string", "toFixed": "number"}.get(operation)
    target = function.child_by_field_name("object")
    keys = []
    while target.type == "member_expression":
        key = target.child_by_field_name("property")
        if key.type != "property_identifier" or any(child.type == "optional_chain" for child in target.children):
            break
        keys.insert(0, text(key))
        target = target.child_by_field_name("object")
    if expected is None or text(target) != data or any(child.type == "optional_chain" for child in function.children):
        result.unresolved.append("response")
        return
    path = "$" + "".join("/" + key.replace("~", "~0").replace("/", "~1") for key in keys)
    result.facts.append(fact("response", path, expected))


def backend_types(method, controller, root):
    result = TypeContract()
    params = children(method.child_by_field_name("parameters"))
    block = method.child_by_field_name("body")
    statements = children(block)
    # Um único retorno evita branches, mutações e aliases implícitos.
    straight = (block is not None and block.type == "block" and len(statements) == 1
                and statements[0].type == "return_statement" and not any(
                    node.type in {"conditional_expression", "conditional_access_expression", "lambda_expression", "assignment_expression", "binary_expression"}
                    for node in walk(block)))
    partial = any(child.type == "modifier" and text(child) == "partial" for child in controller.named_children)
    aliases = any(node.type == "using_directive" and "=" in text(node) for node in walk(root))
    shadowed_json = any(node.type in {"class_declaration", "struct_declaration", "record_declaration"}
                        and text(node.child_by_field_name("name")) == "JsonElement" for node in walk(root))
    if partial or aliases or shadowed_json:
        result.unresolved.extend(["body", "query", "response"])
        return result
    for parameter in params:
        name = text(parameter.child_by_field_name("name"))
        typename = text(parameter.child_by_field_name("type"))
        attrs = attributes(parameter)
        if attrs == [("FromBody", [])]:
            imported = typename == "System.Text.Json.JsonElement" or (
                typename == "JsonElement" and any(text(node) == "using System.Text.Json;" for node in walk(root)))
            getters = []
            if straight and imported:
                for node in walk(block):
                    if node.type != "invocation_expression":
                        continue
                    function = node.child_by_field_name("function")
                    if function.type != "member_access_expression" or children(node.child_by_field_name("arguments")):
                        continue
                    kind = {"GetString": "string", "GetBoolean": "boolean", "GetInt32": "int32", "GetDouble": "number"}.get(text(function.child_by_field_name("name")))
                    value = function.child_by_field_name("expression")
                    if kind is None or value.type != "invocation_expression":
                        continue
                    args = children(value.child_by_field_name("arguments"))
                    if text(value.child_by_field_name("function")) != name + ".GetProperty" or len(args) != 1:
                        continue
                    key = literal(children(args[0])[0]) if len(children(args[0])) == 1 else None
                    if key is not None:
                        getters.append(fact("body", "$/" + key.replace("~", "~0").replace("/", "~1"), kind))
            result.facts.extend(getters)
            if not getters:
                result.unresolved.append("body")
        elif attrs == [("FromQuery", [])] and typename == "string" and straight:
            # O tipo string declarado sozinho não exige conteúdo numérico.
            conversions = [node for node in walk(block) if node.type == "invocation_expression"
                           and text(node.child_by_field_name("function")) in {"int.Parse", "System.Int32.Parse"}
                           and text(node.child_by_field_name("arguments")) == "(" + name + ")"]
            if conversions:
                result.facts.append(fact("query", name, "integer_text"))
            else:
                result.unresolved.append("query")
        else:
            result.unresolved.append("query" if any(attr == "FromQuery" for attr, _ in attrs) else "body")
    # Content com JSON literal fixa o formato efetivamente escrito, sem inferir DTO.
    if straight:
        returned = children(statements[0])
        invocation = returned[0] if len(returned) == 1 else None
        if invocation is not None and invocation.type == "invocation_expression":
            function = text(invocation.child_by_field_name("function"))
            args = children(invocation.child_by_field_name("arguments"))
            shadowed = any(node.type in {"method_declaration", "property_declaration", "variable_declarator"}
                           and text(node.child_by_field_name("name")) == "Content" for node in walk(controller))
            if function in {"Content", "base.Content"} and (function == "base.Content" or not shadowed) and len(args) == 2:
                values = [literal(children(arg)[0]) if len(children(arg)) == 1 else None for arg in args]
                if values[0] is not None and values[1] == "application/json":
                    try:
                        result.facts.extend(json_facts(decode_json(values[0]), "response"))
                    except (ValueError, RecursionError):
                        pass
    if not any(item.location == "response" for item in result.facts):
        result.unresolved.append("response")
    result.unresolved = list(dict.fromkeys(result.unresolved))
    return result
