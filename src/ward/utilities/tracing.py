import functools
import logging
from collections.abc import Awaitable
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Concatenate
from typing import Generator
from typing import ParamSpec
from typing import TypeVar

from mcp.server.fastmcp.server import Context

P = ParamSpec("P")
R = TypeVar("R")

LOG_DIR = Path.home() / ".ward"
LOG_FILE = LOG_DIR / "debug.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("ward")


@contextmanager
def start_tracing(name: str) -> Generator[None, None, None]:
    logger.info(f"Starting: {name}")
    try:
        yield None
    finally:
        logger.info(f"Finished: {name}")


@contextmanager
def with_span(parent_span: None, name: str) -> Generator[None, None, None]:
    logger.debug(f"Span: {name}")
    yield None


def with_tool_span(
    span_name: str | None = None,
    send_metrics: bool = True,
    is_semgrep_scan: bool = True,
) -> Callable[
    [Callable[Concatenate[Context, P], Awaitable[R]]],
    Callable[Concatenate[Context, P], Awaitable[R]],
]:
    def decorator(
        func: Callable[Concatenate[Context, P], Awaitable[R]],
    ) -> Callable[Concatenate[Context, P], Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(ctx: Context, *args: P.args, **kwargs: P.kwargs) -> R:
            name = span_name or func.__name__
            logger.info(f"Tool called: {name}")
            try:
                result = await func(ctx, *args, **kwargs)
                logger.info(f"Tool succeeded: {name}")
                return result
            except Exception as e:
                logger.error(f"Tool failed: {name} - {e}")
                raise e

        return wrapper

    return decorator
