param(
    [string]$AppRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'app'),
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$Target = Join-Path $AppRoot 'node_modules\@wonderwhy-er\desktop-commander\dist\config.js'
$Original = "const CONFIG_DIR = path.join(USER_HOME, '.claude-server-commander');"
$Patched = "const CONFIG_DIR = process.env.DESKTOP_COMMANDER_CONFIG_DIR ? path.resolve(process.env.DESKTOP_COMMANDER_CONFIG_DIR) : path.join(USER_HOME, '.claude-server-commander');"

if (-not (Test-Path $Target)) {
    throw "Desktop Commander config.js not found. Run npm ci first: $Target"
}

$Content = [IO.File]::ReadAllText($Target)
if ($Content.Contains($Patched)) {
    Write-Output 'RDC_CONFIG_DIR_PATCH_ALREADY_APPLIED'
    exit 0
}

$Matches = ([regex]::Matches($Content, [regex]::Escape($Original))).Count
if ($Matches -ne 1) {
    throw "RDC upstream changed: expected exactly 1 CONFIG_DIR baseline line, found $Matches. Rebase the patch before continuing."
}

if ($CheckOnly) {
    Write-Output 'RDC_CONFIG_DIR_PATCH_REQUIRED'
    exit 0
}

$Updated = $Content.Replace($Original, $Patched)
[IO.File]::WriteAllText($Target, $Updated, (New-Object Text.UTF8Encoding($false)))
Write-Output 'RDC_CONFIG_DIR_PATCH_APPLIED'
