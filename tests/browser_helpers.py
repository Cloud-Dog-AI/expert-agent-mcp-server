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
Shared browser test helpers.
"""

import os
from pathlib import Path

import pytest
from selenium.webdriver.chrome.options import Options
from src.config.loader import get_config


def resolve_chrome_binary() -> str:
    """
    Resolve Chrome/Chromium binary location from config/env in a deterministic order.
    """
    configured = get_config("test.chrome_binary")
    candidates = [
        configured,
        os.getenv("CHROME_BINARY"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    pytest.fail("No Chrome/Chromium binary found. Configure test.chrome_binary or CHROME_BINARY.")


def build_headless_chrome_options() -> Options:
    """
    Build a low-overhead headless Chrome profile for local integration tests.
    """
    opts = Options()
    opts.binary_location = resolve_chrome_binary()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--disable-sync")
    opts.add_argument("--metrics-recording-only")
    opts.add_argument("--mute-audio")
    opts.add_argument("--window-size=1440,1200")
    opts.page_load_strategy = "eager"
    return opts
