import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from mcp.types import INTERNAL_ERROR
from mcp.types import INVALID_PARAMS

from ward.models import CodeFile
from ward.models import CodePath

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
}


def detect_language(code_files: list[CodeFile]) -> str | None:
    detected_langs: set[str] = set()
    for f in code_files:
        ext = Path(f.path).suffix.lower()
        if ext in LANGUAGE_EXTENSIONS:
            detected_langs.add(LANGUAGE_EXTENSIONS[ext])
    if len(detected_langs) == 1:
        return detected_langs.pop()
    return None


def safe_join(base_dir: str, untrusted_path: str) -> str:
    base_path = Path(base_dir).resolve()

    if not untrusted_path or untrusted_path == "." or untrusted_path.strip("/") == "":
        return base_path.as_posix()

    if Path(untrusted_path).is_absolute():
        raise ValueError("Untrusted path must be relative")

    full_path = base_path / Path(untrusted_path)

    if not full_path == full_path.resolve():
        raise ValueError(
            f"Untrusted path escapes the base directory!: {untrusted_path}"
        )

    return full_path.as_posix()


def validate_absolute_path(path_to_validate: str, param_name: str) -> str:
    if not Path(path_to_validate).is_absolute():
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message=f"{param_name} must be an absolute path. Received: {path_to_validate}",
            )
        )

    normalized_path = os.path.normpath(path_to_validate)

    if not Path(normalized_path).resolve() == Path(normalized_path):
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message=f"{param_name} contains invalid path traversal sequences",
            )
        )

    return normalized_path


def validate_config(config: str | None = None) -> str:
    if (
        config is None
        or config.startswith("p/")
        or config.startswith("r/")
        or config == "auto"
    ):
        return config or ""
    return validate_absolute_path(config, "config")


def create_temp_files_from_code_content(code_files: list[CodeFile]) -> str:
    temp_dir = None

    try:
        temp_dir = tempfile.mkdtemp(prefix="ward_scan_")

        for file_info in code_files:
            filename = file_info.path
            if not filename:
                continue

            temp_file_path = safe_join(temp_dir, filename)

            try:
                os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)

                with open(temp_file_path, "w") as f:
                    f.write(file_info.content)
            except OSError as e:
                raise McpError(
                    ErrorData(
                        code=INTERNAL_ERROR,
                        message=f"Failed to create or write to file {filename}: {e!s}",
                    )
                ) from e

        return temp_dir
    except Exception as e:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR, message=f"Failed to create temporary files: {e!s}"
            )
        ) from e


def get_scan_args(temp_dir: str, config: str | None = None, file_count: int = 1) -> list[str]:
    memory = min(500 + (file_count * 50), 4000)
    timeout = min(30 + (file_count * 2), 300)

    args = ["scan", "--json", "--quiet", f"--timeout={timeout}", f"--max-memory={memory}"]
    if config:
        args.extend(["--config", config])
    args.append(temp_dir)
    return args


def validate_local_files(local_files: list[CodePath]) -> list[CodeFile]:
    if not local_files:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message="local_files must be a non-empty list of file objects",
            )
        )
    try:
        validated_local_files = []
        for file in local_files:
            path = file.path
            if not Path(path).is_absolute():
                raise McpError(
                    ErrorData(
                        code=INVALID_PARAMS,
                        message="code_files.path must be a absolute path",
                    )
                )
            contents = Path(path).read_text()
            validated_local_files.append(
                CodeFile(path=Path(path).name, content=contents)
            )
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS, message=f"Invalid local code files format: {e!s}"
            )
        ) from e

    return validated_local_files


def validate_remote_files(code_files: list[CodeFile]) -> list[CodeFile]:
    if not code_files:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message="code_files must be a non-empty list of file objects",
            )
        )
    try:
        validated_code_files = [CodeFile.model_validate(file) for file in code_files]

        return validated_code_files
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS, message=f"Invalid remote code files format: {e!s}"
            )
        ) from e


def remove_temp_dir_from_results(results: dict, temp_dir: str) -> None:
    for finding in results.get("results", []):
        if "path" in finding:
            try:
                finding["path"] = os.path.relpath(finding["path"], temp_dir)
            except ValueError:
                continue

    if "scanned" in results.get("paths", {}):
        results["paths"]["scanned"] = [
            os.path.relpath(path, temp_dir) for path in results["paths"]["scanned"]
        ]

    if "skipped" in results.get("paths", {}):
        results["paths"]["skipped"] = [
            os.path.relpath(path, temp_dir) for path in results["paths"]["skipped"]
        ]


def get_git_info(workspace_dir: str | None) -> dict[str, str]:
    if workspace_dir is None:
        return {"username": "unknown", "repo": "unknown", "branch": "unknown"}
    try:
        username = subprocess.run(
            ["git", "config", "user.name"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        repo = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return {"username": username or "unknown", "repo": repo or "unknown", "branch": branch or "unknown"}
    except Exception:
        return {"username": "unknown", "repo": "unknown", "branch": "unknown"}
