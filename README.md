# 🛡️ AI Model Risk Auditor

**An agentic AI red-team and model-risk auditor for banking AI.**
Built for the AI Hackathon 2026 · authored by Shiva.

**Repository:** https://github.com/Shivakad029/Spookathon1

It attacks an AI assistant across **six risk types**, judges each response with
**deterministic evidence**, scores the overall risk, **auto-remediates** each
failing area and proves the fix, maps every finding to the controls bank
validators already use (SR 11-7, NIST AI RMF, OWASP LLM Top 10, ECOA/Reg B), and
enforces a pass/fail **release gate** in CI.

> **Attack source:** adversarial phrasings come from **Microsoft PyRIT** (MIT).
> This project adds the banking objectives, judging, scoring, remediation,
> reporting, release gate and dashboard. **All data is synthetic — never point
> this at a production system.**

Runs **offline in deterministic mock mode** with no account and no network, or
against the **live model** through the Nexus AI gateway (see Configuration).

---

## 1. Problem statement and solution

- **Problem & solution document:** [`docs/PROBLEM_AND_SOLUTION.md`](docs/PROBLEM_AND_SOLUTION.md)
- **Known limitations & next steps:** [`docs/LIMITATIONS_AND_NEXT_STEPS.md`](docs/LIMITATIONS_AND_NEXT_STEPS.md)
- **Architecture / flow diagram:** [`docs/architecture.md`](docs/architecture.md) · [`docs/architecture.html`](docs/architecture.html)

**In one line:** banks are deploying GenAI assistants with no adversarial
red-team and no pass/fail gate; this tool provides both, with reproducible
evidence a model-risk validator can trust.

---

## 2. The six risk types

| Module | Risk (OWASP / Reg) | Deterministic proof of a failure |
|---|---|---|
| **Prompt Injection** | Jailbreaks (LLM01) | planted canary / system prompt appears in reply |
| **Document Injection** | Indirect injection (LLM01) | instruction hidden in an uploaded doc is obeyed |
| **Data Leakage** | Data leakage (LLM02) | a planted canary account or another customer's data leaks |
| **Hallucination** | Hallucination (LLM09) | invents a policy that exists in no document |
| **Fair Lending** | Bias (ECOA/Reg B) | two prompts differing only by zip/name/age get different loan amounts |
| **Excessive Agency** | Excessive agency (LLM06) | a money-moving tool executes without verification |

Serious verdicts are **deterministic** (canary match, tool execution,
paired-prompt diff). Only the "did it invent a policy?" check uses an LLM judge,
and only when a model is configured; otherwise a grounding check is used. The
method is recorded on every finding.

---

## 3. Setup

**Requirements:** Python 3.11 or 3.12.

```bash
# 1. (recommended) create a virtual environment
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1      (or use the .bat launchers below)
# macOS/Linux: source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt
```

Windows one-click launchers are included: **`setup.bat`**, **`run.bat`**,
**`test.bat`**, **`audit.bat`**. VS Code / Visual Studio setup:
[`docs/VISUAL_STUDIO.md`](docs/VISUAL_STUDIO.md) · [`docs/WINDOWS_QUICKSTART.md`](docs/WINDOWS_QUICKSTART.md).

No configuration is needed to run — it works offline in mock mode out of the box.

---

## 4. Run / replay instructions

```bash
# Before / after audits (the core demo)
python -m app.cli audit --version v1       # 🔴 Critical  (risk 39.3, 10/53 passed)
python -m app.cli audit --version v2       # 🟢 Low        (risk 0.0, 53/53 passed)

# Auto-remediate: turn on one control per failing module and prove it worked
python -m app.cli remediate

# Release gate (exit code 1 on fail — this is what CI runs)
python -m app.cli gate --version v1        # FAIL (exit 1)
python -m app.cli gate --version v2        # PASS (exit 0)

# Write a self-contained HTML validation report
python -m app.cli audit --version v1 --report report.html --with-remediation

# Other commands
python -m app.cli suite        # test-suite summary (counts, attack source)
python -m app.cli inventory    # the AI model inventory
python -m app.cli ping         # check the live model connection (one call)
python -m app.cli preflight    # pre-demo: ping all configured models on both endpoints
```

