"""Audit runner: sends each test case to the target bot, judges it, scores the run,
and (optionally) streams progress events for the live dashboard.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import yaml

from .. import llm
from ..config import ATTACKS_DIR
from ..target_bot.bot import Guardrails, ABCBankBot
from . import attack_source as src
from .judge import Finding, judge_pair, judge_single
from .scoring import Scorecard, score

log = logging.getLogger(__name__)

ProgressCB = Callable[[dict], None]


def _module_titles() -> dict[str, str]:
    spec = yaml.safe_load((ATTACKS_DIR / "objectives.yaml").read_text(encoding="utf-8"))["modules"]
    return {k: v["title"] for k, v in spec.items()}


@dataclass
class AuditResult:
    bot_version: str
    guardrails: list[str]
    engine: str
    pyrit_source: str
    duration_s: float
    scorecard: Scorecard
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bot_version": self.bot_version,
            "guardrails": self.guardrails,
            "engine": self.engine,
            "pyrit_source": self.pyrit_source,
            "duration_s": round(self.duration_s, 2),
            "scorecard": self.scorecard.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
        }


def _run_case(bot: ABCBankBot, case: src.TestCase) -> Finding:
    if case.technique == "paired":
        ra = bot.chat(case.pair[0], session=dict(case.session))
        rb = bot.chat(case.pair[1], session=dict(case.session))
        return judge_pair(case, ra, rb)

    history: list[dict] = []
    resp = None
    for i, turn in enumerate(case.turns):
        doc = case.document if i == len(case.turns) - 1 else None
        resp = bot.chat(turn, history=history, document=doc, session=dict(case.session))
        history.append({"role": "user", "content": turn})
        history.append({"role": "assistant", "content": resp.reply})
    return judge_single(case, resp)


def run_audit(bot_version: str = "v1", guardrails: Guardrails | None = None,
              modules: list[str] | None = None, engine: str | None = None,
              max_jailbreaks: int | None = None, progress: ProgressCB | None = None) -> AuditResult:
    """Run a full audit. bot_version is a label; guardrails decide actual behaviour.

    v1 -> no guardrails (ungoverned). v2 -> all guardrails (governed). A custom
    Guardrails object overrides the label (used by auto-remediation).
    """
    if guardrails is None:
        guardrails = Guardrails.all() if bot_version == "v2" else Guardrails.none()
    bot = ABCBankBot(guardrails=guardrails, engine=engine)

    cases = src.build_suite(modules=modules, max_jailbreaks=max_jailbreaks)
    titles = _module_titles()
    log.info("Audit start: version=%s engine=%s guardrails=[%s] cases=%d modules=%s",
             bot_version, bot.engine, ", ".join(guardrails.enabled()) or "none",
             len(cases), modules or "all")
    if progress:
        progress({"event": "start", "bot_version": bot_version, "total": len(cases),
                  "guardrails": guardrails.enabled(), "engine": bot.engine,
                  "pyrit_source": src.pyrit_source()})

    findings: list[Finding] = []
    llm.reset_tokens()
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        f = _run_case(bot, case)
        findings.append(f)
        log.debug("case %d/%d %s [%s/%s] -> %s via %s", i, len(cases), case.id,
                  case.module, case.technique, "PASS" if f.passed else "FAIL", f.method)
        if progress:
            progress({"event": "case", "i": i, "total": len(cases), "module": case.module,
                      "case_id": case.id, "passed": f.passed, "control": f.control,
                      "method": f.method, "severity": f.severity})
    sc = score(findings, titles)
    duration = time.time() - t0
    log.info("Audit done: version=%s rating=%s risk=%.1f passed=%d/%d control_failures=%d in %.2fs",
             bot_version, sc.rating, sc.risk_score, sc.passed, sc.total, sc.control_failures, duration)
    tok = llm.token_usage()
    if tok["calls"]:
        log.info("LLM tokens: %d model call(s), in=%d out=%d total=%d",
                 tok["calls"], tok["in"], tok["out"], tok["total"])
    result = AuditResult(
        bot_version=bot_version, guardrails=guardrails.enabled(), engine=bot.engine,
        pyrit_source=src.pyrit_source(), duration_s=duration, scorecard=sc, findings=findings)
    if progress:
        progress({"event": "done", "scorecard": sc.to_dict()})
    return result


def iter_audit(**kwargs) -> Iterator[dict]:
    """Generator wrapper so the API can stream events as they happen."""
    events: list[dict] = []
    run_audit(progress=events.append, **kwargs)
    yield from events
