"""
Zero-Leak Privacy & Secret Redaction Gate.

Ensures that insights extracted from local conversations/diaries and code committed
to public GitHub repositories never leak personal identifiers, credentials, or
private infrastructure endpoints. Exact personal tokens are loaded at runtime from
gitignored `.state/private_denylist.json` so zero PII ever sits in public source code.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class RedactionRule:
    name: str
    pattern: re.Pattern
    replacement: str


DEFAULT_RULES: List[RedactionRule] = [
    RedactionRule(
        name="openai_or_gateway_api_key",
        pattern=re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
        replacement="sk-REDACTED",
    ),
    RedactionRule(
        name="github_pat",
        pattern=re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        replacement="ghp_REDACTED",
    ),
    RedactionRule(
        name="google_api_key",
        pattern=re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
        replacement="AIzaREDACTED",
    ),
    RedactionRule(
        name="campus_and_personal_email",
        pattern=re.compile(
            r"\b(?![A-Za-z0-9._%+-]+@(?:example\.(?:com|net|org)|users\.noreply\.github\.com|localhost|test\.local)\b)"
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            re.IGNORECASE,
        ),
        replacement="builder@example.com",
    ),
    RedactionRule(
        name="phone_numbers",
        pattern=re.compile(r"(?:\+?60\s*1\d{8,9}|\+?86\s*1[3-9]\d{9})"),
        replacement="+00-000000000",
    ),
    RedactionRule(
        name="private_handles",
        pattern=re.compile(r"\b(?:WX|TG):[A-Za-z0-9_\u4e00-\u9fa5]{2,32}\b"),
        replacement="USER:REDACTED",
    ),
    RedactionRule(
        name="private_ips_and_hosts",
        pattern=re.compile(
            r"\b(?!(?:127\.0\.0\.1|0\.0\.0\.0|192\.0\.2\.\d+|198\.51\.100\.\d+|203\.0\.113\.\d+)\b)"
            r"(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
        ),
        replacement="node.example.net",
    ),
]


def _load_local_denylist_rules(denylist_path: Optional[str] = None) -> List[RedactionRule]:
    path = denylist_path or os.path.expanduser("~/Desktop/project/.state/private_denylist.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    extra: List[RedactionRule] = []
    replacements = {
        "student_id": "00000000",
        "passport_no": "REDACTED_ID",
        "phone_numbers": "+00-000000000",
        "private_ips_and_hosts": "node.example.net",
    }
    for rule_name, tokens in (data or {}).items():
        clean_tokens = [re.escape(str(t)) for t in (tokens or []) if t]
        if clean_tokens:
            extra.append(
                RedactionRule(
                    name=str(rule_name),
                    pattern=re.compile(r"(?:" + "|".join(clean_tokens) + r")", re.IGNORECASE),
                    replacement=replacements.get(rule_name, "REDACTED"),
                )
            )
    return extra


class PrivacyGate:
    """Scans and sanitizes text or repository files prior to Git commit/push."""

    def __init__(self, rules: Optional[List[RedactionRule]] = None, denylist_path: Optional[str] = None):
        if rules is not None:
            self.rules = list(rules)
        else:
            self.rules = list(DEFAULT_RULES) + _load_local_denylist_rules(denylist_path=denylist_path)

    def sanitize_text(self, text: str) -> Tuple[str, List[str]]:
        """Return sanitized text and a list of triggered rule names."""
        if not text:
            return "", []
        triggered: List[str] = []
        out = text
        for rule in self.rules:
            if rule.pattern.search(out):
                triggered.append(rule.name)
                out = rule.pattern.sub(rule.replacement, out)
        return out, sorted(set(triggered))

    def scan_text(self, text: str) -> List[str]:
        """Return list of rule names that matched without modifying the text."""
        if not text:
            return []
        return sorted({rule.name for rule in self.rules if rule.pattern.search(text)})

    def assert_clean(self, text: str, context: str = "content") -> None:
        """Raise ValueError if any sensitive pattern is detected in text."""
        hits = self.scan_text(text)
        if hits:
            raise ValueError(f"PrivacyGate blocked {context}: matched sensitive rules {hits}")
