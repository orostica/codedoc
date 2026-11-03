"""Extração sintática conservadora; padrões não resolvidos viram lacunas."""

from hashlib import sha256
import re
from urllib.parse import urlsplit

from tree_sitter import Language, Parser
import tree_sitter_c_sharp
import tree_sitter_typescript

from codedoc.models import Call, Dependency, Endpoint, Evidence, Gap, Symbol
from codedoc.contracts import body_requirement, request_body, serialization_risk
from codedoc.syntax import attributes, literal, property_name, stable_id, text, walk


class Extractor:
    def __init__(self, repository_id: str, revision: str, file: str, source: bytes):
        self.repository_id, self.revision, self.file, self.source = repository_id, revision, file, source
        self.symbols, self.evidence, self.dependencies = [], [], []
        self.calls, self.endpoints, self.gaps = [], [], []
        self.nodes = {}

    def gap(self, code: str, call_id: str | None = None):
        self.gaps.append(Gap(repository_id=self.repository_id, file=self.file, code=code, call_id=call_id))

    def symbol(self, node, kind: str, name: str) -> Symbol:
        key = (node.type, node.start_byte, node.end_byte)
        if key in self.nodes:
            return self.nodes[key]
        symbol_id = f"{self.repository_id}:{self.file}:{kind}:{name}:{node.start_point.row + 1}:{node.start_point.column}"
        location = dict(repository_id=self.repository_id, file=self.file,
                        start_line=node.start_point.row + 1,
                        end_line=max(node.start_point.row + 1, node.end_point.row + (node.end_point.column != 0)))
        evidence_id = stable_id("ev-", symbol_id, self.revision)
        symbol = Symbol(id=symbol_id, name=name, kind=kind, evidence_id=evidence_id, **location)
        self.symbols.append(symbol)
        self.evidence.append(Evidence(id=evidence_id, symbol=symbol_id, revision=self.revision,
                                      source_hash=sha256(self.source).hexdigest(), **location))
        self.nodes[key] = symbol
        return symbol

    def parse(self):
        if self.file.lower().endswith(".cs"):
            language = tree_sitter_c_sharp.language()
        else:
            language = (tree_sitter_typescript.language_tsx() if self.file.lower().endswith((".tsx", ".jsx"))
                        else tree_sitter_typescript.language_typescript())
        root = Parser(Language(language)).parse(self.source).root_node
        if root.has_error:
            self.gap("syntax_error")
            return self
        module = self.symbol(root, "module", self.file)
        if serialization_risk(root, self.file.lower().endswith(".cs")):
            self.gap("dotnet_serialization_unresolved" if self.file.lower().endswith(".cs") else "javascript_serialization_unresolved")
        if self.file.lower().endswith(".cs"):
            self.csharp(root, module)
        else:
            self.typescript(root, module)
        return self

    def typescript(self, root, module):
        nodes = list(walk(root))
        for node in nodes:
            if node.type == "import_statement":
                target = literal(node.child_by_field_name("source"))
                if target is not None:
                    self.dependencies.append(Dependency(from_symbol=module.id, target=target,
                                                         kind="import", evidence_id=module.evidence_id))
            if node.type in {"function_declaration", "function_expression", "arrow_function"}:
                name = text(node.child_by_field_name("name"))
                if not name and node.parent and node.parent.type == "variable_declarator":
                    name = text(node.parent.child_by_field_name("name"))
                self.symbol(node, "function", name or "anonymous")
        fetch_calls = [node for node in nodes if node.type == "call_expression"
                       and text(node.child_by_field_name("function")) == "fetch"]
        # Qualquer outro uso do identificador impede assumir fetch global neste recorte.
        shadowed = any(node.type == "identifier" and text(node) == "fetch"
                       and not (node.parent.type == "call_expression"
                                and node.parent.child_by_field_name("function") == node)
                       for node in nodes)
        for node in fetch_calls:
            parent = node.parent
            while parent and parent.type not in {"function_declaration", "function_expression", "arrow_function"}:
                parent = parent.parent
            symbol = self.nodes[(parent.type, parent.start_byte, parent.end_byte)] if parent else module
            arguments = node.child_by_field_name("arguments").named_children
            url = literal(arguments[0]) if arguments else None
            method = "GET"
            if len(arguments) > 2:
                method = None
            if len(arguments) >= 2:
                options = arguments[1]
                if options.type != "object" or any(item.type != "pair" for item in options.named_children):
                    method = None
                else:
                    keys = [property_name(item.child_by_field_name("key")) for item in options.named_children]
                    methods = [item.child_by_field_name("value") for item, key in zip(options.named_children, keys)
                               if key == "method"]
                    # Chaves computadas podem sobrescrever o método.
                    if any(key is None or key == "__proto__" for key in keys):
                        method = None
                    elif len(methods) == 1:
                        value = literal(methods[0])
                        method = value.upper() if value else None
                    elif methods:
                        method = None
            if shadowed:
                url, method = None, None
            if url:
                try:
                    parsed = urlsplit(url)
                    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                            or parsed.username is not None or parsed.password is not None
                            or re.search(r"[\s\\]", url)):
                        url = None
                    else:
                        _ = parsed.port
                        url = parsed._replace(query="", fragment="").geturl()
                except ValueError:
                    url = None
            call = Call(id=stable_id("call-", symbol.id, str(node.start_byte)), symbol_id=symbol.id,
                        repository_id=self.repository_id, method=method, url=url, evidence_id=symbol.evidence_id,
                        body=request_body(node, root))
            self.calls.append(call)
            if url is None or method is None:
                self.gap("fetch_unresolved", call.id)
        if any(node.type == "call_expression" and text(node.child_by_field_name("function")).startswith("axios") for node in nodes):
            self.gap("axios_not_supported")
        if any(node.type == "call_expression" and text(node.child_by_field_name("function")).endswith(".fetch") for node in nodes):
            self.gap("member_fetch_not_supported")

    def csharp(self, root, module):
        for node in walk(root):
            if node.type == "using_directive":
                self.dependencies.append(Dependency(from_symbol=module.id, target=text(node), kind="using", evidence_id=module.evidence_id))
            if node.type != "class_declaration":
                continue
            name = text(node.child_by_field_name("name"))
            class_symbol = self.symbol(node, "class", name)
            attrs = attributes(node)
            routes = [args for attr, args in attrs if attr == "Route"]
            base = next((item for item in node.named_children if item.type == "base_list"), None)
            if not name.endswith("Controller"):
                continue
            if (base is None or len(base.named_children) != 1
                    or text(base.named_children[0]) not in {"ControllerBase", "Controller"}):
                self.gap("controller_base_unresolved")
                continue
            if any(attr == "NonController" for attr, _ in attrs):
                continue
            if len(routes) != 1 or len(routes[0]) != 1 or routes[0][0] is None:
                self.gap("controller_route_unresolved")
                continue
            prefix = routes[0][0].replace("[controller]", name[:-10])
            body = node.child_by_field_name("body")
            for method in body.named_children:
                if method.type != "method_declaration":
                    continue
                symbol = self.symbol(method, "method", name + "." + text(method.child_by_field_name("name")))
                method_attrs = attributes(method)
                http = [(attr[4:].upper(), args) for attr, args in method_attrs
                        if attr in {"HttpGet", "HttpPost", "HttpPut", "HttpPatch", "HttpDelete", "HttpHead", "HttpOptions"}]
                if not http:
                    self.gap("controller_action_unresolved")
                    continue
                if (len(http) != 1 or any(attr in {"Route", "AcceptVerbs", "NonAction"} for attr, _ in method_attrs)
                        or not any(item.type == "modifier" and text(item) == "public" for item in method.named_children)):
                    self.gap("controller_action_unresolved")
                    continue
                verb, args = http[0]
                if len(args) > 1 or (args and args[0] is None):
                    self.gap("controller_action_unresolved")
                    continue
                suffix = args[0] if args else ""
                route = suffix[2:] if suffix.startswith("~/") else (suffix if suffix.startswith("/") else prefix.strip("/") + "/" + suffix)
                route = "/" + route.strip("/")
                if any(char in route for char in "{}[]?#"):
                    self.gap("route_pattern_not_supported")
                    continue
                self.endpoints.append(Endpoint(id=stable_id("endpoint-", symbol.id, verb, route), symbol_id=symbol.id,
                                               repository_id=self.repository_id, method=verb, route=route,
                                               evidence_ids=[class_symbol.evidence_id, symbol.evidence_id],
                                               request=body_requirement(method, node, root)))
        if any(node.type == "invocation_expression" and re.search(r"\.Map(Get|Post|Put|Delete|Patch)$", text(node.child_by_field_name("function"))) for node in walk(root)):
            self.gap("minimal_api_not_supported")
