param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8764
)

$ErrorActionPreference = 'Stop'
# Compatibility entry point: use the canonical app and its existing data identity.
# Never substitute an empty Runtime root to bypass unresolved control state.
$launcher = Join-Path $PSScriptRoot 'start.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw 'The canonical Lumina launcher is missing.'
}
$previousPort = [Environment]::GetEnvironmentVariable('LUMINA_PORT', 'Process')
try {
    [Environment]::SetEnvironmentVariable('LUMINA_PORT', [string]$Port, 'Process')
    & $launcher
}
finally {
    [Environment]::SetEnvironmentVariable('LUMINA_PORT', $previousPort, 'Process')
}
