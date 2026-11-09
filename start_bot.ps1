# Starts Otaku Kitchen Bot without saving the BotFather token on disk.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyLauncher -and -not $python) {
    Write-Host 'Python не найден. Установите Python 3.10+ с https://www.python.org/downloads/windows/' -ForegroundColor Yellow
    Write-Host 'Во время установки включите Add Python to PATH.'
    exit 1
}
Write-Host 'Otaku Kitchen Bot (@otakukitchen_recipes_bot)' -ForegroundColor Cyan
Write-Host 'Вставьте токен из @BotFather (ввод не отображается; токен НЕ сохраняется на диск).'
$secure = Read-Host 'BOT_TOKEN' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:BOT_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
if ([string]::IsNullOrWhiteSpace($env:BOT_TOKEN)) {
    Write-Host 'Токен не введён.' -ForegroundColor Yellow
    exit 1
}
Write-Host 'Запуск... Откройте https://t.me/otakukitchen_recipes_bot и нажмите Start.'
try {
    if ($pyLauncher) { & py -3 bot.py } else { & python bot.py }
} finally {
    Remove-Item Env:\BOT_TOKEN -ErrorAction SilentlyContinue
}
