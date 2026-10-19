$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtimePath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
function Test-ProjectPython([string]$candidate) {
    if (!(Test-Path -LiteralPath $candidate)) { return $false }
    & $candidate -c 'import sys' *> $null
    return $LASTEXITCODE -eq 0
}
if (!(Test-Path -LiteralPath $runtimePath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '请先安装 Python 3.10 或更新版本。' }
}
if (!(Test-ProjectPython $runtimePath)) {
    # Keep the previous environment intact if its original Python was moved.
    $existingCliRuntime = Join-Path (Split-Path -Parent $PSScriptRoot) 'wechat-cli-build-env/Scripts/python.exe'
    if (Test-ProjectPython $existingCliRuntime) {
        $runtimePath = $existingCliRuntime
        Write-Host '原项目环境暂不可用，使用已有本机 CLI 环境；原环境已保留。'
    } else {
        $runtimePath = Join-Path $PSScriptRoot '.venv-recovery/Scripts/python.exe'
        if (!(Test-Path -LiteralPath $runtimePath)) {
            python -m venv .venv-recovery
        }
        if (!(Test-ProjectPython $runtimePath)) { throw '可用 Python 环境未找到，原环境已保留。请先安装 Python 3.10 或更新版本。' }
    }
}
& $runtimePath -c 'import click, Crypto, zstandard'
if ($LASTEXITCODE -ne 0) {
    & $runtimePath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '微信组件依赖安装失败，请检查网络后重试。' }
}
& $runtimePath -X utf8 server.py @args
exit $LASTEXITCODE
