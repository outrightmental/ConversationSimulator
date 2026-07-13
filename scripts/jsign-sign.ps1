#Requires -Version 7.2
# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Sign a Windows binary via Google Cloud KMS + jsign, with signtool/PFX fallback.

.DESCRIPTION
  Invoked by Tauri's bundle.windows.signCommand for each binary Tauri packages
  (ConversationSimulator.exe, convsim-core.exe, etc.) and by the release workflow
  post-build step for the outer NSIS installer and MSI.

  Priority order:
    1. GCP KMS   — GCP_SA_KEY_JSON + GCP_KMS_KEY + WINDOWS_CODESIGN_CERT
    2. PFX       — CERT_PFX_BASE64 + CERT_PASSWORD
    3. INFO-skip — neither set (fork-friendly, unsigned dev builds)

  Key-version pinning: enumerates ENABLED Cloud KMS CryptoKeyVersions, compares
  each version's public key (SubjectPublicKeyInfo DER) with the leaf certificate
  in WINDOWS_CODESIGN_CERT, and signs with the matching version. Fails loudly if
  none match — prevents signing with a rotated key that no longer chains to the
  issued certificate, and catches wrong chain order (leaf must be first).

.PARAMETER FilePath
  Path to the binary to sign. Supplied as the {path} placeholder from Tauri's
  bundle.windows.signCommand, or passed directly from the release workflow.

.NOTES
  Pin JSIGN_SHA256 before first production use:
    Invoke-WebRequest -Uri $JSIGN_DOWNLOAD_URL -OutFile jsign.jar
    (Get-FileHash jsign.jar -Algorithm SHA256).Hash.ToLower()
  Update the constant below with the result and remove the placeholder comment.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$FilePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Constants ─────────────────────────────────────────────────────────────────
$JSIGN_VERSION      = '7.0'
# PLACEHOLDER — replace with real SHA-256 before production use:
#   (Get-FileHash jsign-7.0.jar -Algorithm SHA256).Hash.ToLower()
$JSIGN_SHA256       = '0000000000000000000000000000000000000000000000000000000000000000'
$JSIGN_DOWNLOAD_URL = "https://github.com/ebourg/jsign/releases/download/$JSIGN_VERSION/jsign-$JSIGN_VERSION.jar"
$JSIGN_CACHE_DIR    = if ($env:RUNNER_TOOL_CACHE) {
                          Join-Path $env:RUNNER_TOOL_CACHE "jsign\$JSIGN_VERSION"
                      } else {
                          Join-Path ([IO.Path]::GetTempPath()) "jsign-$JSIGN_VERSION"
                      }
$JSIGN_JAR          = Join-Path $JSIGN_CACHE_DIR "jsign-$JSIGN_VERSION.jar"
$TSA_URL            = 'http://timestamp.sectigo.com'

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Info { param([string]$msg) Write-Host "  INFO  $msg" }
function Write-Step { param([string]$msg) Write-Host "  -->   $msg" }
function Fail       { param([string]$msg) Write-Error $msg; exit 1 }

