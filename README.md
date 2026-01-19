# Ward

MCP server for AI-powered code quality analysis. Detects security issues, bugs, code smells, and performance problems.

Supports: Python, JavaScript/TypeScript, Go, Java, Ruby, Rust, C/C++, and more.

## Quick Start

**Requires Python 3.10+**

### 1. Install

```bash
pip install semgrep ward-mcp
```

### 2. Add to MCP config

**Claude Desktop / Cursor / Windsurf** (`mcp.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ward": {
      "command": "python",
      "args": ["-m", "ward", "mcp"]
    }
  }
}
```

**Claude Code CLI** (`~/.claude/mcp_servers.json`):

```json
{
  "ward": {
    "type": "stdio",
    "command": "python",
    "args": ["-m", "ward", "mcp"]
  }
}
```

Done. Your AI agent now has access to Ward's scanning tools.

## Tools

| Tool | Description |
|------|-------------|
| `scan_remote` | Scan code content directly |
| `scan` | Scan files by path |
| `scan_with_custom_rule` | Scan with custom YAML rules |

## Auto-scan Setup (Optional)

Add to your project's `CLAUDE.md` or `.cursorrules`:

```
After generating code, use ward mcp - scan_remote tool to check for issues.
Format: scan_remote(code_files=[{"path": "filename.py", "content": "code"}])
If issues found: fix and scan again.
```

## Warning - first mcp call will be longer due to installation.

## Troubleshooting

**"semgrep not found"** - Run `pip install semgrep`

**Server won't start** - Check `python -m ward mcp` runs without errors

## License

MIT
