import json
import os
import shutil
import subprocess

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from mcp.types import INTERNAL_ERROR

from ward.models import ScanResult
from ward.utilities.tracing import logger


def check_scanner_installed() -> bool:
    return shutil.which("semgrep") is not None


def _run_process_sync(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    scanner_path = shutil.which("semgrep")
    if scanner_path is None:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message="Scanner engine not found. Install: pip install semgrep",
            )
        )

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["LC_ALL"] = "en_US.UTF-8"
    env["LANG"] = "en_US.UTF-8"

    process = subprocess.run(
        [scanner_path, *args],
        stdin=subprocess.PIPE,
        capture_output=True,
        env=env,
    )
    return process


async def run_scanner_output(args: list[str]) -> str:
    process = _run_process_sync(args)

    if process.stdout is None or process.stderr is None:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message="Error running scanner: stdout or stderr is None",
            )
        )

    if process.returncode not in (0, 1):
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Error running scanner: ({process.returncode}) {process.stderr.decode()}",
            )
        )

    return process.stdout.decode()


def parse_scan_output(json_str: str) -> ScanResult:
    try:
        data = json.loads(json_str)
        return ScanResult.model_validate(data)
    except json.JSONDecodeError as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Failed to parse JSON output: {e!s}",
            )
        ) from e
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Error validating output: {e!s}",
            )
        ) from e


def map_severity(scanner_severity: str, metadata: dict) -> str:
    category = metadata.get("category", "")
    severity_upper = scanner_severity.upper()

    severity_map: dict[str, dict[str, str]] = {
        "ERROR": {
            "security": "critical",
            "correctness": "critical",
            "bug": "critical",
            "performance": "high",
            "default": "high",
        },
        "WARNING": {
            "security": "high",
            "correctness": "high",
            "bug": "high",
            "performance": "medium",
            "default": "medium",
        },
    }

    if category == "security" or "cwe" in metadata:
        cat_key = "security"
    elif category in ("correctness", "bug"):
        cat_key = category
    elif category == "performance":
        cat_key = "performance"
    else:
        cat_key = "default"

    return severity_map.get(severity_upper, {}).get(cat_key, "low")
