import subprocess
import sys

# 对应你三个脚本的路径（根据实际项目调整）
scripts = [
    "D:\Workspace\CollectPlatform\WebService\Mock\mock_mmWav.py",
    "D:\Workspace\CollectPlatform\WebService\Mock\mock_mmWav2.py",
    "D:\Workspace\CollectPlatform\WebService\\app\main.py"
]

processes = []
for script in scripts:
    # 用当前PyCharm的Python解释器启动，后台运行
    p = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    processes.append(p)
    print(f"✅ 已启动 {script}，进程ID: {p.pid}")

# 等待所有进程结束（注释掉则主脚本退出，子进程继续后台运行）
for p in processes:
    p.wait()