# workflow-orchestration-queue

Headless agentic orchestration platform that transforms GitHub Issues into automated execution orders for AI agents.

## Overview

workflow-orchestration-queue represents a paradigm shift from **Interactive AI Coding** to **Headless Agentic Orchestration**. Traditional AI developer tools require a human-in-the-loop to navigate files, provide context, and trigger executions. This system replaces manual overhead with persistent, event-driven infrastructure that transforms GitHub Issues into "Execution Orders" autonomously fulfilled by specialized AI agents.

## Architecture (The Four Pillars)

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

### 1. The Ear (Notifier Service)
- FastAPI webhook receiver at `/webhooks/github`
- HMAC SHA256 signature verification
- Intelligent event triaging

### 2. The State (GitHub Issues Queue)
- "Markdown as a Database" pattern
- Label-based state machine tracking
- Distributed locking via assignees

### 3. The Brain (Sentinel Orchestrator)
- Persistent background polling service
- Task claiming with assign-then-verify pattern
- Shell-bridge execution for worker management

### 4. The Hands (Opencode Worker)
- Isolated DevContainer execution
- AI workflow automation via opencode CLI

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- uv package manager

### Local Development

1. **Clone and setup:**
   ```bash
   git clone https://github.com/intel-agency/workflow-orchestration-queue-echo33-a.git
   cd workflow-orchestration-queue-echo33-a
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Install dependencies:**
   ```bash
   uv pip install -e ".[dev]"
   ```

4. **Run the notifier service:**
   ```bash
   python -m orchestration_queue.notifier_service
   ```

5. **Run the sentinel orchestrator:**
   ```bash
   python -m orchestration_queue.orchestrator_sentinel
   ```

### Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up -d

# Run with sentinel enabled
docker-compose --profile sentinel up -d
```

## Project Structure

```
workflow-orchestration-queue/
├── src/orchestration_queue/
│   ├── __init__.py               # Package initialization
│   ├── notifier_service.py       # FastAPI webhook receiver (The Ear)
│   ├── orchestrator_sentinel.py  # Background polling daemon (The Brain)
│   ├── models/
│   │   ├── work_item.py          # WorkItem, TaskType, WorkItemStatus
│   │   └── github_events.py      # GitHub webhook payload schemas
│   └── queue/
│       └── github_queue.py       # ITaskQueue + GitHubQueue implementation
├── tests/
│   ├── conftest.py               # Pytest fixtures
│   ├── unit/                     # Unit tests
│   └── integration/              # Integration tests
├── pyproject.toml                # uv configuration
├── Dockerfile                    # Production container
├── docker-compose.yml            # Local development stack
└── .env.example                  # Environment template
```

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12+ |
| Web Framework | FastAPI |
| ASGI Server | Uvicorn |
| Data Validation | Pydantic |
| HTTP Client | HTTPX |
| Package Manager | uv |
| Containerization | Docker |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check endpoint |
| `/webhooks/github` | POST | GitHub webhook receiver |

## Task State Machine

```
agent:queued → agent:in-progress → agent:success
                              ↘ agent:error
                              ↘ agent:infra-failure
                              ↘ agent:reconciling (stale recovery)
```

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `GITHUB_TOKEN` | GitHub PAT for API access | Yes |
| `GITHUB_ORG` | GitHub organization name | Yes |
| `GITHUB_REPO` | GitHub repository name | Yes |
| `WEBHOOK_SECRET` | HMAC webhook secret | Recommended |
| `SENTINEL_BOT_LOGIN` | Sentinel's GitHub username | For claiming |
| `LOG_LEVEL` | Logging level | No (default: INFO) |

## Documentation

- [Architecture Guide](plan_docs/OS-APOW%20Architecture%20Guide%20v3.2.md)
- [Development Plan](plan_docs/OS-APOW%20Development%20Plan%20v4.2.md)
- [Implementation Specification](plan_docs/OS-APOW%20Implementation%20Specification%20v1.2.md)
- [Tech Stack](plan_docs/tech-stack.md)
- [Architecture Overview](plan_docs/architecture.md)

## License

MIT License - see [LICENSE](LICENSE) for details.
