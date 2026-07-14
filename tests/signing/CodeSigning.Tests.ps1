#Requires -Version 7.2
# SPDX-License-Identifier: Apache-2.0
<#
  Unit tests for scripts/lib/CodeSigning.psm1 — the pure helpers behind
  scripts/jsign-sign.ps1 (Windows Authenticode signing via Google Cloud KMS).

  Why these exist: the signing path only runs on a v* release tag with the KMS
  secrets present, so nothing on the way to main ever executed it. A call that
  fails on every PowerShell version — $cert.GetRSAPublicKey(), an extension
  method invoked with instance syntax — therefore sailed into main and broke the
  v0.2.3 release at the signing step. These tests exercise that code with
  synthetic certificates, no KMS credentials and no network required, so the
  same class of defect fails a PR instead of a release.
#>

BeforeAll {
    $ModulePath = Join-Path $PSScriptRoot '..' '..' 'scripts' 'lib' 'CodeSigning.psm1'
    Import-Module $ModulePath -Force

    # ── Synthetic certificate helpers ─────────────────────────────────────────
    function New-PemBlock {
        param([string]$Label, [byte[]]$Der)

        $b64 = [Convert]::ToBase64String($Der)
        $sb  = [Text.StringBuilder]::new()
        [void]$sb.AppendLine("-----BEGIN $Label-----")
        for ($i = 0; $i -lt $b64.Length; $i += 64) {
            $len = [Math]::Min(64, $b64.Length - $i)
            [void]$sb.AppendLine($b64.Substring($i, $len))
        }
        [void]$sb.AppendLine("-----END $Label-----")
        return $sb.ToString()
    }

    function New-SelfSignedRsaCert {
        param([string]$Subject = 'CN=ConvSim Test Leaf')

        $rsa = [Security.Cryptography.RSA]::Create(2048)
        $req = [Security.Cryptography.X509Certificates.CertificateRequest]::new(
                   $Subject, $rsa,
                   [Security.Cryptography.HashAlgorithmName]::SHA256,
                   [Security.Cryptography.RSASignaturePadding]::Pkcs1)
        $cert = $req.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1),
                                      [DateTimeOffset]::UtcNow.AddDays(365))
        return [pscustomobject]@{
            Cert    = $cert
            Key     = $rsa
            CertPem = New-PemBlock -Label 'CERTIFICATE' -Der $cert.RawData
            # How Cloud KMS returns a CryptoKeyVersion public key.
            KmsPem  = New-PemBlock -Label 'PUBLIC KEY' -Der $rsa.ExportSubjectPublicKeyInfo()
            SpkiB64 = [Convert]::ToBase64String($rsa.ExportSubjectPublicKeyInfo())
        }
    }

    function New-SelfSignedEcdsaCert {
        param([string]$Subject = 'CN=ConvSim Test EC Leaf')

        $ec  = [Security.Cryptography.ECDsa]::Create(
                   [Security.Cryptography.ECCurve]::CreateFromFriendlyName('nistP256'))
        $req = [Security.Cryptography.X509Certificates.CertificateRequest]::new(
                   $Subject, $ec, [Security.Cryptography.HashAlgorithmName]::SHA256)
        $cert = $req.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1),
                                      [DateTimeOffset]::UtcNow.AddDays(365))
        return [pscustomobject]@{
            Cert    = $cert
            CertPem = New-PemBlock -Label 'CERTIFICATE' -Der $cert.RawData
            SpkiB64 = [Convert]::ToBase64String($ec.ExportSubjectPublicKeyInfo())
        }
    }
}

