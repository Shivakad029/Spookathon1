# Vendored PyRIT attack data

The files in this directory originate from Microsoft PyRIT (Python Risk
Identification Tool for generative AI), version 1.1.0, released under the MIT
License (see LICENSE in this directory).

- `jailbreak/*.yaml` — adversarial prompt templates from
  `pyrit/datasets/jailbreak/templates/`, copied **unmodified**, except:
    - `jailbreak/anti_gpt.yaml` — **adapted** from PyRIT's "AntiGPT" template:
      ChatGPT/AntiGPT references changed to Claude/AntiClaude to better target the
      Anthropic model under test. This is a derivative work; the MIT License
      permits modification, and the original attribution is retained in the file.
- `seeds/psfuzz_steal_system.prompt` — system-prompt-extraction seed from
  `pyrit/datasets/seed_datasets/local/`, copied unmodified.

Source: https://github.com/Azure/PyRIT

Why vendored: the auditor prefers the installed `pyrit` package as its attack
source when it is importable (see `app/auditor/attack_source.py`). These copies
let the project and its CI run without installing PyRIT's full runtime. They are
the *attack phrasings*; the benign banking test objectives this project adds
live in `attacks/objectives.yaml`.
