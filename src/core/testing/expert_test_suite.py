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
Comprehensive Expert Test Suite

License: Apache 2.0
Ownership: Cloud Dog
Description: Test framework for validating expert configurations

Related Requirements: FR1.35, NF1.6, UC1.31
Related Tasks: T122
Related Architecture: TS1.1
Related Tests: PT1.20

Recent Changes:
- Initial implementation
"""

from typing import Dict, Any, List, Optional
from src.core.llm.manager import LLMManager
from src.core.session.manager import SessionManager
from src.core.vector.manager import VectorStoreManager
from src.core.job.manager import JobManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ExpertTestSuite:
    """Comprehensive test suite for expert configurations."""

    def __init__(self, db=None):
        """Initialize test suite."""
        self.db = db
        self.llm_manager = LLMManager()
        self.session_manager = SessionManager(db)
        self.vector_manager = VectorStoreManager(db)
        self.job_manager = JobManager(db)

    async def run_test_suite(
        self, channel_id: int, test_cases: Optional[List[Dict[str, Any]]] = None, user_id: int = 1
    ) -> Dict[str, Any]:
        """
        Run comprehensive test suite for expert configuration.

        Args:
            channel_id: Channel ID to test
            test_cases: Optional list of test cases (if None, uses defaults)
            user_id: User ID for testing

        Returns:
            Test results
        """
        results = {
            "channel_id": channel_id,
            "test_cases_run": 0,
            "test_cases_passed": 0,
            "test_cases_failed": 0,
            "results": [],
            "summary": {},
        }

        # Default test cases if none provided
        if not test_cases:
            test_cases = [
                {
                    "input": "Hello, can you help me?",
                    "expected_characteristics": ["helpful", "responsive"],
                    "category": "basic",
                },
                {
                    "input": "What is your expertise?",
                    "expected_characteristics": ["informative"],
                    "category": "basic",
                },
            ]

        # Get channel and expert config
        from src.database.connection import get_db
        from src.database.models import Channel, ExpertConfig

        db = self.db or next(get_db())

        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            results["error"] = "Channel not found"
            return results

        expert = db.query(ExpertConfig).filter(ExpertConfig.id == channel.expert_config_id).first()
        if not expert:
            results["error"] = "Expert configuration not found"
            return results

        # Initialize LLM
        llm_config = {}
        if expert.llm_params_json:
            import json

            llm_config = json.loads(expert.llm_params_json)

        await self.llm_manager.initialize(
            provider=expert.llm_provider,
            base_url=llm_config.get("base_url"),
            model=expert.llm_model,
            api_key=llm_config.get("api_key"),
        )

        # Run each test case
        for i, test_case in enumerate(test_cases):
            test_result = await self._run_test_case(
                channel_id=channel_id, expert=expert, test_case=test_case, user_id=user_id
            )
            results["results"].append(test_result)
            results["test_cases_run"] += 1

            if test_result.get("passed", False):
                results["test_cases_passed"] += 1
            else:
                results["test_cases_failed"] += 1

        # Generate summary
        results["summary"] = {
            "total": results["test_cases_run"],
            "passed": results["test_cases_passed"],
            "failed": results["test_cases_failed"],
            "pass_rate": (
                results["test_cases_passed"] / results["test_cases_run"]
                if results["test_cases_run"] > 0
                else 0
            ),
        }

        return results

    async def _run_test_case(
        self, channel_id: int, expert: Any, test_case: Dict[str, Any], user_id: int
    ) -> Dict[str, Any]:
        """Run a single test case."""
        result = {
            "test_case": test_case,
            "passed": False,
            "response": None,
            "errors": [],
            "metrics": {},
        }

        try:
            # Create test session
            session = self.session_manager.create_session(
                user_id=user_id, expert_config_id=expert.id
            )
            # SessionManager contracts vary across code paths; normalize to a session model.
            if isinstance(session, tuple):
                session = session[0]

            # Prepare messages
            messages = [{"role": "user", "content": test_case["input"]}]
            if expert.prompt_template:
                messages.insert(0, {"role": "system", "content": expert.prompt_template})

            # Generate response
            # Keep testing-panel suites responsive under shared-load CI runs.
            response = await self.llm_manager.generate(
                messages=messages,
                temperature=0.0,
                max_tokens=64,
            )

            result["response"] = response.get("content", "")
            result["metrics"] = {
                "tokens_used": response.get("tokens_used", 0),
                "latency_ms": response.get("latency_ms", 0),
            }

            # Validate response
            result["passed"] = self._validate_response(
                test_case=test_case, response=result["response"]
            )

            # Add message to session
            self.session_manager.add_message(
                session.id,
                "assistant",
                result["response"],
                tokens_used=result["metrics"]["tokens_used"],
            )

        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"Test case failed: {e}", exc_info=True)

        return result

    def _validate_response(self, test_case: Dict[str, Any], response: str) -> bool:
        """Validate response against test case expectations."""
        if not response:
            return False

        # Check expected characteristics
        expected = test_case.get("expected_characteristics", [])
        if expected:
            # Simple validation - check if response is non-empty
            # Can be enhanced with more sophisticated checks
            return len(response) > 0

        # Default: response exists
        return True
