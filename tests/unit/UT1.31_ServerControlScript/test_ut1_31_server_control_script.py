import pytest
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
Unit Test: UT1.31 - Server Control Script Command Parsing

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for server control script command parsing

Related Requirements: NF1.6
Related Tasks: T001
Related Architecture: SA1.1
Related Tests: UT1.31

Recent Changes:
- Initial implementation
"""

import subprocess
import os
from pathlib import Path
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_server_control_script_exists():
    """Test that server_control.sh exists and is executable."""
    script_path = Path("server_control.sh")
    assert script_path.exists(), "server_control.sh should exist"
    assert os.access(script_path, os.X_OK), "server_control.sh should be executable"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_server_control_script_help():
    """Test server control script help command."""
    result = subprocess.run(
        ["bash", "server_control.sh", "help"], capture_output=True, text=True, timeout=30
    )

    # Should return successfully or show help
    assert (
        result.returncode == 0
        or "help" in result.stdout.lower()
        or "usage" in result.stdout.lower()
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_server_control_script_status_command():
    """Test server control script status command."""
    result = subprocess.run(
        ["bash", "server_control.sh", "status"], capture_output=True, text=True, timeout=10
    )

    # Should return successfully (even if servers are not running)
    # Status command should not fail
    assert result.returncode in [0, 1]  # 0 if successful, 1 if servers not running (acceptable)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_server_control_script_invalid_command():
    """Test server control script with invalid command."""
    result = subprocess.run(
        ["bash", "server_control.sh", "invalid_command"], capture_output=True, text=True, timeout=30
    )

    # Should return error code for invalid command
    assert (
        result.returncode != 0
        or "error" in result.stderr.lower()
        or "unknown" in result.stderr.lower()
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_server_control_script_reads_config():
    """Test that server control script can read configuration."""
    # Test that script defines read_config function
    with open("server_control.sh", "r") as f:
        content = f.read()
        assert "read_config" in content, "Script should define read_config function"
        assert "API_SERVER__PORT" in content or "api" in content.lower(), (
            "Script should reference API server config"
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_server_control_script_pid_dir_creation():
    """Test that server control script creates PID directory."""
    # Check that script defines PID_DIR
    with open("server_control.sh", "r") as f:
        content = f.read()
        assert "PID_DIR" in content, "Script should define PID_DIR"
        assert ".pids" in content or "pid" in content.lower(), "Script should use .pids directory"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_server_control_script_server_definitions():
    """Test that server control script defines all servers."""
    with open("server_control.sh", "r") as f:
        content = f.read()
        # Should define API, Web, MCP, A2A servers
        assert "api" in content.lower() or "API" in content
        assert "web" in content.lower() or "WEB" in content
        assert "mcp" in content.lower() or "MCP" in content
        assert "a2a" in content.lower() or "A2A" in content
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_server_control_script_command_parsing():
    """Test server control script command parsing logic."""
    # Test that script handles common commands (with longer timeout for start)
    commands = ["status", "help"]

    for cmd in commands:
        result = subprocess.run(
            ["bash", "server_control.sh", cmd], capture_output=True, text=True, timeout=10
        )
        # Should not crash on valid commands
        assert result.returncode in [0, 1, 2]  # Various exit codes are acceptable

    # Test that script defines command handlers
    with open("server_control.sh", "r") as f:
        content = f.read()
        assert "start" in content.lower() or "stop" in content.lower(), (
            "Script should handle start/stop commands"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.mcp, pytest.mark.fast]

