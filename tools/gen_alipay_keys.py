"""生成支付宝沙箱用的应用密钥对（RSA2048）。

    python tools/gen_alipay_keys.py

会在 keys/ 下生成：
    app_private_key.pem   应用私钥，留在本机，不要提交、不要发给别人
    app_public_key.txt    应用公钥（一整行），粘贴到沙箱应用的“接口加签方式 → 自定义密钥 → 公钥模式”
然后把页面上显示的“支付宝公钥”复制下来，存成 keys/alipay_public_key.txt。
详细步骤见 docs/07-支付宝沙箱配置.md。
"""
import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "keys"


def main() -> None:
    private_path = KEYS / "app_private_key.pem"
    public_path = KEYS / "app_public_key.txt"
    if private_path.exists() and "--force" not in sys.argv:
        sys.exit(f"{private_path} 已存在。确定要换新密钥请加 --force（换了之后要重新上传公钥）。")
    KEYS.mkdir(exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    public_der = key.public_key().public_bytes(serialization.Encoding.DER,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    public_line = base64.b64encode(public_der).decode()
    public_path.write_text(public_line + "\n", encoding="utf-8")
    print(f"已生成：\n  {private_path}\n  {public_path}\n")
    print("把下面这一整行粘贴到沙箱应用的“应用公钥”里：\n")
    print(public_line)


if __name__ == "__main__":
    main()
