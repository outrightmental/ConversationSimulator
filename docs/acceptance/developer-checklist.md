<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Developer acceptance checklist

**Owner:** Developer experience team
**Scope:** Every MVP release candidate must pass or document exceptions.

The developer journey covers: run locally → understand docs → add a runtime adapter → add a scenario → run tests → read debug output → file an issue.

---

## Automated checks (run in CI)

```bash
# From repo root:
python -m pytest tests/acceptance/test_developer_flow.py -v
```

| Test class | What it verifies | CI label |
|---|---|---|
| `TestMonorepoStructure` | Expected directories and entry-point scripts are present | `[setup]` |
| `TestSchemaLoad` | `convsim_core`, `convsim_prompt`, runtime types, and JSON schemas all load | `[setup]` |
| `TestPackValidationCLI` | `validate_pack_dir` is callable; returns `[]` on valid pack; official packs pass | `[pack-valid]` |
| `TestRuntimeRegistry` | Fake runtime ID is `"fake"`, reports READY, lists at least one model | `[health]` |
| `TestDebugLogging` | Session create emits at least one log record; health endpoint includes `runtime` and `database` | `[health]` |
| `TestAdapterStub` | A subclass of `FakeChatRuntime` satisfies the adapter interface | `[setup]` |
| `TestOfficialPackGate` | All official packs pass `validate_pack_dir` | `[pack-valid]` |
| `TestBackendHealth` | `/api/health` returns `status: ok`; has `status`, `database`, `runtime` fields | `[health]` |

All automated checks must pass before any manual step begins.

---

## Manual checks (sign-off required)

### D-M1 — Run locally from scratch

```bash
git clone https://github.com/outrightmental/ConversationSimulator.git
cd ConversationSimulator
./scripts/setup.sh
./scripts/dev.sh
```

- [ ] `setup.sh` completes without errors
- [ ] `dev.sh` starts all services; logs show no error-level lines at startup
- [ ] `curl http://127.0.0.1:7355/api/health` returns `{"status": "ok", ...}`

### D-M2 — Understand the documentation

Read `README.md`, `docs/architecture.md`, and `docs/runtime-adapters.md`.

- [ ] Developer can describe the 5 services and their ports (from `docs/architecture.md`)
- [ ] Developer can locate the fake runtime source in `services/convsim-core/convsim_core/runtime/fake.py`
- [ ] Developer can describe the difference between a PLAY-mode and EXPLICIT_DOWNLOAD network call

### D-M3 — Add a runtime adapter

Follow `docs/runtime-adapters.md`.

- [ ] Create a minimal adapter class that extends `FakeChatRuntime`
- [ ] Override `id` and `display_name`
- [ ] Confirm the adapter's `health()` returns `READY`
- [ ] (Automated: `TestAdapterStub` above covers this)

### D-M4 — Add a scenario

Follow `docs/scenario-authoring.md`.

- [ ] Create a new scenario YAML under `packs/local-dev/<my-pack>/scenarios/`
- [ ] Run `node packages/scenario-schema/tests/validate-packs.js packs/local-dev/<my-pack>` — exits 0
- [ ] Scenario appears in the `/api/scenarios` list after restart

### D-M5 — Run the test suite

```bash
# Backend
cd services/convsim-core && python -m pytest -v

# Acceptance
cd ../.. && python -m pytest tests/acceptance/ -v

# Frontend
pnpm --filter @convsim/web test
pnpm --filter @convsim/cli test
```

- [ ] All backend tests pass
- [ ] All acceptance tests pass
- [ ] Frontend tests pass (or known failures documented)

### D-M6 — Read debug output

```bash
cd services/convsim-core
CONVSIM_LOG_LEVEL=DEBUG python -m convsim_core.main &
curl -s -X POST http://127.0.0.1:7355/api/sessions \
     -H 'Content-Type: application/json' \
     -d '{"scenario_id":"behavioral_interview","difficulty":"normal","player_role_name":"Dev","language":"en","input_mode":"text-only","tts_enabled":false,"show_state_meters":false,"save_transcript":true}'
```

- [ ] DEBUG log lines appear in the terminal for the session create call
- [ ] Log lines include session_id and scenario_id context

### D-M7 — File an issue

- [ ] Developer can find the issue templates in `.github/ISSUE_TEMPLATE/`
- [ ] Bug report template includes reproduction steps and environment fields
- [ ] Developer can link to `CONTRIBUTING.md` for guidelines

---

## Sign-off

| Item | Result | Tester | Date | Notes |
|---|---|---|---|---|
| Automated suite | PASS / FAIL | | | |
| D-M1 Run locally | PASS / FAIL / SKIP | | | |
| D-M2 Understand docs | PASS / FAIL / SKIP | | | |
| D-M3 Add adapter | PASS / FAIL / SKIP | | | |
| D-M4 Add scenario | PASS / FAIL / SKIP | | | |
| D-M5 Run tests | PASS / FAIL / SKIP | | | |
| D-M6 Debug output | PASS / FAIL / SKIP | | | |
| D-M7 File issue | PASS / FAIL / SKIP | | | |

**Release decision:** All automated checks PASS + manual checks D-M1 through D-M7 PASS (or documented SKIP) required before MVP tag.
