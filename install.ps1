<#
.SYNOPSIS
    Verify that ratchet's hooks work on this machine, then say how to install it.
.DESCRIPTION
    Claude Code installs ratchet itself, from the GitHub marketplace, so this
    copies and registers nothing. It does the part a plugin manager cannot: prove
    the hook scripts actually work here before you let them gate your work.

    It deliberately does not register this folder as a marketplace: a local
    folder source loads the working copy in place, so an unfinished edit here
    would reach every session on the machine.

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
    Write-Error "Hook tests failed. Don't install a plugin whose hooks are broken."
    exit 1
}

# 3. Validate the manifest, if the CLI is present.
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Write-Host "-> Validating plugin manifest..." -ForegroundColor Green
    $validateExit = Invoke-Native "claude" @("plugin", "validate", (Join-Path $RepoDir "plugin"))
    if ($validateExit -ne 0) {
        Write-Error "Plugin manifest failed validation."
        exit 1
    }
} else {
    Write-Host "-- claude CLI not found; skipping manifest validation." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. To install, in Claude Code:" -ForegroundColor Cyan
Write-Host "  /plugin marketplace add joshuarcarlile-cpu/ratchet"
Write-Host "  /plugin install ratchet@ratchet-marketplace"
Write-Host ""
Write-Host "Then run /project-profile once per project so the verification gate"
Write-Host "knows what your check command is."
