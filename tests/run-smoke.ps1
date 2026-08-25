param([switch]$SkipTunnelLive)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Assert-PowerShellSyntax {
    param([string]$Path)
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        throw "PowerShell syntax error in $Path : $($errors[0].Message)"
    }
}

function Get-DescendantIds {
    param([int]$RootPid)
    $all = Get-CimInstance Win32_Process
    $ids = New-Object System.Collections.Generic.List[int]
    $queue = New-Object System.Collections.Generic.Queue[int]
    $queue.Enqueue($RootPid)
    while ($queue.Count -gt 0) {
        $parent = $queue.Dequeue()
        foreach ($child in $all | Where-Object { $_.ParentProcessId -eq $parent }) {
            if (-not $ids.Contains([int]$child.ProcessId)) {
                $ids.Add([int]$child.ProcessId)
                $queue.Enqueue([int]$child.ProcessId)
            }
        }
    }
    return @($ids)
}

Write-Host '=== Smoke: syntax / distribution safety ===' -ForegroundColor Cyan
Assert-PowerShellSyntax (Join-Path $RepoRoot 'setup.ps1')
Assert-PowerShellSyntax (Join-Path $RepoRoot 'secure-tunnel-supervisor.ps1')
Assert-PowerShellSyntax (Join-Path $RepoRoot 'rdc\patches\apply-config-dir-patch.ps1')
Assert-PowerShellSyntax (Join-Path $RepoRoot 'rdc\patches\apply-disable-mcp-ui-patch.ps1')
if (-not (Test-Path (Join-Path $RepoRoot 'desktop\uv.lock'))) { throw 'Desktop Worker uv.lock is missing.' }
if (-not (Test-Path (Join-Path $RepoRoot 'app\uv.lock'))) { throw 'Bridge GUI uv.lock is missing.' }
[void](Get-Content (Join-Path $RepoRoot 'versions.json') -Raw | ConvertFrom-Json)
[void](Get-Content (Join-Path $RepoRoot 'rdc\app\package.json') -Raw | ConvertFrom-Json)

$env:PYTHONPATH = (Join-Path $RepoRoot 'app')
& uv.exe run --project (Join-Path $RepoRoot 'app') --frozen python (Join-Path $RepoRoot 'tests\bridge_app_smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Bridge app/distribution smoke failed.' }
& uv.exe run --project (Join-Path $RepoRoot 'app') --frozen python (Join-Path $RepoRoot 'tests\tunnel_provisioning_smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Tunnel provisioning interface smoke failed.' }

$patcher = Join-Path $RepoRoot 'rdc\patches\apply-config-dir-patch.ps1'
& $patcher -CheckOnly
if ($LASTEXITCODE -ne 0) { throw 'RDC config patch validation failed.' }
$uiPatcher = Join-Path $RepoRoot 'rdc\patches\apply-disable-mcp-ui-patch.ps1'
& $uiPatcher -CheckOnly
if ($LASTEXITCODE -ne 0) { throw 'RDC MCP UI patch validation failed.' }

$configPath = Join-Path $env:LOCALAPPDATA 'Rex-Desktop-Bridge\rdc\config\config.json'
if (-not (Test-Path $configPath)) { throw "RDC runtime config missing: $configPath. Run setup.ps1 first." }
$cfg = Get-Content $configPath -Raw | ConvertFrom-Json
if ($cfg.telemetryEnabled -ne $false) { throw 'RDC telemetry must be disabled.' }
if (-not $cfg.allowedDirectories -or @($cfg.allowedDirectories).Count -eq 0) { throw 'RDC allowedDirectories must not be empty.' }

Write-Host '=== Smoke: RDC (OS/CLI) observed MCP ===' -ForegroundColor Cyan
& node.exe (Join-Path $RepoRoot 'tests\rdc_local_mcp_smoke.mjs')
if ($LASTEXITCODE -ne 0) { throw 'RDC local MCP smoke failed.' }
& node.exe (Join-Path $RepoRoot 'tests\rdc_filesystem_guard_smoke.mjs')
if ($LASTEXITCODE -ne 0) { throw 'RDC filesystem guard smoke failed.' }

Write-Host '=== Smoke: Serena (Code/Repo) observed MCP ===' -ForegroundColor Cyan
$commit = (Get-Content (Join-Path $RepoRoot 'versions.json') -Raw | ConvertFrom-Json).serena.commit
$with = "git+https://github.com/oraios/serena@$commit"
& uv.exe run --with $with python (Join-Path $RepoRoot 'tests\serena_mcp_smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Serena MCP smoke failed.' }

Write-Host '=== Smoke: Rex Desktop (GUI + Vision) observed MCP ===' -ForegroundColor Cyan
& uv.exe run --project (Join-Path $RepoRoot 'desktop') --frozen python (Join-Path $RepoRoot 'tests\desktop_mcp_smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Rex Desktop MCP smoke failed.' }

Write-Host '=== Smoke: tunnel Job Object kill-on-close ===' -ForegroundColor Cyan
$stateDir = Join-Path $env:LOCALAPPDATA 'Rex-Desktop-Bridge\state\job-test'
Remove-Item $stateDir -Recurse -Force -ErrorAction SilentlyContinue
$supervisorPath = Join-Path $RepoRoot 'secure-tunnel-supervisor.ps1'
$args = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $supervisorPath + '" -Profile test -DisplayName Test -StateName job-test -TestChildOnly'
$supervisor = Start-Process powershell.exe -ArgumentList $args -WindowStyle Hidden -PassThru
try {
    $live = Join-Path $stateDir 'live.json'
    $deadline = (Get-Date).AddSeconds(15)
    while (-not (Test-Path $live) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if (-not (Test-Path $live)) { throw 'Job supervisor did not publish live state.' }
    $state = Get-Content $live -Raw | ConvertFrom-Json
    $childPid = [int]$state.child_pid
    Start-Sleep -Milliseconds 800
    $captured = @($childPid) + @(Get-DescendantIds -RootPid $childPid)
    Stop-Process -Id $supervisor.Id -Force
    Start-Sleep -Milliseconds 800
    $alive = @($captured | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($alive.Count -gt 0) { throw "Job Object leaked child PIDs: $($alive -join ',')" }
}
finally {
    Stop-Process -Id $supervisor.Id -Force -ErrorAction SilentlyContinue
    Remove-Item $stateDir -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'JOB_OBJECT_KILL_ON_CLOSE_SMOKE_OK' -ForegroundColor Green

if (-not $SkipTunnelLive) {
    Write-Host 'Live tunnel acceptance is intentionally manual in prototype 0.1.0.' -ForegroundColor Yellow
}

Write-Host 'SMOKE_ALL_OK' -ForegroundColor Green