function ConvertTo-Base64Url {
    param([string]$Text)
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text)) `
        -replace '=+$','' -replace '\+','-' -replace '/','_'
}

function Get-GcpAccessToken {
    param([psobject]$Sa)

    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $header  = ConvertTo-Base64Url '{"alg":"RS256","typ":"JWT"}'
    $payload = ConvertTo-Base64Url (ConvertTo-Json @{
        iss   = $Sa.client_email
        scope = 'https://www.googleapis.com/auth/cloudkms'
        aud   = 'https://oauth2.googleapis.com/token'
        exp   = ($now + 3600)
        iat   = $now
    } -Compress)

    $toSign  = "$header.$payload"
    $rsa     = [Security.Cryptography.RSA]::Create()
    $pkcs8   = ($Sa.private_key -replace '-----[^-]+-----','' -replace '\s','')
    $n       = [int]0
    $rsa.ImportPkcs8PrivateKey([Convert]::FromBase64String($pkcs8), [ref]$n)
    $sig = [Convert]::ToBase64String(
        $rsa.SignData([Text.Encoding]::UTF8.GetBytes($toSign),
                      [Security.Cryptography.HashAlgorithmName]::SHA256,
                      [Security.Cryptography.RSASignaturePadding]::Pkcs1)
    ) -replace '=+$','' -replace '\+','-' -replace '/','_'

    $resp = Invoke-RestMethod -Uri 'https://oauth2.googleapis.com/token' -Method POST -Body @{
        grant_type = 'urn:ietf:params:oauth:grant-type:jwt-bearer'
        assertion  = "$toSign.$sig"
    }
    return $resp.access_token
}

function Find-MatchingKeyVersion {
    param(
        [string]$Token,
        [string]$KeyRingPath,
        [string]$KeyName,
        [string]$CertPem
    )

    # Extract the leaf cert (first PEM block) and its SubjectPublicKeyInfo DER.
    $leafPem    = ($CertPem -split '(?=-----BEGIN CERTIFICATE-----)' |
                   Where-Object { $_ -match '-----BEGIN CERTIFICATE-----' })[0]
    $leafB64    = $leafPem -replace '-----[^-]+-----','' -replace '\s',''
    $cert       = [Security.Cryptography.X509Certificates.X509Certificate2]::new(
                      [Convert]::FromBase64String($leafB64))
    $certKey    = $cert.GetRSAPublicKey() ?? $cert.GetECDsaPublicKey()
    if (-not $certKey) {
        Fail 'Cannot extract RSA or ECDSA public key from leaf cert in WINDOWS_CODESIGN_CERT.'
    }
    $certSpkiB64 = [Convert]::ToBase64String($certKey.ExportSubjectPublicKeyInfo())

    # List ENABLED CryptoKeyVersions.
    $hdrs    = @{ Authorization = "Bearer $Token" }
    $listUri = ("https://cloudkms.googleapis.com/v1/$KeyRingPath/cryptoKeys/$KeyName/" +
                "cryptoKeyVersions?filter=state%3DENABLED")
    $resp    = Invoke-RestMethod -Uri $listUri -Headers $hdrs -ErrorAction Stop
    $vers    = @($resp.cryptoKeyVersions)

    if ($vers.Count -eq 0) {
        Fail ("ERROR: Key-version pinning failed — no ENABLED CryptoKeyVersion found under " +
              "$KeyRingPath/cryptoKeys/$KeyName. " +
              "Enable at least one version in Cloud KMS before signing.")
    }

    foreach ($v in $vers) {
        $pkResp    = Invoke-RestMethod -Uri "https://cloudkms.googleapis.com/v1/$($v.name)/publicKey" `
                                       -Headers $hdrs -ErrorAction Stop
        $kmsSpkiB64 = $pkResp.pem -replace '-----[^-]+-----','' -replace '\s',''
        if ($certSpkiB64 -eq $kmsSpkiB64) {
            Write-Step "Key-version pinning: matched $($v.name)"
            return $v.name
        }
    }

    Fail ("ERROR: Key-version pinning failed — no ENABLED CryptoKeyVersion in " +
          "$KeyRingPath/cryptoKeys/$KeyName has a public key matching the leaf certificate " +
          "in WINDOWS_CODESIGN_CERT. Check that the leaf cert is listed first in the PEM chain " +
          "and that the certificate was issued against the current key version. To recover: " +
          "issue a new certificate against the active key version, or re-enable the matching " +
          "key version in Cloud KMS.")
}

function Get-JsignJar {
    if (-not (Test-Path $JSIGN_CACHE_DIR)) {
        New-Item -ItemType Directory -Path $JSIGN_CACHE_DIR -Force | Out-Null
    }
    if (-not (Test-Path $JSIGN_JAR)) {
        Write-Step "Downloading jsign $JSIGN_VERSION..."
        Invoke-WebRequest -Uri $JSIGN_DOWNLOAD_URL -OutFile $JSIGN_JAR -UseBasicParsing
    }
    $actual       = (Get-FileHash $JSIGN_JAR -Algorithm SHA256).Hash.ToLower()
    $isPlaceholder = ($JSIGN_SHA256 -match '^0+$')
    if ($isPlaceholder) {
        Write-Info "JSIGN_SHA256 is a placeholder — skipping integrity check."
        Write-Info "Pin it in scripts/jsign-sign.ps1 to: $actual"
    } elseif ($actual -ne $JSIGN_SHA256) {
        Remove-Item $JSIGN_JAR -Force
        Fail ("jsign.jar SHA-256 mismatch.`n" +
              "  Expected : $JSIGN_SHA256`n" +
              "  Actual   : $actual`n" +
              "Update JSIGN_SHA256 in scripts/jsign-sign.ps1 if the jar was intentionally upgraded.")
    }
    Write-Step "jsign $JSIGN_VERSION ready."
    return $JSIGN_JAR
}

function Get-Signtool {
    $st = (Get-Command signtool.exe -ErrorAction SilentlyContinue)?.Source
    if (-not $st) {
        $st = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" `
                 -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
              Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
              Sort-Object FullName -Descending |
              Select-Object -First 1 -ExpandProperty FullName
    }
    return $st
}

# ── Main ──────────────────────────────────────────────────────────────────────

