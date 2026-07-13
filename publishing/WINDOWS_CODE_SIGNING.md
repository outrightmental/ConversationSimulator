<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Windows Code Signing

> **Purpose:** Step-by-step runbook for signing the Windows Conversation
> Simulator installer with an Authenticode certificate so that Windows Defender
> SmartScreen does not block the installer on end-user machines.
>
> **Audience:** Platform team members who run the release CI pipeline and
> any maintainer performing a manual release build.
>
> **Gate:** A signed Windows installer is required before Stage 3 (Steam private
> beta). See gate G3-01 in [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md).

---

## Background

Windows Defender SmartScreen applies a reputation score to executables. An
unsigned installer (one with no Authenticode signature) shows "Windows protected
your PC" and requires the user to click "More info → Run anyway" to proceed.
A signed installer from a recognised publisher suppresses the SmartScreen
warning once the certificate has accumulated download reputation.

### EV vs OV certificates

| Type | Immediate SmartScreen reputation | HSM required | Cost |
|------|----------------------------------|--------------|------|
| Extended Validation (EV) | Yes — trust is granted immediately | Yes (USB token or cloud HSM) | Higher |
| Organisation Validation (OV) | No — reputation builds from download count | No | Lower |

Outright Mental should obtain an **EV certificate** for the Stage 4 public
release to avoid SmartScreen warnings on first install. An OV certificate is
acceptable for Stage 3 private beta where the tester pool is small.

---

## Certificate procurement

Purchase an Authenticode code-signing certificate from a CA trusted by
Microsoft, such as DigiCert, Sectigo, or GlobalSign. The certificate must be
issued to **Outright Mental**.

### EV certificate delivery

EV certificates are delivered on a hardware security module (USB token or
via a cloud HSM service). The signing process uses the HSM directly:

```powershell
# Sign with an EV USB token using signtool (Windows SDK)
signtool.exe sign `
  /n "Outright Mental" `
  /tr http://timestamp.digicert.com `
  /td sha256 /fd sha256 /v `
  "apps\desktop\src-tauri\target\release\bundle\nsis\ConversationSimulator_*_x64-setup.exe"
```

For cloud HSM (e.g. DigiCert KeyLocker), install the vendor's signing client
and use the same `signtool.exe` command with the cloud-signed identity.

### OV certificate delivery

OV certificates are delivered as a `.pfx` file containing the certificate
chain and private key.

1. Purchase the certificate from a trusted CA.
2. Complete identity verification (they will contact Outright Mental directly).
3. Download the `.pfx` file after issuance.
4. Set a strong passphrase on the `.pfx`.

---

## CI setup (GitHub Actions secrets)

### Org-level secret inventory

The following Windows signing and scanning secrets are stored at the
**outrightmental organisation level**, scoped to `ConversationSimulator` and
`FeverTilt`. They are entered once and rotated in one place.

| Secret name | Contents | Used by |
|-------------|----------|---------|
| `WINDOWS_CODESIGN_CERT` | Base64-encoded PEM chain (leaf first) matching the Cloud KMS key | Future KMS/jsign signing step (see note below) |
| `GCP_SA_KEY_JSON` | GCP service-account key JSON for Cloud KMS access | Future KMS/jsign signing step |
| `GCP_KMS_KEY` | Fully-qualified Cloud KMS key resource path | Future KMS/jsign signing step |
| `AZURE_CLIENT_ID` | Azure service-principal client ID for Defender storage | Future Defender upload step |
| `AZURE_CLIENT_SECRET` | Azure service-principal secret | Future Defender upload step |
| `AZURE_TENANT_ID` | Azure tenant ID | Future Defender upload step |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID | Future Defender upload step |
| `AZURE_SCAN_STORAGE_ACCOUNT` | Storage account name for Defender-monitored upload | Future Defender upload step |
| `AZURE_SCAN_CONTAINER` | Blob container name for Defender-monitored upload | Future Defender upload step |

> **Note:** The KMS/jsign signing migration and the Azure Defender upload job
> are tracked as separate issues. Until those land, `release.yml` uses the
> PFX-based approach described below, with `WINDOWS_SIGN_CERT_PFX` and
> `WINDOWS_SIGN_CERT_PASSWORD` set as repo-level secrets.

**To set or rotate org-level secrets** (values supplied interactively, never
committed):

```bash
gh secret set WINDOWS_CODESIGN_CERT \
  --org outrightmental \
  --visibility selected \
  --repos ConversationSimulator,FeverTilt
# repeat for each secret in the table above
```

Or use the org Settings UI: GitHub → outrightmental org **Settings → Secrets
and variables → Actions → Secrets → New organisation secret**, then set
**Repository access** to *Selected repositories: ConversationSimulator, FeverTilt*.

