#requires -Version 7.0

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $NsisPath,
    [string] $SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")),
    [Parameter(Mandatory = $true)] [string] $EvidenceOut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-True {
    param([bool] $Condition, [string] $Message)
    if (-not $Condition) { throw $Message }
}

function Get-OnlyFile {
    param([string] $Root, [string] $Name)
    $matches = @(Get-ChildItem -LiteralPath $Root -Recurse -Force -File | Where-Object Name -eq $Name)
    Assert-True ($matches.Count -eq 1) "Expected exactly one $Name under $Root; found $($matches.Count)."
    return $matches[0].FullName
}

function Get-PeMachine {
    param([string] $Path)
    $stream = [IO.File]::OpenRead($Path)
    try {
        $reader = [IO.BinaryReader]::new($stream)
        Assert-True ($reader.ReadUInt16() -eq 0x5A4D) "$Path is not a PE executable."
        $stream.Position = 0x3C
        $peOffset = $reader.ReadUInt32()
        $stream.Position = $peOffset
        Assert-True ($reader.ReadUInt32() -eq 0x00004550) "$Path has no PE signature."
        return $reader.ReadUInt16()
    } finally {
        $stream.Dispose()
    }
}

function Get-TreeInventory {
    param([string] $Root)
    $resolved = (Resolve-Path -LiteralPath $Root).Path
    $result = @{}
    foreach ($item in Get-ChildItem -LiteralPath $resolved -Recurse -Force) {
        Assert-True (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Payload contains a reparse point: $($item.FullName)"
        Assert-True (-not ($item.FullName -match '(^|[\\/])__pycache__([\\/]|$)' -or $item.Extension -in @('.pyc', '.pyo'))) "Payload contains a Python cache: $($item.FullName)"
        if (-not $item.PSIsContainer) {
            $relative = [IO.Path]::GetRelativePath($resolved, $item.FullName).Replace('\', '/')
            $result[$relative] = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return $result
}

function Assert-SameTree {
    param([string] $Source, [string] $Packaged)
    $sourceFiles = Get-TreeInventory $Source
    $packagedFiles = Get-TreeInventory $Packaged
    $sourceNames = @($sourceFiles.Keys | Sort-Object)
    $packagedNames = @($packagedFiles.Keys | Sort-Object)
    $missing = @($sourceNames | Where-Object { -not $packagedFiles.ContainsKey($_) })
    $extra = @($packagedNames | Where-Object { -not $sourceFiles.ContainsKey($_) })
    $difference = "missing=[$($missing -join ', ')]; extra=[$($extra -join ', ')]"
    Assert-True (($sourceNames -join "`n") -ceq ($packagedNames -join "`n")) "Packaged resource file set differs: $Packaged ($difference)"
    foreach ($name in $sourceNames) {
        Assert-True ($sourceFiles[$name] -eq $packagedFiles[$name]) "Packaged resource bytes differ: $Packaged/$name"
    }
}

function Get-Ai4HeorUninstallEntry {
    $paths = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    $entries = @($paths | ForEach-Object {
        Get-ChildItem -LiteralPath $_ -ErrorAction SilentlyContinue |
            Where-Object { [string]$_.GetValue('DisplayName') -eq 'AI4HEOR' } |
            ForEach-Object { Get-ItemProperty -LiteralPath $_.PSPath }
    })
    Assert-True ($entries.Count -eq 1) "Expected one installed AI4HEOR registry entry; found $($entries.Count)."
    return $entries[0]
}

function Resolve-InstallRoot {
    param($Entry)
    $installLocationProperty = $Entry.PSObject.Properties['InstallLocation']
    $installLocation = if ($installLocationProperty) { [string]$installLocationProperty.Value } else { '' }
    if ($installLocation -and (Test-Path -LiteralPath $installLocation)) {
        return (Resolve-Path -LiteralPath $installLocation).Path
    }
    $uninstallProperty = $Entry.PSObject.Properties['UninstallString']
    $uninstallString = if ($uninstallProperty) { [string]$uninstallProperty.Value } else { '' }
    $quoted = [regex]::Match($uninstallString, '^\s*"([^"]+)"')
    if ($quoted.Success) { return Split-Path -Parent $quoted.Groups[1].Value }
    $plain = ($uninstallString -split '\s+')[0]
    Assert-True (-not [string]::IsNullOrWhiteSpace($plain)) "Installed AI4HEOR has no usable install location."
    return Split-Path -Parent $plain
}

Assert-True ($env:RUNNER_OS -eq 'Windows') "Windows package verification must run on a Windows runner."
Assert-True ([Environment]::Is64BitOperatingSystem) "Windows package verification requires a 64-bit host."

$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$NsisPath = (Resolve-Path -LiteralPath $NsisPath).Path
$config = Get-Content -LiteralPath (Join-Path $SourceRoot 'apps/desktop/src-tauri/tauri.conf.json') -Raw | ConvertFrom-Json
$expectedVersion = [string]$config.version
Assert-True ((Split-Path $NsisPath -Leaf) -match '^AI4HEOR_.+_x64-setup\.exe$') "Unexpected NSIS filename: $NsisPath"

$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("ai4heor-windows-verification-" + [guid]::NewGuid())
$verificationPath = Join-Path $temporaryRoot 'windows-verification.json'
$workspace = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AI4HEOR'
$frontendBootstrapLog = Join-Path (Join-Path $env:APPDATA ([string]$config.identifier)) 'debug.log'
$openScienceWorkspace = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'OpenScience'
$openScienceExisted = Test-Path -LiteralPath $openScienceWorkspace -PathType Container
$openScienceMarker = Join-Path $openScienceWorkspace ("ai4heor-isolation-" + [guid]::NewGuid() + ".txt")
$createdWorkspace = $false
$installRoot = $null
$startedProcess = $null
$verification = [ordered]@{}
New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null

try {
    Assert-True (-not (Test-Path -LiteralPath $workspace)) "First-launch workspace already exists: $workspace"
    Assert-True (-not (Test-Path -LiteralPath $frontendBootstrapLog)) "Frontend bootstrap log already exists: $frontendBootstrapLog"
    New-Item -ItemType Directory -Path $openScienceWorkspace -Force | Out-Null
    Set-Content -LiteralPath $openScienceMarker -Value 'preserve-open-science' -Encoding utf8

    $install = Start-Process -FilePath $NsisPath -ArgumentList '/S' -Wait -PassThru
    Assert-True ($install.ExitCode -eq 0) "NSIS silent install failed with exit code $($install.ExitCode)."
    $entry = Get-Ai4HeorUninstallEntry
    Assert-True ([string]$entry.DisplayName -eq 'AI4HEOR') "Unexpected installed product name: $($entry.DisplayName)"
    Assert-True ([string]$entry.DisplayVersion -eq $expectedVersion) "Installed version does not match $expectedVersion."
    $installRoot = Resolve-InstallRoot $entry
    $verification.nsis = [ordered]@{
        product_name = [string]$entry.DisplayName
        product_version = [string]$entry.DisplayVersion
        install_root = $installRoot
    }

    $mainExe = Get-OnlyFile $installRoot 'ai4s-workbench.exe'
    $opencodeExe = Get-OnlyFile $installRoot 'opencode.exe'
    $uvExe = Get-OnlyFile $installRoot 'uv.exe'
    foreach ($binary in @($mainExe, $opencodeExe, $uvExe)) {
        Assert-True ((Get-PeMachine $binary) -eq 0x8664) "Packaged binary is not x86-64: $binary"
    }
    $opencodeVersion = (& $opencodeExe --version 2>&1 | Out-String).Trim()
    Assert-True ($LASTEXITCODE -eq 0 -and $opencodeVersion.Contains('1.17.13-ai4heor.2')) "Unexpected packaged OpenCode version: $opencodeVersion"
    $uvVersion = (& $uvExe --version 2>&1 | Out-String).Trim()
    Assert-True ($LASTEXITCODE -eq 0 -and $uvVersion.Contains('0.11.26')) "Unexpected packaged uv version: $uvVersion"

    $registry = Get-OnlyFile $installRoot 'asset-admission-registry.json'
    $resourceRoot = Split-Path -Parent $registry
    $resourceCount = 0
    foreach ($property in $config.bundle.resources.PSObject.Properties) {
        $source = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent (Join-Path $SourceRoot 'apps/desktop/src-tauri/tauri.conf.json')) $property.Name))
        $destination = Join-Path $resourceRoot ([string]$property.Value).TrimEnd('/', '\')
        if (Test-Path -LiteralPath $source -PathType Container) {
            Assert-True (Test-Path -LiteralPath $destination -PathType Container) "Packaged resource directory is missing: $destination"
            Assert-SameTree $source $destination
            $resourceCount += (Get-TreeInventory $source).Count
        } else {
            Assert-True (Test-Path -LiteralPath $destination -PathType Leaf) "Packaged resource file is missing: $destination"
            $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
            $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
            Assert-True ($sourceHash -eq $destinationHash) "Packaged resource bytes differ: $destination"
            $resourceCount += 1
        }
    }
    Get-TreeInventory $installRoot | Out-Null

    $oldPythonPath = $env:PYTHONPATH
    $oldNoBytecode = $env:PYTHONDONTWRITEBYTECODE
    try {
        $env:PYTHONPATH = Join-Path $resourceRoot 'heor-core/src'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        & python -B -m unittest discover -s (Join-Path $SourceRoot 'python/heor_core/tests') -q
        Assert-True ($LASTEXITCODE -eq 0) "Packaged HEOR tests failed."
    } finally {
        $env:PYTHONPATH = $oldPythonPath
        $env:PYTHONDONTWRITEBYTECODE = $oldNoBytecode
    }
    $verification.payload = [ordered]@{ resource_files = $resourceCount; opencode_version = $opencodeVersion; uv_version = $uvVersion }

    $startedProcess = Start-Process -FilePath $mainExe -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    $appProcesses = @()
    $opencodeProcesses = @()
    $opencodeHttpProof = $null
    $frontendBootstrapProof = $null
    do {
        Start-Sleep -Milliseconds 500
        $processes = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($installRoot, [StringComparison]::OrdinalIgnoreCase) })
        $appProcesses = @($processes | Where-Object { $_.ExecutablePath -ieq $mainExe })
        $opencodeProcesses = @($processes | Where-Object Name -eq 'opencode.exe')
        $createdWorkspace = Test-Path -LiteralPath $workspace -PathType Container
        $openSciencePreserved = (Test-Path -LiteralPath $openScienceMarker -PathType Leaf) -and ((Get-Content -LiteralPath $openScienceMarker -Raw).Trim() -eq 'preserve-open-science')
        $opencodeHttpProof = $null
        $frontendBootstrapProof = $null
        if ($opencodeProcesses.Count -eq 1) {
            $portMatch = [regex]::Match([string]$opencodeProcesses[0].CommandLine, '(?:^|\s)--port\s+([0-9]{1,5})(?:\s|$)')
            if ($portMatch.Success) {
                $port = [int]$portMatch.Groups[1].Value
                if ($port -ge 1 -and $port -le 65535) {
                    try {
                        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/global/health" -Method Get -SkipHttpErrorCheck -NoProxy -TimeoutSec 2
                        if ([int]$response.StatusCode -eq 401) {
                            $opencodeHttpProof = [ordered]@{
                                authentication_enforced = $true
                                path = '/global/health'
                                unauthenticated_status = 401
                            }
                        }
                    } catch {
                        $opencodeHttpProof = $null
                    }
                }
            }
        }
        if (Test-Path -LiteralPath $frontendBootstrapLog -PathType Leaf) {
            $frontendLogTail = (Get-Content -LiteralPath $frontendBootstrapLog -Tail 256) -join "`n"
            $frontendStarted = [regex]::IsMatch($frontendLogTail, '(?m)^\d+ bootstrap: starting bundled runtime$')
            $frontendReady = [regex]::Match($frontendLogTail, '(?m)^\d+ bootstrap: runtime at http://127\.0\.0\.1:(\d+)$')
            if ($frontendStarted -and $frontendReady.Success) {
                $frontendPort = [int]$frontendReady.Groups[1].Value
                if ($frontendPort -ge 1 -and $frontendPort -le 65535) {
                    $frontendBootstrapProof = [ordered]@{
                        app_shell_mounted = $true
                        javascript_executed = $true
                        tauri_runtime_command_returned = $true
                    }
                }
            }
        }
        $ready = $appProcesses.Count -eq 1 -and $opencodeProcesses.Count -eq 1 -and $null -ne $opencodeHttpProof -and $null -ne $frontendBootstrapProof -and $createdWorkspace -and $openSciencePreserved
    } while (-not $ready -and [DateTime]::UtcNow -lt $deadline)
    Assert-True $ready "First launch did not reach one app process, one bundled OpenCode process with authenticated HTTP readiness, frontend bootstrap through Tauri IPC, and a new workspace within 60 seconds."
    $verification.first_launch = [ordered]@{
        app_process_id = $appProcesses[0].ProcessId
        app_executable = $appProcesses[0].ExecutablePath
        opencode_process_id = $opencodeProcesses[0].ProcessId
        opencode_executable = $opencodeProcesses[0].ExecutablePath
        opencode_http = $opencodeHttpProof
        frontend_bootstrap = $frontendBootstrapProof
        workspace = $workspace
        workspace_isolation = [ordered]@{
            app_process_id = $appProcesses[0].ProcessId
            opencode_process_id = $opencodeProcesses[0].ProcessId
            workspace = $workspace
            open_science_workspace = $openScienceWorkspace
            open_science_workspace_preserved = $true
            marker_preserved = (Split-Path -Leaf $openScienceMarker)
            cleanup_verified = $false
        }
    }

    foreach ($process in @($appProcesses + $opencodeProcesses)) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $cleanupDeadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $remaining = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -ieq $mainExe -or $_.ExecutablePath -ieq $opencodeExe) })
    } while ($remaining.Count -gt 0 -and [DateTime]::UtcNow -lt $cleanupDeadline)
    Assert-True ($remaining.Count -eq 0) "Packaged AI4HEOR processes were not cleaned up after first-launch verification."
    $startedProcess = $null
    $verification.first_launch.workspace_isolation.cleanup_verified = $true

    $verification | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $verificationPath -Encoding utf8
    & python (Join-Path $SourceRoot 'scripts/release/release_evidence.py') record `
        --platform windows `
        --target x86_64-pc-windows-msvc `
        --bundle "nsis=$NsisPath" `
        --check nsis-installed-payload `
        --check scientific-resources `
        --check packaged-heor-tests `
        --check bundled-sidecars `
        --check nsis-silent-install `
        --check first-launch-process `
        --check frontend-bootstrap `
        --check opencode-authenticated-http `
        --check workspace-created `
        --check workspace-isolated `
        --verification-json $verificationPath `
        --source-root $SourceRoot `
        --output $EvidenceOut
    Assert-True ($LASTEXITCODE -eq 0) "Release evidence generation failed."
} finally {
    if ($installRoot) {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($installRoot, [StringComparison]::OrdinalIgnoreCase) } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        $uninstaller = Get-ChildItem -LiteralPath $installRoot -Filter 'uninstall.exe' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($uninstaller) { Start-Process -FilePath $uninstaller.FullName -ArgumentList '/S' -Wait | Out-Null }
    }
    if ($createdWorkspace -and (Test-Path -LiteralPath $workspace)) { Remove-Item -LiteralPath $workspace -Recurse -Force }
    if (Test-Path -LiteralPath $openScienceMarker) { Remove-Item -LiteralPath $openScienceMarker -Force }
    if (-not $openScienceExisted -and (Test-Path -LiteralPath $openScienceWorkspace) -and (Get-ChildItem -LiteralPath $openScienceWorkspace -Force | Measure-Object).Count -eq 0) { Remove-Item -LiteralPath $openScienceWorkspace -Force }
    if (Test-Path -LiteralPath $temporaryRoot) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force }
}
