"""启动饮料机。

    python run.py                          # 全部用参考实现（数据在内存里，重启即清空）
    python run.py --real inventory,stats   # 只把库存、统计换成正式实现
    python run.py --real all               # 全部正式实现（最终演示）
    python run.py --open                   # 启动后用 Edge 应用模式打开点单页
    python run.py --lan                    # 允许同一 Wi-Fi 的手机扫演示二维码付款
    python run.py --payment alipay         # 用支付宝沙箱收款（配置见 docs/07）

组件名：repository, ingredient, order, inventory, stats, machine
"""
from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _relaunch_in_venv() -> None:
    """当前 Python 没装 Flask 时，自动改用项目里的 .venv 重新启动。"""
    try:
        import flask  # noqa: F401
        return
    except ImportError:
        pass
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python.exe",
                      ROOT / ".venv" / "bin" / "python"):
        if candidate.exists() and candidate.resolve() != Path(sys.executable).resolve():
            sys.exit(subprocess.call([str(candidate), str(ROOT / "run.py"), *sys.argv[1:]]))
    sys.exit("没有找到 Flask。请先在项目目录运行：\n"
             "  python -m venv .venv\n"
             "  .venv 里的 python -m pip install -r requirements-dev.txt")


_relaunch_in_venv()

from drink.web.api import create_app  # noqa: E402
from drink.wiring import COMPONENTS, OWNERS, build  # noqa: E402

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


def lan_ips() -> list[str]:
    """本机可能的局域网 IPv4 地址，按“像真实 Wi-Fi / 有线网卡”的程度排序。

    排除：回环、链路本地、198.18.0.0/15（Clash 等代理的 TUN 网卡）、100.64.0.0/10（Tailscale 等组网工具）。
    虚拟机 / WSL 的虚拟网卡在宿主机一侧通常是 x.x.x.1，所以排在后面。
    """
    import ipaddress

    found = set()
    try:
        found |= {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))          # 不会真的发包，只是让系统选一条路由
            found.add(sock.getsockname()[0])
    except OSError:
        pass
    skip = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "169.254.0.0/16", "198.18.0.0/15", "100.64.0.0/10")]
    good = [ip for ip in found if not any(ipaddress.ip_address(ip) in n for n in skip)]

    def rank(ip):
        a = ipaddress.ip_address(ip)
        return (ip.endswith(".1"), not a.is_private, not ip.startswith("192.168."), ip)

    return sorted(good, key=rank)


def make_payment(kind: str, config_path: str):
    if kind == "mock":
        return None                       # build() 默认用 MockPayment
    if kind == "alipay":
        from drink.model import DrinkError
        from drink.sales.payment_alipay import AlipaySandboxPayment
        try:
            return AlipaySandboxPayment.from_config(config_path)
        except ImportError:
            sys.exit("接支付宝需要 cryptography：pip install -r requirements-alipay.txt")
        except (DrinkError, OSError, ValueError) as e:
            sys.exit(f"支付宝配置有误：{e}\n请按 docs/07-支付宝沙箱配置.md 检查 {config_path}")
    sys.exit(f"未知支付方式 {kind}，可选 mock / alipay")


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
    p.add_argument("--payment", default="mock", choices=["mock", "alipay"], help="收款方式")
    p.add_argument("--alipay-config", default="alipay.json", help="支付宝配置文件")
    p.add_argument("--lan", action="store_true", help="监听局域网，手机可扫码打开演示收银台")
    p.add_argument("--public-url", default=None, help="手机访问本机的地址，如 http://10.0.0.5:3000（--lan 自动检测不准时用）")
    args = p.parse_args()

    real = parse_real(args.real)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    system = build(real, db_path=args.db, payment=make_payment(args.payment, args.alipay_config))
    if args.public_url:
        args.lan = True
    candidates = lan_ips() if args.lan else []
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    public_url = args.public_url or (f"http://{candidates[0]}:{args.port}" if candidates else None)
    app = create_app(system, demo=not args.no_demo, public_url=public_url)

    print("组件来源：")
    for c in COMPONENTS:
        print(f"  {c:<11} {'正式实现' if c in real else '参考实现':<6}  ({OWNERS[c]})")
    print(f"收款方式：{'支付宝沙箱' if args.payment == 'alipay' else '模拟支付'}")
    url = f"http://127.0.0.1:{args.port}"
    print(f"点单页 {url}/    维护页 {url}/admin")
    if public_url:
        print(f"手机扫码地址 {public_url}（手机和电脑需连同一个 Wi-Fi；Windows 首次运行可能要允许防火墙）")
        others = [ip for ip in candidates if ip not in public_url]
        if others and not args.public_url:
            print(f"  如果手机打不开，换成这些地址之一试试：--public-url http://<IP>:{args.port}，候选 IP：{'、'.join(others)}")
    elif args.lan:
        print("没找到局域网地址，请用 --public-url 指定，例如 --public-url http://192.168.1.5:3000")
    if args.open:
        threading.Timer(1.0, open_window, args=(url, args.kiosk)).start()
    app.run(host=host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
