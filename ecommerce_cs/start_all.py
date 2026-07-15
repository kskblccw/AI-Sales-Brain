"""
start_all.py — 一键启动所有服务

    python start_all.py              # 启动全部（8000 + 8001）
    python start_all.py --kb-only    # 仅知识库管理
    python start_all.py --chat-only  # 仅客服系统
"""

import sys
import subprocess
import threading
import time

PYTHON = r"D:\pycharm\condavenv\learn_langchain\python.exe"


def run_server(script: str, port: int, name: str):
    """在子进程中启动服务"""
    proc = subprocess.Popen(
        [PYTHON, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(f"[{name}] 端口 {port} 已启动 (PID={proc.pid})")

    # 流式输出日志
    def _stream():
        for line in proc.stdout:
            if line.strip():
                print(f"[{name}] {line.rstrip()}")

    t = threading.Thread(target=_stream, daemon=True)
    t.start()
    return proc


def main():
    kb_only = "--kb-only" in sys.argv
    chat_only = "--chat-only" in sys.argv

    procs = []

    if not kb_only:
        procs.append(run_server("server.py", 8000, "客服系统"))
        time.sleep(1)

    if not chat_only:
        procs.append(run_server("kb_server.py", 8001, "知识库"))
        time.sleep(1)

    print("\n" + "=" * 60)
    if not kb_only:
        print(f"  客服系统:  http://localhost:8000")
    if not chat_only:
        print(f"  知识库管理: http://localhost:8001")
    print("  Ctrl+C 停止所有服务")
    print("=" * 60 + "\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n正在停止...")
        for p in procs:
            p.terminate()
        print("已停止。")


if __name__ == "__main__":
    main()
