# 启动 HIA Demo —— 路径自适应(用脚本所在目录),两台机器通用。
# 干净的 python.org venv:ssl 原生可用,直接启动即可。
# 兼容:若某台机器的 venv 由 Anaconda 创建而缺 OpenSSL DLL(import ssl 失败),
#       自动探测常见 Anaconda 安装位置并补 PATH,无需手改。
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

& $py -c "import ssl" 2>$null
if ($LASTEXITCODE -ne 0) {
    foreach ($base in @("$env:USERPROFILE\Anaconda3", "$env:USERPROFILE\miniconda3",
                        "D:\ProgramData\Anaconda3", "C:\ProgramData\Anaconda3")) {
        if (Test-Path (Join-Path $base "Library\bin")) {
            $env:PATH = "$base;$base\Library\bin;$base\Library\mingw-w64\bin;" +
                        "$base\Library\usr\bin;$base\Scripts;$base\DLLs;" + $env:PATH
            Write-Host "[run.ps1] 检测到 venv 缺 ssl,已补 Anaconda DLL: $base"
            break
        }
    }
}
# --server.address 0.0.0.0 让同一局域网的同事可通过 http://<本机IP>:8501 访问
& $py -m streamlit run (Join-Path $root "app.py") --server.address 0.0.0.0 --server.port 8501
