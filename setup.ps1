param(
    [switch]$SkipPrerequisiteInstall,
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VersionsPath = Join-Path $RepoRoot 'versions.json'
if (-not (Test-Path $VersionsPath)) { throw "Missing versions.json: $VersionsPath" }
$Versions = Get-Content $VersionsPath -Raw | ConvertFrom-Json

$RuntimeRoot = Join-Path $env:LOCALAPPDATA 'Rex-Desktop-Bridge'
$BackupRoot = Join-Path $RuntimeRoot 'backups'
$StateRoot = Join-Path $RuntimeRoot 'state'
$TunnelToolDir = Join-Path $RepoRoot 'tools\tunnel-client'
$TunnelExe = Join-Path $TunnelToolDir 'tunnel-client.exe'
New-Item -ItemType Directory -Force -Path $RuntimeRoot, $BackupRoot, $StateRoot, $TunnelToolDir | Out-Null

function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machine, $user) -join ';'
}

function Ensure-Command {
    param([string]$Name, [string]$WingetId)
    if (Get-Command $Name -ErrorAction SilentlyContinue) { return }
    if ($SkipPrerequisiteInstall) { throw "$Name is required but not installed." }
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "$Name is required and winget is unavailable. Install $WingetId, then rerun Setup-All.cmd."
    }
    Write-Host "Installing prerequisite $WingetId ..." -ForegroundColor Yellow
    & winget.exe install --id $WingetId -e --source winget --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE -ne 0) { throw "winget install failed for $WingetId (exit $LASTEXITCODE)." }
    Refresh-ProcessPath
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is still unavailable after installation. Open a new terminal and rerun Setup-All.cmd."
    }
}

