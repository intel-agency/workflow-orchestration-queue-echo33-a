# workflow-orchestration-queue Technology Stack

## Overview

This document details the technology stack for **workflow-orchestration-queue**, a headless agentic orchestration platform that transforms GitHub Issues into automated execution orders for AI agents.

---

## Core Language & Runtime

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| **Primary Language** | Python | 3.12+ | Orchestrator logic, webhook receiver, data models |
| **Shell Scripts** | Bash / PowerShell Core (pwsh) | Latest | Shell bridge execution, auth synchronization |

### Python 3.12+ Selection Rationale
- Native async/await support for non-blocking I/O
- Improved error messages for debugging
- Significant performance enhancements over earlier versions
- Strong ecosystem for web services and API clients

---

## Web Framework & Server

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Web Framework** | FastAPI | High-performance async webhook receiver |
| **ASGI Server** | Uvicorn | Production-ready async HTTP server |
| **API Documentation** | OpenAPI/Swagger | Auto-generated API docs at `/docs` |

### FastAPI Selection Rationale
- Native Pydantic integration for request/response validation
- Automatic OpenAPI schema generation
- Async-first design matching our architecture
- Built-in dependency injection for testability

---

## Data Validation & Settings

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Data Models** | Pydantic | Strict schema validation for WorkItem, TaskType, WorkItemStatus |
| **Settings Management** | pydantic-settings | Environment variable validation and loading |

### Key Models
- `WorkItem` - Unified work item across all components
- `TaskType` - Enum: PLAN, IMPLEMENT, BUGFIX
- `WorkItemStatus` - Enum mapping to GitHub labels

---

## HTTP Client

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Async HTTP Client** | HTTPX | GitHub REST API calls with connection pooling |

### HTTPX Selection Rationale
- Fully asynchronous (unlike `requests`)
- Connection pooling for performance
- Native timeout support
- Compatible with async/await patterns

---

## Package Management

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Package Manager** | uv | Fast dependency installation and resolution |
| **Lock File** | uv.lock | Deterministic package versions |
| **Project Config** | pyproject.toml | Project metadata and dependencies |

### uv Selection Rationale
- Written in Rust for orders-of-magnitude speed improvement
- Drop-in replacement for pip/pip-tools
- Fast DevContainer build times
- Deterministic dependency resolution

---

## Containerization & Isolation

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Container Runtime** | Docker | Worker isolation and reproducibility |
| **Development Environment** | DevContainer | High-fidelity developer and agent environment |
| **Orchestration** | Docker Compose | Multi-container scenarios (e.g., app + database) |

### Security Constraints
- Worker containers run in isolated Docker network
- Resource limits: 2 CPUs, 4GB RAM per worker
- Ephemeral credentials injected as temp environment variables
- Network isolation from host infrastructure

---

## Shell Bridge Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Primary Bridge** | devcontainer-opencode.sh | Worker lifecycle management |
| **Auth Scripts** | gh-auth.ps1, common-auth.ps1 | GitHub App token synchronization |
| **Indexing** | update-remote-indices.ps1 | Vector index maintenance |

### Shell-Bridge Pattern (ADR 07)
The orchestrator interacts with worker environments **exclusively** via shell scripts:
- `up` - Provision Docker network and volumes
- `start` - Launch opencode-server in container
- `prompt` - Execute agent workflow
- `stop` - Graceful shutdown between tasks

---

## LLM Integration

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Agent Runtime** | opencode CLI | LLM agent execution environment |
| **Primary Model** | GLM-5 (zai-coding-plan) | Code generation and orchestration |
| **Fallback Models** | Claude 3.5 Sonnet | Alternative reasoning |

### MCP Servers
- `@modelcontextprotocol/server-sequential-thinking` - Structured reasoning
- `@modelcontextprotocol/server-memory` - Knowledge graph persistence

---

## State Management

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Primary Store** | GitHub Issues | "Markdown as a Database" pattern |
| **State Labels** | agent:queued, agent:in-progress, etc. | Task state machine |
| **Locking** | GitHub Assignees | Distributed lock semaphore |

### State Machine
```
agent:queued → agent:in-progress → agent:success
                              ↘ agent:error
                              ↘ agent:infra-failure
                              ↘ agent:reconciling (stale recovery)
```

---

## Security Components

| Component | Implementation | Purpose |
|-----------|---------------|---------|
| **Webhook Verification** | HMAC SHA256 | Prevent spoofing and prompt injection |
| **Credential Scrubbing** | Regex patterns | Sanitize logs before public posting |
| **Token Management** | Ephemeral env vars | Least-privilege credential injection |

### Scrubbed Patterns
- GitHub PATs: `ghp_*`, `ghs_*`, `gho_*`, `github_pat_*`
- Bearer tokens, API keys (`sk-*`)
- ZhipuAI keys

---

## Logging & Observability

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Structured Logging** | Python logging | Console output with sentinel ID |
| **Heartbeat System** | GitHub comments | Task progress visibility |
| **Audit Trail** | GitHub Issues | Complete history of state changes |

---

## Development Tools

| Tool | Purpose |
|------|---------|
| **gh CLI** | GitHub API interactions |
| **git** | Version control |
| **uvx** | Ephemeral tool execution |

---

## Future Considerations

The architecture supports future integration with:
- **Linear / Jira** - Alternative queue providers via ITaskQueue interface
- **Redis** - Caching layer for high-throughput scenarios
- **PostgreSQL** - Persistent state for multi-tenant deployments
- **Cross-repo polling** - GitHub Search API for org-wide discovery
