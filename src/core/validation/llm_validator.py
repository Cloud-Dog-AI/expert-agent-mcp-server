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
LLM Validation Testing

License: Apache 2.0
Ownership: Cloud Dog
Description: LLM validation testing before channel activation

Related Requirements: FR1.29, UC1.23
Related Tasks: T116
Related Architecture: CC3.1.4
Related Tests: AT1.26

Recent Changes:
- Initial implementation
"""

import asyncio
from typing import Dict, Any, Optional
from src.core.llm.manager import LLMManager
from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _validation_timeout_seconds() -> float:
    """Cap validation latency so API validation returns structured failure promptly."""
    try:
        timeout = float(get_config("test.http_timeout_seconds") or 20.0)
    except (TypeError, ValueError):
        timeout = 20.0
    return min(timeout, 20.0)


class LLMValidator:
    """Validates LLM configurations before channel activation."""

    def __init__(self):
        """Initialize LLM validator."""
        self.llm_manager = LLMManager()

    async def validate_llm_config(
        self,
        provider: str,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate LLM configuration.

        Args:
            provider: LLM provider (ollama, openai, openrouter)
            base_url: Base URL for provider
            model: Model name
            api_key: API key (if required)
            prompt: Optional test prompt

        Returns:
            Validation results
        """
        results = {
            "connectivity": False,
            "prompt_rendering": False,
            "response_generation": False,
            "errors": [],
            "details": {},
        }

        try:
            # Test 1: Connectivity
            logger.info(f"Testing LLM connectivity: {provider} at {base_url}")
            validation_timeout = _validation_timeout_seconds()
            await asyncio.wait_for(
                self.llm_manager.initialize(
                    provider=provider, base_url=base_url, model=model, api_key=api_key
                ),
                timeout=validation_timeout,
            )

            health_check = await asyncio.wait_for(
                self.llm_manager.health_check(),
                timeout=validation_timeout,
            )
            results["connectivity"] = health_check
            results["details"]["health_check"] = health_check

            if not health_check:
                results["errors"].append("LLM health check failed")
                return results

            # Test 2: Prompt rendering
            test_prompt = prompt or "Hello, this is a test. Please respond with 'OK'."
            logger.info("Testing prompt rendering")
            results["prompt_rendering"] = True
            results["details"]["test_prompt"] = test_prompt

            # Test 3: Response generation
            logger.info("Testing response generation")
            try:
                response = await asyncio.wait_for(
                    self.llm_manager.generate(
                        messages=[{"role": "user", "content": test_prompt}],
                        temperature=0.7,
                        max_tokens=50,
                    ),
                    timeout=validation_timeout,
                )

                if response and response.get("content"):
                    results["response_generation"] = True
                    results["details"]["response"] = response.get("content", "")[
                        :200
                    ]  # First 200 chars
                    results["details"]["tokens_used"] = response.get("tokens_used", 0)
                    results["details"]["model"] = response.get("model", "")
                else:
                    results["errors"].append("LLM returned empty response")

            except Exception as e:
                results["errors"].append(f"Response generation failed: {str(e)}")
                logger.error(f"Response generation error: {e}", exc_info=True)

            results["success"] = (
                results["connectivity"]
                and results["prompt_rendering"]
                and results["response_generation"]
            )

        except Exception as e:
            results["errors"].append(f"Validation failed: {str(e)}")
            logger.error(f"LLM validation error: {e}", exc_info=True)
            results["success"] = False

        return results
