# 自动饮料机 · 结对编程小组

课程《结对编程实践》项目：一台自助饮料机上运行的单机程序。网页界面 + Python（Flask）后端 + SQLite，付款可模拟，也可接支付宝沙箱。

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows 官方 Python
                                   # MSYS2 的 Python 或 macOS / Linux：source .venv/bin/activate
pip install -r requirements-dev.txt

python run.py --open               # 打开点单窗口；维护页在 /admin
pytest                             # 跑测试，最后会打印每个人的进度
```

Windows 也可以直接双击 `start.bat`。

常用启动参数：

```bash
python run.py --lan                 # 手机和电脑连同一 Wi-Fi，可扫付款码打开“演示收银台”
python run.py --public-url http://10.0.0.5:3000   # 自动检测的 IP 不对时（开了代理 / 虚拟机网卡），手动指定
python run.py --payment alipay      # 用支付宝沙箱收款（先按 docs/07 配置）
python run.py --real all            # 全部使用组员的正式实现
python run.py --open --kiosk        # 全屏，模拟售货机屏幕
```

## 分工

| | 负责 | 代码 |
|---|---|---|
| A | GUI：点单页、维护页、HTTP 接口层 | `drink/web/` |
| B | 销售端 + 食材端：订单、支付、菜单、计价、推荐 | `drink/sales/` |
| C | 数据维护 + 机器维护：库存、补货、统计、机器模拟器 | `drink/maintenance/` |
| D | 数据结构：实体、数据库、数据访问、集成 | `drink/model/`、`drink/wiring.py` |

## 怎么开工

1. 读 `docs/01-需求规格.md` 和 `docs/06-分工与里程碑.md` 里你的部分；
2. 打开你的文件，把 `raise NotImplementedError  # TODO` 换成实现；
3. 跑 `pytest tests/contract/<你的测试>.py -k real`，直到全绿；
4. `python run.py --real <你的组件>` 在完整程序里看效果。

组件名：`repository`（D）、`ingredient`、`order`（B）、`inventory`、`stats`、`machine`（C）。没写完的组件自动用参考实现顶上，所以谁都不用等别人。

## 文档

| 文档 | 内容 |
|---|---|
| [01 需求规格](docs/01-需求规格.md) | 按人分的需求清单（必做 / 加分）、假设、演示脚本 |
| [02 系统架构](docs/02-系统架构.md) | 技术选型、分层、依赖规则、轮询驱动、目录结构 |
| [03 详细设计](docs/03-详细设计.md) | 数据模型、计价与换算规则、订单状态机、错误处理 |
| [04 接口契约](docs/04-接口契约.md) | Python 接口、HTTP 接口与 JSON 示例、修改流程 |
| [05 测试计划](docs/05-测试计划.md) | 怎么跑测试、需求与测试对照、界面验收清单 |
| [06 分工与里程碑](docs/06-分工与里程碑.md) | 每人任务、自由发挥范围、对应课程活动的时间线 |
| [07 支付宝沙箱配置](docs/07-支付宝沙箱配置.md) | 开通沙箱、生成密钥、填配置、扫码联调 |
