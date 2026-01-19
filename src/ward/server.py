import json
import os
import shutil
import tempfile
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import Prompt
from mcp.server.fastmcp.resources.types import FunctionResource
from mcp.server.fastmcp.server import Context
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from mcp.types import INTERNAL_ERROR
from mcp.types import INVALID_PARAMS
from pydantic import Field
from pydantic import ValidationError

from ward.models import AnalyzerIssue
from ward.models import CodeFile
from ward.models import CodePath
from ward.models import CombinedScanResult
from ward.models import ScanResult
from ward.models import TreeSitterResult
from ward.scanner import check_scanner_installed
from ward.scanner import run_scanner_output
from ward.utilities.tracing import logger
from ward.utilities.tracing import with_tool_span
from ward.utilities.utils import create_temp_files_from_code_content
from ward.utilities.utils import detect_language
from ward.utilities.utils import get_scan_args
from ward.utilities.utils import LANGUAGE_EXTENSIONS
from ward.utilities.utils import remove_temp_dir_from_results
from ward.utilities.utils import validate_config
from ward.utilities.utils import validate_local_files
from ward.utilities.utils import validate_remote_files

TREE_SITTER_AVAILABLE = False
try:
    from ward.analyzer.engine import run_treesitter_analysis
    TREE_SITTER_AVAILABLE = True
except ImportError:
    pass

CATEGORY_CONFIG_MAP: dict[str, str] = {
    "all": "p/default",
    "security": "p/security-audit",
    "bugs": "p/default",
    "performance": "p/default",
}


def resolve_config(category: str, config: str | None, code_files: list[CodeFile]) -> str:
    if config:
        return config
    if category == "quality":
        detected = detect_language(code_files)
        if detected:
            return f"p/{detected}"
        return "p/default"
    return CATEGORY_CONFIG_MAP.get(category, "p/default")


REMOTE_CODE_FILES_FIELD = Field(
    description="List of dictionaries with 'path' and 'content' keys"
)
LOCAL_CODE_FILES_FIELD = Field(
    description="List of dictionaries with 'path' pointing to the absolute path of the code file"
)
CONFIG_FIELD = Field(
    description="Optional configuration string (e.g. 'p/docker', 'p/xss', 'auto')",
    default=None,
)
RULE_FIELD = Field(description="YAML rule string")
RULE_ID_FIELD = Field(description="Rule ID")
CODE_FIELD = Field(description="The code to get the AST for")
LANGUAGE_FIELD = Field(description="The programming language of the code")
ISSUE_ID_FIELD = Field(description="Issue ID (UUID) from previous analysis")


