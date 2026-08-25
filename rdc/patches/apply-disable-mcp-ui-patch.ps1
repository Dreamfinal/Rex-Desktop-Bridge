param(
    [string]$AppRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'app'),
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$Target = Join-Path $AppRoot 'node_modules\@wonderwhy-er\desktop-commander\dist\server.js'
$Original = '        const showMcpUiPreviews = await shouldShowMcpUiPreviews();'
$Patched = '        const showMcpUiPreviews = false; // Rex Desktop Bridge: suppress embedded MCP UI previews'

if (-not (Test-Path $Target)) {
    throw "Desktop Commander server.js not found. Run npm ci first: $Target"
}

$Content = [IO.File]::ReadAllText($Target)
if ($Content.Contains($Patched)) {
    Write-Output 'RDC_MCP_UI_PATCH_ALREADY_APPLIED'
    exit 0
}

$Matches = ([regex]::Matches($Content, [regex]::Escape($Original))).Count
if ($Matches -ne 1) {
    throw "RDC upstream changed: expected exactly 1 MCP UI preview baseline line, found $Matches. Rebase the patch before continuing."
}

if ($CheckOnly) {
    Write-Output 'RDC_MCP_UI_PATCH_REQUIRED'
    exit 0
}

$Updated = $Content.Replace($Original, $Patched)
[IO.File]::WriteAllText($Target, $Updated, (New-Object Text.UTF8Encoding($false)))
Write-Output 'RDC_MCP_UI_PATCH_APPLIED'
