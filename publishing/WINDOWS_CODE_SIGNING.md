<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Windows Code Signing

> **Purpose:** Runbook for Windows Authenticode signing via Google Cloud KMS +
> jsign. The private key never exists on the runner; signing uses a Cloud HSM key
> whose public certificate is stored as an org-level GitHub Actions secret.
>
> **Audience:** Platform team members who manage the release CI pipeline and any
> maintainer performing a manual release build.
>
> **Gate:** A signed Windows installer is required before Stage 3 (Steam private
> beta). See gate G3-01 in [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md).

---

## Architecture

Signing is split into two phases:

1. **Payload signing (during `tauri build`)** — Tauri's `bundle.windows.signCommand`
   hook calls `scripts/jsign-sign.ps1` for each binary it packages
   (`ConversationSimulator.exe`, `convsim-core.exe`, and any other bundled
   executables). This means the NSIS payload is signed before it is packaged.

2. **Installer signing (post-build)** — The release workflow's "Sign Windows
   installers (Authenticode)" step calls the same script for the outer NSIS `.exe`
   and MSI packages.

### Why Cloud KMS?

| Property | Cloud KMS (current) | PFX / signtool (legacy) |
|----------|---------------------|-----------------------------|
| Private key location | Google Cloud HSM — never on runner | Decoded to `RUNNER_TEMP` per run |
| Key rotation | Issue new cert against new key version; pinning catches stale pairs | Replace the PFX secret |
| Shared across products | Yes — same key signs FeverTilt and ConversationSimulator | No — separate PFX per repo |
| SmartScreen immediate trust | Requires EV cert (applies regardless of signing method) | Same |

### Signing priority in `scripts/jsign-sign.ps1`

1. **GCP KMS** — when `GCP_SA_KEY_JSON` + `GCP_KMS_KEY` + `WINDOWS_CODESIGN_CERT` are all present.
2. **PFX fallback** — when `WINDOWS_SIGN_CERT_PFX` + `WINDOWS_SIGN_CERT_PASSWORD` are present.
3. **INFO-skip** — when neither is configured (fork builds, local dev — produces an unsigned artifact).

---

## Key-version pinning

At signing time, `jsign-sign.ps1` calls the Cloud KMS API to enumerate all
**ENABLED** `CryptoKeyVersions` for the configured key. It compares each
version's public key (SubjectPublicKeyInfo DER) with the leaf certificate in
`WINDOWS_CODESIGN_CERT`. Signing proceeds only with the version whose public key
matches the certificate.

**Why this matters:**

- If the KMS key is rotated (new version enabled, old version disabled), the
  script fails loudly with an actionable message rather than producing a
  signature that chains to the wrong certificate.
- The certificate in `WINDOWS_CODESIGN_CERT` and the active KMS key version must
  be consistent at all times.

**If pinning fails:** the script exits with:

```
ERROR: Key-version pinning failed — no ENABLED CryptoKeyVersion in
<keyring>/cryptoKeys/<key> has a public key matching the leaf certificate
in WINDOWS_CODESIGN_CERT. Check that the leaf cert is listed first in the PEM
chain and that the certificate was issued against the current key version. ...
```

---

## Org-level secret inventory

All secrets below are stored at the **outrightmental organisation level**,
scoped to `ConversationSimulator` and `FeverTilt`. Set or rotate them in one
place and both products pick up the change automatically.

| Secret name | Contents | Used by |
|-------------|----------|---------|
| `WINDOWS_CODESIGN_CERT` | Base64-encoded PEM certificate chain (leaf first) matching the Cloud KMS key | `jsign-sign.ps1` KMS path |
| `GCP_SA_KEY_JSON` | GCP service-account key JSON for Cloud KMS access | `jsign-sign.ps1` KMS path |
| `GCP_KMS_KEY` | Fully-qualified Cloud KMS key resource path, e.g. `projects/P/locations/global/keyRings/KR/cryptoKeys/K` | `jsign-sign.ps1` KMS path |
| `WINDOWS_SIGN_CERT_PFX` | Base64-encoded PFX (legacy fallback only) | `jsign-sign.ps1` PFX path |
| `WINDOWS_SIGN_CERT_PASSWORD` | PFX passphrase (legacy fallback only) | `jsign-sign.ps1` PFX path |

**Setting or rotating org-level secrets** (supply values interactively, never commit):

```bash
gh secret set WINDOWS_CODESIGN_CERT \
  --org outrightmental \
  --visibility selected \
  --repos ConversationSimulator,FeverTilt
# Repeat for GCP_SA_KEY_JSON and GCP_KMS_KEY.
```

