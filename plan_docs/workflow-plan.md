# Workflow Execution Plan: project-setup

**Generated:** 2026-03-27
**Dynamic Workflow:** project-setup
**Repository:** intel-agency/workflow-orchestration-queue-echo33-a

---

## 1. Overview

### Workflow Name
`project-setup`

### Workflow File Reference
Remote canonical: `https://raw.githubusercontent.com/nam20485/agent-instructions/main/ai_instruction_modules/ai-workflow-assignments/dynamic-workflows/project-setup.md`

### Project Name & Description
**workflow-orchestration-queue (OS-APOW)**

A groundbreaking headless agentic orchestration platform that transforms the paradigm from "Interactive AI Coding" to "Headless Agentic Orchestration." The system translates GitHub Issues into automated Execution Orders fulfilled by specialized AI agents without human intervention. It consists of four pillars:

1. **The Ear (Notifier):** FastAPI webhook receiver for secure event ingestion
2. **The State (Queue):** GitHub Issues as distributed state management ("Markdown as a Database")
3. **The Brain (Sentinel):** Persistent polling orchestrator managing worker lifecycles
4. **The Hands (Worker):** Opencode agent executing in isolated DevContainers

### Total Assignments
6 assignments in sequential execution order

### High-Level Summary
This workflow sets up the project foundation for the workflow-orchestration-queue system. It initializes the repository infrastructure, creates the application plan based on the detailed specification documents, scaffolds the project structure, creates agent-friendly documentation, captures lessons learned, and merges all changes via PR approval.

---

## 2. Project Context Summary

### Key Facts from plan_docs/

| Document | Key Information |
|----------|-----------------|
| **OS-APOW Architecture Guide v3.2** | 4-pillar architecture (Notifier, Queue, Sentinel, Worker), ADRs 07-09, shell-bridge execution, polling-first resiliency, self-bootstrapping lifecycle |
| **OS-APOW Development Plan v4.2** | 4-phase roadmap (Seeding → Sentinel MVP → Ear → Deep Orchestration), user stories, risk assessment |
| **OS-APOW Implementation Specification v1.2** | Tech stack details, project structure, acceptance criteria, test cases |
| **OS-APOW Plan Review** | Code review findings, issues (I-1 to I-10), recommendations (R-1 to R-9) |
| **OS-APOW Simplification Report v1** | Applied simplifications (S-3 to S-11), kept abstractions (S-1, S-2) |

### Technology Stack

| Category | Technology |
|----------|------------|
| **Language** | Python 3.12+ |
| **Web Framework** | FastAPI + Uvicorn |
| **Validation** | Pydantic |
| **HTTP Client** | HTTPX (async) |
| **Package Manager** | uv (Rust-based) |
| **Containerization** | Docker + Docker Compose |
| **Dev Environment** | DevContainers |
| **CLI Tools** | GitHub CLI (gh), opencode CLI |

### Repository Details
- **Repo:** `intel-agency/workflow-orchestration-queue-echo33-a`
- **Branch Strategy:** main (production), develop (integration)
- **Template Source:** `intel-agency/workflow-orchestration-queue-echo33-a`

### Key Constraints & Requirements

1. **Security:** HMAC webhook verification, credential scrubbing, network isolation
2. **Concurrency:** Assign-then-verify pattern using GitHub Assignees as distributed lock
3. **Resiliency:** Polling-first with jittered exponential backoff
4. **Isolation:** Worker containers in dedicated Docker network, 2 CPUs / 4GB RAM limits
5. **Transparency:** "Markdown as a Database" - all state visible in GitHub Issues

### Known Risks (from Plan Review)

| Risk | Mitigation |
|------|------------|
| GitHub API Rate Limiting | GitHub App tokens (5,000 req/hr), local caching |
| LLM Looping/Hallucination | Max steps timeout, cost guardrails, retry counter |
| Concurrency Collisions | Assign-then-verify locking pattern |
| Container Drift | Stop worker between tasks |
| Security Injection | HMAC validation, isolated worker containers |

---

## 3. Assignment Execution Plan

### Assignment 1: init-existing-repository

| Field | Content |
|-------|---------|
| **Short ID** | `init-existing-repository` |
| **Title** | Initiate Existing Repository |
| **Goal** | Initialize the repository with branch protection, GitHub Project, labels, and renamed workspace files |
| **Key Acceptance Criteria** | - New branch `dynamic-workflow-project-setup` created (MUST be first) <br> - Branch protection ruleset imported from `.github/protected-branches_ruleset.json` <br> - GitHub Project created with columns: Not Started, In Progress, In Review, Done <br> - Labels imported from `.github/.labels.json` <br> - Workspace/devcontainer files renamed to project name <br> - PR created from branch to `main` |
| **Project-Specific Notes** | This is a template repository clone. The branch protection ruleset already exists in `.github/protected-branches_ruleset.json`. Labels are defined in `.github/.labels.json`. The devcontainer name should be renamed to `workflow-orchestration-queue-echo33-a-devcontainer`. |
| **Prerequisites** | - GitHub authentication with scopes: `repo`, `project`, `read:project`, `read:user`, `user:email` <br> - `administration: write` scope for branch protection API |
| **Dependencies** | None (first assignment) |
| **Risks / Challenges** | - Branch protection API requires PAT with `administration: write` scope <br> - GitHub Project creation may fail if org limits reached <br> - PR creation requires at least one commit on branch |
| **Events** | None |

