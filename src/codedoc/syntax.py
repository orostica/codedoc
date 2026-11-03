"""Utilidades puras para as árvores sintáticas e identificadores locais."""

from hashlib import sha256
import json


def stable_id(prefix: str, *parts: str) -> str:
    return prefix + sha256("\0".join(parts).encode()).hexdigest()[:24]


def walk(node):
    yield node
    for child in node.named_children:
        yield from walk(child)


def text(node) -> str:
    return node.text.decode("utf-8") if node is not None else ""


def literal(node) -> str | None:
    value = text(node)
    if node is None or node.type not in {"string", "string_literal"}:
        return None
    try:
        if value.startswith('"'):
            decoded = json.loads(value)
            return decoded if isinstance(decoded, str) else None
        if value.startswith("'") and value.endswith("'") and "\\" not in value:
            return value[1:-1]
    except ValueError:
        pass
    return None


def property_name(node) -> str | None:
    if node.type == "property_identifier":
        return text(node)
    return literal(node)


def attributes(node):
    result = []
    for child in node.named_children:
        if child.type != "attribute_list":
            continue
        for attr in child.named_children:
            name = text(attr.child_by_field_name("name"))
            arguments = next((item for item in attr.named_children if item.type == "attribute_argument_list"), None)
            values = [] if arguments is None else [
                literal(item.named_children[0]) if len(item.named_children) == 1 else None
                for item in arguments.named_children
            ]
            result.append((name, values))
    return result
