# -*- coding: utf-8 -*-
"""启动期安全配置检查（安全审计分册 03 - #11 / #12）

在服务启动前检查关键安全配置：

1. 应用签名密钥 ``APP.SECRET_KEY``（JWT / 会话签名）：
   - 为空或仍是模板占位符 → error，中断启动；
   - 长度不足 32 位 → warn，仅提示不中断（保证本地 ``--dev`` 的开发密钥还能启动）。
2. 默认管理员账号创建配置 ``ADMIN.*``：
   - ``create_admin=true`` 但用户名 / 口令为空、口令过短或命中弱口令黑名单 → 检查失败，
     由调用方（``run_server.py``）跳过建号，不中断启动。

约束：
- 所有日志只包含长度、来源等非敏感信息，**绝不拼接密钥明文**；
- 放行开关环境变量 ``KAHUNA_ALLOW_INSECURE_STARTUP=1`` 只在非生产模式（``--dev``）下
  可以放行 error 级问题，生产模式（``--prod``）下无效。

本模块刻意保持无副作用（不在导入期读配置），便于单元测试注入配置替身。
"""

import os
from typing import Optional, Tuple

from src_v2.core.log import logger

# ---------------------------------------------------------------------------
# 常量：占位符 / 弱口令 / 环境变量
# ---------------------------------------------------------------------------

# 已知的模板 / 示例占位密钥（比较时统一转小写）
PLACEHOLDER_SECRET_KEYS = {
    "change-me-to-a-random-secret-key",
    "your-secret-key-here",
    "changeme",
    "secret",
    "secret-key",
    "your-secret-key",
}

# 占位符片段：密钥值中包含这些片段（大小写不敏感）即视为占位符
PLACEHOLDER_SUBSTRINGS = (
    "change-me",
    "your-secret",
    "placeholder",
)

# 弱管理员口令黑名单（比较时统一转小写）
# 注意：不要在这里加入仓库现有的开发用密钥，避免本地 --dev 被误杀。
WEAK_ADMIN_PASSWORDS = {
    "kahuna",
    "kahuna123",
    "kahuna123456",
    "admin",
    "adminadmin12",
    "admin1234567",
    "administrator",
    "password",
    "password1234",
    "passwd",
    "changeme",
    "qwerty",
    "qwertyuiop12",
    "123456",
    "12345678",
    "123456789",
    "1234567890",
    "123456789012",
    "111111",
    "000000",
    "abc123",
    "root",
    "test",
}

# 长度下限
MIN_SECRET_KEY_LENGTH = 32
MIN_ADMIN_PASSWD_LENGTH = 12

# 环境变量
SECRET_KEY_ENV = "KAHUNA_SECRET_KEY"
ALLOW_INSECURE_ENV = "KAHUNA_ALLOW_INSECURE_STARTUP"

# 生成随机密钥的提示命令（不含任何真实密钥）
SECRET_KEY_HINT = 'python -c "import secrets;print(secrets.token_urlsafe(32))"'


def inspect_secret_key(value: Optional[str]) -> Tuple[bool, str, str]:
    """检查应用签名密钥（APP.SECRET_KEY）。

    返回 ``(ok, level, message)``，其中 level ∈ {"ok", "warn", "error"}。
    空值 / 占位符 → error；长度 < 32 → warn；其余 → ok。
    message 中只包含长度与修复建议，不包含密钥明文。
    """
    if value is None:
        return (
            False,
            "error",
            "APP.SECRET_KEY 未配置（None），JWT / 会话签名密钥必须显式设置",
        )

    key = str(value).strip()
    if not key:
        return (
            False,
            "error",
            "APP.SECRET_KEY 为空，JWT / 会话签名密钥必须显式设置",
        )

    lowered = key.lower()
    is_placeholder = lowered in PLACEHOLDER_SECRET_KEYS or any(
        fragment in lowered for fragment in PLACEHOLDER_SUBSTRINGS
    )
    if is_placeholder:
        return (
            False,
            "error",
            f"APP.SECRET_KEY 仍是模板/示例占位符（长度 {len(key)}），必须更换为随机长密钥",
        )

    if len(key) < MIN_SECRET_KEY_LENGTH:
        return (
            False,
            "warn",
            (
                f"APP.SECRET_KEY 长度仅 {len(key)} 位（建议 ≥ {MIN_SECRET_KEY_LENGTH} 位）；"
                f"可用 {SECRET_KEY_HINT} 生成，或通过环境变量 {SECRET_KEY_ENV} 覆盖"
            ),
        )

    return True, "ok", f"APP.SECRET_KEY 长度 {len(key)} 位，符合要求"