**Rotation:** Rotating a secret at org level updates it for all scoped
repositories simultaneously. Run `gh secret list --org outrightmental` to
confirm the inventory after any change.

### Current approach: PFX-based signing (repo-level secrets)

Until the KMS migration lands, the release workflow uses `.pfx`-based
Authenticode signing via `signtool.exe`. Store the following as
**repository-level** GitHub Actions secrets (Settings → Secrets and variables
→ Actions → Secrets):

| Secret name | Contents |
|-------------|----------|
| `WINDOWS_SIGN_CERT_PFX` | Base64-encoded `.pfx` file |
| `WINDOWS_SIGN_CERT_PASSWORD` | Passphrase for the `.pfx` file |

**To base64-encode the `.pfx` on Windows:**
```powershell
certutil -encode cert.pfx cert.b64
# Copy the content between -----BEGIN CERTIFICATE----- and -----END CERTIFICATE-----
# (including all lines) into the secret value.
```

**To base64-encode on macOS / Linux:**
```bash
base64 -i cert.pfx -o cert.b64
```

The release workflow (`release.yml`) signs the installers in a dedicated
**"Sign Windows installers (Authenticode)"** step that runs *after*
`cargo tauri build`, not through Tauri's own bundler. That step decodes
`WINDOWS_SIGN_CERT_PFX` to a temporary `.pfx`, locates `signtool.exe` from the
Windows SDK, and signs every `.exe` and `.msi` under
`apps\desktop\src-tauri\target\release\bundle`. When `WINDOWS_SIGN_CERT_PFX`
is absent (contributor forks, unsigned local builds), the step logs a notice
and exits 0, producing an unsigned installer. The step only runs on Windows
runners (`if: runner.os == 'Windows'`).

For **EV certificates via cloud HSM**, the CI integration depends on the
vendor. Consult DigiCert's or Sectigo's CI documentation for the required
environment variables and CLI tooling for GitHub Actions.

---

## Manual signing

Use this procedure for local testing or one-off manual signing.

### Prerequisites

- Windows SDK installed (provides `signtool.exe`)
  - Install via: Visual Studio Installer → Individual Components → Windows 10 SDK
  - Or download the [Windows SDK](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/)
  directly.
- The `.pfx` file accessible on disk (OV), or the EV USB token plugged in (EV).

### Step 1 — Build the unsigned installer

```powershell
# From the repo root in PowerShell:
pnpm --filter @convsim/desktop build

# Unsigned installers are in:
#   apps\desktop\src-tauri\target\release\bundle\nsis\ConversationSimulator_*_x64-setup.exe
#   apps\desktop\src-tauri\target\release\bundle\msi\ConversationSimulator_*_x64.msi
```

### Step 2 — Sign the installers

```powershell
# OV certificate (.pfx)
signtool.exe sign `
  /f path\to\cert.pfx `
  /p <password> `
  /tr http://timestamp.digicert.com `
  /td sha256 /fd sha256 /v `
  "apps\desktop\src-tauri\target\release\bundle\nsis\ConversationSimulator_*_x64-setup.exe"

# Sign the MSI as well if distributing it
signtool.exe sign `
  /f path\to\cert.pfx `
  /p <password> `
  /tr http://timestamp.digicert.com `
  /td sha256 /fd sha256 /v `
  "apps\desktop\src-tauri\target\release\bundle\msi\ConversationSimulator_*_x64.msi"
```

The `/tr` flag adds a trusted timestamp so the signature remains valid after
the certificate expires. Always include it.

### Step 3 — Verify the signature

```powershell
# Verify via signtool
signtool.exe verify /pa /v `
  "apps\desktop\src-tauri\target\release\bundle\nsis\ConversationSimulator_*_x64-setup.exe"

