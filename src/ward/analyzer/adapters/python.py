from typing import TYPE_CHECKING

import tree_sitter
import tree_sitter_python

from ward.analyzer.adapters.base import LanguageAdapter
from ward.analyzer.concepts import Concept

if TYPE_CHECKING:
    from tree_sitter import Node

PYTHON_CONCEPT_MAP: dict[Concept, list[str]] = {
    Concept.IMPORT: ["import_statement", "import_from_statement"],
    Concept.FUNCTION: ["function_definition", "lambda"],
    Concept.ASYNC_FUNCTION: ["function_definition"],
    Concept.LOOP: ["for_statement", "while_statement", "for_in_clause"],
    Concept.ASYNC_CALL: ["call"],
    Concept.EXCEPTION_HANDLER: ["except_clause"],
    Concept.FUNCTION_CALL: ["call"],
    Concept.VARIABLE_ASSIGNMENT: ["assignment", "augmented_assignment"],
    Concept.AWAIT: ["await"],
    Concept.QUERY_CALL: ["call"],
    Concept.IO_CALL: ["call"],
    Concept.EXCEPTION_TYPE: ["identifier", "attribute"],
    Concept.WITH_STATEMENT: ["with_statement"],
}

QUERY_PATTERNS: list[str] = [
    "get",
    "filter",
    "all",
    "first",
    "one",
    "execute",
    "fetchone",
    "fetchall",
    "fetchmany",
    "query",
    "select",
    "find",
    "find_one",
    "find_all",
    "find_by",
]

IO_PATTERNS: list[str] = [
    "open",
    "read",
    "write",
    "close",
    "connect",
    "send",
    "recv",
    "request",
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "fetch",
    "download",
    "upload",
]

BLOCKING_IO_PATTERNS: list[str] = [
    "open",
    "read",
    "write",
    "readline",
    "readlines",
    "sleep",
    "connect",
    "send",
    "recv",
    "sendall",
    "recvfrom",
    "accept",
    "listen",
    "input",
]

BLOCKING_IO_MODULES: list[str] = [
    "time.sleep",
    "socket.connect",
    "socket.send",
    "socket.recv",
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "requests.patch",
    "urllib.request.urlopen",
]

BROAD_EXCEPTION_TYPES: set[str] = {
    "Exception",
    "BaseException",
}


class PythonAdapter(LanguageAdapter):
    def __init__(self) -> None:
        self._parser: tree_sitter.Parser | None = None
        self._language = tree_sitter.Language(tree_sitter_python.language())

    def get_node_types(self, concept: Concept) -> list[str]:
        return PYTHON_CONCEPT_MAP.get(concept, [])

    def get_language(self) -> str:
        return "python"

    def get_parser(self) -> tree_sitter.Parser:
        if self._parser is None:
            self._parser = tree_sitter.Parser(self._language)
        return self._parser

    def _get_call_name(self, node: "Node", code_bytes: bytes) -> str | None:
        for child in node.children:
            if child.type == "identifier":
                return self.get_node_text(child, code_bytes)
            if child.type == "attribute":
                return self._get_attribute_name(child, code_bytes)
        return None

    def _get_attribute_name(self, node: "Node", code_bytes: bytes) -> str | None:
        last_identifier = None
        for child in node.children:
            if child.type == "identifier":
                last_identifier = self.get_node_text(child, code_bytes)
        return last_identifier

    def _get_full_attribute_path(self, node: "Node", code_bytes: bytes) -> str:
        parts: list[str] = []
        current = node
        while current is not None:
            if current.type == "identifier":
                parts.insert(0, self.get_node_text(current, code_bytes))
                break
            if current.type == "attribute":
                for child in current.children:
                    if child.type == "identifier":
                        parts.insert(0, self.get_node_text(child, code_bytes))
                for child in current.children:
                    if child.type in ("identifier", "attribute"):
                        current = child
                        break
                else:
                    break
            else:
                break
        return ".".join(parts)

    def is_query_call(self, node: "Node", code_bytes: bytes) -> bool:
        if node.type != "call":
            return False
        call_name = self._get_call_name(node, code_bytes)
        if call_name is None:
            return False
        return call_name.lower() in [p.lower() for p in QUERY_PATTERNS]

    def is_io_call(self, node: "Node", code_bytes: bytes) -> bool:
        if node.type != "call":
            return False
        call_name = self._get_call_name(node, code_bytes)
        if call_name is None:
            return False
        return call_name.lower() in [p.lower() for p in IO_PATTERNS]

    def is_blocking_io_call(self, node: "Node", code_bytes: bytes) -> bool:
        if node.type != "call":
            return False
        call_name = self._get_call_name(node, code_bytes)
        if call_name is None:
            return False

        if call_name.lower() in [p.lower() for p in BLOCKING_IO_PATTERNS]:
            return True

        for child in node.children:
            if child.type == "attribute":
                full_path = self._get_full_attribute_path(child, code_bytes)
                if full_path in BLOCKING_IO_MODULES:
                    return True

        return False

    def get_exception_type_text(
        self, node: "Node", code_bytes: bytes
    ) -> str | None:
        if node.type != "except_clause":
            return None

        for child in node.children:
            if child.type in ("identifier", "attribute"):
                return self.get_node_text(child, code_bytes)
            if child.type == "as_pattern":
                for subchild in child.children:
                    if subchild.type in ("identifier", "attribute"):
                        return self.get_node_text(subchild, code_bytes)
        return None

    def is_broad_exception(self, exception_type: str) -> bool:
        return exception_type in BROAD_EXCEPTION_TYPES

    def is_async_function(self, node: "Node") -> bool:
        if node.type != "function_definition":
            return False
        for child in node.children:
            if child.type == "async":
                return True
        return False

    def has_await_wrapper(self, node: "Node") -> bool:
        parent = node.parent
        while parent is not None:
            if parent.type == "await":
                return True
            if parent.type in (
                "function_definition",
                "class_definition",
                "module",
            ):
                return False
            parent = parent.parent
        return False