@with_tool_span(is_semgrep_scan=False)
async def get_rule_schema(ctx: Context) -> str:
    """Get the JSON schema for writing custom analysis rules."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get("https://semgrep.dev/api/schema_url")
            response.raise_for_status()
            data: dict[str, str] = response.json()
            schema_url: str = data["schema_url"]

            response = await client.get(schema_url)
            response.raise_for_status()
            return str(response.text)
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Error getting rule schema: {e!s}",
            )
        ) from e


@with_tool_span(is_semgrep_scan=False)
async def get_supported_languages(ctx: Context) -> list[str]:
    """List all programming languages supported by the analyzer."""
    args = ["show", "supported-languages"]

    languages = await run_scanner_output(args)
    return [lang.strip() for lang in languages.strip().split("\n") if lang.strip()]


@with_tool_span()
async def scan_with_custom_rule(
    ctx: Context,
    code_files: list[CodeFile] = REMOTE_CODE_FILES_FIELD,
    rule: str = Field(description="Custom YAML rule to apply. Use write_custom_rule prompt for help writing rules."),
) -> ScanResult:
    """Scan code with a custom YAML rule for project-specific patterns or requirements."""
    validated_code_files = validate_remote_files(code_files)
    temp_dir = None
    try:
        temp_dir = create_temp_files_from_code_content(validated_code_files)
        rule_file_path = os.path.join(temp_dir, "rule.yaml")
        with open(rule_file_path, "w", encoding="utf-8") as f:
            f.write(rule)

        args = get_scan_args(temp_dir, rule_file_path, len(validated_code_files))
        output = await run_scanner_output(args)
        results: ScanResult = ScanResult.model_validate_json(output)

        remove_temp_dir_from_results(results.model_dump(), temp_dir)
        return results

    except McpError as e:
        raise e
    except ValidationError as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR, message=f"Error parsing scan output: {e!s}"
            )
        ) from e
    except Exception as e:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=f"Error running scan: {e!s}")
        ) from e

    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


@with_tool_span(is_semgrep_scan=False)
async def get_abstract_syntax_tree(
    ctx: Context,
    code: str = CODE_FIELD,
    language: str = LANGUAGE_FIELD,
) -> str:
    """Parse code and return its Abstract Syntax Tree (AST) in JSON format for deep analysis."""
    temp_dir = None
    temp_file_path = ""
    try:
        temp_dir = tempfile.mkdtemp(prefix="ward_ast_")
        temp_file_path = os.path.join(temp_dir, "code.txt")

        with open(temp_file_path, "w") as f:
            f.write(code)

        args = [
            "--dump-ast",
            "-l",
            language,
            "--json",
            temp_file_path,
        ]
        return await run_scanner_output(args)

    except McpError as e:
        raise e
    except ValidationError as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR, message=f"Error parsing output: {e!s}"
            )
        ) from e
    except OSError as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Failed to create or write to file {temp_file_path}: {e!s}",
            )
        ) from e
    except Exception as e:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=f"Error running scan: {e!s}")
        ) from e
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


@with_tool_span()
async def _run_scan(
    ctx: Context,
    code_files: list[CodeFile],
    config: str = "p/default",
) -> ScanResult:
    temp_dir = None
    try:
        temp_dir = create_temp_files_from_code_content(code_files)
        args = get_scan_args(temp_dir, config, len(code_files))
        output = await run_scanner_output(args)
        results: ScanResult = ScanResult.model_validate_json(output)
        remove_temp_dir_from_results(results.model_dump(), temp_dir)

        return results

    except McpError as e:
        raise e
    except ValidationError as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR, message=f"Error parsing scan output: {e!s}"
            )
        ) from e
    except Exception as e:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=f"Error running scan: {e!s}")
        ) from e

    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _get_language_from_path(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    return LANGUAGE_EXTENSIONS.get(ext)


async def _run_treesitter_on_files(
    code_files: list[CodeFile],
) -> TreeSitterResult:
    if not TREE_SITTER_AVAILABLE:
        return TreeSitterResult(
            issues=[],
            summary={"total": 0, "error": 0, "warning": 0, "info": 0},
        )

    files_with_lang: list[tuple[str, str, str]] = []
    for cf in code_files:
        lang = _get_language_from_path(cf.path)
        if lang:
            files_with_lang.append((cf.path, cf.content, lang))

    if not files_with_lang:
        return TreeSitterResult(
            issues=[],
            summary={"total": 0, "error": 0, "warning": 0, "info": 0},
        )

    return await run_treesitter_analysis(files_with_lang)


@with_tool_span()
async def scan_remote(
    ctx: Context,
    code_files: list[CodeFile] = Field(
        description="REQUIRED: Code to scan. Pass the code you are about to write/edit. Format: [{\"path\": \"filename.py\", \"content\": \"code here\"}]"
    ),
    category: str = Field(
        default="all",
        description="Analysis focus: 'all' (comprehensive), 'security' (vulnerabilities), 'quality' (code smells), 'bugs' (correctness), 'performance'",
    ),
    config: str | None = Field(
        default=None,
        description="Advanced: Override with specific config (e.g. 'p/python', 'p/security-audit'). Takes precedence over category.",
    ),
) -> CombinedScanResult:
    """Scan code content for issues. Use AFTER generating code. Pass code as string, not file path."""
    validated_code_files = validate_remote_files(code_files)
    resolved_config = resolve_config(category, config, validated_code_files)

    scan_result = await _run_scan(ctx, validated_code_files, resolved_config)
    treesitter_result = await _run_treesitter_on_files(validated_code_files)

    return CombinedScanResult(
        scan=scan_result,
        patterns=treesitter_result,
    )


@with_tool_span()
async def scan(
    ctx: Context,
    code_files: list[CodePath] = Field(
        description="List of absolute file paths to scan. Format: [{\"path\": \"/absolute/path/to/file.py\"}]"
    ),
    category: str = Field(
        default="all",
        description="Analysis focus: 'all' (comprehensive), 'security' (vulnerabilities), 'quality' (code smells), 'bugs' (correctness), 'performance'",
    ),
    config: str | None = Field(
        default=None,
        description="Advanced: Override with specific config (e.g. 'p/python', 'p/security-audit'). Takes precedence over category.",
    ),
) -> ScanResult:
    """Scan existing files on disk for issues. Pass absolute file paths. For generated code not yet saved, use scan_remote instead."""
    validated_local_files = validate_local_files(code_files)
    resolved_config = resolve_config(category, config, validated_local_files)
    return await _run_scan(ctx, validated_local_files, resolved_config)


@with_tool_span(is_semgrep_scan=False)
async def explain_issue(
    ctx: Context,
    issue_id: str = ISSUE_ID_FIELD,
) -> str:
    """[NOT IMPLEMENTED] Get detailed explanation for a detected issue."""
    raise NotImplementedError(
        "Phase 1: LLM service not implemented. "
        "This tool will use Claude API to explain security issues in detail."
    )


@with_tool_span(is_semgrep_scan=False)
async def suggest_fix(
    ctx: Context,
    issue_id: str = ISSUE_ID_FIELD,
) -> str:
    """[NOT IMPLEMENTED] Get suggested code fix for a detected issue."""
    raise NotImplementedError(
        "Phase 1: LLM service not implemented. "
        "This tool will use Claude API to suggest code fixes for security issues."
    )


@with_tool_span()
async def analyze_cross_file(
    ctx: Context,
    project_path: str = Field(description="Absolute path to project root"),
) -> str:
    """[NOT IMPLEMENTED] Analyze cross-file dependencies and taint flow."""
    raise NotImplementedError(
        "Phase 2: Graph analysis not implemented. "
        "This tool will perform cross-file taint analysis to detect complex vulnerabilities."
    )


def setup_ward() -> str:
    """Instructions for setting up Ward MCP server."""
    prompt_template = """
    You are setting up Ward MCP server.

    1) Install the analyzer engine:
    - Run: `pip install semgrep`

    2) Verify installation:
    - Run: `semgrep --version`

    3) Test the server:
    - Run: `python -m ward mcp`

    Ward provides security scanning with placeholders for:
    - Phase 1: LLM-powered explanations and fixes (explain_issue, suggest_fix)
    - Phase 2: Cross-file taint analysis (analyze_cross_file)
    """
    return prompt_template


def write_custom_rule(
    code: str = CODE_FIELD,
    language: str = LANGUAGE_FIELD,
) -> str:
    """Generate a custom YAML rule for detecting specific code patterns."""
    prompt_template = """You are an expert at writing code analysis rules.

