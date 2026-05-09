"""Helpers for extracting and validating JSON from LLM responses."""

import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def parse_json_response(text: str) -> Dict[str, Any]:
    """Parse a JSON object from a Claude response string.

    Handles the common case where the model wraps its output in markdown
    code fences (```json ... ```) before attempting a bare json.loads().
    Falls back to a regex search for the outermost {...} block.

    Raises ValueError if no valid JSON object can be found.
    """
    text = text.strip()

    # Strip optional markdown code fence
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    # Fast path: the whole response is valid JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: find the first complete {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Found a JSON-like block but it failed to parse: {exc}\n"
                f"Snippet: {match.group()[:300]}"
            ) from exc

    raise ValueError(
        f"No JSON object found in Claude response. First 300 chars:\n{text[:300]}"
    )
