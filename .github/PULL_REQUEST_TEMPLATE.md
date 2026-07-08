<!-- SPDX-License-Identifier: CC-BY-4.0 -->
## Summary

<!-- Describe what changed and why. Link the issue this closes if applicable. -->

Closes #

---

## Checklist

### Tests and CI

- [ ] All existing tests pass locally
  - Backend: `cd packages/prompt-composer && python -m pytest` and `cd services/convsim-core && python -m pytest`
  - Frontend: `pnpm test:types` and `pnpm --filter @convsim/web test`
  - CLI/pack-loader: `pnpm --filter @convsim/pack-loader test` and `pnpm --filter @convsim/cli test`
- [ ] New behaviour is covered by new or updated tests
- [ ] Smoke check passes: `bash scripts/smoke-check.sh`

### Schema validation

- [ ] Schema load test passes: `node packages/scenario-schema/tests/load-schemas.js`
- [ ] Schema validation test passes: `node packages/scenario-schema/tests/validate-schemas.js`
- [ ] Zod unit tests pass: `pnpm --filter @convsim/scenario-schema exec vitest run`

### Pack validation (if packs changed)

- [ ] Official packs pass schema validation: `node packages/scenario-schema/tests/validate-packs.js packs/official`
- [ ] Official packs pass full policy check: `for d in packs/official/*/; do convsim-validate-pack "$d"; done`
- [ ] Offline smoke test runs where possible: `for d in packs/official/*/; do npx convsim offline-smoke-test "$d"; done`

### Scenario pack requirements (if adding or modifying a pack)

- [ ] Pack contains only data and asset files (YAML/JSON, images, audio, docs) — no executables, scripts, or symlinks
- [ ] `manifest.yaml` includes a `license` field with an SPDX identifier
- [ ] All NPCs are clearly fictional (no named real persons)
- [ ] A safety policy YAML is present and referenced from `manifest.yaml`
- [ ] At least one smoke test per entry scenario exists in `tests/`
- [ ] Content rating matches the declared `content_rating` in `manifest.yaml`

### Documentation

- [ ] New documentation files include `<!-- SPDX-License-Identifier: CC-BY-4.0 -->` header
- [ ] New source files include `# SPDX-License-Identifier: Apache-2.0` header
- [ ] Links in new or modified docs resolve correctly

---

## Testing notes

<!-- Describe how you tested this change. What did you verify manually? -->
