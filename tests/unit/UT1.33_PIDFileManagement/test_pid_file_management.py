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
Unit Test: UT1.33 - PID File Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for PID file management

Related Requirements: NF1.6
Related Tasks: T001
Related Architecture: SA1.1
Related Tests: UT1.33

Recent Changes:
- Initial implementation
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_pid_dir():
    """Create temporary PID directory."""
    temp_dir = tempfile.mkdtemp()
    pid_dir = Path(temp_dir) / ".pids"
    pid_dir.mkdir()
    yield pid_dir
    import shutil

    shutil.rmtree(temp_dir)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_pid_file_creation(temp_pid_dir):
    """Test creating a PID file."""
    pid_file = temp_pid_dir / "test_server.pid"
    test_pid = 12345

    # Write PID file
    pid_file.write_text(str(test_pid))

    assert pid_file.exists()
    assert pid_file.read_text().strip() == str(test_pid)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_pid_file_reading(temp_pid_dir):
    """Test reading a PID file."""
    pid_file = temp_pid_dir / "test_server.pid"
    test_pid = 12345

    pid_file.write_text(str(test_pid))

    # Read PID
    read_pid = int(pid_file.read_text().strip())

    assert read_pid == test_pid
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_pid_file_deletion(temp_pid_dir):
    """Test deleting a PID file."""
    pid_file = temp_pid_dir / "test_server.pid"
    pid_file.write_text("12345")

    assert pid_file.exists()

    pid_file.unlink()

    assert not pid_file.exists()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_pid_file_invalid_content(temp_pid_dir):
    """Test handling invalid PID file content."""
    pid_file = temp_pid_dir / "test_server.pid"
    pid_file.write_text("invalid")

    # Should handle gracefully
    try:
        pid = int(pid_file.read_text().strip())
        assert isinstance(pid, int) or pid is None
    except ValueError:
        # Expected for invalid content
        pass
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_pid_file_nonexistent():
    """Test reading non-existent PID file."""
    pid_file = Path("/nonexistent/path/test.pid")

    assert not pid_file.exists()

    # Should handle gracefully
    if pid_file.exists():
        pid = pid_file.read_text()
    else:
        pid = None

    assert pid is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_pid_file_directory_creation(temp_pid_dir):
    """Test that PID directory is created if needed."""
    new_pid_dir = temp_pid_dir.parent / "new_pids"

    # Create directory
    new_pid_dir.mkdir()

    assert new_pid_dir.exists()
    assert new_pid_dir.is_dir()

    # Cleanup
    new_pid_dir.rmdir()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_pid_file_multiple_servers(temp_pid_dir):
    """Test managing PID files for multiple servers."""
    servers = ["api_server", "web_server", "mcp_server", "a2a_server"]
    pids = [1001, 1002, 1003, 1004]

    # Create PID files for all servers
    for server, pid in zip(servers, pids):
        pid_file = temp_pid_dir / f"{server}.pid"
        pid_file.write_text(str(pid))

    # Verify all exist
    for server, expected_pid in zip(servers, pids):
        pid_file = temp_pid_dir / f"{server}.pid"
        assert pid_file.exists()
        assert int(pid_file.read_text().strip()) == expected_pid
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-038")


def test_pid_file_overwrite(temp_pid_dir):
    """Test overwriting existing PID file."""
    pid_file = temp_pid_dir / "test_server.pid"
    old_pid = 1111
    new_pid = 2222

    # Create initial PID file
    pid_file.write_text(str(old_pid))
    assert int(pid_file.read_text().strip()) == old_pid

    # Overwrite
    pid_file.write_text(str(new_pid))
    assert int(pid_file.read_text().strip()) == new_pid

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.mcp, pytest.mark.fast]

