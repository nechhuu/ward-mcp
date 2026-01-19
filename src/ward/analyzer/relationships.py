from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from tree_sitter import Node
    from ward.analyzer.adapters.base import LanguageAdapter
    from ward.analyzer.concepts import Concept


class RelationshipType(Enum):
    ANCESTOR_CONTAINS = "ancestor_contains"
    MISSING_SIBLING = "missing_sibling"
    WRONG_CHILD = "wrong_child"
    REPEATED_IN = "repeated_in"
    WRONG_POSITION = "wrong_position"


def find_ancestor_of_type(
    node: "Node",
    target_types: list[str],
) -> "Node | None":
    current = node.parent
    while current is not None:
        if current.type in target_types:
            return current
        current = current.parent
    return None


def check_ancestor_contains(
    node: "Node",
    target_concept: "Concept",
    adapter: "LanguageAdapter",
) -> bool:
    target_types = adapter.get_node_types(target_concept)
    return find_ancestor_of_type(node, target_types) is not None


def find_siblings(node: "Node") -> list["Node"]:
    if node.parent is None:
        return []
    return [child for child in node.parent.children if child.id != node.id]


def check_missing_sibling(
    node: "Node",
    required_concept: "Concept",
    adapter: "LanguageAdapter",
) -> bool:
    required_types = adapter.get_node_types(required_concept)
    siblings = find_siblings(node)
    for sibling in siblings:
        if sibling.type in required_types:
            return False
    return True


def check_wrong_child(
    node: "Node",
    child_check_fn: Callable[["Node"], bool],
) -> bool:
    for child in node.children:
        if child_check_fn(child):
            return True
    return False


def find_nodes_of_type(
    node: "Node",
    target_types: list[str],
) -> list["Node"]:
    result: list["Node"] = []
    if node.type in target_types:
        result.append(node)
    for child in node.children:
        result.extend(find_nodes_of_type(child, target_types))
    return result


def check_repeated_in(
    container_node: "Node",
    pattern_concept: "Concept",
    adapter: "LanguageAdapter",
    min_count: int = 1,
) -> list["Node"]:
    pattern_types = adapter.get_node_types(pattern_concept)
    matches = find_nodes_of_type(container_node, pattern_types)
    if len(matches) > min_count:
        return matches
    return []


def check_wrong_position(
    node: "Node",
    position_rule: Callable[["Node"], bool],
) -> bool:
    return position_rule(node)


def is_direct_child_of(node: "Node", parent_types: list[str]) -> bool:
    if node.parent is None:
        return False
    return node.parent.type in parent_types


def get_function_body_children(node: "Node") -> list["Node"]:
    for child in node.children:
        if child.type == "block":
            return list(child.children)
    return []


def is_at_module_level(node: "Node") -> bool:
    if node.parent is None:
        return True
    return node.parent.type == "module"


def has_descendant_of_type(
    node: "Node",
    target_types: list[str],
) -> bool:
    for child in node.children:
        if child.type in target_types:
            return True
        if has_descendant_of_type(child, target_types):
            return True
    return False


def find_all_nodes(
    root: "Node",
    predicate: Callable[["Node"], bool],
) -> list["Node"]:
    result: list["Node"] = []
    if predicate(root):
        result.append(root)
    for child in root.children:
        result.extend(find_all_nodes(child, predicate))
    return result
