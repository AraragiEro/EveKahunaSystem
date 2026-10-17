# -*- coding: utf-8 -*-
"""启动期安全配置检查单元测试（安全审计分册 03 - #11 / #12）

所有用例均通过参数注入 / monkeypatch 隔离真实的 config.toml 与真实环境变量，
不依赖仓库内任何真实配置内容。
"""

import pytest

from src_v2.core.config.security_check import (
    PLACEHOLDER_SECRET_KEYS,
    enforce_startup_security,
    inspect_admin_config,
    inspect_secret_key,
)

# 测试用的强密钥（≥32 位，非占位符）
STRONG_KEY = "Qk7pZ2mW9xR4tY6uI8oP1aS3dF5gH7jK0lZ2xC4vB6n"
# 仓库本地开发用的短密钥（9~10 位，只应命中 warn，不能中断 --dev）
DEV_SHORT_KEY = "zhucct1111"


class FakeConfig:
    """配置对象替身，模拟 TomlConfigParser 的 get / getboolean 行为。"""

    def __init__(
        self,
        secret_key=None,
        create_admin=False,
        admin_user="",
        admin_passwd="",
        app_section=True,
    ):
        self._data = {
            "ADMIN": {
                "create_admin": create_admin,
                "admin_user": admin_user,
                "admin_passwd": admin_passwd,
            }
        }
        if app_section:
            self._data["APP"] = {} if secret_key is None else {"SECRET_KEY": secret_key}

    def get(self, section, key, fallback=None):
        return self._data.get(section, {}).get(key, fallback)

    def getboolean(self, section, key, fallback=None):
        value = self._data.get(section, {}).get(key)
        if value is None:
            return fallback
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes", "on")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """每个用例都从干净的环境变量开始，避免受开发机真实环境干扰。"""
    monkeypatch.delenv("KAHUNA_SECRET_KEY", raising=False)
    monkeypatch.delenv("KAHUNA_ALLOW_INSECURE_STARTUP", raising=False)


@pytest.mark.unit
class TestInspectSecretKey:
    """inspect_secret_key 的分级判定。"""

    @pytest.mark.parametrize(
        "value",
        [
            "change-me-to-a-random-secret-key",
            "CHANGE-ME-TO-A-RANDOM-SECRET-KEY",
            "your-secret-key-here",
            "changeme",
            "secret",
            "secret-key",
            "your-secret-key",
            "please-change-me-now",
            "my-placeholder-value-1234567890",
        ],
    )
    def test_placeholder_is_error(self, value):
        """占位符 / 含占位片段的值应判为 error。"""
        ok, level, message = inspect_secret_key(value)
        assert ok is False
        assert level == "error"
        assert message  # 必须有中文提示
        assert value not in message  # 不能回显密钥明文

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_is_error(self, value):
        """空值 / None 应判为 error。"""
        ok, level, message = inspect_secret_key(value)
        assert ok is False
        assert level == "error"
        assert message

    def test_short_dev_key_is_warn(self):
        """短开发密钥只 warn，保证本地 --dev 不被误杀。"""
        ok, level, message = inspect_secret_key(DEV_SHORT_KEY)
        assert ok is False
        assert level == "warn"
        assert DEV_SHORT_KEY not in message
        # 提示里应给出生成方式或环境变量名
        assert "KAHUNA_SECRET_KEY" in message or "secrets" in message

    def test_strong_key_is_ok(self):
        """32 位以上随机串应判为 ok。"""
        ok, level, message = inspect_secret_key(STRONG_KEY)
        assert ok is True
        assert level == "ok"
        assert STRONG_KEY not in message

    def test_placeholder_set_contains_required_entries(self):
        """占位符集合至少包含审计要求的关键项。"""
        required = {
            "change-me-to-a-random-secret-key",
            "your-secret-key-here",
            "changeme",
            "secret",
            "secret-key",
            "your-secret-key",
        }
        assert required.issubset(PLACEHOLDER_SECRET_KEYS)


@pytest.mark.unit
class TestInspectAdminConfig:
    """inspect_admin_config 的判定。"""

    def test_create_admin_false_passes(self):
        """未启用 create_admin 时直接通过。"""
        ok, reason = inspect_admin_config(False, "", "")
        assert ok is True
        assert reason == ""

    def test_empty_password_rejected(self):
        """create_admin=true 且口令为空 → 拒绝。"""
        ok, reason = inspect_admin_config(True, "ops", "")
        assert ok is False
        assert "admin_passwd" in reason

    def test_empty_user_rejected(self):
        """create_admin=true 且用户名为空 → 拒绝。"""
        ok, reason = inspect_admin_config(True, "  ", "A-strong-passwd-123")
        assert ok is False
        assert "admin_user" in reason

    def test_default_kahuna_password_rejected(self):
        """默认口令 kahuna/kahuna 必须被拒绝。"""
        ok, reason = inspect_admin_config(True, "kahuna", "kahuna")
        assert ok is False
        assert reason

    def test_long_weak_password_rejected(self):
        """长度达标但命中弱口令黑名单 → 拒绝。"""
        ok, reason = inspect_admin_config(True, "ops", "kahuna123456")
        assert ok is False
        assert "黑名单" in reason

    def test_strong_password_passes(self):
        """12 位混合口令 → 通过。"""
        ok, reason = inspect_admin_config(True, "ops", "Kx7-Qm2v-Rt9p")
        assert ok is True
        assert reason == ""


@pytest.mark.unit
class TestEnforceStartupSecurity:
    """enforce_startup_security 的启动拦截行为。"""

    def test_placeholder_secret_raises_system_exit_in_prod(self):
        """占位符密钥 → prod 下抛 SystemExit。"""
        cfg = FakeConfig(secret_key="change-me-to-a-random-secret-key")
        with pytest.raises(SystemExit):
            enforce_startup_security(prod=True, config_obj=cfg)

    def test_placeholder_secret_raises_system_exit_in_dev(self):
        """占位符密钥 → 即使 --dev 也默认中断（放行需显式开关）。"""
        cfg = FakeConfig(secret_key="your-secret-key-here")
        with pytest.raises(SystemExit):
            enforce_startup_security(prod=False, config_obj=cfg)

    def test_empty_secret_raises_system_exit(self):
        """空密钥 → 抛 SystemExit。"""
        cfg = FakeConfig(secret_key="")
        with pytest.raises(SystemExit):
            enforce_startup_security(prod=True, config_obj=cfg)

    def test_missing_app_section_raises_system_exit(self):
        """配置缺段（无 [APP]）时不应崩溃，而是按空值中断。"""
        cfg = FakeConfig(app_section=False)
        with pytest.raises(SystemExit):
            enforce_startup_security(prod=True, config_obj=cfg)

    def test_short_dev_key_does_not_raise(self):
        """9~10 位开发密钥只告警，不中断 dev 启动。"""
        cfg = FakeConfig(secret_key=DEV_SHORT_KEY)
        # 不抛异常即通过
        enforce_startup_security(prod=False, config_obj=cfg)

    def test_short_key_warn_allows_prod_startup(self):
        """warn 级问题在生产模式下同样放行（不中断）。"""
        cfg = FakeConfig(secret_key=DEV_SHORT_KEY)
        enforce_startup_security(prod=True, config_obj=cfg)

    def test_strong_key_passes_both_modes(self):
        """强密钥在生产 / 开发模式下都放行。"""
        enforce_startup_security(prod=True, config_obj=FakeConfig(secret_key=STRONG_KEY))
        enforce_startup_security(prod=False, config_obj=FakeConfig(secret_key=STRONG_KEY))

    def test_env_secret_key_overrides_config_placeholder(self, monkeypatch):
        """环境变量密钥优先，可覆盖配置文件中的占位符。"""
        monkeypatch.setenv("KAHUNA_SECRET_KEY", STRONG_KEY)
        cfg = FakeConfig(secret_key="change-me-to-a-random-secret-key")
        enforce_startup_security(prod=True, config_obj=cfg)

    def test_allow_insecure_releases_error_in_dev(self, monkeypatch):
        """非 prod + 放行开关 → error 级问题放行。"""
        monkeypatch.setenv("KAHUNA_ALLOW_INSECURE_STARTUP", "1")
        cfg = FakeConfig(secret_key="change-me-to-a-random-secret-key")
        # 不抛异常即通过
        enforce_startup_security(prod=False, config_obj=cfg)

    def test_allow_insecure_ignored_in_prod(self, monkeypatch):
        """prod 下放行开关无效，仍然中断启动。"""
        monkeypatch.setenv("KAHUNA_ALLOW_INSECURE_STARTUP", "1")
        cfg = FakeConfig(secret_key="change-me-to-a-random-secret-key")
        with pytest.raises(SystemExit):
            enforce_startup_security(prod=True, config_obj=cfg)

    def test_weak_admin_config_does_not_abort_startup(self):
        """管理员配置过弱只告警，不中断启动（由 run_server 跳过建号）。"""
        cfg = FakeConfig(
            secret_key=STRONG_KEY,
            create_admin=True,
            admin_user="kahuna",
            admin_passwd="kahuna",
        )
        # 不抛异常即通过
        enforce_startup_security(prod=True, config_obj=cfg)
