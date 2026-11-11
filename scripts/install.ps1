[CmdletBinding()]
param(
    [string]$Source,
    [string]$Version = 'v0.2.0',
    [string]$Prefix,
    [string]$BinDir,
    [string]$Python,
    [switch]$WithoutExtras
)

$ErrorActionPreference = 'Stop'
$InstallerRef = 'v0.2.0'
$PythonExecutable = $null
$PythonPrefixArguments = @()

if ($Python) {
    $Candidates = @(@{Executable=$Python; Arguments=@()})
} else {
    $Candidates = @(
        @{Executable='py'; Arguments=@('-3')},
        @{Executable='python'; Arguments=@()},
        @{Executable='python3'; Arguments=@()}
    )
}
foreach ($Candidate in $Candidates) {
    try {
        $Resolved = Get-Command $Candidate.Executable -CommandType Application -ErrorAction Stop
        $ProbeArguments = @($Candidate.Arguments) + @('-c', 'import sys; raise SystemExit(sys.version_info < (3, 10))')
        & $Resolved.Source @ProbeArguments 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonExecutable = $Resolved.Source
            $PythonPrefixArguments = @($Candidate.Arguments)
            break
        }
    } catch {
        continue
    }
}
if (-not $PythonExecutable) {
    throw 'Python 3.10+ is required. Install Python or pass -Python C:\path\to\python.exe.'
}

$Helper = $null
$TemporaryDirectory = $null
if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'install.py') -PathType Leaf)) {
    $Helper = Join-Path $PSScriptRoot 'install.py'
} elseif ($Source -and (Test-Path -LiteralPath (Join-Path $Source 'scripts/install.py') -PathType Leaf)) {
    $Helper = Join-Path $Source 'scripts/install.py'
}
try {
    if (-not $Helper) {
        $TemporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ('memory-book-installer-' + [System.Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $TemporaryDirectory | Out-Null
        $Helper = Join-Path $TemporaryDirectory 'install.py'
        $Url = "https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/$InstallerRef/scripts/install.py"
        $Download = 'from pathlib import Path; from urllib.request import urlopen; import sys; r=urlopen(sys.argv[2],timeout=30); Path(sys.argv[1]).write_bytes(r.read()); r.close()'
        $DownloadArguments = $PythonPrefixArguments + @('-c', $Download, $Helper, $Url)
        & $PythonExecutable @DownloadArguments
        if ($LASTEXITCODE -ne 0) { throw 'Could not download the official installer helper.' }
    }
    $InstallArguments = $PythonPrefixArguments + @($Helper, '--version', $Version)
    if ($Source) { $InstallArguments += @('--source', $Source) }
    if ($Prefix) { $InstallArguments += @('--prefix', $Prefix) }
    if ($BinDir) { $InstallArguments += @('--bin-dir', $BinDir) }
    if ($WithoutExtras) { $InstallArguments += '--without-extras' }
    & $PythonExecutable @InstallArguments
    if ($LASTEXITCODE -ne 0) { throw "AI-Memory-Book installation failed with exit code $LASTEXITCODE." }
} finally {
    if ($TemporaryDirectory) {
        Remove-Item -LiteralPath $TemporaryDirectory -Recurse -Force
    }
}
