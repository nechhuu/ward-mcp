import os
import sys

from ward.scanner import check_scanner_installed
from ward.server import create_server


def main():
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"

    if len(sys.argv) < 2:
        print("Usage: python -m ward mcp")
        sys.exit(1)

    if sys.argv[1] == "mcp":
        if not check_scanner_installed():
            print("Scanner not found. Install: pip install semgrep")
            sys.exit(1)
        server = create_server()
        server.run()
    else:
        print(f"Unknown command: {sys.argv[1]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
