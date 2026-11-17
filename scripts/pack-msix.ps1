# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Packs the Microsoft Store edition of Conversation Simulator into an MSIX.

.DESCRIPTION
  The Store package is the release's Windows files, the same signed tree that
  goes to Steam (steam-depot-windows.tar.gz from release.yml), with three
  differences:

    * ConversationSimulator.exe is the Store build of the shell: the same
      code, built without the `steam` Cargo feature, so it neither needs nor
      loads Valve's steam_api64.dll. -Exe names it.
    * The Steam-only files are left out: steam_api64.dll, installscript.vdf
      and the WebView2 bootstrapper it runs. Windows 10 2004 and later already
      carry the WebView2 runtime, and a Store app cannot run an installer.
    * AppxManifest.xml and its three logos, from publishing/microsoft-store/
    (Assets-demo/ for the demo, whose icon says DEMO).

  -Edition demo packs the free demo (publishing/MICROSOFT_STORE.md, "The
  demo") from the demo release's depot; its identity is the demo product's.

  The package is not signed here: the Store signs what it publishes. Every
  binary inside already carries the studio's Authenticode signature.

  See publishing/MICROSOFT_STORE.md.

.EXAMPLE
  ./scripts/pack-msix.ps1 -Depot steam-depot-windows -Exe msstore/ConversationSimulator.exe -Tag v0.4.10 -OutFile conversation-simulator-v0.4.10.msix
#>
param(
  # The extracted Windows depot (steam-depot-windows/ from the release build).
  [Parameter(Mandatory = $true)][string]$Depot,
  # The Store build of the shell (built without --features steam).
  [Parameter(Mandatory = $true)][string]$Exe,
  # The release tag, vMAJOR.MINOR.PATCH.
  [Parameter(Mandatory = $true)][string]$Tag,
  [Parameter(Mandatory = $true)][string]$OutFile,
  [string]$IdentityName = $env:MSSTORE_IDENTITY_NAME,
  [string]$Publisher = $env:MSSTORE_PUBLISHER,
  [string]$PublisherDisplayName = $env:MSSTORE_PUBLISHER_DISPLAY_NAME,
  # Where the package's files are assembled. Emptied first.
  [string]$Layout = (Join-Path ([System.IO.Path]::GetTempPath()) 'convsim-msix-layout'),
  # Assemble the layout and stop: for registering it locally with
  # Add-AppxPackage -Register (Developer Mode) to try the packaged app.
  [switch]$LayoutOnly,
  # Which product: the paid full app, or the free demo.
  [ValidateSet('full', 'demo')][string]$Edition = 'full'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$storeDir = Join-Path $repo 'publishing\microsoft-store'
$editions = @{
  full = @{ Name = 'Conversation Simulator'; Description = 'Rehearse real conversations with simulated characters, on your own computer.'; Assets = 'Assets' }
  demo = @{ Name = 'Conversation Simulator Demo'; Description = 'Try five real conversations with simulated characters, on your own computer.'; Assets = 'Assets-demo' }
}
$product = $editions[$Edition]

foreach ($pair in @(@('IdentityName', $IdentityName), @('Publisher', $Publisher), @('PublisherDisplayName', $PublisherDisplayName))) {
  if (-not $pair[1]) { throw "$($pair[0]) is empty: pass -$($pair[0]) or set the matching MSSTORE_ variable (publishing/MICROSOFT_STORE.md)." }
}
if (-not $Publisher.StartsWith('CN=')) { throw "Publisher must be the CN=... value from Partner Center's Product identity page, not '$Publisher'." }
if (-not (Test-Path (Join-Path $Depot 'resources'))) { throw "$Depot is not an extracted Windows depot: it has no resources\ folder." }
if (-not (Test-Path $Exe)) { throw "The Store build of the shell is not at $Exe." }

# The Store takes MAJOR.MINOR.BUILD.0: the fourth part is reserved for it.
if ($Tag -notmatch '^v?(\d+)\.(\d+)\.(\d+)$') { throw "Tag '$Tag' is not vMAJOR.MINOR.PATCH; a pre-release cannot be a Store version." }
foreach ($part in 1..3) { if ([int]$Matches[$part] -gt 65535) { throw "Version part $($Matches[$part]) is over 65535." } }
$version = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"

# A shell built with the steam feature imports steam_api64.dll and would not
# start without it. The name is in its import table as plain ASCII.
$exeText = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes((Resolve-Path $Exe)))
if ($exeText.IndexOf('steam_api64.dll', [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
  throw "$Exe links steam_api64.dll: it is the Steam build. Build the shell without --features steam for the Store."
}

if (Test-Path $Layout) { Remove-Item -Recurse -Force $Layout }
New-Item -ItemType Directory -Force -Path $Layout | Out-Null
$steamOnly = @('steam_api64.dll', 'steam_appid.txt', 'installscript.vdf', 'MicrosoftEdgeWebView2Setup.exe', 'ConversationSimulator.exe')
Get-ChildItem -Path $Depot -Force | Where-Object { $steamOnly -notcontains $_.Name } | ForEach-Object {
  Copy-Item -Path $_.FullName -Destination $Layout -Recurse -Force
}
Copy-Item -Path $Exe -Destination (Join-Path $Layout 'ConversationSimulator.exe') -Force
Copy-Item -Path (Join-Path $storeDir $product.Assets) -Destination (Join-Path $Layout 'Assets') -Recurse -Force

$manifest = Get-Content -Raw -Path (Join-Path $storeDir 'AppxManifest.xml')
$manifest = $manifest.Replace('__IDENTITY_NAME__', $IdentityName).Replace('__PUBLISHER_DISPLAY_NAME__', $PublisherDisplayName).Replace('__PUBLISHER__', $Publisher).Replace('__VERSION__', $version)
$manifest = $manifest.Replace('__DISPLAY_NAME__', $product.Name).Replace('__DESCRIPTION__', $product.Description)
if ($manifest -match '__[A-Z_]+__') { throw "AppxManifest.xml still has the placeholder $($Matches[0]) in it." }
[System.IO.File]::WriteAllText((Join-Path $Layout 'AppxManifest.xml'), $manifest, (New-Object System.Text.UTF8Encoding($false)))

$files = @(Get-ChildItem -Path $Layout -Recurse -File)
$mb = [math]::Round((($files | Measure-Object -Property Length -Sum).Sum) / 1MB, 1)
Write-Host "Layout: $Layout ($($files.Count) files, $mb MB), $($product.Name) $version"
if ($LayoutOnly) { return }

$makeappx = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter makeappx.exe -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like '*\x64\*' } | Sort-Object FullName | Select-Object -Last 1
if (-not $makeappx) { throw 'makeappx.exe was not found in the Windows SDK.' }
$outDir = Split-Path -Parent $OutFile
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
& $makeappx.FullName pack /d $Layout /p $OutFile /o
if ($LASTEXITCODE) { throw "makeappx failed (exit $LASTEXITCODE)." }
$package = Get-Item $OutFile
Write-Host "Packed: $($package.FullName) ($([math]::Round($package.Length / 1MB, 1)) MB)"
