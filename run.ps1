# 启动 HIA Demo
# Anaconda 建的 venv 在 Windows 上缺 OpenSSL DLL,需把 Anaconda\Library\bin 加到 PATH
$a = "D:\ProgramData\Anaconda3"
$env:PATH = "$a;$a\Library\bin;$a\Library\mingw-w64\bin;$a\Library\usr\bin;$a\Scripts;$a\DLLs;" + $env:PATH
# --server.address 0.0.0.0 让同一局域网的同事可通过 http://<本机IP>:8501 访问
& "E:\projects\hia_demo\.venv\Scripts\python.exe" -m streamlit run "E:\projects\hia_demo\app.py" --server.address 0.0.0.0 --server.port 8501