**Live dashboard (replay visually):**
```bash
python run_server.py           # or: uvicorn app.api:app --reload   (or run.bat)
# open http://localhost:8000
```
Click **Audit v1** → red, **Critical**, gate **FAIL**; **Audit v2** → green,
**Low**, gate **PASS**; **Auto-remediate** → each module red → green.

**Replaying a stored run:** every audit is saved to a local SQLite database
(`output/auditor.db`); `GET /api/report/{run_id}` re-renders any past run's report.

---

## 5. Configuration

All configuration is via environment variables (a local `.env` file;
`cp .env.example .env`). **With everything blank, the tool runs offline in mock
mode.** `.env` is gitignored — never commit secrets.

### Run against the live model (Nexus AI gateway)
```dotenv
# OpenAI-compatible endpoint
AZURE_OPENAI_ENDPOINT=https://m-aix-7api-aigateway-01.azure-api.net/aix-openai-api/v1/models
AZURE_OPENAI_DEPLOYMENT=gpt-5.6-terra
AZURE_OPENAI_API_VERSION=2025-04-01-preview

# Gateway auth: the team key is sent in a custom header (not Authorization)
AUDITOR_GATEWAY_AUTH_HEADER=mtb-client_id
MTB_CLIENT_ID=<your team key>              # never commit this

# Claude endpoint on the same gateway (used by `preflight` / optional target)
ANTHROPIC_GATEWAY_ENDPOINT=https://m-aix-7api-aigateway-01.azure-api.net/aix-anthropic-api/v1/anthropic
ANTHROPIC_MODEL=claude-sonnet-5
ANTHROPIC_VERSION=2023-06-01

# Use the live model for the target bot and the hallucination judge
AUDITOR_USE_LLM_TARGET=true
AUDITOR_USE_LLM_JUDGE=true
```

| Variable | Meaning | Default |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | OpenAI-compatible base URL | *(blank → mock)* |
| `AZURE_OPENAI_DEPLOYMENT` | model id to attack (see Exact model IDs) | `gpt-5.6-terra` |
| `AZURE_OPENAI_API_VERSION` | gateway api-version | `2024-10-21` |
| `AUDITOR_GATEWAY_AUTH_HEADER` | custom auth header name | *(blank = Authorization: Bearer)* |
| `MTB_CLIENT_ID` | the team key (sent in that header) | *(blank)* |
| `ANTHROPIC_GATEWAY_ENDPOINT` | Claude base URL on the gateway | *(blank)* |
| `AUDITOR_USE_LLM_TARGET` | attack the live model vs. mock | `false` |
| `AUDITOR_USE_LLM_JUDGE` | use the LLM for the hallucination check | `false` |
| `AUDITOR_GATE_MAX_RISK` | release-gate risk threshold | `10` |
| `AUDITOR_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` | `INFO` |
| `AUDITOR_DEBUG_LLM` | print every model request/response | `false` |
| `AUDITOR_LLM_LOG` | also append those traces to a file | *(blank)* |
| `AUDITOR_DB_PATH` | SQLite database path | `output/auditor.db` |

The code also supports classic **Azure OpenAI** (`*.openai.azure.com`), **Azure
Foundry v1** (`*.services.ai.azure.com/openai/v1`, key or Microsoft Entra ID),
and **Azure AI Content Safety – Prompt Shields** (`AZURE_CONTENT_SAFETY_*`); the
endpoint style is auto-detected. See [`docs/AZURE_SETUP.md`](docs/AZURE_SETUP.md).

---

## 6. Runtime

- **Language/runtime:** Python 3.11/3.12.
- **Libraries:** FastAPI + Uvicorn (dashboard/API), PyYAML, httpx, pytest; `openai`
  (live OpenAI calls), `azure-identity` (only for Entra auth) — all optional for
  mock mode. See `requirements.txt`.
- **Default mode:** fully offline, deterministic — no network, no account.
- **Live mode:** HTTPS calls to the Nexus AI gateway. An audit is ~53 model calls;
  if a call fails or is filtered, it falls back to deterministic logic so a demo
  never stalls. Conversations are stateless (full history re-sent each call).