function Install-TunnelClient {
    $version = [string]$Versions.tunnel_client.version
    $asset = [string]$Versions.tunnel_client.windows_amd64_asset
    $expectedZip = ([string]$Versions.tunnel_client.windows_amd64_zip_sha256).ToUpperInvariant()
    $expectedExe = ([string]$Versions.tunnel_client.tested_exe_sha256).ToUpperInvariant()

    if (Test-Path $TunnelExe) {
        $installedVersion = (& $TunnelExe --version 2>$null | Select-Object -First 1)
        $installedHash = (Get-FileHash $TunnelExe -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($installedVersion -match [regex]::Escape($version) -and $installedHash -eq $expectedExe) {
            Write-Host "Tunnel client $version already verified." -ForegroundColor Green
            return
        }
        Write-Host 'Existing tunnel-client does not match the pinned tested build; replacing it.' -ForegroundColor Yellow
    }

    $downloadRoot = Join-Path $env:TEMP ('Rex-Desktop-Bridge-tunnel-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    try {
        $zip = Join-Path $downloadRoot $asset
        $url = "https://github.com/openai/tunnel-client/releases/download/v$version/$asset"
        Write-Host "Downloading official OpenAI tunnel-client v$version ..." -ForegroundColor Yellow
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
        $zipHash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($zipHash -ne $expectedZip) { throw "Tunnel client ZIP SHA256 mismatch. Expected $expectedZip, got $zipHash." }
        $extract = Join-Path $downloadRoot 'extract'
        Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
        $candidate = Get-ChildItem $extract -Recurse -File -Filter 'tunnel-client.exe' | Select-Object -First 1
        if (-not $candidate) { throw 'tunnel-client.exe not found inside official release archive.' }
        Copy-Item $candidate.FullName $TunnelExe -Force
        $exeHash = (Get-FileHash $TunnelExe -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($exeHash -ne $expectedExe) { throw "Tunnel client EXE SHA256 mismatch. Expected $expectedExe, got $exeHash." }
        Write-Host "Tunnel client verified: $(& $TunnelExe --version | Select-Object -First 1)" -ForegroundColor Green
    }
    finally {
        Remove-Item $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Install-RdcRuntime {
    $app = Join-Path $RepoRoot 'rdc\app'
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    $oldTelemetry = $env:DESKTOP_COMMANDER_DISABLE_TELEMETRY
    $env:DESKTOP_COMMANDER_DISABLE_TELEMETRY = '1'
    try {
        Write-Host 'Installing pinned Desktop Commander dependencies ...' -ForegroundColor Yellow
        Push-Location $app
        try {
            & $npm ci --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit $LASTEXITCODE." }
        }
        finally { Pop-Location }
    }
    finally { $env:DESKTOP_COMMANDER_DISABLE_TELEMETRY = $oldTelemetry }

    $patcher = Join-Path $RepoRoot 'rdc\patches\apply-config-dir-patch.ps1'
    & $patcher
    if ($LASTEXITCODE -ne 0) { throw 'RDC config-dir patch failed.' }

    $uiPatcher = Join-Path $RepoRoot 'rdc\patches\apply-disable-mcp-ui-patch.ps1'
    & $uiPatcher
    if ($LASTEXITCODE -ne 0) { throw 'RDC MCP UI suppression patch failed.' }

    $configDir = Join-Path $RuntimeRoot 'rdc\config'
    $configPath = Join-Path $configDir 'config.json'
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    if (Test-Path $configPath) {
        $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
    }
    else {
        $cfg = Get-Content (Join-Path $RepoRoot 'runtime-templates\rdc-config.json') -Raw | ConvertFrom-Json
    }
    if (-not $cfg.PSObject.Properties['allowedDirectories']) {
        $cfg | Add-Member -NotePropertyName allowedDirectories -NotePropertyValue @($env:USERPROFILE)
    } else { $cfg.allowedDirectories = @($env:USERPROFILE) }
    if (-not $cfg.PSObject.Properties['telemetryEnabled']) {
        $cfg | Add-Member -NotePropertyName telemetryEnabled -NotePropertyValue $false
    } else { $cfg.telemetryEnabled = $false }
    [IO.File]::WriteAllText($configPath, ($cfg | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))
    Write-Host "RDC config: $configPath" -ForegroundColor Green
}

function Install-UvProject {
    param([string]$Name, [string]$ProjectDir)
    $lock = Join-Path $ProjectDir 'uv.lock'
    if (-not (Test-Path $lock)) { throw "$Name lockfile missing: $lock" }
    Write-Host "Installing $Name dependencies ..." -ForegroundColor Yellow
    & uv.exe sync --project $ProjectDir --frozen
    if ($LASTEXITCODE -ne 0) { throw "$Name uv sync failed with exit $LASTEXITCODE." }
    Write-Host "$Name runtime verified." -ForegroundColor Green
}

function New-BridgeShortcut {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'Rex Desktop Bridge.lnk'
    $appDir = Join-Path $RepoRoot 'app'
    $venvPython = Join-Path $appDir '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) { throw "Bridge Python runtime missing: $venvPython" }
    $basePython = (& $venvPython -c 'import sys; print(sys._base_executable)').Trim()
    if (-not (Test-Path $basePython)) { throw "Bridge base Python runtime missing: $basePython" }
    $pythonw = Join-Path (Split-Path $basePython -Parent) 'pythonw.exe'
    if (-not (Test-Path $pythonw)) { throw "Bridge base pythonw runtime missing: $pythonw" }
    $ws = New-Object -ComObject WScript.Shell
    $shortcut = $ws.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = '-m bridge.gui'
    $shortcut.WorkingDirectory = $appDir
    $shortcut.WindowStyle = 1
    $shortcut.Description = 'Rex Desktop Bridge GUI control center. Runs three tunnels headlessly; terminal logs open on demand.'
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
    $shortcut.Save()
    Write-Host "Shortcut: $shortcutPath" -ForegroundColor Green
}

Write-Host '=== Rex Desktop Bridge setup ===' -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Ensure-Command -Name 'git.exe' -WingetId 'Git.Git'
Ensure-Command -Name 'node.exe' -WingetId 'OpenJS.NodeJS.LTS'
Ensure-Command -Name 'npm.cmd' -WingetId 'OpenJS.NodeJS.LTS'
Ensure-Command -Name 'uv.exe' -WingetId 'astral-sh.uv'
Ensure-Command -Name 'uvx.exe' -WingetId 'astral-sh.uv'

Install-TunnelClient
Install-RdcRuntime
Install-UvProject -Name 'Rex Desktop Worker' -ProjectDir (Join-Path $RepoRoot 'desktop')
Install-UvProject -Name 'Rex Desktop Bridge GUI' -ProjectDir (Join-Path $RepoRoot 'app')
New-BridgeShortcut

if (-not $SkipSmoke) {
    $smoke = Join-Path $RepoRoot 'tests\run-smoke.ps1'
    if (Test-Path $smoke) {
        & $smoke -SkipTunnelLive
        if ($LASTEXITCODE -ne 0) { throw 'Smoke tests failed.' }
    }
}

Write-Host ''
Write-Host 'SETUP_ALL_OK' -ForegroundColor Green
Write-Host 'Open "Rex Desktop Bridge" from the Desktop.'
Write-Host 'Fresh installs do not require tunnel IDs or API keys during Setup-All.cmd.'
Write-Host 'The GUI guides first-time users through Runtime key, optional Admin key, tunnel creation, and ChatGPT connection.'