$hasKms = ($env:GCP_SA_KEY_JSON -and $env:GCP_KMS_KEY -and $env:WINDOWS_CODESIGN_CERT)
$hasPfx = ($env:CERT_PFX_BASE64 -and $env:CERT_PASSWORD)

if (-not $hasKms -and -not $hasPfx) {
    Write-Info "No signing credentials configured — skipping: $FilePath"
    Write-Info "For KMS signing : set GCP_SA_KEY_JSON + GCP_KMS_KEY + WINDOWS_CODESIGN_CERT"
    Write-Info "For PFX fallback: set CERT_PFX_BASE64 + CERT_PASSWORD"
    Write-Info "See publishing/WINDOWS_CODE_SIGNING.md for setup."
    exit 0
}

Write-Step "Signing: $FilePath"

if ($hasKms) {
    # ── Path 1: Google Cloud KMS + jsign ─────────────────────────────────────
    Write-Step "Mode: Google Cloud KMS (jsign $JSIGN_VERSION)"

    $sa          = $env:GCP_SA_KEY_JSON | ConvertFrom-Json
    $kmsKeyPath  = $env:GCP_KMS_KEY   # projects/P/locations/L/keyRings/KR/cryptoKeys/K
    $keyRingPath = $kmsKeyPath -replace '/cryptoKeys/[^/]+$', ''
    $keyName     = ($kmsKeyPath -split '/cryptoKeys/')[-1]

    $rawCert  = $env:WINDOWS_CODESIGN_CERT
    $certPem  = if ($rawCert -match '-----BEGIN') { $rawCert }
                else { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($rawCert)) }

    $saKeyFile = $null
    $certFile  = $null
    try {
        $saKeyFile = [IO.Path]::Combine([IO.Path]::GetTempPath(),
                         [IO.Path]::GetRandomFileName() + '.json')
        $env:GCP_SA_KEY_JSON | Set-Content -Path $saKeyFile -Encoding UTF8

        $certFile = [IO.Path]::Combine([IO.Path]::GetTempPath(),
                        [IO.Path]::GetRandomFileName() + '.pem')
        $certPem | Set-Content -Path $certFile -Encoding UTF8

        $token       = Get-GcpAccessToken -Sa $sa
        $versionName = Find-MatchingKeyVersion -Token $token `
                           -KeyRingPath $keyRingPath -KeyName $keyName -CertPem $certPem

        # Alias relative to the keyring: "keyName/cryptoKeyVersions/N"
        $alias = ($versionName -split [Regex]::Escape("$keyRingPath/cryptoKeys/"))[-1]

        $jar = Get-JsignJar

        Write-Step "Invoking jsign (alias: $alias)..."
        & java -jar $jar `
            --storetype GOOGLECLOUD `
            --storepass $saKeyFile `
            --keystore  $keyRingPath `
            --alias     $alias `
            --certfile  $certFile `
            --tsaurl    $TSA_URL `
            --tsmode    RFC3161 `
            $FilePath
        if ($LASTEXITCODE -ne 0) { Fail "jsign exited $LASTEXITCODE for: $FilePath" }
        Write-Info "Signed (KMS): $FilePath"

    } finally {
        if ($saKeyFile -and (Test-Path $saKeyFile)) { Remove-Item $saKeyFile -Force }
        if ($certFile  -and (Test-Path $certFile))  { Remove-Item $certFile  -Force }
    }

} else {
    # ── Path 2: PFX / signtool fallback ──────────────────────────────────────
    Write-Step "Mode: PFX / signtool fallback"

    $signtool = Get-Signtool
    if (-not $signtool) {
        Fail "signtool.exe not found. Install the Windows SDK or switch to GCP KMS signing."
    }
    Write-Step "signtool: $signtool"

    $pfxFile = $null
    try {
        $pfxFile = Join-Path ($env:RUNNER_TEMP ?? [IO.Path]::GetTempPath()) 'convsim-sign.pfx'
        $b64     = ($env:CERT_PFX_BASE64 -split "`r?`n" |
                    Where-Object { $_ -notmatch '^-----' }) -join ''
        [IO.File]::WriteAllBytes($pfxFile, [Convert]::FromBase64String($b64))

        & $signtool sign /f $pfxFile /p $env:CERT_PASSWORD `
            /tr $TSA_URL /td sha256 /fd sha256 /v $FilePath
        if ($LASTEXITCODE -ne 0) { Fail "signtool exited $LASTEXITCODE for: $FilePath" }
        Write-Info "Signed (PFX): $FilePath"

    } finally {
        if ($pfxFile -and (Test-Path $pfxFile)) { Remove-Item $pfxFile -Force }
    }
}
