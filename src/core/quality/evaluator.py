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
Response Quality Evaluator

License: Apache 2.0
Ownership: Cloud Dog
Description: Evaluates LLM response quality

Related Requirements: FR1.30, UC1.28
Related Tasks: T117
Related Architecture: MO1.4
Related Tests: AT1.27

Recent Changes:
- Initial implementation
"""

from typing import Dict, Any, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class QualityEvaluator:
    """Evaluates response quality metrics."""

    def __init__(self):
        """Initialize quality evaluator."""
        pass

    def evaluate_response(
        self, prompt: str, response: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate response quality.

        Args:
            prompt: Original prompt
            response: LLM response
            context: Additional context (session, channel, etc.)

        Returns:
            Quality metrics
        """
        # Basic quality metrics (can be enhanced with LLM-based evaluation)
        metrics = {
            "relevance_score": self._calculate_relevance(prompt, response),
            "completeness_score": self._calculate_completeness(prompt, response),
            "accuracy_score": 0.5,  # Placeholder - would need domain knowledge or LLM evaluation
            "overall_score": 0.0,
            "feedback": [],
        }

        # Calculate overall score (weighted average)
        metrics["overall_score"] = (
            metrics["relevance_score"] * 0.4
            + metrics["completeness_score"] * 0.4
            + metrics["accuracy_score"] * 0.2
        )

        # Generate feedback
        if metrics["relevance_score"] < 0.5:
            metrics["feedback"].append("Response may not be relevant to the prompt")
        if metrics["completeness_score"] < 0.5:
            metrics["feedback"].append("Response may be incomplete")
        if metrics["overall_score"] < 0.5:
            metrics["feedback"].append("Overall quality is below threshold")

        return metrics

    def _calculate_relevance(self, prompt: str, response: str) -> float:
        """Calculate relevance score (0.0-1.0)."""
        # Simple keyword overlap (can be enhanced)
        prompt_words = set(prompt.lower().split())
        response_words = set(response.lower().split())

        if not prompt_words:
            return 1.0

        overlap = len(prompt_words.intersection(response_words))
        relevance = min(overlap / len(prompt_words), 1.0)

        return relevance

    def _calculate_completeness(self, prompt: str, response: str) -> float:
        """Calculate completeness score (0.0-1.0)."""
        # Simple heuristic: response length relative to prompt
        # Can be enhanced with question-answering completeness checks
        if not response:
            return 0.0

        # Check for question marks in prompt (questions should have answers)
        has_question = "?" in prompt

        if has_question:
            # Check if response seems to answer (has some content)
            if len(response) < 10:
                return 0.3
            elif len(response) < 50:
                return 0.6
            else:
                return 0.9
        else:
            # For non-questions, completeness is based on response length
            if len(response) < 20:
                return 0.4
            elif len(response) < 100:
                return 0.7
            else:
                return 1.0

    def collect_user_feedback(
        self,
        job_id: int,
        user_id: int,
        rating: int,  # 1-5
        feedback_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Collect user feedback on response quality.

        Args:
            job_id: Job ID
            user_id: User ID
            rating: Rating (1-5)
            feedback_text: Optional feedback text

        Returns:
            Feedback record
        """
        # Store feedback (would integrate with database)
        feedback = {
            "job_id": job_id,
            "user_id": user_id,
            "rating": rating,
            "feedback_text": feedback_text,
            "timestamp": None,  # Would be set by database
        }

        logger.info(f"Collected user feedback for job {job_id}: rating {rating}")
        return feedback