Describe 'Get-CertificateSpkiBase64' {

    It 'extracts the SubjectPublicKeyInfo from an RSA leaf certificate' {
        # THE regression test for the v0.2.3 release failure. The previous
        # implementation called $cert.GetRSAPublicKey() — an extension method
        # invoked with instance syntax — and threw
        # "does not contain a method named 'GetRSAPublicKey'" here.
        $rsa = New-SelfSignedRsaCert

        $actual = Get-CertificateSpkiBase64 -CertPem $rsa.CertPem

        $actual | Should -Be $rsa.SpkiB64
    }

    It 'falls back to the ECDSA public key for an EC leaf certificate' {
        $ec = New-SelfSignedEcdsaCert

        $actual = Get-CertificateSpkiBase64 -CertPem $ec.CertPem

        $actual | Should -Be $ec.SpkiB64
    }

    It 'reads the LEAF when the PEM holds a full chain (leaf first)' {
        # jsign requires leaf-first ordering; pinning must key off the leaf, not
        # whichever certificate happens to appear later in the bundle.
        $leaf         = New-SelfSignedRsaCert -Subject 'CN=Leaf'
        $intermediate = New-SelfSignedRsaCert -Subject 'CN=Intermediate'
        $chainPem     = $leaf.CertPem + $intermediate.CertPem

        $actual = Get-CertificateSpkiBase64 -CertPem $chainPem

        $actual | Should -Be $leaf.SpkiB64
        $actual | Should -Not -Be $intermediate.SpkiB64
    }

    It 'produces a value that matches the Cloud KMS public-key PEM for the same key' {
        # This is the exact comparison Find-MatchingKeyVersion makes to pin the
        # signing key to the issued certificate. If these two ever stop agreeing,
        # every release fails "no ENABLED CryptoKeyVersion ... matching the leaf".
        $rsa = New-SelfSignedRsaCert

        $fromCert = Get-CertificateSpkiBase64 -CertPem $rsa.CertPem
        $fromKms  = ConvertFrom-PemPublicKey -Pem $rsa.KmsPem

        $fromCert | Should -Be $fromKms
    }

    It 'does NOT match a KMS public key from a different (rotated) key' {
        $issued  = New-SelfSignedRsaCert
        $rotated = New-SelfSignedRsaCert

        $fromCert = Get-CertificateSpkiBase64 -CertPem $issued.CertPem
        $fromKms  = ConvertFrom-PemPublicKey -Pem $rotated.KmsPem

        $fromCert | Should -Not -Be $fromKms
    }
}

Describe 'Get-LeafCertificate' {

    It 'throws an actionable error when the PEM holds no certificate block' {
        { Get-LeafCertificate -CertPem 'not a certificate' } |
            Should -Throw '*No PEM CERTIFICATE block*'
    }
}

Describe 'Resolve-CertPem' {

    It 'passes raw PEM through unchanged' {
        $rsa = New-SelfSignedRsaCert

        Resolve-CertPem -RawCert $rsa.CertPem | Should -Be $rsa.CertPem
    }

    It 'decodes a base64-wrapped PEM (secret pasted as base64)' {
        $rsa    = New-SelfSignedRsaCert
        $b64Pem = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($rsa.CertPem))

        $resolved = Resolve-CertPem -RawCert $b64Pem

        $resolved | Should -Be $rsa.CertPem
        # And the decoded form must still drive the SPKI extraction end to end.
        Get-CertificateSpkiBase64 -CertPem $resolved | Should -Be $rsa.SpkiB64
    }
}

Describe 'Split-KmsKeyPath' {

    It 'splits a well-formed key path into keyring path and key name' {
        $parts = Split-KmsKeyPath -KeyPath 'projects/p1/locations/global/keyRings/ring/cryptoKeys/codesign'

        $parts.KeyRingPath | Should -Be 'projects/p1/locations/global/keyRings/ring'
        $parts.KeyName     | Should -Be 'codesign'
    }

    It 'rejects a malformed key path instead of deferring to an opaque KMS 404' {
        { Split-KmsKeyPath -KeyPath 'projects/p1/cryptoKeys/codesign' } |
            Should -Throw '*must have the form*'
    }

    It 'rejects a key path that includes a key VERSION suffix' {
        # jsign's --keystore takes the keyring path; a version-qualified key here
        # produces a signature attempt against a path that does not exist.
        { Split-KmsKeyPath -KeyPath 'projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1' } |
            Should -Throw '*must have the form*'
    }
}

Describe 'ConvertTo-Base64Url' {

    It 'emits URL-safe base64 with no padding (JWT segment)' {
        $encoded = ConvertTo-Base64Url -Text '{"alg":"RS256","typ":"JWT"}'

        $encoded | Should -Not -Match '='
        $encoded | Should -Not -Match '\+'
        $encoded | Should -Not -Match '/'
    }

    It 'round-trips back to the original text' {
        $text    = '{"iss":"sa@example.iam.gserviceaccount.com"}'
        $encoded = ConvertTo-Base64Url -Text $text

        # Restore standard base64 alphabet and padding, then decode.
        $b64 = $encoded -replace '-', '+' -replace '_', '/'
        switch ($b64.Length % 4) {
            2 { $b64 += '==' }
            3 { $b64 += '=' }
        }

        [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)) | Should -Be $text
    }
}
