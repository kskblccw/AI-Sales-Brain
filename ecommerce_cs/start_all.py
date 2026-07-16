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
import os
from pathlib import Path

PYTHON = r"D:\pycharm\condavenv\learn_langchain\python.exe"
ROOT = Path(__file__).parent  # ecommerce_cs 目录


def run_server(script: str, port: int, name: str):
    """在子进程中启动服务"""
    script_path = ROOT / script
    if not script_path.exists():
        print(f"[{name}] 脚本不存在: {script_path}")
        return None

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        [PYTHON, str(script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        env=env,
    )
    print(f"[{name}] 端口 {port} 已启动 (PID={proc.pid})")

    # 流式输出日志
    def _stream():
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    print(f"[{name}] {line}")
        except Exception:
            pass

    t = threading.Thread(target=_stream, daemon=True)
    t.start()

    # 等 2 秒看进程是否立即退出（启动失败）
    time.sleep(2)
    ret = proc.poll()
    if ret is not None:
        print(f"[{name}] 启动失败，退出码 {ret}。请检查端口 {port} 是否被占用或依赖是否就绪。")
        return None

    return proc


def main():
    kb_only = "--kb-only" in sys.argv
    chat_only = "--chat-only" in sys.argv

    procs = []

    if not kb_only:
        p = run_server("server.py", 8000, "客服系统")
        if p:
            procs.append(p)

    if not chat_only:
        p = run_server("kb_server.py", 8001, "知识库")
        if p:
            procs.append(p)

    if not procs:
        print("\n没有成功启动的服务，退出。")
        return

    print("\n" + "=" * 60)
    if not kb_only:
        print(f"  客服系统:  http://localhost:8000")
    if not chat_only:
        print(f"  知识库管理: http://localhost:8001")
    print("  Ctrl+C 停止所有服务")
    print("=" * 60 + "\n")

    try:
        while True:
            # 持续检查进程状态
            for p in procs:
                ret = p.poll()
                if ret is not None:
                    print(f"[警告] 进程 PID={p.pid} 意外退出，退出码 {ret}")
                    procs.remove(p)
            if not procs:
                print("所有服务已退出。")
                break
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n正在停止...")
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("已停止。")


if __name__ == "__main__":
    main()
