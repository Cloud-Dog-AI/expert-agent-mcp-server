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
Test Helpers for AT1.12 and AT1.13
Output Storage and Test Utilities

License: Apache 2.0
Ownership: Cloud Dog
Description: Helper functions for test output storage and retrieval
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class TestOutputStorage:
    __test__ = False  # Prevent pytest from collecting this helper as a test class
    """Manages test output storage and retrieval."""

    def __init__(self, test_name: str, session_id: Optional[int] = None):
        """
        Initialize output storage.

        Args:
            test_name: Name of test (e.g., 'scenario_1_transformer_api')
            session_id: Session ID (optional, will be set when session created)
        """
        self.test_name = test_name
        self.session_id = session_id
        self.base_path = Path("working") / "AT1.12_AT1.13_TEST_OUTPUTS" / test_name

        if session_id:
            self.session_path = self.base_path / f"session_{session_id}"
            self.session_path.mkdir(parents=True, exist_ok=True)
        else:
            self.session_path = self.base_path
            self.session_path.mkdir(parents=True, exist_ok=True)

        self.messages: List[Dict[str, Any]] = []
        self.jobs: List[Dict[str, Any]] = []
        self.summaries: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {
            "test_name": test_name,
            "started_at": datetime.utcnow().isoformat(),
            "session_id": session_id,
        }

    def set_session_id(self, session_id: int):
        """Update session ID and create session directory."""
        self.session_id = session_id
        self.metadata["session_id"] = session_id
        self.session_path = self.base_path / f"session_{session_id}"
        self.session_path.mkdir(parents=True, exist_ok=True)

    def save_message(self, message: Dict[str, Any], turn_number: int):
        """Save a message to storage."""
        message_with_turn = {
            "turn_number": turn_number,
            "timestamp": datetime.utcnow().isoformat(),
            **message,
        }
        self.messages.append(message_with_turn)

        # Save incrementally
        messages_file = self.session_path / "messages.json"
        with open(messages_file, "w", encoding="utf-8") as f:
            json.dump(self.messages, f, indent=2, ensure_ascii=False)

    def save_job(self, job_id: str, job_data: Dict[str, Any]):
        """Save a job response to storage."""
        job_record = {"job_id": job_id, "timestamp": datetime.utcnow().isoformat(), **job_data}
        self.jobs.append(job_record)

        # Save individual job file
        job_file = self.session_path / f"job_{job_id}_response.json"
        with open(job_file, "w", encoding="utf-8") as f:
            json.dump(job_data, f, indent=2, ensure_ascii=False)

        # Save to jobs list
        jobs_file = self.session_path / "jobs.json"
        with open(jobs_file, "w", encoding="utf-8") as f:
            json.dump(self.jobs, f, indent=2, ensure_ascii=False)

    def save_summary(self, summary_data: Dict[str, Any]):
        """Save a summary to storage."""
        summary_with_timestamp = {"timestamp": datetime.utcnow().isoformat(), **summary_data}
        self.summaries.append(summary_with_timestamp)

        # Save incrementally
        summaries_file = self.session_path / "summaries.json"
        with open(summaries_file, "w", encoding="utf-8") as f:
            json.dump(self.summaries, f, indent=2, ensure_ascii=False)

    def save_conversation_log(self, conversation_data: Dict[str, Any]):
        """Save full conversation log."""
        log_file = self.session_path / "conversation_log.json"
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)

    def save_test_metadata(self, metadata: Dict[str, Any]):
        """Save test metadata."""
        self.metadata.update(metadata)
        self.metadata["completed_at"] = datetime.utcnow().isoformat()

        metadata_file = self.session_path / "test_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)

    def generate_test_summary(self) -> Dict[str, Any]:
        """Generate test summary with links."""
        return {
            "test_name": self.test_name,
            "session_id": self.session_id,
            "started_at": self.metadata.get("started_at"),
            "completed_at": self.metadata.get("completed_at"),
            "total_messages": len(self.messages),
            "total_jobs": len(self.jobs),
            "total_summaries": len(self.summaries),
            "outputs": {
                "messages": {
                    "file": f"working/AT1.12_AT1.13_TEST_OUTPUTS/{self.test_name}/session_{self.session_id}/messages.json",
                    "count": len(self.messages),
                },
                "jobs": {
                    "file": f"working/AT1.12_AT1.13_TEST_OUTPUTS/{self.test_name}/session_{self.session_id}/jobs.json",
                    "count": len(self.jobs),
                    "individual_files": [
                        f"working/AT1.12_AT1.13_TEST_OUTPUTS/{self.test_name}/session_{self.session_id}/job_{job['job_id']}_response.json"
                        for job in self.jobs
                    ],
                },
                "summaries": {
                    "file": f"working/AT1.12_AT1.13_TEST_OUTPUTS/{self.test_name}/session_{self.session_id}/summaries.json",
                    "count": len(self.summaries),
                },
                "conversation_log": {
                    "file": f"working/AT1.12_AT1.13_TEST_OUTPUTS/{self.test_name}/session_{self.session_id}/conversation_log.json"
                },
                "test_metadata": {
                    "file": f"working/AT1.12_AT1.13_TEST_OUTPUTS/{self.test_name}/session_{self.session_id}/test_metadata.json"
                },
            },
        }

    def save_test_summary(self):
        """Save test summary to file."""
        summary = self.generate_test_summary()
        summary_file = self.session_path / "test_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        return summary


def validate_config_loaded():
    """Validate that configuration is loaded (hard fail if not)."""
    from src.config.loader import get_config, load_config

    load_config.cache_clear()

    # Hard fail if critical config missing
    llm_provider = get_config("llm.provider")
    if not llm_provider:
        raise ValueError("llm.provider not configured. Check your --env file.")

    return True
