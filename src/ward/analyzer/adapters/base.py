from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ward.analyzer.concepts import Concept


class LanguageAdapter(ABC):
    @abstractmethod
    def get_node_types(self, concept: Concept) -> list[str]:
        pass

    @abstractmethod
    def get_language(self) -> str:
        pass

    @abstractmethod
    def get_parser(self) -> "tree_sitter.Parser":
        pass

    @abstractmethod
    def is_query_call(self, node: "tree_sitter.Node", code_bytes: bytes) -> bool:
        pass

    @abstractmethod
    def is_io_call(self, node: "tree_sitter.Node", code_bytes: bytes) -> bool:
        pass

    @abstractmethod
    def is_blocking_io_call(self, node: "tree_sitter.Node", code_bytes: bytes) -> bool:
        pass

    @abstractmethod
    def get_exception_type_text(
        self, node: "tree_sitter.Node", code_bytes: bytes
    ) -> str | None:
        pass

    @abstractmethod
    def is_broad_exception(self, exception_type: str) -> bool:
        pass

    def get_node_text(self, node: "tree_sitter.Node", code_bytes: bytes) -> str:
        return code_bytes[node.start_byte : node.end_byte].decode("utf-8")
