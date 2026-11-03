"""Extração conservadora da presença de chaves JSON, sem executar fontes."""

import json
import re

from codedoc.models import BodyRequirement, RequestBody
from codedoc.syntax import attributes, literal, property_name, text, walk


def children(node):
    return [item for item in node.named_children if item.type != "comment"] if node else []


def object_pairs(node):
    if node is None or node.type != "object":
        return None
    result = {}
    for pair in children(node):
        if pair.type != "pair":
            return None
        key = property_name(pair.child_by_field_name("key"))
        if key is None or key in result or key == "__proto__":
            return None
        result[key] = pair.child_by_field_name("value")
    return result


def encodable(value: str) -> bool:
    try:
        value.encode("utf-8")
        return True
    except UnicodeError:
        return False


def primitive(node) -> bool:
    if node.type in {"true", "false", "null"}:
        return True
    if node.type == "string":
        return literal(node) is not None
    return node.type in {"number", "unary_expression"} and re.fullmatch(
        r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", text(node)
    ) is not None


def global_stringify(root) -> bool:
    for node in walk(root):
        if node.type == "identifier" and text(node) == "JSON":
            member = node.parent
            if (member.type != "member_expression" or member.child_by_field_name("object") != node
                    or text(member.child_by_field_name("property")) != "stringify"
                    or member.parent.type != "call_expression"
                    or member.parent.child_by_field_name("function") != member):
                return False
    return True


def serialization_risk(root, csharp: bool) -> bool:
    if csharp:
        return any((node.type == "identifier" and text(node) in {
            "AddNewtonsoftJson", "JsonConverter", "JsonConverterAttribute", "JsonConverterFactory", "Converters", "InputFormatters"
        }) or (node.type in {"class_declaration", "struct_declaration", "record_declaration"}
               and text(node.child_by_field_name("name")) == "JsonElement") for node in walk(root))
    if not global_stringify(root):
        return True
    return any(node.type == "member_expression" and (
        text(node.child_by_field_name("property")) == "toJSON" or
        (text(node.child_by_field_name("object")) in {"globalThis", "window", "self"}
         and text(node.child_by_field_name("property")) == "JSON")
    ) for node in walk(root))


def request_body(call, root) -> RequestBody:
    unknown = lambda reason: RequestBody(status="unknown", reason=reason)
    args = children(call.child_by_field_name("arguments"))
    if len(args) == 1:
        return RequestBody(status="none", reason="body_not_provided")
    if len(args) != 2 or (options := object_pairs(args[1])) is None:
        return unknown("request_options_unresolved")
    if "body" not in options:
        return RequestBody(status="none", reason="body_not_provided")
    headers = object_pairs(options.get("headers"))
    content_types = [] if headers is None else [literal(value) for key, value in headers.items() if key.lower() == "content-type"]
    if (len(content_types) != 1 or content_types[0] is None
            or content_types[0].split(";", 1)[0].strip().lower() != "application/json"):
        return unknown("json_content_type_unresolved")
    body = options["body"]
    encoded = literal(body)
    if encoded is not None:
        try:
            # Python aceita NaN/Infinity por padrão; JSON HTTP não aceita esses tokens.
            def reject_constant(_):
                raise ValueError
            value = json.loads(encoded, parse_constant=reject_constant)
            if isinstance(value, dict) and all(encodable(key) for key in value):
                return RequestBody(status="object", fields=sorted(value), reason="literal_json_object")
        except (ValueError, RecursionError):
            pass
        return unknown("json_body_not_object_or_invalid")
    if (body.type != "call_expression" or text(body.child_by_field_name("function")) != "JSON.stringify"
            or not global_stringify(root)):
        return unknown("body_serialization_unresolved")
    arguments = children(body.child_by_field_name("arguments"))
    if len(arguments) != 1 or (pairs := object_pairs(arguments[0])) is None:
        return unknown("body_serialization_unresolved")
    if any(key == "toJSON" or not encodable(key) or not primitive(value) for key, value in pairs.items()):
        return unknown("body_values_unresolved")
    return RequestBody(status="object", fields=sorted(pairs), reason="inline_json_stringify_object")


