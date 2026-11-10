"""启动饮料机。

    python run.py                          # 全部用参考实现（数据在内存里，重启即清空）
    python run.py --real inventory,stats   # 只把库存、统计换成正式实现
    python run.py --real all               # 全部正式实现（最终演示）
    python run.py --open                   # 启动后用 Edge 应用模式打开点单页

组件名：repository, ingredient, order, inventory, stats, machine
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path

from drink.web.api import create_app
from drink.wiring import COMPONENTS, OWNERS, build

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def parse_real(text: str) -> set[str]:
    if not text:
        return set()
    if text == "all":
        return set(COMPONENTS)
    return {x.strip() for x in text.split(",") if x.strip()}


def open_window(url: str, kiosk: bool) -> None:
    edge = shutil.which("msedge") or next((p for p in EDGE_PATHS if Path(p).exists()), None)
    chrome = shutil.which("google-chrome") or shutil.which("chrome") or shutil.which("chromium")
    browser = edge or chrome
    if browser:
        flag = "--kiosk" if kiosk else f"--app={url}"
        args = [browser, flag, url, "--edge-kiosk-type=fullscreen"] if kiosk else [browser, flag]
        subprocess.Popen(args)
    else:
        webbrowser.open(url)


def main() -> None:
    p = argparse.ArgumentParser(description="自动饮料机")
    p.add_argument("--real", default="", help="用正式实现的组件，逗号分隔，或 all")
    p.add_argument("--db", default="data/drink.db", help="SQLite 文件（repository 用正式实现时）")
    p.add_argument("--port", type=int, default=3000)
    p.add_argument("--no-demo", action="store_true", help="关闭 /api/dev 演示接口")
    p.add_argument("--open", action="store_true", help="启动后打开点单窗口")
    p.add_argument("--kiosk", action="store_true", help="全屏锁定（配合 --open）")
    args = p.parse_args()

    real = parse_real(args.real)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    system = build(real, db_path=args.db)
    app = create_app(system, demo=not args.no_demo)

    print("组件来源：")
    for c in COMPONENTS:
        print(f"  {c:<11} {'正式实现' if c in real else '参考实现':<6}  ({OWNERS[c]})")
    url = f"http://127.0.0.1:{args.port}"
    print(f"点单页 {url}/    维护页 {url}/admin")
    if args.open:
        threading.Timer(1.0, open_window, args=(url, args.kiosk)).start()
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
