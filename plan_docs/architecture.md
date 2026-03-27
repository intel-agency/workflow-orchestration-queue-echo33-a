# workflow-orchestration-queue Architecture

## Executive Summary

workflow-orchestration-queue represents a paradigm shift from **Interactive AI Coding** to **Headless Agentic Orchestration**. Traditional AI developer tools require a human-in-the-loop to navigate files, provide context, and trigger executions. This system replaces manual overhead with persistent, event-driven infrastructure that transforms GitHub Issues into "Execution Orders" autonomously fulfilled by specialized AI agents.

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         workflow-orchestration-queue                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│  │   THE EAR    │────▶│  THE STATE   │────▶│  THE BRAIN   │                │
│  │   (Notifier) │     │   (Queue)    │     │  (Sentinel)  │                │
│  └──────────────┘     └──────────────┘     └──────────────┘                │
│         │                    │                    │                         │
│         │                    │                    ▼                         │
│         │                    │           ┌──────────────┐                  │
│         │                    │           │  THE HANDS   │                  │
│         │                    │           │   (Worker)   │                  │
│         │                    │           └──────────────┘                  │
│         │                    │                    │                         │
│         ▼                    ▼                    ▼                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     GitHub (State Persistence)                       │   │
│  │   Issues • Labels • Comments • Milestones • Assignees               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Four Pillars

### 1. The Ear (Work Event Notifier)

**Technology:** Python 3.12, FastAPI, UV, Pydantic

**Role:** Primary gateway for external stimuli and asynchronous triggers.

**Responsibilities:**
- **Secure Webhook Ingestion** - Hardened endpoint at `/webhooks/github`
- **Cryptographic Verification** - HMAC SHA256 validation against `WEBHOOK_SECRET`
- **Intelligent Event Triage** - Parse issue body/labels into unified WorkItem
- **Queue Initialization** - Apply `agent:queued` label via GitHub API

**Security Model:**
- Rejects requests with invalid/missing `X-Hub-Signature-256`
- Prevents "Prompt Injection via Webhook" attacks
- Returns 401 Unauthorized before any JSON parsing

---

### 2. The State (Work Queue)

**Technology:** GitHub Issues, Labels, Milestones

**Philosophy:** "Markdown as a Database" - leveraging GitHub as the persistence layer for world-class audit logs, transparent versioning, and built-in UI.

**State Machine (Label Logic):**

| Label | Meaning |
|-------|---------|
| `agent:queued` | Task validated, awaiting Sentinel |
| `agent:in-progress` | Sentinel claimed the issue |
| `agent:reconciling` | Stale task being recovered |
| `agent:success` | Terminal success (PR created, tests passed) |
| `agent:error` | Technical failure (logs posted to issue) |
| `agent:infra-failure` | Infrastructure failure (container/build error) |
| `agent:stalled-budget` | Cost guardrails exceeded (future) |

**Concurrency Control:**
- GitHub "Assignees" act as distributed lock semaphore
- **Assign-then-verify pattern**: (1) assign, (2) re-fetch, (3) verify assignee
- Prevents race conditions between multiple Sentinel instances

---

### 3. The Brain (Sentinel Orchestrator)

**Technology:** Python (Async Background Service), Shell Scripts, Docker CLI

**Role:** Persistent supervisor managing worker lifecycle and mapping intent to execution.

**Lifecycle:**

1. **Polling Discovery** (every 60s)
   - Query GitHub Issues API for `agent:queued` label
   - Jittered exponential backoff on rate limits (403/429)

2. **Auth Synchronization**
   - Run `gh-auth.ps1` for GitHub App tokens

3. **Task Claiming**
   - Assign-then-verify distributed locking
   - Post claim comment with start time

4. **Shell-Bridge Execution**
   - `devcontainer-opencode.sh up` - Provision infrastructure
   - `devcontainer-opencode.sh start` - Launch opencode-server
   - `devcontainer-opencode.sh prompt "{instruction}"` - Execute workflow

5. **Heartbeat System**
   - Post status comment every 5 minutes
   - Background `asyncio` coroutine running concurrently

6. **Environment Reset**
   - Stop worker container between tasks
   - Prevent state bleed while enabling fast restart

7. **Graceful Shutdown**
   - Handle `SIGTERM`/`SIGINT` signals
   - Finish current task before exiting

---

### 4. The Hands (Opencode Worker)

**Technology:** opencode CLI, LLM Core (GLM-5), DevContainer

**Role:** Execution layer where actual coding happens.

**Worker Capabilities:**
- **Contextual Awareness** - Access to project structure and vector indices
- **Instructional Logic** - Reads markdown workflow modules from `/local_ai_instruction_modules/`
- **Verification** - Runs local test suites before submitting PRs

**Isolation:**
- Dedicated Docker network (no host access)
- Resource constraints (2 CPUs, 4GB RAM)
- Ephemeral credentials (destroyed on exit)

---

## Data Flow (Happy Path)

