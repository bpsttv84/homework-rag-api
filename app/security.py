"""Input length limits, prompt-injection patterns, output checks."""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import HTTPException, status

from app.config import get_settings

SUSPICIOUS_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"ignore\s+all\s+(prior|previous)\s+instructions",
    r"\bsystem\s*:",
    r"<\|im_start\|>",
    r"</s>",
    r"you\s+are\s+now\s+(DAN|jailbroken)",
    r"reveal\s+your\s+(system\s+)?prompt",
    r"<\s*script",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in SUSPICIOUS_PATTERNS]

_OUTPUT_LEAK_PATTERNS = [
    re.compile(r"you\s+are\s+an\s+AI\s+assistant", re.I),
    re.compile(r"<\|system\|>", re.I),
]


def _log_suspicious_request(message: str, reason: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\t{reason}\t{message[:500]!r}\n"
    Path("suspicious_requests.log").open("a", encoding="utf-8").write(line)


def _log_suspicious_response(text: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\t{text[:800]!r}\n"
    Path("suspicious_responses.log").open("a", encoding="utf-8").write(line)


def validate_user_message(message: str) -> None:
    settings = get_settings()
    if len(message) > settings.max_message_chars:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message exceeds {settings.max_message_chars} characters",
        )
    for rx in _COMPILED:
        if rx.search(message):
            _log_suspicious_request(message, rx.pattern)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Suspicious input blocked (prompt-injection pattern)",
            )


def postcheck_output(text: str) -> bool:
    """Return True if output should be flagged (output_filtered)."""
    for rx in _OUTPUT_LEAK_PATTERNS:
        if rx.search(text):
            _log_suspicious_response(text)
            return True
    return False
