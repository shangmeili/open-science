#requires -Version 7.0

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $MsiPath,
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
    Assert-True (($sourceNames -join "`n") -ceq ($packagedNames -join "`n")) "Packaged resource file set differs: $Packaged"
    foreach ($name in $sourceNames) {
        Assert-True ($sourceFiles[$name] -eq $packagedFiles[$name]) "Packaged resource bytes differ: $Packaged/$name"
    }
}

function Get-MsiProperty {
    param($Database, [string] $Name)
    $view = $Database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property``='$Name'")
    try {
        $view.Execute()
        $record = $view.Fetch()
        if ($null -eq $record) { return $null }
        return $record.StringData(1)
    } finally {
        $view.Close()
    }
}

function Get-Ai4HeorUninstallEntry {
    $paths = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $entries = @($paths | ForEach-Object {
        Get-ItemProperty -Path $_ -ErrorAction SilentlyContinue |
            Where-Object DisplayName -eq 'AI4HEOR'
    })
    Assert-True ($entries.Count -eq 1) "Expected one installed AI4HEOR registry entry; found $($entries.Count)."
    return $entries[0]
}

function Resolve-InstallRoot {
    param($Entry)
    if ($Entry.InstallLocation -and (Test-Path -LiteralPath $Entry.InstallLocation)) {
        return (Resolve-Path -LiteralPath $Entry.InstallLocation).Path
    }
    $quoted = [regex]::Match([string]$Entry.UninstallString, '^\s*"([^"]+)"')
    if ($quoted.Success) { return Split-Path -Parent $quoted.Groups[1].Value }
    $plain = ([string]$Entry.UninstallString -split '\s+')[0]
    Assert-True (-not [string]::IsNullOrWhiteSpace($plain)) "Installed AI4HEOR has no usable install location."
    return Split-Path -Parent $plain
}

Assert-True ($env:RUNNER_OS -eq 'Windows') "Windows package verification must run on a Windows runner."
Assert-True ([Environment]::Is64BitOperatingSystem) "Windows package verification requires a 64-bit host."

$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$MsiPath = (Resolve-Path -LiteralPath $MsiPath).Path
$NsisPath = (Resolve-Path -LiteralPath $NsisPath).Path
$config = Get-Content -LiteralPath (Join-Path $SourceRoot 'apps/desktop/src-tauri/tauri.conf.json') -Raw | ConvertFrom-Json
$expectedVersion = [string]$config.version
Assert-True ((Split-Path $MsiPath -Leaf) -match '^AI4HEOR_.+_x64_en-US\.msi$') "Unexpected MSI filename: $MsiPath"
Assert-True ((Split-Path $NsisPath -Leaf) -match '^AI4HEOR_.+_x64-setup\.exe$') "Unexpected NSIS filename: $NsisPath"

$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("ai4heor-windows-verification-" + [guid]::NewGuid())
$extractRoot = Join-Path $temporaryRoot 'msi'
$verificationPath = Join-Path $temporaryRoot 'windows-verification.json'
$workspace = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'OpenScience'
$createdWorkspace = $false
$installRoot = $null
$startedProcess = $null
$verification = [ordered]@{}
New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null