---

### Assignment 2: create-app-plan

| Field | Content |
|-------|---------|
| **Short ID** | `create-app-plan` |
| **Title** | Create Application Plan |
| **Goal** | Create a comprehensive application plan based on the specification documents, documented as a GitHub Issue |
| **Key Acceptance Criteria** | - Application template analyzed from `plan_docs/` <br> - `plan_docs/tech-stack.md` created <br> - `plan_docs/architecture.md` created <br> - Planning issue created using `.github/ISSUE_TEMPLATE/application-plan.md` <br> - Milestones created and linked <br> - Issue added to GitHub Project <br> - Labels applied (planning, documentation) |
| **Project-Specific Notes** | The primary app spec is distributed across multiple documents in `plan_docs/`: Architecture Guide, Development Plan, Implementation Specification. These should be synthesized into a unified plan. Key phases from Dev Plan: Phase 0 (Seeding), Phase 1 (Sentinel MVP), Phase 2 (Ear/Webhook), Phase 3 (Deep Orchestration). |
| **Prerequisites** | - GitHub Project exists (from init-existing-repository) <br> - Labels exist (from init-existing-repository) |
| **Dependencies** | `init-existing-repository` (for project, labels, milestones infrastructure) |
| **Risks / Challenges** | - Synthesizing multiple detailed spec documents into one plan <br> - Stakeholder approval iteration cycles <br> - Ensuring all acceptance criteria from Implementation Spec are addressed |
| **Events** | `pre-assignment-begin` → gather-context <br> `on-assignment-failure` → recover-from-error <br> `post-assignment-complete` → report-progress |

---

### Assignment 3: create-project-structure

| Field | Content |
|-------|---------|
| **Short ID** | `create-project-structure` |
| **Title** | Create Project Structure |
| **Goal** | Create the actual project scaffolding: solution structure, Docker configs, dev environment, documentation, CI/CD foundation |
| **Key Acceptance Criteria** | - Solution/project structure created (pyproject.toml, src/ layout) <br> - Dockerfile and docker-compose.yml created <br> - Dev environment scripts created <br> - Documentation structure (README.md, docs/) <br> - CI/CD workflow structure in `.github/workflows/` <br> - All actions pinned to commit SHAs <br> - Repository summary (`.ai-repository-summary.md`) created <br> - Solution builds successfully |
| **Project-Specific Notes** | Tech stack is Python 3.12 with uv package manager. Project structure from Implementation Spec: <br>```\nworkflow-orchestration-queue/\n├── pyproject.toml\n├── uv.lock\n├── src/\n│   ├── notifier_service.py\n│   ├── orchestrator_sentinel.py\n│   ├── models/\n│   │   ├── work_item.py\n│   │   └── github_events.py\n│   └── queue/\n│       └── github_queue.py\n├── scripts/\n├── local_ai_instruction_modules/\n└── docs/\n``` |
| **Prerequisites** | Application plan exists (issue or `APP_PLAN.md`) |
| **Dependencies** | `create-app-plan` (for tech stack and architecture decisions) |
| **Risks / Challenges** | - Docker healthcheck commands should use Python stdlib, not curl <br> - Editable installs (`uv pip install -e .`) require source copied before install <br> - All GitHub Actions must be SHA-pinned |
| **Events** | None |

---

### Assignment 4: create-agents-md-file

| Field | Content |
|-------|---------|
| **Short ID** | `create-agents-md-file` |
| **Title** | Create AGENTS.md File |
| **Goal** | Create a comprehensive `AGENTS.md` file at repository root with context and instructions for AI coding agents |
| **Key Acceptance Criteria** | - `AGENTS.md` exists at repository root <br> - Contains project overview, setup commands, project structure <br> - Contains code style conventions and testing instructions <br> - All listed commands have been validated by running them <br> - Committed and pushed to working branch |
| **Project-Specific Notes** | This project uses Python 3.12 with uv, FastAPI, Pydantic. Key commands: <br> - Install: `uv sync` <br> - Run tests: `uv run pytest` <br> - Run sentinel: `uv run python src/orchestrator_sentinel.py` <br> - Run notifier: `uv run uvicorn src.notifier_service:app` <br> Should cross-reference with existing README.md and `.ai-repository-summary.md`. |
| **Prerequisites** | - Repository initialized <br> - Application plan exists <br> - Project structure created |
| **Dependencies** | `create-project-structure` (needs actual structure to document) |
| **Risks / Challenges** | - Commands must be validated by actually running them <br> - Avoid duplicating README.md content - complement it <br> - Ensure consistency with `.ai-repository-summary.md` |
| **Events** | None |

---

### Assignment 5: debrief-and-document