def inspect_admin_config(
    create_admin: bool,
    admin_user: Optional[str],
    admin_passwd: Optional[str],
) -> Tuple[bool, str]:
    """检查默认管理员账号创建配置。

    返回 ``(ok, reason)``；ok 为 False 时 reason 是中文失败原因（不含口令明文）。
    未启用 create_admin 时直接视为通过。
    """
    if not create_admin:
        return True, ""

    user = (admin_user or "").strip()
    passwd = admin_passwd or ""

    if not user:
        return False, "ADMIN.admin_user 为空，无法创建管理员账号"

    if not passwd:
        return False, "ADMIN.admin_passwd 为空，拒绝创建管理员账号"

    if len(passwd) < MIN_ADMIN_PASSWD_LENGTH:
        return (
            False,
            f"ADMIN.admin_passwd 长度仅 {len(passwd)} 位（要求 ≥ {MIN_ADMIN_PASSWD_LENGTH} 位）",
        )

    if passwd.strip().lower() in WEAK_ADMIN_PASSWORDS:
        return (
            False,
            "ADMIN.admin_passwd 命中弱口令黑名单（如 kahuna/kahuna、admin/admin、password、123456 等）",
        )

    return True, ""


def _load_config():
    """延迟导入全局配置对象，避免模块导入期产生循环导入 / 副作用。"""
    from src_v2.core.config.config import config as global_config

    return global_config


def _read_effective_secret_key(cfg) -> Tuple[Optional[str], str]:
    """读取实际生效的签名密钥，返回 ``(值, 来源)``；来源仅用于日志。"""
    env_key = (os.environ.get(SECRET_KEY_ENV) or "").strip()
    if env_key:
        return env_key, "env"

    try:
        value = cfg.get("APP", "SECRET_KEY", fallback="")
    except Exception:  # 配置对象异常时不阻断启动流程，交给调用方按空值处理
        value = ""
    return value, "config"


def enforce_startup_security(prod: bool, config_obj=None) -> None:
    """执行启动期安全检查；error 级问题会中断启动（SystemExit(1)）。

    参数：
        prod: 是否为生产模式（``--prod``）；
        config_obj: 可选的配置对象注入（须提供 ``get`` / ``getboolean``），
            默认使用全局 ``src_v2.core.config.config.config``，便于单元测试隔离。

    放行开关 ``KAHUNA_ALLOW_INSECURE_STARTUP=1`` 仅在非生产模式下放行 error 级问题，
    生产模式下该变量会被忽略并在日志中说明。
    """
    cfg = config_obj if config_obj is not None else _load_config()
    allow_insecure = (os.environ.get(ALLOW_INSECURE_ENV) or "").strip() == "1"

    if allow_insecure and prod:
        logger.warning(
            f"启动安全检查：{ALLOW_INSECURE_ENV}=1 在生产模式（--prod）下无效，"
            "安全检查照常执行并可能中断启动"
        )

    secret_key, source = _read_effective_secret_key(cfg)
    source_desc = (
        f"环境变量 {SECRET_KEY_ENV}" if source == "env" else "配置文件 APP.SECRET_KEY"
    )

    ok, level, message = inspect_secret_key(secret_key)
    if level == "ok":
        logger.info(f"启动安全检查通过：{message}（来源：{source_desc}）")
    elif level == "warn":
        logger.warning(f"启动安全检查告警：{message}（来源：{source_desc}）")
    else:
        logger.error(f"启动安全检查失败：{message}（来源：{source_desc}）")
        if not prod and allow_insecure:
            logger.warning(
                f"已检测到 {ALLOW_INSECURE_ENV}=1，开发模式下忽略该错误并继续启动"
                "（生产模式不允许放行）"
            )
        else:
            logger.error(
                "已中断启动：请在 config.toml 的 [APP] SECRET_KEY 或环境变量 "
                f"{SECRET_KEY_ENV} 中配置一个随机长密钥（建议 ≥ {MIN_SECRET_KEY_LENGTH} 位）"
            )
            raise SystemExit(1)

    # 管理员创建配置只告警不中断（安全审计 #11 要求“跳过建号”而非“服务起不来”）
    try:
        create_admin = bool(cfg.getboolean("ADMIN", "create_admin", fallback=False))
        admin_user = (cfg.get("ADMIN", "admin_user", fallback="") or "").strip()
        admin_passwd = cfg.get("ADMIN", "admin_passwd", fallback="") or ""
    except Exception as e:  # 配置节缺失 / 类型异常时不让启动期检查本身炸掉
        logger.warning(f"启动安全检查：读取 ADMIN 配置失败，跳过管理员配置检查: {e}")
        return

    admin_ok, admin_reason = inspect_admin_config(create_admin, admin_user, admin_passwd)
    if create_admin and not admin_ok:
        logger.warning(
            f"启动安全检查：ADMIN 配置不完整或口令过弱（{admin_reason}），"
            "启动后将跳过管理员账号创建"
        )
