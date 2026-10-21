# Known Limitations & Recommended Next Steps

**Project:** AI Model Risk Auditor · AI Hackathon 2026
**Repository:** https://github.com/Shivakad029/Spookathon1

This is an honest account of what the prototype does **not** do yet, and the
roadmap to production. Naming the limits is part of the model-risk discipline the
tool is meant to support.

---

## Known limitations

### Target & data
1. **The target bot is a stand-in.** The default bot is a deterministic,
   rule-based (regex + templates) assistant with *planted* flaws so the demo has
   something to find offline. It is not a real model — it demonstrates the
   *method*. (Live mode against `gpt-5.6-terra` is supported; see below.)
2. **Synthetic data only.** Customers, accounts, policies and canaries are
   invented. Nothing is a real finding until the tool is pointed at a real model.
3. **Toy retrieval.** `retrieve_policy()` is keyword overlap over a few markdown
   files — no embeddings or semantic search. Enough to show grounded-vs-
   hallucinated behaviour, not a production RAG step.

### Attacks & judging
4. **Static attack set.** Jailbreak phrasings are PyRIT's vendored templates
   (DAN, AIM, etc.) applied by string substitution — not adaptive or generative.
   A determined adversary evolves faster than a fixed template list.
5. **Regex-based guardrails.** `prompt_shield`, `output_filter` etc. are
   deterministic patterns. They are transparent and reproducible, but a novel
   phrasing can slip past them — hence `prompt_injection` remediation shows
   **partial** (≈95%), not 100%. This is by design (defence in depth needs
   layering) but is a real coverage gap.
6. **One LLM-graded check.** Only the hallucination check can use an LLM judge;
   its agreement with human labels is assumed, not measured here.
7. **Prompt Shields not on the hackathon gateway.** The Nexus AI gateway does not
   expose Azure AI Content Safety, so `prompt_shield` runs on its regex fallback
   in that configuration (the Azure Content Safety path exists but is unused).

### Scoring, gate & scope
8. **Thresholds are illustrative.** The risk weights and the gate threshold
   (default 10) are sensible defaults, not a calibrated risk appetite — in
   production, model risk owns these numbers.
9. **Framework mapping is not an attestation.** Mapping findings to SR 11-7 /
   NIST / OWASP / ECOA is illustrative, not a compliance certification.
10. **No auth / multi-tenant on the dashboard.** The FastAPI app and SQLite store
    have no authentication, RBAC or encryption — fine for a local demo, not for
    shared or production use.
11. **Gateway auth header unconfirmed.** The OpenAI endpoint's auth header name
    was "[TO BE CONFIRMED]" in the hackathon doc; it defaults to `mtb-client_id`
    and is configurable via `AUDITOR_GATEWAY_AUTH_HEADER`.

---

## Recommended next steps

### Highest leverage (near term)
1. **Attack the live model end-to-end.** Run the full suite against
   `gpt-5.6-terra` / `claude-sonnet-5` and report real findings — which attacks a
   production-grade model resists and which still land. (`preflight` + the live
   `.env` are already in place.) This is the biggest credibility jump.
2. **Quantitative fair-lending.** Replace the pass/fail bias check with a
   disparate-impact / statistical-parity measure across many paired profiles, with
   a chart — the single most important risk for a bank audience.
3. **LLM-based prompt shield.** Add an AI classifier for injection (via the same
   gateway model) with the regex as fallback, to close the `prompt_injection`
   coverage gap.

### Medium term
4. **Real retrieval.** Swap the keyword retriever for Azure AI Search / a vector
   store, keeping the same `grounded_only` contract.
5. **Adaptive attacks.** Use PyRIT's model-driven attack generation (and
   multi-turn orchestrators) instead of only static templates.
6. **More controls, layered.** Input PII minimization, spotlighting/delimiting of
   untrusted document text, output link/exfiltration guard, toxicity/fairness
   filter, step-up auth per transaction tier, human-in-the-loop above a threshold
   (see [`ADDING_GUARDRAILS.md`](ADDING_GUARDRAILS.md)).
7. **Judge validation.** Measure the LLM judge's agreement with human labels and
   report it, so the one AI-graded check is itself evidenced.

### Production hardening
8. **Durable storage & auth.** Move from SQLite to Postgres; add authentication,
   RBAC, audit logging and encryption to the dashboard/API.
9. **Governed thresholds & sign-off.** Let model risk own the weights, the gate
   threshold and an approval workflow; version the scorecard criteria.
10. **Secrets & tenancy.** Key Vault / managed identity for credentials;
    per-model, per-environment isolation; rate-limit handling and cost controls
    for large live runs.

---

## Summary

The prototype proves the **method** — attack → prove failure with deterministic
evidence → score → gate → remediate-and-prove → map to controls — with a working
offline demo and a live-model path. The next steps turn it from a convincing
demonstration into a tool model-risk and engineering teams could adopt: real
findings against real models, quantitative fairness, adaptive attacks, layered
controls, and production-grade storage, auth and governance.
