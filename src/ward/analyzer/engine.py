from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import yaml

from ward.analyzer.adapters.base import LanguageAdapter
from ward.analyzer.adapters.python import PythonAdapter
from ward.analyzer.concepts import Concept
from ward.analyzer.relationships import (
    RelationshipType,
    check_ancestor_contains,
    find_all_nodes,
    find_nodes_of_type,
)
from ward.models import AnalyzerIssue, AnalyzerRule, TreeSitterResult

if TYPE_CHECKING:
    from tree_sitter import Node

RULES_DIR = Path(__file__).parent / "rules"


class AnalysisEngine:
    def __init__(self) -> None:
        self.adapters: dict[str, LanguageAdapter] = {
            "python": PythonAdapter(),
        }
        self.rules: list[AnalyzerRule] = []
        self._load_rules()

    def _load_rules(self) -> None:
        if not RULES_DIR.exists():
            return

        for rule_file in RULES_DIR.glob("*.yaml"):
            with open(rule_file, "r", encoding="utf-8") as f:
                rule_data = yaml.safe_load(f)
                if rule_data:
                    self.rules.append(
                        AnalyzerRule(
                            id=rule_data.get("id", rule_file.stem),
                            target_concept=rule_data.get("target_concept", ""),
                            relationship=rule_data.get("relationship", ""),
                            relationship_target=rule_data.get("relationship_target"),
                            severity=rule_data.get("severity", "warning"),
                            message=rule_data.get("message", ""),
                            languages=rule_data.get("languages", []),
                            query_patterns=rule_data.get("query_patterns", []),
                            io_patterns=rule_data.get("io_patterns", []),
                        )
                    )

    def _find_nodes(
        self,
        root: "Node",
        target_types: list[str],
    ) -> list["Node"]:
        return find_nodes_of_type(root, target_types)

    def _create_issue(
        self,
        node: "Node",
        rule: AnalyzerRule,
        code_bytes: bytes,
        file_path: str,
    ) -> AnalyzerIssue:
        code_snippet = code_bytes[node.start_byte : node.end_byte].decode("utf-8")
        return AnalyzerIssue(
            id=str(uuid4()),
            rule_id=rule.id,
            severity=rule.severity,
            message=rule.message,
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1] + 1,
            end_line=node.end_point[0] + 1,
            end_column=node.end_point[1] + 1,
            code_snippet=code_snippet,
        )

    def _check_import_in_function(
        self,
        node: "Node",
        adapter: LanguageAdapter,
    ) -> bool:
        return check_ancestor_contains(node, Concept.FUNCTION, adapter)

    def _is_part_of_method_chain(self, node: "Node") -> bool:
        parent = node.parent
        if parent is None:
            return False
        if parent.type == "attribute":
            grandparent = parent.parent
            if grandparent is not None and grandparent.type == "call":
                return True
        return False

    def _check_query_in_loop(
        self,
        node: "Node",
        adapter: LanguageAdapter,
        code_bytes: bytes,
    ) -> bool:
        if not adapter.is_query_call(node, code_bytes):
            return False
        if self._is_part_of_method_chain(node):
            return False
        return check_ancestor_contains(node, Concept.LOOP, adapter)

    def _check_missing_await(
        self,
        node: "Node",
        adapter: PythonAdapter,
        code_bytes: bytes,
    ) -> bool:
        if node.type != "call":
            return False

        func_node = self._find_containing_function(node)
        if func_node is None:
            return False

        if not adapter.is_async_function(func_node):
            return False

        if adapter.is_blocking_io_call(node, code_bytes):
            return False

        return not adapter.has_await_wrapper(node)

    def _find_containing_function(self, node: "Node") -> "Node | None":
        current = node.parent
        while current is not None:
            if current.type == "function_definition":
                return current
            current = current.parent
        return None

    def _check_broad_exception(
        self,
        node: "Node",
        adapter: LanguageAdapter,
        code_bytes: bytes,
    ) -> bool:
        if node.type != "except_clause":
            return False

        exception_type = adapter.get_exception_type_text(node, code_bytes)
        if exception_type is None:
            return True

        return adapter.is_broad_exception(exception_type)

    def _check_blocking_io(
        self,
        node: "Node",
        adapter: PythonAdapter,
        code_bytes: bytes,
    ) -> bool:
        if node.type != "call":
            return False

        func_node = self._find_containing_function(node)
        if func_node is None:
            return False

        if not adapter.is_async_function(func_node):
            return False

        return adapter.is_blocking_io_call(node, code_bytes)

    def _check_relationship(
        self,
        node: "Node",
        rule: AnalyzerRule,
        adapter: LanguageAdapter,
        code_bytes: bytes,
    ) -> bool:
        relationship = RelationshipType(rule.relationship)

        if rule.id == "import-in-function":
            return self._check_import_in_function(node, adapter)

        if rule.id == "n-plus-one-query":
            return self._check_query_in_loop(node, adapter, code_bytes)

        if rule.id == "missing-await":
            if isinstance(adapter, PythonAdapter):
                return self._check_missing_await(node, adapter, code_bytes)
            return False

        if rule.id == "broad-exception":
            return self._check_broad_exception(node, adapter, code_bytes)

        if rule.id == "blocking-io":
            if isinstance(adapter, PythonAdapter):
                return self._check_blocking_io(node, adapter, code_bytes)
            return False

        if relationship == RelationshipType.ANCESTOR_CONTAINS:
            if rule.relationship_target:
                target_concept = Concept(rule.relationship_target)
                return check_ancestor_contains(node, target_concept, adapter)

        return False

    async def analyze(
        self,
        code: str,
        language: str,
        file_path: str = "<unknown>",
    ) -> list[AnalyzerIssue]:
        if language not in self.adapters:
            return []

        adapter = self.adapters[language]
        parser = adapter.get_parser()
        code_bytes = code.encode("utf-8")
        tree = parser.parse(code_bytes)

        issues: list[AnalyzerIssue] = []

        for rule in self.rules:
            if language not in rule.languages:
                continue

            target_concept = Concept(rule.target_concept)
            target_types = adapter.get_node_types(target_concept)

            if rule.id == "missing-await":
                call_types = adapter.get_node_types(Concept.FUNCTION_CALL)
                matches = self._find_nodes(tree.root_node, call_types)
            elif rule.id == "blocking-io":
                call_types = adapter.get_node_types(Concept.FUNCTION_CALL)
                matches = self._find_nodes(tree.root_node, call_types)
            else:
                matches = self._find_nodes(tree.root_node, target_types)

            for node in matches:
                if self._check_relationship(node, rule, adapter, code_bytes):
                    issues.append(
                        self._create_issue(node, rule, code_bytes, file_path)
                    )

        return issues

    async def analyze_files(
        self,
        files: list[tuple[str, str, str]],
    ) -> TreeSitterResult:
        all_issues: list[AnalyzerIssue] = []

        for file_path, content, language in files:
            file_issues = await self.analyze(content, language, file_path)
            all_issues.extend(file_issues)

        summary = {
            "total": len(all_issues),
            "error": sum(1 for i in all_issues if i.severity == "error"),
            "warning": sum(1 for i in all_issues if i.severity == "warning"),
            "info": sum(1 for i in all_issues if i.severity == "info"),
        }

        return TreeSitterResult(issues=all_issues, summary=summary)


_engine: AnalysisEngine | None = None


def get_engine() -> AnalysisEngine:
    global _engine
    if _engine is None:
        _engine = AnalysisEngine()
    return _engine


async def run_treesitter_analysis(
    files: list[tuple[str, str, str]],
) -> TreeSitterResult:
    engine = get_engine()
    return await engine.analyze_files(files)