# Or check the Properties dialog: right-click the .exe → Properties → Digital Signatures tab
```

A valid signature shows `Verified: Outright Mental` in the Properties dialog
and `Number of files successfully Verified: 1` in the signtool output.

---

## SmartScreen reputation building

Even a signed installer will initially show a SmartScreen warning if the
certificate is new or the download count is low (this applies to OV certificates;
EV certificates bypass this check).

### For Stage 3 private beta (OV certificate)

- Advise testers: click **More info → Run anyway**. This is expected during
  the private beta with a new certificate.
- Each "Run anyway" click contributes download signal to SmartScreen.
- After a few hundred downloads from diverse IPs, the warning typically stops
  appearing for most users.

### For Stage 4 public release (EV certificate recommended)

- An EV certificate grants immediate SmartScreen trust — no download reputation
  required.
- If using an OV certificate at public launch, communicate clearly in the
  Steam store page that users may see a SmartScreen warning and provide the
  "More info → Run anyway" instructions.
- Monitor the Steam review queue for reports of SmartScreen warnings; they are
  a signal that reputation building is incomplete.

---

## Antivirus false positives

Freshly compiled Rust / Tauri executables are occasionally flagged by antivirus
heuristic detection.

### Triage steps

1. Download a copy of the flagged binary.
2. Submit it to [VirusTotal](https://www.virustotal.com/) for a multi-engine scan.
3. If fewer than 3 engines flag it: the binary is likely safe; submit a
   false-positive report through each flagging vendor's portal.
4. If 3 or more engines flag it: investigate the build pipeline for unexpected
   file inclusions; run the depot audit to confirm no prohibited content is
   embedded.
5. Wait 24–48 hours after submitting false-positive reports; vendor definitions
   update on that cycle.

The depot audit (`./scripts/depot-audit.sh` or `depot-audit.ps1`) catches the
most common sources of false positives — large binary files, Python pickles,
and unexpected model checkpoints.

---

## Rotating the certificate

When the code-signing certificate approaches expiry:

1. Purchase a new certificate from the same or another trusted CA.
2. Export as `.pfx` and base64-encode as described above.
3. Update `WINDOWS_SIGN_CERT_PFX` and `WINDOWS_SIGN_CERT_PASSWORD` as
   repository-level GitHub Actions secrets.
   Once the KMS migration lands, update the org-level `WINDOWS_CODESIGN_CERT`
   secret instead (see [Org-level secret inventory](#ci-setup-github-actions-secrets)):
   ```bash
   gh secret set WINDOWS_CODESIGN_CERT \
     --org outrightmental \
     --visibility selected \
     --repos ConversationSimulator,FeverTilt
   ```
4. Rebuild and sign the current release to confirm the new certificate works.
5. Files signed with the old certificate remain valid because of the trusted
   timestamp embedded at signing time (`/tr`).

---

## Troubleshooting

### SmartScreen blocks the installer despite a valid signature

**Cause:** The certificate is newly issued (OV) and has not yet built reputation.

**Fix:** Advise users to click "More info → Run anyway". Continue distributing
the signed installer — each install contributes to SmartScreen reputation. If
this is the Stage 4 public release, obtain an EV certificate for the next build.

### `signtool.exe` exits with error 0x800b0101 (certificate expired)

**Cause:** The signing certificate has expired.

**Fix:** Rotate to a new certificate as described above. Files previously signed
with a valid timestamp are unaffected; only new builds need to be signed with
the new certificate.

### `signtool.exe` exits with error 0x80096010 (subject does not match)

**Cause:** The installer file path pattern does not match any files, or the
wrong working directory was used.

**Fix:** Use the full absolute path to the installer or confirm the glob pattern
matches the actual filename. Run `dir apps\desktop\src-tauri\target\release\bundle\nsis\`
to see the exact file name.

### CI build produces unsigned installer even when secrets are set

**Cause:** The "Sign Windows installers (Authenticode)" step only runs on
Windows runners, and it skips (exits 0) when `WINDOWS_SIGN_CERT_PFX` is empty.
If the `windows-latest` runner was not used, or the secret was not exposed to
the step's `env:` block, the installer is produced unsigned.

**Fix:** Confirm the release workflow runs the Windows build job on
`windows-latest` and that `WINDOWS_SIGN_CERT_PFX` / `WINDOWS_SIGN_CERT_PASSWORD`
are mapped in that step's `env:` block. In the step log, look for
`Using signtool: ...` and `Signing: ...` lines. The message
`WINDOWS_SIGN_CERT_PFX is not set — producing unsigned build` means the secret
did not reach the step.

---

## Links

- [`docs/platform-notes.md` — Windows section](../docs/platform-notes.md#windows) — system requirements, build prerequisites, code signing overview
- [`docs/steam-mvp-scope.md` — G3-01](../docs/steam-mvp-scope.md) — Stage 3 gate: signed Windows installer required
- [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) — Steam deploy workflow and troubleshooting
- [`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md) — depot content policy and approved binary payload list
- [Tauri Windows signing docs](https://tauri.app/distribute/sign/windows) — upstream reference for Tauri signing variables
- [Microsoft — signtool reference](https://docs.microsoft.com/en-us/windows/win32/seccrypto/signtool) — full signtool flag reference
- [DigiCert timestamp URL](http://timestamp.digicert.com) — recommended timestamp authority (also: Sectigo `http://timestamp.sectigo.com`, GlobalSign `http://timestamp.globalsign.com`)
