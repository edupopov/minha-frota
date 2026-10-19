$ErrorActionPreference = 'Stop'
$root = if ($PSScriptRoot) {
    $PSScriptRoot
} else {
    Join-Path ([Environment]::GetFolderPath('Desktop')) 'veiculo'
}

$app = Join-Path $root 'app.py'
if (-not (Test-Path -LiteralPath $app)) {
    throw "Aplicação não encontrada em: $app"
}

Set-Location -LiteralPath $root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python nao foi encontrado no PATH. Instale Python 3.11 ou superior e tente novamente.'
}

& python $app
