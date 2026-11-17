#Requires -Version 7.2
# SPDX-License-Identifier: Apache-2.0
<#
  Unit tests for scripts/pack-msix.ps1, the Microsoft Store packer
  (publishing/MICROSOFT_STORE.md).

  The packer only runs after a full release, on a Windows runner, so a mistake
  in it would first show up as a failed release. These tests run its checks
  and its -LayoutOnly path against a fake depot: no makeappx, no release build.
#>

BeforeAll {
    $Script = Join-Path $PSScriptRoot '..' '..' 'scripts' 'pack-msix.ps1'
    $Identity = @{
        IdentityName         = 'OutrightMental.ConversationSimulator'
        Publisher            = 'CN=D8FD94F9-AD83-4DB4-95F5-803BB1DF700E'
        PublisherDisplayName = 'Outright Mental'
    }

    function New-FakeDepot {
        param([string]$Root)
        New-Item -ItemType Directory -Force -Path (Join-Path $Root 'resources\bin') | Out-Null
        Set-Content -Path (Join-Path $Root 'resources\bin\convsim-core.exe') -Value 'core'
        foreach ($name in 'ConversationSimulator.exe', 'steam_api64.dll', 'installscript.vdf', 'MicrosoftEdgeWebView2Setup.exe', 'vcruntime140.dll', 'LICENSE', 'version.txt') {
            Set-Content -Path (Join-Path $Root $name) -Value $name
        }
    }
}

Describe 'pack-msix.ps1' {
    BeforeEach {
        $work = Join-Path ([IO.Path]::GetTempPath()) ("msix-test-" + [Guid]::NewGuid().ToString('N'))
        $depot = Join-Path $work 'depot'
        $layout = Join-Path $work 'layout'
        New-FakeDepot -Root $depot
        $storeExe = Join-Path $work 'store.exe'
        Set-Content -Path $storeExe -Value 'MZ a shell built without Steam'
        $steamExe = Join-Path $work 'steam.exe'
        Set-Content -Path $steamExe -Value 'MZ ... steam_api64.dll ...'
    }
    AfterEach { Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue }

    It 'lays out the Store edition: the Store shell, no Steam files, the manifest filled in' {
        & $Script -Depot $depot -Exe $storeExe -Tag v0.4.10 -OutFile (Join-Path $work 'x.msix') -Layout $layout -LayoutOnly @Identity

        Get-Content (Join-Path $layout 'ConversationSimulator.exe') | Should -Be 'MZ a shell built without Steam'
        foreach ($gone in 'steam_api64.dll', 'installscript.vdf', 'MicrosoftEdgeWebView2Setup.exe') {
            Join-Path $layout $gone | Should -Not -Exist
        }
        foreach ($kept in 'resources\bin\convsim-core.exe', 'vcruntime140.dll', 'LICENSE', 'Assets\Square150x150Logo.png', 'Assets\Square44x44Logo.png', 'Assets\StoreLogo.png') {
            Join-Path $layout $kept | Should -Exist
        }
        [xml]$manifest = Get-Content -Raw (Join-Path $layout 'AppxManifest.xml')
        $manifest.Package.Identity.Name | Should -Be 'OutrightMental.ConversationSimulator'
        $manifest.Package.Identity.Publisher | Should -Be 'CN=D8FD94F9-AD83-4DB4-95F5-803BB1DF700E'
        $manifest.Package.Identity.Version | Should -Be '0.4.10.0'
        $manifest.Package.Properties.PublisherDisplayName | Should -Be 'Outright Mental'
        $manifest.Package.Applications.Application.Executable | Should -Be 'ConversationSimulator.exe'
    }

    It 'lays out the free demo with its own name and DEMO logos' {
        $demo = $Identity.Clone(); $demo.IdentityName = 'OutrightMental.ConversationSimulatorDemo'
        & $Script -Edition demo -Depot $depot -Exe $storeExe -Tag v0.4.11 -OutFile (Join-Path $work 'x.msix') -Layout $layout -LayoutOnly @demo

        [xml]$manifest = Get-Content -Raw (Join-Path $layout 'AppxManifest.xml')
        $manifest.Package.Identity.Name | Should -Be 'OutrightMental.ConversationSimulatorDemo'
        $manifest.Package.Properties.DisplayName | Should -Be 'Conversation Simulator Demo'
        $manifest.Package.Applications.Application.VisualElements.DisplayName | Should -Be 'Conversation Simulator Demo'
        $demoLogo = Join-Path $PSScriptRoot '..' '..' 'publishing' 'microsoft-store' 'Assets-demo' 'StoreLogo.png'
        (Get-FileHash (Join-Path $layout 'Assets' 'StoreLogo.png')).Hash | Should -Be (Get-FileHash $demoLogo).Hash
    }

    It 'refuses the Steam build of the shell' {
        { & $Script -Depot $depot -Exe $steamExe -Tag v0.4.10 -OutFile (Join-Path $work 'x.msix') -Layout $layout -LayoutOnly @Identity } |
            Should -Throw '*steam_api64.dll*'
    }

    It 'refuses a pre-release tag, which has no Store version' {
        { & $Script -Depot $depot -Exe $storeExe -Tag v0.5.0-beta.1 -OutFile (Join-Path $work 'x.msix') -Layout $layout -LayoutOnly @Identity } |
            Should -Throw '*pre-release*'
    }

    It 'refuses a publisher that is not the CN= value from Partner Center' {
        $bad = $Identity.Clone(); $bad.Publisher = 'Outright Mental'
        { & $Script -Depot $depot -Exe $storeExe -Tag v0.4.10 -OutFile (Join-Path $work 'x.msix') -Layout $layout -LayoutOnly @bad } |
            Should -Throw '*CN=*'
    }

    It 'refuses a folder that is not a Windows depot' {
        { & $Script -Depot $work -Exe $storeExe -Tag v0.4.10 -OutFile (Join-Path $work 'x.msix') -Layout $layout -LayoutOnly @Identity } |
            Should -Throw '*resources*'
    }
}