```
1. User opens GitHub Issue with [Application Plan] template
                     │
                     ▼
2. GitHub Webhook hits Notifier (FastAPI)
                     │
                     ▼
3. Notifier verifies HMAC signature, validates template
                     │
                     ▼
4. Notifier adds agent:queued label via GitHub API
                     │
                     ▼
5. Sentinel poller discovers queued issue (60s interval)
                     │
                     ▼
6. Sentinel claims task (assign-then-verify)
   - Assigns itself
   - Re-fetches to verify
   - Updates labels to agent:in-progress
                     │
                     ▼
7. Sentinel syncs repo via git clone/pull
                     │
                     ▼
8. Sentinel executes shell bridge:
   - devcontainer-opencode.sh up
   - devcontainer-opencode.sh start
   - devcontainer-opencode.sh prompt "Run workflow..."
                     │
                     ▼
9. Worker executes workflow, creates PRs
   - Heartbeat comments every 5 minutes
                     │
                     ▼
10. Sentinel detects completion, updates to agent:success
```

---

## Key Architectural Decisions (ADRs)

### ADR 07: Standardized Shell-Bridge Execution

**Decision:** Orchestrator interacts with worker environment *exclusively* via `devcontainer-opencode.sh`.

**Rationale:** Reusing shell scripts ensures environment parity between AI and human developers, preventing "Configuration Drift."

**Consequence:** Python code remains lightweight (logic/state); shell handles "Heavy Lifting" (container orchestration).

---

### ADR 08: Polling-First Resiliency Model

**Decision:** Sentinel uses polling as primary discovery; webhooks are optimization.

**Rationale:** Webhooks are "Fire and Forget" - lost if server is down. Polling ensures self-healing on restart.

**Consequence:** System inherently resilient against server downtime and network partitions.

---

### ADR 09: Provider-Agnostic Interface Layer

**Decision:** Queue interactions abstracted behind `ITaskQueue` interface (Strategy Pattern).

**Rationale:** Phase 1 targets GitHub, but architecture supports Linear, Notion, or SQL queues without orchestrator rewrite.

**Interface Methods:**
- `fetch_queued()`
- `claim_task(id, sentinel_id)`
- `update_progress(id, log_line)`
- `finish_task(id, artifacts)`

---

## Security Architecture

### Network Isolation
```
┌─────────────────────────────────────────────────────────┐
│                      Host Server                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Sentinel Orchestrator               │    │
│  └─────────────────────────────────────────────────┘    │
│                         │                                │
│                         │ Shell Bridge                   │
│                         ▼                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │          Isolated Docker Network                 │    │
│  │  ┌─────────────────────────────────────────┐    │    │
│  │  │         Worker DevContainer              │    │    │
│  │  │   • No host network access               │    │    │
│  │  │   • No local subnet access               │    │    │
│  │  │   • Internet access only                 │    │    │
│  │  └─────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Credential Management
- Tokens injected as temporary environment variables
- Never written to disk in container
- Destroyed when container exits
- All public logs scrubbed via `scrub_secrets()`

---

## Self-Bootstrapping Lifecycle

```
Stage 0 (Seeding)
    │  Manual clone of template repo
    ▼
Stage 1 (Manual Launch)
    │  devcontainer-opencode.sh up
    ▼
Stage 2 (Project Setup)
    │  orchestrate-project-setup workflow
    │  • Configure environment
    │  • Index codebase
    ▼
Stage 3 (Handover)
    │  Start sentinel.py service
    │  • AI builds its own features
    │  • Human interacts only via GitHub issues
    ▼
Stage 4 (Autonomous)
    │  System manages its own evolution
    │  • Phase 2 (Webhook) built by AI
    │  • Phase 3 (Deep Orchestration) built by AI
```

---

## Project Structure

```
workflow-orchestration-queue/
├── pyproject.toml               # uv dependencies and metadata
├── uv.lock                      # Deterministic lockfile
├── src/
│   ├── notifier_service.py      # FastAPI webhook receiver
│   ├── orchestrator_sentinel.py # Background polling daemon
│   ├── models/
│   │   ├── work_item.py         # Unified WorkItem, TaskType, WorkItemStatus
│   │   └── github_events.py     # GitHub webhook payload schemas
│   └── queue/
│       └── github_queue.py      # ITaskQueue + GitHubQueue implementation
├── scripts/
│   ├── devcontainer-opencode.sh # Core shell bridge
│   ├── gh-auth.ps1              # GitHub App auth
│   └── update-remote-indices.ps1 # Vector index sync
├── local_ai_instruction_modules/
│   ├── create-app-plan.md       # Planning workflow
│   ├── perform-task.md          # Implementation workflow
│   └── analyze-bug.md           # Bugfix workflow
└── docs/                        # Architecture and user documentation
```

---

## Risk Mitigation Summary

| Risk | Mitigation |
|------|------------|
| GitHub API Rate Limiting | GitHub App tokens (5,000 req/hr); local caching; long-polling |
| LLM Looping/Hallucination | Max steps timeout; cost guardrails; retry counter |
| Concurrency Collisions | Assign-then-verify locking pattern |
| Container Drift | Stop container between tasks |
| Security Injection | HMAC validation; network isolation; credential scrubbing |
