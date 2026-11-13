# 阶段 1-2 提测脚本（PowerShell 版）
# 用法：
#   cd F:\pycharm_aiprogram\ai_sichu
#   先启动服务： uv run python main.py > main.log 2>&1 &   （Git Bash）
#   或参考阶段1-2文档 8.3 节用 PowerShell 启动
#   然后运行：.\scripts\stage1-2_check.ps1
$ErrorActionPreference = "Stop"

# 回到项目根目录：脚本在 scripts/ 里时跳回父目录
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $projectRoot) {
    $projectRoot = Get-Location
}
Set-Location $projectRoot

# 守卫：必须已经在项目根目录
if ((-not (Test-Path "main.py")) -or (-not (Test-Path "app_my"))) {
    throw "[X] 请在项目根目录（含 main.py 和 app_my/ 的目录）运行本脚本。当前目录: $(Get-Location)"
}

# 守卫：git 仓库检查
if (-not (Test-Path ".git" -PathType Container)) {
    Write-Host "[!] 当前还不是 git 仓库。请先在项目根目录执行：git init" -ForegroundColor Yellow
    Write-Host "    之后再运行本脚本。" -ForegroundColor Yellow
    exit 1
}

function Run-UvPy {
    # 把 Python 代码写进项目根目录的临时 .py 文件再执行，避免 PowerShell 参数转义吃掉引号
    param([string]$Command)
    $tmp = Join-Path (Get-Location) ("_tmp_stage12_" + [System.Guid]::NewGuid().ToString().Substring(0, 8) + ".py")
    Set-Content -Path $tmp -Value $Command -Encoding UTF8 -NoNewline
    try {
        $out = uv run python $tmp 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "[X] Python 命令失败:`n$out"
        }
        return $out
    } finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
}

Write-Host "==[1/7]== 目录 + __init__.py"
$dlist = @("app_my\core","app_my\db","app_my\db\models","app_my\knowledge","app_my\tools","app_my\middleware","tests","tests\unit","tests\integration","scripts","docker")
foreach ($d in $dlist) { if (-not (Test-Path $d)) { throw "缺目录 $d" } }
$flist = @("app_my\core\__init__.py","app_my\db\__init__.py","app_my\db\models\__init__.py","app_my\knowledge\__init__.py","app_my\tools\__init__.py","app_my\middleware\__init__.py","tests\__init__.py","tests\unit\__init__.py","tests\integration\__init__.py","scripts\__init__.py")
foreach ($f in $flist) { if (-not (Test-Path $f)) { throw "缺文件 $f" } }
Write-Host "[OK]"

Write-Host "==[2/7]== 依赖齐全（含 oss2）"
Run-UvPy 'import oss2; print("oss2", oss2.__version__)' | Write-Host
Run-UvPy 'import fastapi, uvicorn, pydantic_settings; print("OK")' | Write-Host
Write-Host "[OK]"

Write-Host "==[3/7]== config.py"
Run-UvPy 'from app_my.core.config import settings; print("PORT=", settings.PORT)' | Write-Host

Write-Host "==[4/7]== 惰性 LLM"
Run-UvPy 'from app_my.core.models import has_api_key; print("has_api_key=", has_api_key())' | Write-Host

Write-Host "==[5/7]== 服务已在 8002 运行 + 不退化"
$conn = Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue
if (-not $conn) {
    throw "8002 端口没有服务在跑。请先启动服务：`n  uv run python main.py` 或参考阶段1-2文档 8.3 节"
}
Write-Host "[OK] 8002 已有服务（PID=$($conn.OwningProcess)）"

$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $r = Invoke-WebRequest http://127.0.0.1:8002/health -UseBasicParsing -TimeoutSec 2
        if ($r.Content -match '"status":"ok"') {
            Write-Host "[OK] /health 已通（$i s）"
            $ready = $true
            break
        }
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { throw "8002 有进程但 /health 30s 内未响应" }

$r = Invoke-WebRequest http://127.0.0.1:8002/health -UseBasicParsing
Write-Host $r.Content

# CORS null
$cors = Invoke-WebRequest -Uri http://127.0.0.1:8002/oss/presign -Method OPTIONS `
    -Headers @{"Origin"="null"; "Access-Control-Request-Method"="GET"} -UseBasicParsing
$allowOrigin = $cors.Headers["Access-Control-Allow-Origin"]
if ($allowOrigin -ne "null") { throw "CORS null 未通过: $allowOrigin" }
Write-Host "[OK] CORS null 通过"

$presign = Invoke-WebRequest "http://127.0.0.1:8002/oss/presign?filename=test.jpg" -UseBasicParsing
if ($presign.Content -notmatch '"uploadUrl"') { throw "presign 未通过" }
Write-Host "[OK] presign 通过"

# 流式对话（120 秒超时）
$streamCode = @"
import requests
r = requests.post("http://127.0.0.1:8002/chat/stream",
    json={"message":"用一句话推荐一道鸡蛋和西红柿的菜","image_url":[],"thread_id":"stage1-2-test-ps"},
    stream=True, timeout=120)
assert r.status_code == 200, r.status_code
chunks = []
for line in r.iter_lines():
    if line:
        chunks.append(line.decode("utf-8", "ignore"))
        if len(chunks) >= 3:
            break
assert chunks, "没有返回任何 chunk"
print("OK chunks=", len(chunks))
"@
$streamOut = Run-UvPy $streamCode
Write-Host $streamOut

Write-Host "[OK] 全部不退化验证通过"

Write-Host "==[6/7]== .env.example 已跟踪 / .env 未跟踪"
$trackedExample = git ls-files .env.example 2>&1
if ($LASTEXITCODE -ne 0) { throw "git ls-files 失败: $trackedExample" }
if (-not $trackedExample) { throw ".env.example 未跟踪" }
Write-Host "[OK] .env.example 已跟踪"

$trackedEnv = git ls-files .env 2>&1
if ($LASTEXITCODE -ne 0) { throw "git ls-files 失败: $trackedEnv" }
if ($trackedEnv) { throw ".env 被错误跟踪" }
Write-Host "[OK] .env 未跟踪"

Write-Host "==[7/7]== 没有 .env.txt"
if (Test-Path .env.txt) { throw ".env.txt 仍存在" }
Write-Host "[OK]"

Write-Host "[PASS] 阶段 1-2 全部通过" -ForegroundColor Green