def property_guard(statement, parameter: str):
    if statement.type != "if_statement" or statement.child_by_field_name("alternative") is not None:
        return None
    condition = statement.child_by_field_name("condition")
    if (condition is None or condition.type != "prefix_unary_expression"
            or condition.children[0].type != "!" or len(children(condition)) != 1):
        return None
    invocation = children(condition)[0]
    if invocation.type != "invocation_expression":
        return None
    function = invocation.child_by_field_name("function")
    if (function.type != "member_access_expression"
            or text(function.child_by_field_name("expression")) != parameter
            or text(function.child_by_field_name("name")) != "TryGetProperty"):
        return None
    arguments = children(invocation.child_by_field_name("arguments"))
    if len(arguments) != 2 or len(children(arguments[0])) != 1 or not text(arguments[1]).startswith("out "):
        return None
    field = literal(children(arguments[0])[0])
    output = children(arguments[1])
    if field is None or not encodable(field) or len(output) != 1:
        return None
    if output[0].type == "declaration_expression":
        if text(output[0].child_by_field_name("name")) == parameter:
            return None
    elif output[0].type != "identifier" or text(output[0]) != "_":
        return None
    consequence = statement.child_by_field_name("consequence")
    if consequence.type == "block":
        statements = children(consequence)
        if len(statements) != 1:
            return None
        consequence = statements[0]
    if consequence.type != "return_statement" or len(children(consequence)) != 1:
        return None
    returned = children(consequence)[0]
    if returned.type != "invocation_expression" or children(returned.child_by_field_name("arguments")):
        return None
    result = text(returned.child_by_field_name("function"))
    if result not in {"BadRequest", "base.BadRequest"}:
        return None
    return field, invocation.start_byte, result


def body_requirement(method, controller, root) -> BodyRequirement:
    unknown = lambda reason: BodyRequirement(status="unknown", reason=reason)
    parameters = children(method.child_by_field_name("parameters"))
    if not parameters:
        if any(attr in {"HttpPost", "HttpPut", "HttpPatch"} for attr, _ in attributes(method)):
            return unknown("body_binding_unresolved")
        return BodyRequirement(status="none", reason="no_body_parameter")
    if len(parameters) != 1 or parameters[0].type != "parameter":
        return unknown("body_binding_unresolved")
    parameter = parameters[0]
    attrs = attributes(parameter)
    if len(attrs) != 1 or attrs[0] != ("FromBody", []):
        return unknown("body_binding_unresolved")
    typename = text(parameter.child_by_field_name("type"))
    if typename not in {"JsonElement", "System.Text.Json.JsonElement"}:
        return unknown("body_type_or_validation_unresolved")
    if typename == "JsonElement" and not any(node.type == "using_directive" and
            re.fullmatch(r"using\s+System\.Text\.Json\s*;", text(node)) for node in walk(root)):
        return unknown("json_element_type_unresolved")
    if any(node.type == "using_directive" and "=" in text(node) for node in walk(root)):
        return unknown("json_element_type_unresolved")
    if any(node.type in {"class_declaration", "struct_declaration", "record_declaration"} and
           text(node.child_by_field_name("name")) == "JsonElement" for node in walk(root)):
        return unknown("json_element_type_unresolved")
    if any(child.type == "modifier" and text(child) == "partial" for child in controller.named_children):
        return unknown("partial_controller_unresolved")
    block = method.child_by_field_name("body")
    if block is None or block.type != "block":
        return unknown("backend_guard_unresolved")
    name = text(parameter.child_by_field_name("name"))
    guards = []
    for statement in children(block):
        guard = property_guard(statement, name)
        if guard is None:
            break
        guards.append(guard)
    if not guards:
        return unknown("backend_guard_unresolved")
    if any(result == "BadRequest" for _, _, result in guards) and any(
        node.type in {"method_declaration", "property_declaration", "variable_declarator"}
        and text(node.child_by_field_name("name")) == "BadRequest" for node in walk(controller)
    ):
        return unknown("bad_request_symbol_unresolved")
    checked = {offset for _, offset, _ in guards}
    all_checks = {node.start_byte for node in walk(block) if node.type == "invocation_expression"
                  and text(node.child_by_field_name("function")).endswith(".TryGetProperty")}
    return BodyRequirement(status="known", fields=list(dict.fromkeys(field for field, _, _ in guards)),
                           reason="explicit_presence_guards" if checked == all_checks else "additional_checks_unresolved")