- **Persistence:** local SQLite at `output/auditor.db` (inventory + run history).
- **Logs:** console (stderr); set `AUDITOR_LLM_LOG` to persist model traces.

---

## 7. Exact model IDs

This project uses **`gpt-5.6-terra`** by default (`AZURE_OPENAI_DEPLOYMENT`).
Available on the Nexus AI gateway — use the exact id in the model field:

| Provider | Model | Exact model ID | Notes |
|---|---|---|---|
| OpenAI | GPT-5.6 Terra | `gpt-5.6-terra` | recommended default |
| OpenAI | GPT-5.6 Sol | `gpt-5.6-sol` (alias `gpt-5.6`) | strongest, highest cost |
| OpenAI | GPT-5.6 Luna | `gpt-5.6-luna` | fast / low-cost |
| Anthropic | Claude Sonnet 5 | `claude-sonnet-5` | default Claude target |
| Anthropic | Claude Opus 5 | `claude-opus-5` | stronger reasoning |
| Anthropic | Claude Opus 4.8 | `claude-opus-4-8` | Opus fallback |

Switch models by changing `AZURE_OPENAI_DEPLOYMENT` (OpenAI) or `ANTHROPIC_MODEL`
(Claude). `GET /v1/models` is not available — the id is set explicitly.

---

## 8. Architecture

```
PyRIT templates ─┐
                 ├─ attack_source → test suite → runner → target bot (v1/v2, guardrails)
objectives.yaml ─┘                                   │
                                                     ▼
                                     judge (canary / tool / pair / LLM)
                                                     │
                            ┌────────────────────────┼───────────────────────┐
                            ▼                         ▼                        ▼
                        scoring (risk,           remediation             regmap (SR 11-7,
                        rating)                  (prove each fix)        NIST, OWASP, ECOA)
                            │                         │                        │
                            └──────────── report (HTML) · gate (CI) · storage (inventory + runs)
                                                     │
                                          api (FastAPI + SSE) → dashboard
```

Full diagram: [`docs/architecture.md`](docs/architecture.md) /
[`docs/architecture.html`](docs/architecture.html). Per-file code walkthrough:
[`docs/CODE_WALKTHROUGH.md`](docs/CODE_WALKTHROUGH.md).

| Path | What it is |
|---|---|
| `app/target_bot/` | the ABC Bank Assistant (v1 ungoverned / v2 governed) + guardrails |
| `app/auditor/attack_source.py` | loads PyRIT phrasings, builds the test suite |
| `app/auditor/judge.py` | deterministic + LLM judging with evidence |
| `app/auditor/scoring.py` | weighted risk score and rating |
| `app/auditor/remediation.py` | one-control-per-module fix-and-retest |
| `app/auditor/regmap.py` | finding → regulatory-control mapping |
| `app/llm.py` | model + Content Safety calls (OpenAI / Foundry / gateway / Anthropic) |
| `app/gate.py` / `app/cli.py` | the release gate and CLI |
| `app/api.py` + `app/static/dashboard.html` | API, SSE streaming, live dashboard |
| `app/storage.py` | SQLite model inventory + run history |
| `attacks/objectives.yaml` | the banking test objectives (this project's) |
| `attacks/pyrit_vendored/` | MIT-licensed PyRIT templates + attribution |
| `tests/` | 14 offline end-to-end tests |

---

## 9. Tests & CI

```bash
python -m pytest tests/ -q      # 14 tests, fully offline
```
`.gitlab-ci.yml` runs the tests, writes the validation report as an artifact, and
runs the release gate. (Run tests with `AUDITOR_USE_LLM_*` false so they stay
offline and fast.)

---

## 10. Scope & safety

Hackathon prototype on **synthetic data** — the bot, customers and policies are
invented. It demonstrates the *method*; a production deployment would run against
non-production models only, behind access controls and logging, with thresholds
owned by model risk. Mapping findings to frameworks is **not** a compliance
attestation.

**Third-party licenses:** adversarial attack content is Microsoft PyRIT, MIT
License — see [`attacks/pyrit_vendored/LICENSE`](attacks/pyrit_vendored/LICENSE)
and [`NOTICE.md`](attacks/pyrit_vendored/NOTICE.md).
