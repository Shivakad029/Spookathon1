"""Auto-remediation: for each module that fails, propose the guardrail
that fixes it, re-run just that module with the guardrail on, and report whether the
fix worked. This proves each recommended control rather than asserting it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..target_bot.bot import Guardrails
from .runner import run_audit

log = logging.getLogger(__name__)

# Which guardrail remediates each module, and the human-readable fix description.
MODULE_FIX = {
    "prompt_injection": ("prompt_shield", "Enable Azure AI Content Safety Prompt Shields on user input"),
    "doc_injection": ("document_scan", "Scan uploaded documents for injected instructions before use"),
    "data_leakage": ("output_filter", "Filter output for canaries, the system prompt, and other customers' accounts"),
    "hallucination": ("grounded_only", "Answer policy questions only from retrieved, cited policy text"),
    "fair_lending": ("strip_protected", "Remove names and zip codes before any credit decision"),
    "excessive_agency": ("tool_authz", "Require a verified identity and OTP before any tool executes"),
}


@dataclass
class Remediation:
    module: str
    guardrail: str
    fix: str
    before_pass_rate: float
    after_pass_rate: float
    before_failed: int
    after_failed: int
    resolved: bool
    control_regressions: int        # new control failures the fix introduced (over-blocking)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def remediate(baseline, engine: str | None = None) -> list[Remediation]:
    """Given a baseline AuditResult, remediate each failing module one guardrail at a time."""
    out: list[Remediation] = []
    failing = {m.module: m for m in baseline.scorecard.modules if m.failed > m.control_failed}
    log.info("Remediation: %d failing module(s) to fix: %s", len(failing), ", ".join(failing) or "none")
    for module, before in failing.items():
        if module not in MODULE_FIX:
            log.warning("No remediation mapping for module '%s' — skipping", module)
            continue
        guard_name, fix = MODULE_FIX[module]
        g = Guardrails.from_value([guard_name])
        after_result = run_audit(bot_version="remediated", guardrails=g, modules=[module], engine=engine)
        after = after_result.scorecard.modules[0]
        resolved = (after.failed - after.control_failed) == 0
        log.info("Remediate %s with %s: %.1f%% -> %.1f%% (%s)", module, guard_name,
                 before.pass_rate, after.pass_rate, "resolved" if resolved else "partial")
        out.append(Remediation(
            module=module, guardrail=guard_name, fix=fix,
            before_pass_rate=before.pass_rate, after_pass_rate=after.pass_rate,
            before_failed=before.failed - before.control_failed,
            after_failed=after.failed - after.control_failed,
            resolved=resolved,
            control_regressions=after.control_failed))
    return out
