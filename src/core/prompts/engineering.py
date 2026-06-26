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
Prompt Engineering Utilities

License: Apache 2.0
Ownership: Cloud Dog
Description: Prompt engineering utilities with entropy checking

Related Requirements: FR1.1, T012
Related Tasks: T012
Related Architecture: CC3.1.4
Related Tests: UT1.12, UT1.13

Recent Changes:
- Initial implementation
"""

import math
from typing import Dict, Any, Optional
from collections import Counter
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PromptEngineer:
    """Prompt engineering utilities with entropy checking."""

    def calculate_entropy(self, text: str) -> float:
        """
        Calculate Shannon entropy of text.

        Args:
            text: Text to analyze

        Returns:
            Entropy value (higher = more diverse/random)
        """
        if not text:
            return 0.0

        # Count character frequencies
        char_counts = Counter(text.lower())
        length = len(text)

        # Calculate entropy
        entropy = 0.0
        for count in char_counts.values():
            probability = count / length
            if probability > 0:
                entropy -= probability * math.log2(probability)

        return entropy

    def check_prompt_entropy(
        self, title: str, description: str, min_entropy: float = 2.0
    ) -> Dict[str, Any]:
        """
        Check prompt title and description for sufficient entropy.

        Args:
            title: Prompt title
            description: Prompt description
            min_entropy: Minimum entropy threshold

        Returns:
            Dict with 'valid', 'title_entropy', 'description_entropy', 'recommendations'
        """
        title_entropy = self.calculate_entropy(title)
        desc_entropy = self.calculate_entropy(description)

        recommendations = []

        if title_entropy < min_entropy:
            recommendations.append(
                f"Title entropy ({title_entropy:.2f}) is low. Consider making it more descriptive and specific."
            )

        if desc_entropy < min_entropy:
            recommendations.append(
                f"Description entropy ({desc_entropy:.2f}) is low. Add more detail and context."
            )

        is_valid = title_entropy >= min_entropy and desc_entropy >= min_entropy

        return {
            "valid": is_valid,
            "title_entropy": title_entropy,
            "description_entropy": desc_entropy,
            "min_entropy": min_entropy,
            "recommendations": recommendations,
        }

    def optimize_prompt(self, prompt: str, target_length: Optional[int] = None) -> Dict[str, Any]:
        """
        Optimize prompt for clarity and effectiveness.

        Args:
            prompt: Prompt text
            target_length: Optional target length

        Returns:
            Dict with 'optimized', 'suggestions'
        """
        suggestions = []

        # Check length
        if target_length and len(prompt) > target_length:
            suggestions.append(
                f"Prompt is {len(prompt)} chars, target is {target_length}. Consider shortening."
            )

        # Check for clarity indicators
        clarity_indicators = ["clearly", "specifically", "precisely", "exactly"]
        has_clarity = any(indicator in prompt.lower() for indicator in clarity_indicators)
        if not has_clarity:
            suggestions.append("Consider adding clarity indicators for better results.")

        # Check structure
        has_structure = "\n" in prompt or ":" in prompt
        if not has_structure:
            suggestions.append(
                "Consider using structured format (bullet points, sections) for better organization."
            )

        return {
            "optimized": prompt,  # Would apply optimizations
            "suggestions": suggestions,
        }
