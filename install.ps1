<#
.SYNOPSIS
    Verify and register ratchet as a local Claude Code marketplace.
.DESCRIPTION
    Claude Code manages plugin installation itself, so this does not copy files
    into a plugin directory. It does the part a plugin manager cannot: prove the
    hook scripts actually work on this machine before you let them gate your work.

    Written for Windows PowerShell 5.1 - no &&, no ternary, no null-coalescing.
#>

$ErrorActionPreference = "Stop"

# Native programs write progress to stderr as a matter of course -- unittest
# does, git does. Under $ErrorActionPreference = "Stop", PowerShell 5.1 turns
# those lines into terminating NativeCommandErrors, so a passing test run looks
# like a crash. Run externals through here: exit code is the only verdict.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Out-Host, not bare output: a PowerShell function returns everything
        # written to the pipeline, so streaming the command's stdout here would
        # make the caller's `$exit -ne 0` an array comparison rather than a
        # number one. Only the exit code should come back.
        & $Exe @Arguments | Out-Host
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ratchet - workflow discipline for Claude Code" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$RepoDir = $PSScriptRoot
if (-not $RepoDir) { $RepoDir = (Get-Location).Path }

# 1. Interpreter. `py -3` first: on Windows, `python` is often the Store shim,
#    which resolves on PATH but is not a working interpreter.
#
#    Note the probe does NOT redirect stderr. In PowerShell 5.1, redirecting a
#    native command's stderr wraps each line in a NativeCommandError, which
#    $ErrorActionPreference = "Stop" turns into a terminating error -- so a
#    perfectly good interpreter gets discarded. Exit code alone is the signal.
$Candidates = @(
    @{ Exe = "py";      Probe = @("-3") },
    @{ Exe = "python";  Probe = @() },
    @{ Exe = "python3"; Probe = @() }
)

$Python = $null
foreach ($candidate in $Candidates) {
    if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
    $probeArgs = @($candidate.Probe) + @("-c", "pass")
    & $candidate.Exe @probeArgs
    if ($LASTEXITCODE -eq 0) {
        $Python = $candidate
        break
    }
}

if (-not $Python) {
    Write-Error "No working Python interpreter on PATH. ratchet's hooks need one."
    exit 1
}

$PyExe = $Python.Exe
$PyArgs = @($Python.Probe)

$Version = & $PyExe @PyArgs --version
Write-Host "-> Python: $Version" -ForegroundColor Green

# 2. Run the hook tests. A hook that mangles its own input is worse than no
#    hook, so this is the step worth having.
Write-Host "-> Verifying hook logic..." -ForegroundColor Green
$TestDir = Join-Path $RepoDir "plugin\scripts\tests"
$testArgs = @($PyArgs) + @("-m", "unittest", "discover", "-s", $TestDir, "-p", "test_*.py", "-q")
$testExit = Invoke-Native $PyExe $testArgs
if ($testExit -ne 0) {
    Write-Error "Hook tests failed. Not registering a plugin whose hooks are broken."
    exit 1
}

# 3. Validate and register, if the CLI is present.
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Write-Host "-> Validating plugin manifest..." -ForegroundColor Green
    $validateExit = Invoke-Native "claude" @("plugin", "validate", (Join-Path $RepoDir "plugin"))
    if ($validateExit -ne 0) {
        Write-Error "Plugin manifest failed validation."
        exit 1
    }

    Write-Host "-> Registering local marketplace..." -ForegroundColor Green
    Invoke-Native "claude" @("plugin", "marketplace", "add", $RepoDir) | Out-Null
} else {
    Write-Host "-- claude CLI not found; skipping validation and registration." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. To finish:" -ForegroundColor Cyan
Write-Host "  /plugin install ratchet"
Write-Host ""
Write-Host "Then run /project-profile once per project so the verification gate"
Write-Host "knows what your check command is."
