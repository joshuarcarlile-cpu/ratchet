<#
.SYNOPSIS
    Push the working copy of plugin/ into the installed plugin cache.
.DESCRIPTION
    Hooks do NOT execute from this repo. Claude Code copies plugin/ into
    ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/ at install time and
    runs everything from there -- CLAUDE_PLUGIN_ROOT points at the cache, not at
    the source tree. An edit here is therefore invisible to a running session
    until the plugin is reinstalled, which is a slow way to test a one-line
    change to a hook.

    This copies the working tree over the cache so edits go live immediately.
    Each hook firing re-reads its script from disk, so no restart is needed for
    changes under scripts/ or bin/.

    The exception is hooks.json, which the harness reads once at session start.
    Changing which hooks exist still needs a new session; changing what they do
    does not.

    Written for Windows PowerShell 5.1 - no &&, no ternary, no null-coalescing.
#>

[CmdletBinding()]
param(
    # Report what would be copied without writing anything.
    [switch]$WhatIfOnly
)

$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $PSScriptRoot
$SourceDir = Join-Path $RepoDir "plugin"

if (-not (Test-Path -LiteralPath $SourceDir)) {
    Write-Error "No plugin directory at $SourceDir - run this from the ratchet repo."
    exit 1
}

# Resolve the cache path from the installed-plugins manifest rather than
# hardcoding a version, so this keeps working after a version bump.
$Manifest = Join-Path $env:USERPROFILE ".claude\plugins\installed_plugins.json"
if (-not (Test-Path -LiteralPath $Manifest)) {
    Write-Error "No installed_plugins.json at $Manifest - is ratchet installed?"
    exit 1
}

$Installed = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
$Entries = $Installed.plugins.'ratchet@ratchet-marketplace'
if (-not $Entries) {
    Write-Error "ratchet is not installed. Run /plugin install ratchet first."
    exit 1
}

$TargetDir = $Entries[0].installPath
if (-not (Test-Path -LiteralPath $TargetDir)) {
    Write-Error "Manifest points at $TargetDir but it does not exist."
    exit 1
}

Write-Host "source: $SourceDir"
Write-Host "target: $TargetDir"

if ($WhatIfOnly) {
    Write-Host "-- WhatIfOnly: nothing written." -ForegroundColor Yellow
    exit 0
}

# __pycache__ is deliberately not copied: the hook runner sets
# PYTHONDONTWRITEBYTECODE, and stale bytecode in the cache is exactly the drift
# this script exists to avoid.
$items = Get-ChildItem -LiteralPath $SourceDir -Recurse -Force |
    Where-Object { $_.FullName -notlike '*\__pycache__\*' -and $_.FullName -notlike '*\__pycache__' }

foreach ($item in $items) {
    $relative = $item.FullName.Substring($SourceDir.Length).TrimStart('\')
    $destination = Join-Path $TargetDir $relative
    if ($item.PSIsContainer) {
        if (-not (Test-Path -LiteralPath $destination)) {
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
        }
    } else {
        Copy-Item -LiteralPath $item.FullName -Destination $destination -Force
    }
}

Write-Host "-> synced. Hook script edits are live now; hooks.json needs a new session." -ForegroundColor Green
