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
Prompt Generator

License: Apache 2.0
Ownership: Cloud Dog
Description: Generates prompts and test cases from expert descriptions

Related Requirements: FR1.15, FR1.28, UC1.9, UC1.22
Related Tasks: T053, T115
Related Architecture: CC3.1.4
Related Tests: AT1.15, AT1.25

Recent Changes:
- Initial implementation
"""

import asyncio
from typing import Dict, Any, Optional, List
from src.core.llm.manager import LLMManager
from src.config.loader import get_config
from src.core.cache_integration import build_model_config_hash, cached_prompt_generation
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _generation_timeout_seconds(default: float = 20.0) -> float:
    """Keep prompt-generation calls inside the API request budget."""
    try:
        request_timeout = float(get_config("test.http_timeout_seconds") or default)
    except (TypeError, ValueError):
        request_timeout = default
    return max(5.0, min(request_timeout - 5.0, default))


class PromptGenerator:
    """Generates prompts and test cases from expert descriptions."""

    def __init__(self):
        """Initialize prompt generator."""
        self.llm_manager = LLMManager()

    async def generate_prompt(
        self,
        title: str,
        details: str,
        context_type: Optional[str] = None,
        expected_outcomes: Optional[str] = None,
        available_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a prompt from expert description.

        Args:
            title: Expert title
            details: Expert details/description
            context_type: Type of context (e.g., "technical", "creative", "analytical")
            expected_outcomes: Expected outcomes from the expert
            available_tools: List of available tool names

        Returns:
            Generated prompt and configuration recommendations
        """
        try:
            system_prompt = """You are a prompt engineering assistant. Generate a comprehensive system prompt for an expert AI assistant based on the provided description.

The prompt should:
1. Clearly define the expert's role and expertise
2. Set appropriate tone and style
3. Include guidelines for responses
4. Specify when to use tools (if available)
5. Be clear, concise, and actionable

Return a JSON object with:
- "prompt": The generated system prompt
- "temperature": Recommended temperature (0.0-1.0)
- "max_tokens": Recommended max tokens
- "tool_recommendations": List of recommended tools from available tools
- "reasoning": Brief explanation of choices"""

            user_prompt = f"""Generate a prompt for an expert assistant with the following details:

Title: {title}
Details: {details}
Context Type: {context_type or "general"}
Expected Outcomes: {expected_outcomes or "Helpful, accurate responses"}

Available Tools: {", ".join(available_tools) if available_tools else "None"}

Generate a comprehensive system prompt and configuration recommendations."""
            available_tools_list = list(available_tools or [])
            model_config_hash = build_model_config_hash(
                {
                    "provider": get_config("llm.provider"),
                    "model": get_config("llm.model"),
                    "base_url": get_config("llm.base_url"),
                }
            )

            async def _generate_uncached() -> Dict[str, Any]:
                # Initialize LLM
                await self.llm_manager.initialize()

                try:
                    timeout_budget = _generation_timeout_seconds()
                    response = await asyncio.wait_for(
                        self.llm_manager.generate(
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            temperature=0.7,
                            max_tokens=1500,
                        ),
                        timeout=timeout_budget,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Prompt generation timed out, returning fallback prompt")
                    return {
                        "prompt": f"You are an expert assistant specializing in {title}.\n\n{details}\n\nProvide accurate, helpful, and contextually appropriate responses.",
                        "temperature": 0.7,
                        "max_tokens": 1024,
                        "tool_recommendations": [],
                        "reasoning": "Fallback prompt (LLM timeout)",
                    }

                # Parse response (assuming JSON format)
                import json

                try:
                    result = json.loads(response.get("content", "{}"))
                except json.JSONDecodeError:
                    # If not JSON, extract prompt from response
                    result = {
                        "prompt": response.get("content", ""),
                        "temperature": 0.7,
                        "max_tokens": 1024,
                        "tool_recommendations": [],
                        "reasoning": "Generated from description",
                    }
                return result

            result = await cached_prompt_generation(
                title=title,
                details=details,
                context_type=context_type or "general",
                expected_outcomes=expected_outcomes or "Helpful, accurate responses",
                available_tools=available_tools_list,
                model_config_hash=model_config_hash,
                generate_fn=_generate_uncached,
            )

            logger.info(f"Generated prompt for expert: {title}")
            return result

        except Exception as e:
            logger.error(f"Failed to generate prompt: {e}", exc_info=True)
            # Return default prompt
            return {
                "prompt": f"You are an expert assistant specializing in {title}.\n\n{details}\n\nProvide accurate, helpful, and contextually appropriate responses.",
                "temperature": 0.7,
                "max_tokens": 1024,
                "tool_recommendations": [],
                "reasoning": "Default prompt (generation failed)",
            }

    async def generate_test_cases(
        self,
        title: str,
        details: str,
        prompt: str,
        context_type: Optional[str] = None,
        expected_outcomes: Optional[str] = None,
        num_cases: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Generate test cases for expert configuration.

        Args:
            title: Expert title
            details: Expert details
            prompt: Generated prompt
            context_type: Type of context
            expected_outcomes: Expected outcomes
            num_cases: Number of test cases to generate

        Returns:
            List of test cases
        """
        try:
            # Initialize LLM
            await self.llm_manager.initialize()

            system_prompt = """You are a test case generator for AI expert assistants. Generate test cases that exercise the expert's capabilities.

Each test case should include:
1. A clear input/question
2. Expected response characteristics
3. What to validate (accuracy, completeness, tool usage, etc.)

Return a JSON array of test cases, each with:
- "input": The test input/question
- "expected_characteristics": List of expected response characteristics
- "validation_criteria": What to check in the response
- "category": Test category (e.g., "basic", "edge_case", "tool_usage")"""

            user_prompt = f"""Generate {num_cases} test cases for an expert assistant:

Title: {title}
Details: {details}
Prompt: {prompt}
Context Type: {context_type or "general"}
Expected Outcomes: {expected_outcomes or "Helpful responses"}

Generate diverse test cases that cover:
- Basic functionality
- Edge cases
- Tool usage (if applicable)
- Domain-specific knowledge"""

            try:
                timeout_budget = _generation_timeout_seconds()
                response = await asyncio.wait_for(
                    self.llm_manager.generate(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.8,
                        max_tokens=2000,
                    ),
                    timeout=timeout_budget,
                )
            except asyncio.TimeoutError:
                logger.warning("Test case generation timed out, returning fallback test case")
                return [
                    {
                        "input": f"Test question about {title}",
                        "expected_characteristics": ["helpful"],
                        "validation_criteria": ["response is provided"],
                        "category": "basic",
                    }
                ]

            # Parse response
            import json

            try:
                test_cases = json.loads(response.get("content", "[]"))
                if not isinstance(test_cases, list):
                    test_cases = [test_cases]
            except json.JSONDecodeError:
                # If not JSON, create default test cases
                test_cases = [
                    {
                        "input": f"Tell me about {title.lower()}",
                        "expected_characteristics": ["accurate", "helpful"],
                        "validation_criteria": ["response is relevant", "response is informative"],
                        "category": "basic",
                    }
                ]

            logger.info(f"Generated {len(test_cases)} test cases for expert: {title}")
            return test_cases[:num_cases]

        except Exception as e:
            logger.error(f"Failed to generate test cases: {e}", exc_info=True)
            # Return default test case
            return [
                {
                    "input": f"Test question about {title}",
                    "expected_characteristics": ["helpful"],
                    "validation_criteria": ["response is provided"],
                    "category": "basic",
                }
            ]

    async def validate_prompt(
        self, prompt: str, requirements: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Validate prompt against requirements.

        Args:
            prompt: Prompt to validate
            requirements: List of requirements to check

        Returns:
            Validation results
        """
        try:
            await self.llm_manager.initialize()

            system_prompt = """You are a prompt validator. Analyze prompts for:
1. Clarity and specificity
2. Completeness
3. Actionability
4. Safety considerations
5. Tool usage guidelines (if applicable)

Return a JSON object with:
- "is_valid": Boolean
- "score": Score out of 100
- "strengths": List of strengths
- "weaknesses": List of weaknesses
- "recommendations": List of improvement recommendations"""

            requirements_text = "\n".join([f"- {req}" for req in (requirements or [])])
            user_prompt = f"""Validate this prompt:

{prompt}

Requirements to check:
{requirements_text if requirements_text else "Standard prompt quality requirements"}"""

            try:
                timeout_budget = _generation_timeout_seconds()
                response = await asyncio.wait_for(
                    self.llm_manager.generate(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.3,
                        max_tokens=1000,
                    ),
                    timeout=timeout_budget,
                )
            except asyncio.TimeoutError:
                logger.warning("Prompt validation timed out, returning fallback validation")
                return {
                    "is_valid": False,
                    "score": 50,
                    "strengths": ["Structured prompt provided"],
                    "weaknesses": ["Validation timed out"],
                    "recommendations": ["Retry validation", "Shorten prompt content"],
                }

            import json

            try:
                content = response.get("content", "") or ""
                # Robust extraction: parse the first JSON object in the response.
                start = content.find("{")
                end = content.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    raise json.JSONDecodeError("No JSON object found", content, 0)
                result = json.loads(content[start : end + 1])
                # Hard requirements: must contain is_valid boolean
                if "is_valid" not in result or not isinstance(result.get("is_valid"), bool):
                    raise ValueError("Prompt validator returned invalid schema (missing is_valid)")
            except Exception as e:
                logger.error(f"Prompt validation response parsing failed: {e}", exc_info=True)
                return {
                    "is_valid": False,
                    "score": 0,
                    "strengths": [],
                    "weaknesses": ["Prompt validation failed (invalid LLM response)"],
                    "recommendations": ["Re-run validation or adjust prompt/requirements"],
                }

            return result

        except Exception as e:
            logger.error(f"Failed to validate prompt: {e}", exc_info=True)
            return {
                "is_valid": False,
                "score": 0,
                "strengths": [],
                "weaknesses": ["Validation failed"],
                "recommendations": ["Fix validation error and retry"],
            }