Or via the GitHub UI: **outrightmental org → Settings → Secrets and variables →
Actions → New organisation secret → Repository access: Selected repositories**.

---

## Certificate issuance against a Cloud KMS key (CSR flow)

Certificates are issued to the Cloud KMS key rather than a locally-generated
private key. The CA signs a CSR whose private key lives in Cloud KMS and never
leaves it.

### Step 1 — Create a Cloud KMS key ring and asymmetric signing key

```bash
gcloud kms keyrings create convsim-signing \
  --location global \
  --project YOUR_PROJECT

gcloud kms keys create windows-codesign \
  --location global \
  --keyring convsim-signing \
  --purpose asymmetric-signing \
  --default-algorithm rsa-sign-pkcs1-4096-sha256 \
  --project YOUR_PROJECT
```

### Step 2 — Export the public key and generate a CSR

```bash
# Export the public key from KMS
gcloud kms keys versions get-public-key 1 \
  --key windows-codesign \
  --keyring convsim-signing \
  --location global \
  --project YOUR_PROJECT \
  --output-file kms-public.pem

# Generate a CSR using OpenSSL with the KMS public key.
# Replace the distinguished name fields with the organisation's details.
openssl req -new \
  -key kms-public.pem \
  -keyform PEM \
  -subj "/C=CA/ST=Ontario/L=Toronto/O=Outright Mental Inc/CN=Outright Mental Inc" \
  -out codesign.csr
```

> For RSA PKCS#1 CSRs against a KMS key where you cannot sign locally, use the
> `kms_csr_helper.py` script from the FeverTilt repo
> (`publishing/signing/windows/kms_csr_helper.py`) which signs the CSR
> TBSCertificateRequest using the KMS signing API.

### Step 3 — Submit the CSR to the CA

Submit `codesign.csr` to DigiCert, Sectigo, or your chosen CA through their
code-signing order flow. The CA will verify Outright Mental's identity and issue
a certificate. Download the full chain as a PEM file (leaf certificate first,
followed by any intermediates).

### Step 4 — Store the certificate chain

```bash
# Verify the chain:
openssl verify -CAfile chain.pem leaf.pem

# Base64-encode the full PEM chain (leaf first):
base64 -i fullchain.pem | tr -d '\n' > fullchain.b64

# Set the org-level secret:
gh secret set WINDOWS_CODESIGN_CERT \
  --org outrightmental \
  --visibility selected \
  --repos ConversationSimulator,FeverTilt \
  < fullchain.b64
```

### Step 5 — Configure the remaining KMS secrets

```bash
# GCP_KMS_KEY: full resource path of the key (not a version)
# e.g. projects/my-project/locations/global/keyRings/convsim-signing/cryptoKeys/windows-codesign
gh secret set GCP_KMS_KEY --org outrightmental --visibility selected \
  --repos ConversationSimulator,FeverTilt

# GCP_SA_KEY_JSON: service-account key with cloudkms.cryptoKeyVersions.list
# and cloudkms.cryptoKeyVersions.useToSign permissions on the key
gh secret set GCP_SA_KEY_JSON --org outrightmental --visibility selected \
  --repos ConversationSimulator,FeverTilt
```

### Step 6 — Pin the jsign SHA-256

After verifying the first signed build, pin the jsign jar hash:

```powershell
# On a Windows machine where jsign was already downloaded:
$jar = "$env:RUNNER_TOOL_CACHE\jsign\7.0\jsign-7.0.jar"
(Get-FileHash $jar -Algorithm SHA256).Hash.ToLower()
```

Update `JSIGN_SHA256` in `scripts/jsign-sign.ps1` with the result.

---

## Rotation runbook

### Scenario A — Certificate expiry (key version unchanged)

1. Generate a new CSR against the **same** KMS key version (Step 2 above).
2. Submit to the CA; download the new certificate chain.
3. Update `WINDOWS_CODESIGN_CERT` at org level with the new chain.
4. No change needed to `GCP_KMS_KEY` or `GCP_SA_KEY_JSON`.
5. Trigger a manual release workflow dispatch build and confirm the verify step passes.
6. Log the rotation in `publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`.

### Scenario B — Key rotation (new KMS key version)

1. Create a new key version in Cloud KMS:
   ```bash
   gcloud kms keys versions create \
     --key windows-codesign \
     --keyring convsim-signing \
     --location global \
     --project YOUR_PROJECT
   ```
2. Generate a CSR against the new version and obtain a new certificate (Steps 2–4).
3. Update `WINDOWS_CODESIGN_CERT` with the new chain.
4. The key-version pinning logic automatically selects the new version because its
   public key now matches the updated certificate.