| Field | Content |
|-------|---------|
| **Short ID** | `debrief-and-document` |
| **Title** | Debrief and Document Learnings |
| **Goal** | Capture key learnings, insights, and areas for improvement from the completed workflow |
| **Key Acceptance Criteria** | - Detailed report created using structured template <br> - Report in `.md` file format <br> - All 12 sections complete <br> - All deviations documented <br> - Execution trace saved as `debrief-and-document/trace.md` <br> - Committed and pushed |
| **Project-Specific Notes** | The debrief should capture: <br> - Any issues with the template repository setup <br> - Deviations from the specification documents <br> - Lessons learned about the 4-pillar architecture <br> - Recommendations for Phase 2 and Phase 3 implementation |
| **Prerequisites** | All previous assignments completed |
| **Dependencies** | All previous assignments (to have content to debrief) |
| **Risks / Challenges** | - Thoroughness of the 12-section report <br> - Capturing all deviations accurately <br> - Stakeholder approval iteration |
| **Events** | None |

---

### Assignment 6: pr-approval-and-merge

| Field | Content |
|-------|---------|
| **Short ID** | `pr-approval-and-merge` |
| **Title** | Pull Request Approval and Merge |
| **Goal** | Complete the full PR approval and merge process: resolve comments, obtain approval, merge, close issues |
| **Key Acceptance Criteria** | - All CI/CD status checks pass <br> - CI remediation loop executed (up to 3 attempts) <br> - Code review delegated to `code-reviewer` subagent (NOT self-review) <br> - Auto-reviewer comments waited for <br> - `ai-pr-comment-protocol.md` workflow executed <br> - All review threads resolved <br> - Stakeholder approval obtained <br> - Merge performed (or blocked reason documented) <br> - Source branch deleted <br> - Related issues closed/updated |
| **Project-Specific Notes** | The PR was created in `init-existing-repository` assignment. This assignment resolves all review comments, gets approval, and merges. Must follow the PR Comment Protocols exactly. |
| **Prerequisites** | - PR exists (created in init-existing-repository) <br> - All code changes committed and pushed |
| **Dependencies** | `debrief-and-document` (all work must be complete before merge) |
| **Risks / Challenges** | - CI failures requiring remediation <br> - Multiple rounds of review comments <br> - Merge conflicts with main branch <br> - Auto-reviewer (Copilot, CodeQL) delays |
| **Events** | None |

---

## 4. Sequencing Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    project-setup Workflow Sequence                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────┐
│ 1. init-existing-repository    │
│    - Create branch             │
│    - Import ruleset            │
│    - Create Project            │
│    - Import labels             │
│    - Rename files              │
│    - Create PR                 │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ 2. create-app-plan             │
│    - Analyze spec docs         │
│    - Create tech-stack.md      │
│    - Create architecture.md    │
│    - Create planning issue     │
│    - Create milestones         │
│    - Link to Project           │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ 3. create-project-structure    │
│    - Create src/ layout        │
│    - Create Docker configs     │
│    - Create dev environment    │
│    - Create docs structure     │
│    - Create CI/CD workflows    │
│    - Create .ai-repo-summary   │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ 4. create-agents-md-file       │
│    - Create AGENTS.md          │
│    - Document commands         │
│    - Validate commands         │
│    - Document conventions      │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ 5. debrief-and-document        │
│    - Create debrief report     │
│    - Document lessons learned  │
│    - Create execution trace    │
│    - Get stakeholder approval  │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ 6. pr-approval-and-merge       │
│    - Verify CI passes          │
│    - Delegate code review      │
│    - Resolve all comments      │
│    - Get approval              │
│    - Merge PR                  │
│    - Close issues              │
└────────────────────────────────┘
```

---

## 5. Open Questions

The following questions may need stakeholder input before or during execution:

| # | Question | Context | Resolution Needed Before |
|---|----------|---------|--------------------------|
| 1 | Should the planning issue be created in this repo or a separate planning repo? | Implementation Spec mentions configurable repo via env vars | `create-app-plan` |
| 2 | What is the target milestone for the initial Sentinel MVP? | Dev Plan defines phases but not specific dates | `create-app-plan` |
| 3 | Should the Phase 3 features (Architect Sub-Agent, Self-Healing) be included in the planning issue or deferred? | Plan Review recommends moving to appendix | `create-app-plan` |
| 4 | Who is the designated code reviewer for the PR? | `pr-approval-and-merge` requires delegated review, not self-review | `pr-approval-and-merge` |

---

## 6. Summary

This workflow execution plan covers the complete `project-setup` workflow for the **workflow-orchestration-queue** project. The workflow consists of 6 sequential assignments that will:

1. **Initialize** the repository infrastructure (branch, project, labels, PR)
2. **Plan** the application based on detailed specification documents
3. **Structure** the project with proper scaffolding and CI/CD
4. **Document** with agent-friendly AGENTS.md
5. **Debrief** to capture lessons learned
6. **Merge** all changes via approved PR

The project is a sophisticated headless agentic orchestration platform using Python 3.12, FastAPI, Pydantic, and Docker. Key technical considerations include the shell-bridge execution pattern, assign-then-verify concurrency control, and polling-first resiliency model.

---

**Plan Status:** Ready for Execution
**Created By:** Planner Agent
**Approved By:** _Pending stakeholder approval_
