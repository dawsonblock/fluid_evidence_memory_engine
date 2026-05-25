from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})(?!\d)"
)
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]*?){13,16}(?!\d)")
SIN_RE = re.compile(r"(?<!\d)\d{3}[-\s]?\d{3}[-\s]?\d{3}(?!\d)")
ADDRESS_HINT_RE = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.' -]+\s+(?:street|st|avenue|ave|road|rd|drive|dr|crescent|cres|court|ct|lane|ln|boulevard|blvd)\b",
    re.I,
)


@dataclass(frozen=True)
class SensitiveFinding:
    kind: str
    start: int
    end: int
    text: str


def find_sensitive(text: str) -> list[SensitiveFinding]:
    findings: list[SensitiveFinding] = []
    patterns = [
        ("email", EMAIL_RE),
        ("phone", PHONE_RE),
        ("possible_payment_card", CARD_RE),
        ("possible_sin", SIN_RE),
        ("possible_address", ADDRESS_HINT_RE),
    ]
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            findings.append(
                SensitiveFinding(kind, match.start(), match.end(), match.group(0))
            )
    findings.sort(key=lambda f: (f.start, f.end))
    return findings


def sensitivity_score(text: str) -> float:
    findings = find_sensitive(text)
    if not findings:
        return 0.0
    score = 0.18 * len(findings)
    kinds = {f.kind for f in findings}
    if "possible_sin" in kinds or "possible_payment_card" in kinds:
        score += 0.5
    if "possible_address" in kinds:
        score += 0.35
    return min(1.0, score)


def redact_text(text: str, *, keep_kind: bool = True) -> str:
    findings = find_sensitive(text)
    if not findings:
        return text
    out: list[str] = []
    cursor = 0
    for finding in findings:
        if finding.start < cursor:
            continue
        out.append(text[cursor : finding.start])
        label = f"[REDACTED:{finding.kind}]" if keep_kind else "[REDACTED]"
        out.append(label)
        cursor = finding.end
    out.append(text[cursor:])
    return "".join(out)
