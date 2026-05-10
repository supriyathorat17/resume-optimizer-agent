"""Claude API client wrapping the Anthropic SDK."""

import logging
import sys
import os
from typing import Any, Dict, Optional

import anthropic

# Allow imports from src/ when this module is loaded directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.json_utils import parse_json_response

logger = logging.getLogger(__name__)


class ClaudeAPIClient:
    """Thin wrapper around the Anthropic client for structured resume optimization prompts."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_MAX_TOKENS = 4096

    def __init__(self, api_key: str) -> None:
        """Initialize the Anthropic client with the provided API key."""
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Send a message and return the assistant's text response."""
        kwargs: Dict[str, Any] = {
            "model": model or self.DEFAULT_MODEL,
            "max_tokens": max_tokens or self.DEFAULT_MAX_TOKENS,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def complete_json(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        retries: int = 2,
    ) -> Dict[str, Any]:
        """Send a message and parse the response as JSON.

        Retries up to `retries` times on parse failure, appending an explicit
        correction instruction so Claude self-corrects its output format.
        """
        json_system = (
            system_prompt.rstrip()
            + "\n\nIMPORTANT: Your response must be ONLY a valid JSON object. "
            "No markdown fences, no explanatory text — pure JSON."
        )

        last_error: Exception = RuntimeError("No attempts made")
        raw = ""

        for attempt in range(1 + retries):
            if attempt > 0:
                logger.warning("JSON parse failed (attempt %d), retrying with correction prompt", attempt)
                user_message = (
                    f"{user_message}\n\n"
                    f"Your previous response could not be parsed as JSON. "
                    f"Error: {last_error}. "
                    "Please respond with ONLY the raw JSON object."
                )

            raw = self.complete(
                system_prompt=json_system,
                user_message=user_message,
                model=model,
                max_tokens=max_tokens,
            )

            try:
                return parse_json_response(raw)
            except ValueError as exc:
                last_error = exc

        raise ValueError(
            f"Claude did not return valid JSON after {1 + retries} attempts. "
            f"Last response (first 500 chars):\n{raw[:500]}"
        ) from last_error
