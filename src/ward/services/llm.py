# Phase 1: LLM Intelligence Layer
#
# Components to implement:
# - AnthropicClient: API wrapper with retry, timeout
# - ContextExtractor: AST-based function extraction
# - TokenEstimator: ~4 chars per token
# - ExplanationGenerator: Security explanation prompts
# - FixGenerator: Code fix prompts with diff
#
# Environment: ANTHROPIC_API_KEY
# Model: claude-sonnet-4-20250514
# Max tokens: 500 (explain), 1000 (fix)


async def explain_issue(issue_id: str) -> str:
    raise NotImplementedError("Phase 1: LLM service not implemented")


async def suggest_fix(issue_id: str) -> dict:
    raise NotImplementedError("Phase 1: LLM service not implemented")


class AnthropicClient:
    pass


class ContextExtractor:
    pass


class ExplanationGenerator:
    pass


class FixGenerator:
    pass
