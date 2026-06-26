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
**************************************************
License: Apache 2.0
Ownership: Cloud Dog
Description: Lightweight webhook receiver test rig for FR1.33. Starts a local
HTTP server to capture webhook POSTs, validates optional HMAC signatures, and
exposes a queue for tests to assert delivery.

Related Requirements: FR1.33, FR1.7
Related Tasks: T120
Related Architecture: CC1.1.1
Related Tests: AT1.90, IT2.20, ST1.27

Recent Changes (max 10):
- UNCOMMITTED: Initial webhook receiver test rig
**************************************************
"""

from __future__ import annotations

import hashlib
import hmac
import queue
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional


@dataclass(frozen=True)
class WebhookRequest:
    """Captured webhook request details for test validation."""

    path: str
    headers: Dict[str, str]
    body: bytes
    received_at: float


class WebhookReceiver:
    """Local HTTP server to receive and record webhook calls.

    Inputs: host, port, secret, signature header, optional prefix.
    Outputs: captured requests via wait_for_request/drain_requests.
    Dependencies: stdlib http.server, threading, queue, hmac.
    Limitations: single-process, best-effort delivery capture.
    """

    def __init__(
        self,
        host: str,
        port: int,
        secret: str,
        signature_header: str,
        signature_prefix: str,
    ) -> None:
        """Initialise the receiver without starting the server."""

        self._host = host
        self._port = port
        self._secret = secret
        self._signature_header = signature_header
        self._signature_prefix = signature_prefix
        self._requests: queue.Queue[WebhookRequest] = queue.Queue()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        """Base URL for this receiver once started."""

        return f"http://{self._host}:{self._port}"

    def start(self) -> None:
        """Start the HTTP server in a background thread."""

        if self._server is not None:
            return

        receiver = self

        class _WebhookServer(ThreadingHTTPServer):
            """HTTP server with receiver reference for handler access."""

            def __init__(self, server_address):
                super().__init__(server_address, _WebhookHandler)
                self.receiver = receiver

        class _WebhookHandler(BaseHTTPRequestHandler):
            """Handle incoming webhook POSTs and record them."""

            def log_message(self, format: str, *args) -> None:
                return

            def do_POST(self) -> None:
                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length)
                headers = {k: v for k, v in self.headers.items()}
                request = WebhookRequest(
                    path=self.path,
                    headers=headers,
                    body=body,
                    received_at=time.time(),
                )
                self.server.receiver._requests.put(request)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

        self._server = _WebhookServer((self._host, self._port))
        self._port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the HTTP server and release the port."""

        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None

    def wait_for_request(self, timeout_seconds: float) -> Optional[WebhookRequest]:
        """Wait for a single webhook request up to timeout_seconds."""

        try:
            return self._requests.get(timeout=timeout_seconds)
        except queue.Empty:
            return None

    def drain_requests(self) -> list[WebhookRequest]:
        """Return all captured requests without blocking."""

        drained: list[WebhookRequest] = []
        while True:
            try:
                drained.append(self._requests.get_nowait())
            except queue.Empty:
                return drained

    def verify_signature(self, request: WebhookRequest) -> bool:
        """Verify HMAC signature using configured header and secret."""

        header_value = request.headers.get(self._signature_header, "")
        if not header_value:
            return False
        if not header_value.startswith(self._signature_prefix):
            return False
        provided = header_value[len(self._signature_prefix) :]
        expected = hmac.new(
            self._secret.encode("utf-8"),
            request.body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(provided, expected)