try {
    Assert-True (-not (Test-Path -LiteralPath $workspace)) "First-launch workspace already exists: $workspace"

    $installer = New-Object -ComObject WindowsInstaller.Installer
    $database = $installer.OpenDatabase($MsiPath, 0)
    $productName = Get-MsiProperty $database 'ProductName'
    $productVersion = Get-MsiProperty $database 'ProductVersion'
    $productCode = Get-MsiProperty $database 'ProductCode'
    Assert-True ($productName -eq 'AI4HEOR') "Unexpected MSI ProductName: $productName"
    Assert-True ($productVersion -eq $expectedVersion) "Unexpected MSI ProductVersion: $productVersion"
    Assert-True (-not [string]::IsNullOrWhiteSpace($productCode)) "MSI ProductCode is missing."
    $verification.msi = [ordered]@{ product_name = $productName; product_version = $productVersion; product_code = $productCode }

    $extract = Start-Process -FilePath msiexec.exe -ArgumentList @('/a', "`"$MsiPath`"", '/qn', "TARGETDIR=`"$extractRoot`"") -Wait -PassThru
    Assert-True ($extract.ExitCode -eq 0) "MSI administrative extraction failed with exit code $($extract.ExitCode)."

    $mainExe = Get-OnlyFile $extractRoot 'ai4s-workbench.exe'
    $opencodeExe = Get-OnlyFile $extractRoot 'opencode.exe'
    $uvExe = Get-OnlyFile $extractRoot 'uv.exe'
    foreach ($binary in @($mainExe, $opencodeExe, $uvExe)) {
        Assert-True ((Get-PeMachine $binary) -eq 0x8664) "Packaged binary is not x86-64: $binary"
    }
    $opencodeVersion = (& $opencodeExe --version 2>&1 | Out-String).Trim()
    Assert-True ($LASTEXITCODE -eq 0 -and $opencodeVersion.Contains('1.17.13')) "Unexpected packaged OpenCode version: $opencodeVersion"
    $uvVersion = (& $uvExe --version 2>&1 | Out-String).Trim()
    Assert-True ($LASTEXITCODE -eq 0 -and $uvVersion.Contains('0.11.26')) "Unexpected packaged uv version: $uvVersion"

    $registry = Get-OnlyFile $extractRoot 'asset-admission-registry.json'
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
    Get-TreeInventory $extractRoot | Out-Null

    $oldPythonPath = $env:PYTHONPATH
    $oldNoBytecode = $env:PYTHONDONTWRITEBYTECODE
    try {
        $env:PYTHONPATH = Join-Path $resourceRoot 'heor-core/src'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        & python -m unittest discover -s (Join-Path $SourceRoot 'python/heor_core/tests') -q
        Assert-True ($LASTEXITCODE -eq 0) "Packaged HEOR tests failed."
    } finally {
        $env:PYTHONPATH = $oldPythonPath
        $env:PYTHONDONTWRITEBYTECODE = $oldNoBytecode
    }
    $verification.payload = [ordered]@{ resource_files = $resourceCount; opencode_version = $opencodeVersion; uv_version = $uvVersion }

    $install = Start-Process -FilePath $NsisPath -ArgumentList '/S' -Wait -PassThru
    Assert-True ($install.ExitCode -eq 0) "NSIS silent install failed with exit code $($install.ExitCode)."
    $entry = Get-Ai4HeorUninstallEntry
    Assert-True ([string]$entry.DisplayVersion -eq $expectedVersion) "Installed version does not match $expectedVersion."
    $installRoot = Resolve-InstallRoot $entry
    $installedExe = Get-OnlyFile $installRoot 'ai4s-workbench.exe'
    $startedProcess = Start-Process -FilePath $installedExe -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    $appProcesses = @()
    $opencodeProcesses = @()
    do {
        Start-Sleep -Milliseconds 500
        $processes = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($installRoot, [StringComparison]::OrdinalIgnoreCase) })
        $appProcesses = @($processes | Where-Object { $_.ExecutablePath -ieq $installedExe })
        $opencodeProcesses = @($processes | Where-Object Name -eq 'opencode.exe')
        $createdWorkspace = Test-Path -LiteralPath $workspace -PathType Container
        $ready = $appProcesses.Count -eq 1 -and $opencodeProcesses.Count -eq 1 -and $createdWorkspace
    } while (-not $ready -and [DateTime]::UtcNow -lt $deadline)
    Assert-True $ready "First launch did not reach one app process, one bundled OpenCode process, and a new workspace within 60 seconds."
    $verification.first_launch = [ordered]@{
        app_process_id = $appProcesses[0].ProcessId
        app_executable = $appProcesses[0].ExecutablePath
        opencode_process_id = $opencodeProcesses[0].ProcessId
        opencode_executable = $opencodeProcesses[0].ExecutablePath
        workspace = $workspace
    }

    $verification | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $verificationPath -Encoding utf8
    & python (Join-Path $SourceRoot 'scripts/release/release_evidence.py') record `
        --platform windows `
        --target x86_64-pc-windows-msvc `
        --bundle "msi=$MsiPath" `
        --bundle "nsis=$NsisPath" `
        --check msi-metadata `
        --check msi-payload `
        --check scientific-resources `
        --check packaged-heor-tests `
        --check bundled-sidecars `
        --check nsis-silent-install `
        --check first-launch-process `
        --check workspace-created `
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
    if (Test-Path -LiteralPath $temporaryRoot) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force }
}
