$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
try {
    $sumFile = Join-Path $packageRoot 'SHA256SUMS.txt'
    $checked = 0
    foreach ($line in Get-Content -LiteralPath $sumFile) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)$') { throw 'Formato SHA256SUMS non valido' }
        $expectedHash = $Matches[1]
        $waveName = $Matches[2]
        $wavePath = Join-Path $packageRoot $waveName
        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wavePath).Hash
        if ($actualHash -ne $expectedHash) { throw ('File alterato o incompleto: ' + $waveName) }
        Write-Host ('OK: ' + $waveName)
        $checked++
    }
    if ($checked -ne 2) { throw 'Devono essere verificati esattamente due WAV' }
    Write-Host 'Entrambi i WAV coincidono con quelli verificati. Leggi la guida prima di aggiornare.'
    exit 0
} catch {
    Write-Host ('ERRORE: ' + $_.Exception.Message)
    exit 1
}