Your task is to analyze a given piece of code and create a rule
that can detect specific patterns or issues within that code.

Here is the code you need to analyze:

<code>
{code}
</code>

The code is written in the following programming language:

<language>
{language}
</language>

To write an effective rule, follow these guidelines:
1. Identify a specific pattern, vulnerability, or coding standard violation
2. Create a rule that matches this pattern as precisely as possible
3. Use pattern syntax with metavariables and ellipsis operators
4. Provide a clear and concise message

Write your rule in YAML format with the following keys:
- rules
- id
- pattern
- message
- severity (one of: ERROR, WARNING, INFO, INVENTORY, EXPERIMENT, CRITICAL, HIGH, MEDIUM, LOW)
- languages

Output your rule inside <rule> tags.
"""
    return prompt_template.format(code=code, language=language)


async def _get_rule_schema() -> str:
    schema_url = "https://raw.githubusercontent.com/semgrep/semgrep-interfaces/refs/heads/main/rule_schema_v1.yaml"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(schema_url)
            response.raise_for_status()
            return str(response.text)
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR, message=f"Error loading rule schema: {e!s}"
            )
        ) from e


async def _get_rule_yaml(rule_id: str = RULE_ID_FIELD) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"https://semgrep.dev/c/r/{rule_id}")
            response.raise_for_status()
            return str(response.text)
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR, message=f"Error loading rule: {e!s}"
            )
        ) from e


def create_server() -> FastMCP:
    if not check_scanner_installed():
        logger.error("Scanner engine not installed")
        raise RuntimeError("Scanner engine not found. Install: pip install semgrep")

    mcp = FastMCP(
        name="ward",
        instructions="""Ward is a code quality analyzer. Detects security issues, bugs, code smells, and performance problems.

MANDATORY WORKFLOW - After generating code:
1. Generate your code
2. Call scan_remote with the generated code
3. If issues found: fix them and scan again

TOOL SELECTION:
- scan_remote: Use when you have CODE CONTENT (code you just generated). Pass code as string.
- scan: Use when you have FILE PATHS to existing files on disk. Pass absolute paths.

Example scan_remote call:
scan_remote(code_files=[{"path": "app.py", "content": "your code here"}], category="all")""",
    )

    mcp.add_tool(get_rule_schema)
    mcp.add_tool(get_supported_languages)
    mcp.add_tool(scan_with_custom_rule)
    mcp.add_tool(get_abstract_syntax_tree)
    mcp.add_tool(scan)
    mcp.add_tool(scan_remote)

    mcp.add_tool(explain_issue)
    mcp.add_tool(suggest_fix)
    mcp.add_tool(analyze_cross_file)

    mcp.add_prompt(Prompt.from_function(write_custom_rule))
    mcp.add_prompt(Prompt.from_function(setup_ward))

    mcp.add_resource(
        FunctionResource.from_function(
            uri="ward://rule/schema", fn=_get_rule_schema
        )
    )
    mcp.add_resource(
        FunctionResource.from_function(
            uri="ward://rule/{rule_id}/yaml", fn=_get_rule_yaml
        )
    )

    return mcp
