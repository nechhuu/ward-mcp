from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl


class CodeFile(BaseModel):
    path: str = Field(description="Path of the code file")
    content: str = Field(description="Content of the code file")


class CodePath(BaseModel):
    path: str = Field(description="Absolute path of the code file")


class CodeWithLanguage(BaseModel):
    content: str = Field(description="Content of the code file")
    language: str = Field(
        description="Programming language of the code file", default="python"
    )


class ScanResult(BaseModel):
    version: str = Field(description="Version of the analyzer engine")
    results: list[dict[str, Any]] = Field(description="List of scan results")
    errors: list[dict[str, Any]] = Field(
        description="List of errors encountered during scan", default_factory=list
    )
    paths: dict[str, Any] = Field(description="Paths of the scanned files")
    skipped_rules: list[str] = Field(
        description="List of rules that were skipped during scan", default_factory=list
    )


class ExternalTicket(BaseModel):
    external_slug: str
    url: HttpUrl
    id: int
    linked_issue_ids: list[int]


class ReviewComment(BaseModel):
    external_discussion_id: str
    external_note_id: int | None = None


class Repository(BaseModel):
    name: str
    url: HttpUrl


class Location(BaseModel):
    file_path: str
    line: int
    column: int
    end_line: int
    end_column: int


class SourcingPolicy(BaseModel):
    id: int
    name: str
    slug: str


class Rule(BaseModel):
    name: str
    message: str
    confidence: str
    category: str
    subcategories: list[str]
    vulnerability_classes: list[str]
    cwe_names: list[str]
    owasp_names: list[str]


class Autofix(BaseModel):
    fix_code: str
    explanation: str


class Guidance(BaseModel):
    summary: str
    instructions: str


class Autotriage(BaseModel):
    verdict: str
    reason: str


class Component(BaseModel):
    tag: str
    risk: str


class Assistant(BaseModel):
    autofix: Autofix | None = None
    guidance: Guidance | None = None
    autotriage: Autotriage | None = None
    component: Component | None = None


class Finding(BaseModel):
    id: int
    ref: str
    first_seen_scan_id: int
    syntactic_id: str
    match_based_id: str
    external_ticket: ExternalTicket | None = None
    review_comments: list[ReviewComment]
    repository: Repository
    line_of_code_url: HttpUrl
    triage_state: str
    state: str
    status: str
    severity: str
    confidence: str
    categories: list[str]
    created_at: datetime
    relevant_since: datetime
    rule_name: str
    rule_message: str
    location: Location
    sourcing_policy: SourcingPolicy | None = None
    triaged_at: datetime | None = None
    triage_comment: str | None = None
    triage_reason: str | None = None
    state_updated_at: datetime
    rule: Rule
    assistant: Assistant | None = None


class Issue(BaseModel):
    id: str = Field(description="Unique UUID for this issue")
    type: str = Field(description="Issue type from rule ID")
    severity: str = Field(description="critical/high/medium/low")
    message: str = Field(description="Human-readable description")
    file: str = Field(description="Absolute file path")
    line: int = Field(description="Starting line number (1-indexed)")
    column: int = Field(description="Starting column number (1-indexed)")
    end_line: int = Field(description="Ending line number")
    end_column: int = Field(description="Ending column number")
    code_snippet: str = Field(description="The problematic code")
    rule_url: str = Field(description="Link to rule documentation")


class AnalysisResult(BaseModel):
    file: str | None = Field(description="File path (None for project analysis)")
    issues: list[Issue] = Field(description="List of detected issues")
    summary: dict[str, int] = Field(
        description="Summary counts by severity (total, critical, high, medium, low)"
    )


class LLMExplanation(BaseModel):
    issue_id: str
    explanation: str
    attack_scenario: str | None = None
    fix_recommendation: str | None = None


class LLMFix(BaseModel):
    issue_id: str
    original_code: str
    fixed_code: str
    explanation: str
    diff: str


class GraphNode(BaseModel):
    id: str
    type: str
    name: str
    file: str
    line: int
    taint_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    from_node: str
    to_node: str
    edge_type: str


class AnalyzerRule(BaseModel):
    id: str = Field(description="Unique rule identifier")
    target_concept: str = Field(description="Target concept to detect")
    relationship: str = Field(description="Relationship type to check")
    relationship_target: str | None = Field(
        description="Target concept for relationship", default=None
    )
    severity: str = Field(description="warning/error/info")
    message: str = Field(description="Human-readable message template")
    languages: list[str] = Field(description="Supported languages")
    query_patterns: list[str] = Field(
        description="Patterns for query detection", default_factory=list
    )
    io_patterns: list[str] = Field(
        description="Patterns for I/O detection", default_factory=list
    )


class AnalyzerIssue(BaseModel):
    id: str = Field(description="Unique UUID for this issue")
    rule_id: str = Field(description="Rule ID that triggered this issue")
    severity: str = Field(description="warning/error/info")
    message: str = Field(description="Human-readable description")
    file: str = Field(description="File path")
    line: int = Field(description="Starting line number (1-indexed)")
    column: int = Field(description="Starting column number (1-indexed)")
    end_line: int = Field(description="Ending line number")
    end_column: int = Field(description="Ending column number")
    code_snippet: str = Field(description="The problematic code")


class TreeSitterResult(BaseModel):
    issues: list[AnalyzerIssue] = Field(description="List of detected issues")
    summary: dict[str, int] = Field(
        description="Summary counts by severity (total, error, warning, info)"
    )


class CombinedScanResult(BaseModel):
    scan: ScanResult = Field(description="Security scan results")
    patterns: TreeSitterResult = Field(
        description="Pattern analysis results"
    )
