"""初始数据与业务常量。负责人：D（数据结构）；数值可由 B、C 提出修改。

全组测试都依赖这里的数字，改动时同步修改测试里的期望值。
"""
from .entities import Material, MenuItem, Recipe
from .enums import ItemKind, Size, Sugar, Temperature

MACHINE_ID = "M001"
TZ_OFFSET_HOURS = 8              # 统计“按小时分布”时使用的时区（北京时间）
PAYMENT_TIMEOUT_MS = 120_000     # 下单后 2 分钟内未付款自动关闭
MAX_ADDONS = 3

MATERIALS: tuple[Material, ...] = (
    Material("black_tea", "红茶液", "mL", 5000, 800),
    Material("green_tea", "茉莉绿茶液", "mL", 5000, 800),
    Material("coffee", "咖啡液", "mL", 3000, 500),
    Material("milk", "牛奶", "mL", 5000, 800),
    Material("lemon_juice", "柠檬汁", "mL", 2000, 300),
    Material("soda", "气泡水", "mL", 5000, 800),
    Material("syrup", "糖浆", "mL", 2000, 300),
    Material("ice", "冰块", "g", 5000, 800),
    Material("pearl", "黑糖珍珠", "g", 2000, 300),
    Material("pudding", "布丁", "g", 1500, 200),
    Material("coconut", "椰果", "g", 1500, 200),
    Material("cup", "杯子", "个", 200, 20),
)

MENU_ITEMS: tuple[MenuItem, ...] = (
    MenuItem("milk_tea", "经典奶茶", ItemKind.BASE, 1200, "醇厚茶底 · 丝滑奶香", "#cda56c",
             {"black_tea": 200, "milk": 150}),
    MenuItem("jasmine", "茉莉绿茶", ItemKind.BASE, 800, "清新花香 · 轻盈回甘", "#b9c779",
             {"green_tea": 350}),
    MenuItem("latte", "醇香拿铁", ItemKind.BASE, 1500, "浓郁烘焙 · 香气满杯", "#866653",
             {"coffee": 120, "milk": 200}),
    MenuItem("lemon_soda", "鲜柠气泡", ItemKind.BASE, 1000, "清爽果香 · 细密气泡", "#d1cc76",
             {"lemon_juice": 60, "soda": 300}, hot_allowed=False),
    MenuItem("pearl", "黑糖珍珠", ItemKind.ADDON, 200, consumption={"pearl": 40}),
    MenuItem("pudding", "香滑布丁", ItemKind.ADDON, 300, consumption={"pudding": 50}),
    MenuItem("coconut", "椰果", ItemKind.ADDON, 200, consumption={"coconut": 40}),
)

# 初始库存：椰果为 0（演示“售罄”），布丁低于预警线（演示“库存预警”）
INITIAL_STOCK: dict[str, int] = {m.id: m.capacity for m in MATERIALS} | {
    "coconut": 0,
    "pudding": 150,
}

# ----- 配方换算规则（食材端 B 使用） -----
SIZE_EXTRA_FEN = {Size.M: 0, Size.L: 300}
SIZE_FACTOR = {Size.M: 1.0, Size.L: 1.4}         # 大杯：基底、糖、冰按 1.4 倍，加料不变
SUGAR_SYRUP_ML = {Sugar.NONE: 0, Sugar.LIGHT: 9, Sugar.HALF: 15, Sugar.FULL: 30}  # 中杯
ICE_G = {Temperature.ICED: 80, Temperature.NORMAL: 0, Temperature.HOT: 0}         # 中杯

DEFAULT_RECIPE = Recipe("milk_tea", (), Size.M, Temperature.ICED, Sugar.HALF)

# 销量数据不足时的推荐兜底
PRESET_RECOMMENDATIONS: tuple[Recipe, ...] = (
    Recipe("jasmine", (), Size.M, Temperature.ICED, Sugar.LIGHT),
    Recipe("milk_tea", ("pearl",), Size.M, Temperature.ICED, Sugar.HALF),
    Recipe("latte", (), Size.M, Temperature.HOT, Sugar.NONE),
)
