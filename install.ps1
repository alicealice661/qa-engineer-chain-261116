# 安装 qa-engineer-chain 到 skills 目录（Windows / PowerShell）
# 用法:
#   .\install.ps1                  # 装到 %USERPROFILE%\.workbuddy\skills
#   .\install.ps1 -Target D:\skills
#   .\install.ps1 -DryRun          # 只列会装什么，不动文件
# 若被安全策略拦住，先执行:
#   Set-ExecutionPolicy -Scope Process Bypass -Force
param(
    [string]$Target = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = Join-Path $Here "skills"

if (-not (Test-Path $Src)) {
    Write-Error "找不到 $Src"
    exit 1
}
if ([string]::IsNullOrWhiteSpace($Target)) {
    $Target = Join-Path $env:USERPROFILE ".workbuddy\skills"
}

Write-Output "源目录  : $Src"
Write-Output "目标目录: $Target"
if ($DryRun) { Write-Output "模式    : dry-run（不会修改任何文件）" }
Write-Output ""

if (-not (Test-Path $Target)) {
    if ($DryRun) {
        Write-Output "目标目录不存在，实际安装时会创建。"
    } else {
        New-Item -ItemType Directory -Path $Target -Force | Out-Null
        Write-Output "已创建目标目录。"
    }
}

$dirs = Get-ChildItem -Path $Src -Directory | Sort-Object Name
$installed = 0
$conflicts = @()

foreach ($d in $dirs) {
    $dest = Join-Path $Target $d.Name
    if (Test-Path $dest) {
        $conflicts += $d.Name
    } else {
        $installed++
        if ($DryRun) {
            Write-Output "  [将安装] $($d.Name)"
        } else {
            Copy-Item -Path $d.FullName -Destination $dest -Recurse
            Write-Output "  [已安装] $($d.Name)"
        }
    }
}

Write-Output ""
Write-Output "合计：$($dirs.Count) 个技能"
Write-Output "  将安装/已安装：$installed"
Write-Output "  同名跳过     ：$($conflicts.Count)"

if ($conflicts.Count -gt 0) {
    Write-Output ""
    Write-Output "以下同名技能已存在，未覆盖（如需替换请先备份再删除）："
    foreach ($n in $conflicts) { Write-Output "  - $n" }
    Write-Output ""
    Write-Output "提示：想用修好的版本，先备份：Copy-Item '$Target' '$Target.bak' -Recurse，再删掉要替换的目录重跑。"
}

if (-not $DryRun -and $installed -gt 0) {
    Write-Output ""
    Write-Output "完成。多数 runtime 会自动监听目录变化，无需重启；没生效就重开一次会话。"
}
