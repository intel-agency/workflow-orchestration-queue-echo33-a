#!/usr/bin/env bash
set -euo pipefail

# Local driver: build the devcontainer, spin it up, run smoke tests inside, tear down.
# Requires: Docker, @devcontainers/cli (npm install -g @devcontainers/cli)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default to consumer devcontainer config, allow override via environment
DEVCONTAINER_CONFIG="${DEVCONTAINER_CONFIG:-$REPO_ROOT/.devcontainer/devcontainer.json}"

echo "=== Devcontainer Build & Test ==="
echo ""

# Check prerequisites
for cmd in docker devcontainer; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: '$cmd' is required but not found. Install it first."
    exit 1
  fi
done

# Step 1: Build the devcontainer
echo "--- Step 1: Building devcontainer ---"
devcontainer build --workspace-folder "$REPO_ROOT" --config "$DEVCONTAINER_CONFIG"
echo ""

# Step 2: Start the devcontainer
echo "--- Step 2: Starting devcontainer ---"
devcontainer up --workspace-folder "$REPO_ROOT" --config "$DEVCONTAINER_CONFIG"
echo ""

# Step 3: Run tool smoke tests inside the container
echo "--- Step 3: Running tool smoke tests ---"
devcontainer exec --workspace-folder "$REPO_ROOT" --config "$DEVCONTAINER_CONFIG" \
  bash test/test-devcontainer-tools.sh
echo ""

# Step 4: Run Docker resource verification tests
echo "--- Step 4: Running Docker resource verification tests ---"
devcontainer exec --workspace-folder "$REPO_ROOT" --config "$DEVCONTAINER_CONFIG" \
  bash test/test-devcontainer-resources.sh
echo ""

# Step 5: Run prompt assembly tests inside the container
echo "--- Step 5: Running prompt assembly tests ---"
devcontainer exec --workspace-folder "$REPO_ROOT" --config "$DEVCONTAINER_CONFIG" \
  bash test/test-prompt-assembly.sh
echo ""

echo "=== All devcontainer tests complete ==="
