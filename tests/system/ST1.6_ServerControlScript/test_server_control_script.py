# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
System Test: ST1.6 - Server Control Script Integration with All Servers

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for server control script integration with all servers

Related Requirements: NF1.2
Related Tasks: T054
Related Architecture: DO1.1
Related Tests: ST1.6

Recent Changes:
- Initial implementation
"""

import pytest
import subprocess
import os
from pathlib import Path


def _run_script(
    script_path: Path, test_env_file: Path, args: list[str], timeout: int
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(script_path), "--env", str(test_env_file), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _is_running(output: str) -> bool:
    text = output.lower()
    if "not running" in text:
        return False
    if "running" in text:
        return True
    pytest.fail("Unable to determine server running state from status output")


@pytest.fixture
def script_path():
    """Get path to server_control.sh script."""
    project_root = Path(__file__).parent.parent.parent.parent
    script = project_root / "server_control.sh"
    assert script.exists(), f"server_control.sh not found at {script}"
    return script
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_exists(script_path):
    """Test that server_control.sh exists and is executable."""
    assert script_path.exists()
    assert os.access(script_path, os.X_OK)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_help(script_path, test_env_file):
    """Test script help/usage information."""
    result = _run_script(script_path, test_env_file, ["help"], timeout=5)
    assert result.returncode in [0, 1, 2]
    assert "usage:" in result.stdout.lower()
    assert "commands:" in result.stdout.lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_status_command(script_path, test_env_file):
    """Test status command."""
    result = _run_script(script_path, test_env_file, ["status"], timeout=10)
    assert result.returncode in [0, 1]
    assert "expert agent mcp server - status" in result.stdout.lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_status_specific_server(script_path, test_env_file):
    """Test status command for specific server."""
    for server in ["api", "web", "mcp", "a2a"]:
        result = _run_script(script_path, test_env_file, ["status", server], timeout=10)
        assert result.returncode in [0, 1]
        assert server in result.stdout.lower()
        assert "server" in result.stdout.lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_recognizes_server_names(script_path, test_env_file):
    """Test that script recognizes all server names."""
    valid_servers = ["api", "web", "mcp", "a2a"]

    for server in valid_servers:
        # Try status command for each server
        result = _run_script(script_path, test_env_file, ["status", server], timeout=10)
        # Should not fail with "unknown server" error
        assert "unknown" not in result.stderr.lower()
        assert "unknown" not in result.stdout.lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_command_parsing(script_path, test_env_file):
    """Test that script parses commands correctly."""
    # Test commands that don't start servers (safe for testing)
    safe_commands = ["status"]

    for cmd in safe_commands:
        result = _run_script(script_path, test_env_file, [cmd], timeout=10)
        # Should not crash on valid commands
        # May return non-zero if servers not configured, but should not error
        assert result.returncode in [0, 1, 2]
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_pid_file_handling(script_path, test_env_file):
    """Test that script handles PID files correctly."""
    # Check if PID files directory exists
    project_root = Path(__file__).parent.parent.parent.parent
    project_root / "pids"

    # Script should work whether PID directory exists or not
    result = _run_script(script_path, test_env_file, ["status"], timeout=10)
    # Should complete without crashing
    assert result.returncode in [0, 1]
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_log_file_handling(script_path, test_env_file):
    """Test that script handles log files correctly."""
    # Check if logs directory exists
    project_root = Path(__file__).parent.parent.parent.parent
    project_root / "logs"

    # Script should work whether log directory exists or not
    result = _run_script(script_path, test_env_file, ["status"], timeout=10)
    # Should complete without crashing
    assert result.returncode in [0, 1]
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_configuration_loading(script_path, test_env_file):
    """Test that script loads configuration correctly."""
    # Script should load configuration from defaults.yaml or config.yaml
    result = _run_script(script_path, test_env_file, ["status"], timeout=10)
    # Should complete (may show configuration errors, but should not crash)
    assert result.returncode in [0, 1]
    assert "ports from configuration" in result.stdout.lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_port_detection(script_path, test_env_file):
    """Test that script can detect server ports."""
    result = _run_script(script_path, test_env_file, ["status"], timeout=10)
    # Output should mention ports or server information
    # Even if servers aren't running, should show port configuration
    assert "port" in result.stdout.lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_start_stop_cycle(script_path, test_env_file):
    """Test starting and stopping the web server (restores original state)."""
    status_before = _run_script(script_path, test_env_file, ["status", "web"], timeout=10)
    assert status_before.returncode in [0, 1]
    was_running = _is_running(status_before.stdout)

    if was_running:
        stop_result = _run_script(script_path, test_env_file, ["stop", "web"], timeout=20)
        assert stop_result.returncode in [0, 1]
        status_stopped = _run_script(script_path, test_env_file, ["status", "web"], timeout=10)
        assert not _is_running(status_stopped.stdout)
        start_result = _run_script(script_path, test_env_file, ["start", "web"], timeout=30)
        assert start_result.returncode == 0
        status_started = _run_script(script_path, test_env_file, ["status", "web"], timeout=10)
        assert _is_running(status_started.stdout)
    else:
        start_result = _run_script(script_path, test_env_file, ["start", "web"], timeout=30)
        assert start_result.returncode == 0
        status_started = _run_script(script_path, test_env_file, ["status", "web"], timeout=10)
        assert _is_running(status_started.stdout)
        stop_result = _run_script(script_path, test_env_file, ["stop", "web"], timeout=20)
        assert stop_result.returncode in [0, 1]
        status_stopped = _run_script(script_path, test_env_file, ["status", "web"], timeout=10)
        assert not _is_running(status_stopped.stdout)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_error_handling_invalid_command(script_path, test_env_file):
    """Test script error handling for invalid commands."""
    result = _run_script(script_path, test_env_file, ["invalid_command"], timeout=5)
    # Should handle invalid command gracefully
    # May return non-zero or show usage/help
    assert result.returncode in [0, 1, 2]
    assert "unknown command" in result.stdout.lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-035")


def test_script_error_handling_invalid_server(script_path, test_env_file):
    """Test script error handling for invalid server name."""
    result = _run_script(script_path, test_env_file, ["status", "invalid_server"], timeout=5)
    # Should handle invalid server name gracefully
    # May return non-zero or show error message
    assert result.returncode in [0, 1, 2]
    assert "unknown server" in result.stdout.lower() or "unknown server" in result.stderr.lower()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy]

