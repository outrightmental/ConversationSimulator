#Requires -Version 7.2
# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Pure helper functions for Windows code signing (scripts/jsign-sign.ps1).

.DESCRIPTION
  These functions are deliberately free of network calls, filesystem writes, and
  environment lookups so they can be unit-tested on any runner without Cloud KMS
  credentials, a real code-signing certificate, or a signable binary.

  That matters: the signing path only ever executes on a v* release tag with the
  KMS secrets present, so before these tests existed, its first execution of any
  kind was during a release — which is how a call that fails 100% of the time
  (`$cert.GetRSAPublicKey()`, see Get-CertificateSpkiBase64) reached main and
  broke the v0.2.3 release.

  Covered by tests/signing/CodeSigning.Tests.ps1, run on windows-latest in CI.
#>

Set-StrictMode -Version Latest

function Resolve-CertPem {
    <#
    .SYNOPSIS
      Normalize the WINDOWS_CODESIGN_CERT secret to PEM text.
    .DESCRIPTION
      The secret may hold either raw PEM ("-----BEGIN CERTIFICATE-----...") or that
      same PEM base64-encoded a second time, depending on how it was pasted into
      GitHub. Accept both.
    #>
    param([Parameter(Mandatory)][string]$RawCert)

    if ($RawCert -match '-----BEGIN') { return $RawCert }
    return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($RawCert.Trim()))
}

function Get-LeafCertificate {
    <#
    .SYNOPSIS
      Return the FIRST certificate in a PEM chain as an X509Certificate2.
    .DESCRIPTION
      jsign requires the leaf (end-entity) certificate first in the chain. Taking
      element [0] is what makes a wrong chain order detectable: an intermediate in
      first position yields a public key that will not match any KMS key version,
      and Find-MatchingKeyVersion fails with an actionable message instead of
      producing a signature that chains to nothing.
    #>
    param([Parameter(Mandatory)][string]$CertPem)

    # @(...) is load-bearing: Where-Object returns a bare string, not an array, when
    # exactly one block matches — and indexing [0] into a string yields its first
    # CHARACTER ('-'), not the certificate. That made a single-certificate secret
    # (no intermediates) fail with an opaque base64 error while a full chain worked.
    $blocks = @($CertPem -split '(?=-----BEGIN CERTIFICATE-----)' |
                Where-Object { $_ -match '-----BEGIN CERTIFICATE-----' })
    if ($blocks.Count -eq 0) {
        throw 'No PEM CERTIFICATE block found in WINDOWS_CODESIGN_CERT.'
    }

    $leafB64 = $blocks[0] -replace '-----[^-]+-----', '' -replace '\s', ''
    return [Security.Cryptography.X509Certificates.X509Certificate2]::new(
               [Convert]::FromBase64String($leafB64))
}

function Get-CertificateSpkiBase64 {
    <#
    .SYNOPSIS
      Base64 of the leaf certificate's SubjectPublicKeyInfo (DER).
    .DESCRIPTION
      This is the value compared against each Cloud KMS CryptoKeyVersion's public
      key to pin the signing key to the issued certificate.

      GetRSAPublicKey / GetECDsaPublicKey are C# *extension* methods
      (RSACertificateExtensions / ECDsaCertificateExtensions), not instance members
      of X509Certificate2. PowerShell does not bind extension methods to instance
      syntax, so `$cert.GetRSAPublicKey()` throws "does not contain a method named
      'GetRSAPublicKey'" on every PowerShell version. They must be invoked as the
      statics they are. Each returns $null for a certificate holding a key of the
      other type, which is what makes the RSA-then-ECDSA fallback work.
    #>
    param([Parameter(Mandatory)][string]$CertPem)

    $cert = Get-LeafCertificate -CertPem $CertPem

    $key = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($cert)
    if (-not $key) {
        $key = [Security.Cryptography.X509Certificates.ECDsaCertificateExtensions]::GetECDsaPublicKey($cert)
    }
    if (-not $key) {
        throw 'Cannot extract RSA or ECDSA public key from leaf cert in WINDOWS_CODESIGN_CERT.'
    }

    return [Convert]::ToBase64String($key.ExportSubjectPublicKeyInfo())
}

function ConvertFrom-PemPublicKey {
    <#
    .SYNOPSIS
      Strip PEM armour and whitespace, leaving the base64 DER body.
    .DESCRIPTION
      Cloud KMS returns a CryptoKeyVersion public key as a PEM-wrapped
      SubjectPublicKeyInfo, so stripping the armour yields a value directly
      comparable with Get-CertificateSpkiBase64.
    #>
    param([Parameter(Mandatory)][string]$Pem)

    return ($Pem -replace '-----[^-]+-----', '' -replace '\s', '')
}

function Split-KmsKeyPath {
    <#
    .SYNOPSIS
      Split GCP_KMS_KEY into the keyring path (jsign's --keystore) and key name.
    .DESCRIPTION
      Validates the shape up front. Without this, a malformed GCP_KMS_KEY surfaces
      as an opaque 404 from the Cloud KMS REST API partway through signing.
    #>
    param([Parameter(Mandatory)][string]$KeyPath)

    if ($KeyPath -notmatch '^projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+$') {
        throw ("GCP_KMS_KEY must have the form " +
               "projects/<project>/locations/<loc>/keyRings/<ring>/cryptoKeys/<key> — got: $KeyPath")
    }

    return [pscustomobject]@{
        KeyRingPath = ($KeyPath -replace '/cryptoKeys/[^/]+$', '')
        KeyName     = ($KeyPath -split '/cryptoKeys/')[-1]
    }
}

function ConvertTo-Base64Url {
    <#
    .SYNOPSIS
      Base64url-encode text (JWT segments for the GCP service-account assertion).
    #>
    param([Parameter(Mandatory)][string]$Text)

    return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text)) `
        -replace '=+$', '' -replace '\+', '-' -replace '/', '_'
}

Export-ModuleMember -Function `
    Resolve-CertPem, `
    Get-LeafCertificate, `
    Get-CertificateSpkiBase64, `
    ConvertFrom-PemPublicKey, `
    Split-KmsKeyPath, `
    ConvertTo-Base64Url
