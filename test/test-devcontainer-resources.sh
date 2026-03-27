#!/usr/bin/env bash
set -euo pipefail

# Test: Verify Docker network and volume provisioning for DevContainer
# This test verifies that the DevContainer creates proper Docker resources.
# Can run INSIDE the devcontainer (tests current environment) or from HOST.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0
DOCKER_AVAILABLE=false

echo "=== DevContainer Docker Resources Verification ==="
echo ""

# Function to check if running inside a devcontainer
is_inside_devcontainer() {
    [[ -f /.dockerenv ]] || [[ -n "${REMOTE_CONTAINERS_IPC:-}" ]] || [[ -n "${VSCODE_REMOTE_CONTAINERS_SESSION:-}" ]]
}

# Function to get container ID
get_container_id() {
    local workspace="${1:-$REPO_ROOT}"
    docker ps -aq --latest --filter "label=devcontainer.local_folder=${workspace}" 2>/dev/null || echo ""
}

# Helper to get the active container ID for tests
_get_test_container_id() {
    if is_inside_devcontainer; then
        hostname 2>/dev/null || cat /etc/hostname 2>/dev/null || echo ""
    else
        get_container_id "$REPO_ROOT"
    fi
}

# Test 1: Check Docker is available
test_docker_available() {
    echo "--- Test 1: Docker availability ---"
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        echo "  PASS: Docker is available and running"
        PASS=$((PASS + 1))
        DOCKER_AVAILABLE=true
    else
        echo "  SKIP: Docker is not available or not running (may be inside devcontainer without Docker socket)"
        DOCKER_AVAILABLE=false
    fi
}

# Test 2: Check Docker network configuration
test_docker_network() {
    echo "--- Test 2: Docker network configuration ---"
    
    if [[ "$DOCKER_AVAILABLE" != "true" ]]; then
        echo "  SKIP: Docker not available"
        return
    fi
    
    local container_id=$(_get_test_container_id)
    
    if [[ -z "$container_id" ]]; then
        echo "  SKIP: No devcontainer found (expected when not running in devcontainer)"
        return
    fi
    
    # Get network info from container
    local network_name
    network_name=$(docker inspect --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$container_id" 2>/dev/null || echo "")
    
    if [[ -n "$network_name" ]]; then
        echo "  PASS: Container connected to network: $network_name"
        PASS=$((PASS + 1))
        
        # Verify network exists and is functional
        if docker network inspect "$network_name" &>/dev/null; then
            echo "  PASS: Network '$network_name' is inspectable"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: Network '$network_name' cannot be inspected"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  FAIL: Container has no network configuration"
        FAIL=$((FAIL + 1))
    fi
}

# Test 3: Check Docker volume provisioning
test_docker_volumes() {
    echo "--- Test 3: Docker volume provisioning ---"
    
    if [[ "$DOCKER_AVAILABLE" != "true" ]]; then
        echo "  SKIP: Docker not available"
        return
    fi
    
    local container_id=$(_get_test_container_id)
    
    if [[ -z "$container_id" ]]; then
        echo "  SKIP: No devcontainer found (expected when not running in devcontainer)"
        return
    fi
    
    # Check for mounted volumes
    local mounts
    mounts=$(docker inspect --format '{{range .Mounts}}{{.Type}}:{{.Destination}} {{end}}' "$container_id" 2>/dev/null || echo "")
    
    if [[ -n "$mounts" ]]; then
        echo "  PASS: Container has mounted volumes"
        PASS=$((PASS + 1))
        echo "  INFO: Mounts: $mounts"
        
        # Check for workspace mount (Docker destinations are absolute paths)
        local workspace_dest="/workspaces/$(basename "$REPO_ROOT")"
        if docker inspect --format '{{range .Mounts}}{{if eq .Destination "/workspaces"}}{{.Source}}{{end}}{{end}}' "$container_id" 2>/dev/null | grep -q .; then
            echo "  PASS: Workspace volume is mounted"
            PASS=$((PASS + 1))
        elif docker inspect --format '{{range .Mounts}}{{if eq .Destination "'"${workspace_dest}"'"}}{{.Source}}{{end}}{{end}}' "$container_id" 2>/dev/null | grep -q .; then
            echo "  PASS: Workspace volume is mounted at ${workspace_dest}"
            PASS=$((PASS + 1))
        else
            echo "  INFO: No explicit workspace mount found (may use bind mount)"
        fi
    else
        echo "  FAIL: Container has no mounted volumes"
        FAIL=$((FAIL + 1))
    fi
}

# Test 4: Check workspace accessibility (inside container only)
test_workspace_accessibility() {
    echo "--- Test 4: Workspace accessibility ---"
    
    if ! is_inside_devcontainer; then
        echo "  SKIP: Test only runs inside devcontainer"
        return
    fi
    
    # Check workspace directory exists and is writable
    local workspace="${WORKSPACE_FOLDER:-/workspaces/$(basename "$REPO_ROOT")}"
    
    if [[ -d "$workspace" ]]; then
        echo "  PASS: Workspace directory exists: $workspace"
        PASS=$((PASS + 1))
        
        # Test write access
        local test_file="$workspace/.devcontainer-write-test-$$"
        if touch "$test_file" 2>/dev/null && rm -f "$test_file" 2>/dev/null; then
            echo "  PASS: Workspace is writable"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: Workspace is not writable"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  FAIL: Workspace directory not found: $workspace"
        FAIL=$((FAIL + 1))
    fi
}

# Test 5: Check container labels
test_container_labels() {
    echo "--- Test 5: Container labels ---"
    
    if [[ "$DOCKER_AVAILABLE" != "true" ]]; then
        echo "  SKIP: Docker not available"
        return
    fi
    
    local container_id=$(_get_test_container_id)
    
    if [[ -z "$container_id" ]]; then
        echo "  SKIP: No devcontainer found (expected when not running in devcontainer)"
        return
    fi
    
    # Check for devcontainer labels
    local labels
    labels=$(docker inspect --format '{{range $k, $v := .Config.Labels}}{{$k}}={{$v}}\n{{end}}' "$container_id" 2>/dev/null || echo "")
    
    if echo "$labels" | grep -q "devcontainer"; then
        echo "  PASS: Container has devcontainer labels"
        PASS=$((PASS + 1))
    else
        echo "  INFO: No devcontainer-specific labels found"
    fi
}

# Test 6: Check container state
test_container_state() {
    echo "--- Test 6: Container state ---"
    
    if [[ "$DOCKER_AVAILABLE" != "true" ]]; then
        echo "  SKIP: Docker not available"
        return
    fi
    
    local container_id=$(_get_test_container_id)
    
    if [[ -z "$container_id" ]]; then
        echo "  SKIP: No devcontainer found (expected when not running in devcontainer)"
        return
    fi
    
    local state
    state=$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || echo "")
    
    if [[ "$state" == "running" ]]; then
        echo "  PASS: Container is running"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: Container is not running (state: $state)"
        FAIL=$((FAIL + 1))
    fi
}

# Run all tests
test_docker_available
test_docker_network
test_docker_volumes
test_workspace_accessibility
test_container_labels
test_container_state

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