5. Disable the old key version in Cloud KMS once the new certificate is confirmed:
   ```bash
   gcloud kms keys versions disable 1 \
     --key windows-codesign --keyring convsim-signing --location global
   ```
6. Binaries signed under the old version **remain valid** because of the RFC 3161
   timestamp embedded at signing time. Only new builds use the new key version.

### Dry-run rotation test (CI acceptance criterion)

To verify that the pinning logic hard-fails when the matching version is
disabled, disable the active key version in Cloud KMS, trigger a test build, and
confirm the signing step exits non-zero with the pinning error message. Re-enable
the version before the next release.

---

## SmartScreen reputation

Even with a valid Authenticode signature, Windows SmartScreen evaluates download
reputation separately.

| Certificate type | SmartScreen behaviour |
|------------------|-----------------------|
| Extended Validation (EV) | Immediate trust — no download count required |
| Organisation Validation (OV) | Trust builds with download volume; new certs show "unrecognised publisher" until a few hundred downloads from diverse IPs have accumulated |

**Stage 3 private beta (OV):** Advise testers to click **More info → Run anyway**.
Each accepted install contributes reputation signal.

**Stage 4 public release:** Use an EV certificate backed by the KMS HSM key to
suppress SmartScreen warnings immediately. The same key can back an EV certificate
— request one from DigiCert or Sectigo. The CSR flow above applies unchanged.

---

## Antivirus false positives

Freshly compiled Rust/Tauri executables are occasionally flagged by heuristic
engines. The VirusTotal step in `release.yml` is non-blocking; review results
manually and submit false-positive reports if fewer than three engines flag the
binary.

The depot audit (`scripts/depot-audit.ps1`) catches the most common causes of
false positives (unexpected large binaries, pickle files, ONNX models).

---

## Manual signing (local dev or one-off)

Prerequisites: Java 17+, `scripts/jsign-sign.ps1`, and the GCP credentials
available as environment variables.

```powershell
# Set credentials
$env:GCP_SA_KEY_JSON       = Get-Content path\to\sa-key.json -Raw
$env:GCP_KMS_KEY           = 'projects/P/locations/global/keyRings/convsim-signing/cryptoKeys/windows-codesign'
$env:WINDOWS_CODESIGN_CERT = [Convert]::ToBase64String([IO.File]::ReadAllBytes('fullchain.pem'))

# Sign a specific binary
pwsh -File scripts\jsign-sign.ps1 -FilePath .\path\to\ConversationSimulator.exe

# Verify
signtool.exe verify /pa /v .\path\to\ConversationSimulator.exe
```

---

## Troubleshooting

### Key-version pinning fails with "no ENABLED CryptoKeyVersion"

All key versions are disabled or the key name in `GCP_KMS_KEY` is wrong. List
enabled versions:
```bash
gcloud kms keys versions list \
  --key windows-codesign --keyring convsim-signing --location global \
  --filter 'state=ENABLED'
```

### Key-version pinning fails with "no public key matching the leaf certificate"

The certificate in `WINDOWS_CODESIGN_CERT` was not issued against the currently
active key version, or the PEM chain is in the wrong order (leaf must be first).
Verify with:
```bash
openssl x509 -in leaf.pem -noout -pubkey | openssl pkey -pubin -outform DER | sha256sum
gcloud kms keys versions get-public-key 1 ... | openssl pkey -pubin -outform DER | sha256sum
```
The two hashes must match.

### jsign SHA-256 mismatch

The jar was updated without updating the pin. Download the new jar, compute its
hash, and update `JSIGN_SHA256` in `scripts/jsign-sign.ps1`.

### SmartScreen blocks despite a valid signature

OV certificate with low download count. Advise users to click **More info → Run
anyway** and continue distribution. Each accepted install increases reputation.
Consider upgrading to an EV certificate backed by the same KMS key.

---

## Links

- [`docs/platform-notes.md` — Windows signing section](../docs/platform-notes.md#code-signing-smartscreen)
- [`docs/steam-mvp-scope.md` — G3-01](../docs/steam-mvp-scope.md) — Stage 3 gate
- [`scripts/jsign-sign.ps1`](../scripts/jsign-sign.ps1) — signing script
- [`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md) — depot content policy
- [jsign documentation](https://ebourg.github.io/jsign/) — `--storetype GOOGLECLOUD` reference
- [Google Cloud KMS — asymmetric signing](https://cloud.google.com/kms/docs/create-validate-signatures)
- [Sectigo timestamp URL](http://timestamp.sectigo.com) — RFC 3161 TSA used by jsign
