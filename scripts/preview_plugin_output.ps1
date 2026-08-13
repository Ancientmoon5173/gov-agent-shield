param(
    [string]$RepoRoot = "E:\Openclaw项目\揭榜挂帅\揭榜挂帅项目主体\GovAgent-Shield",
    [string]$OpenClawRoot = "D:\OpenClaw\openclaw-main"
)

$ErrorActionPreference = "Stop"

$pluginSrc = Join-Path $RepoRoot "openclaw_plugin\govagent-shield"
$pluginDst = Join-Path $OpenClawRoot "extensions\govagent-shield"

if (-not (Test-Path -LiteralPath $pluginSrc)) {
    throw "插件源目录不存在: $pluginSrc"
}
if (-not (Test-Path -LiteralPath $pluginDst)) {
    throw "OpenClaw 扩展目录不存在: $pluginDst"
}

Write-Host "同步插件到 $pluginDst"
Get-ChildItem -LiteralPath $pluginSrc -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $pluginDst -Recurse -Force
}

$env:SHIELD_PREVIEW = "1"
$previewOut = Join-Path $RepoRoot "scripts\preview_output.txt"
$env:SHIELD_PREVIEW_OUT = $previewOut
if (Test-Path -LiteralPath $previewOut) {
    Remove-Item -LiteralPath $previewOut -Force
}
$vitest = Join-Path $OpenClawRoot "node_modules\.bin\vitest.cmd"
Push-Location $OpenClawRoot
try {
    & $vitest run "extensions\govagent-shield\test\preview_output.test.ts" *>&1
    if (Test-Path -LiteralPath $previewOut) {
        Write-Host ""
        Get-Content -LiteralPath $previewOut
    }
}
finally {
    Pop-Location
}
