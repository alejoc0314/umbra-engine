"""Escáner de secretos de alta precisión sobre las líneas añadidas de un diff."""

import re

from umbra.contracts.envelope import Finding

PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY"),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "anthropic-key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "openai-key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    "google-api-key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
}


def scan_diff(diff: str) -> list[Finding]:
    findings, current, line_no = [], None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            line_no = int(match.group(1)) - 1 if match else 0
        elif line.startswith("+"):
            line_no += 1
            for rule, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(Finding(severity="critical", rule=rule, file=current,
                                            line=line_no, message=f"posible secreto ({rule})"))
        elif not line.startswith("-"):
            line_no += 1
    return findings
