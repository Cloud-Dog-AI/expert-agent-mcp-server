#!/bin/bash
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

# Setup script for local development
# Activates virtual environment and sets up Python path

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✓ Virtual environment created and activated"
fi

# Add src to Python path
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"
echo "✓ Python path configured: ${PYTHONPATH}"

# Set project root
export EXPERT_AGENT_ROOT="${SCRIPT_DIR}"
echo "✓ Project root: ${EXPERT_AGENT_ROOT}"

echo ""
echo "Environment ready for Expert Agent MCP Server development"
echo "Run 'source setup_local.sh' or '. setup_local.sh' to activate"
