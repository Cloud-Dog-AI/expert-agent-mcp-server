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
Base Server Class

License: Apache 2.0
Ownership: Cloud Dog
Description: Base server class with lifecycle management for all four servers

Related Requirements: SV1.2, NF1.2
Related Tasks: T001
Related Architecture: CC1.1
Related Tests: ST1.1

Recent Changes:
- Initial implementation
"""

import asyncio
import signal
from abc import ABC, abstractmethod

from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaseServer(ABC):
    """Base server class with lifecycle management."""

    def __init__(self, server_name: str, config_path: str):
        """
        Initialize base server.

        Args:
            server_name: Name of the server (api, web, mcp, a2a)
            config_path: Configuration path prefix (e.g., 'api_server')
        """
        self.server_name = server_name
        self.config_path = config_path
        self.host = get_config(f"{config_path}.host")
        self.port = get_config(f"{config_path}.port")
        self.debug = get_config(f"{config_path}.debug")
        self.enabled = get_config(f"{config_path}.enabled")

        if self.host is None or self.host == "":
            raise RuntimeError(f"{config_path}.host not configured")
        if self.port is None:
            raise RuntimeError(f"{config_path}.port not configured")
        if self.debug is None:
            raise RuntimeError(f"{config_path}.debug not configured")
        if self.enabled is None:
            raise RuntimeError(f"{config_path}.enabled not configured")

        self._running = False
        self._shutdown_event = asyncio.Event()

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_event.set()

    @abstractmethod
    async def start(self):
        """Start the server."""
        pass

    @abstractmethod
    async def stop(self):
        """Stop the server gracefully."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if server is healthy."""
        pass

    async def run(self):
        """Run the server until shutdown."""
        if not self.enabled:
            logger.warning(f"{self.server_name} is disabled in configuration")
            return

        try:
            logger.info(f"Starting {self.server_name} on {self.host}:{self.port}")
            await self.start()
            self._running = True
            logger.info(f"{self.server_name} started successfully on {self.host}:{self.port}")

            # Wait for shutdown signal
            await self._shutdown_event.wait()

            logger.info(f"Shutting down {self.server_name}...")
            await self.stop()
            self._running = False
            logger.info(f"{self.server_name} stopped")

        except Exception as e:
            logger.error(f"Error running {self.server_name}: {e}", exc_info=True)
            raise

    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running
