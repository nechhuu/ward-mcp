# Caching Layer
#
# Components to implement:
# - IssueCache: LRU cache for 100 issues by UUID
# - LLMResponseCache: TTL cache (7 days) for explanations/fixes
# - Key format: "explain:{issue_type}:{code_hash}"
#
# Storage: In-memory dict for MVP


class IssueCache:
    pass


class LLMResponseCache:
    pass
