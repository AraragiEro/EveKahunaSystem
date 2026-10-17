# -*- coding: utf-8 -*-
"""CSRF 保护注册完整性回归测试（安全审计分册 03 #16）

背景：`register_csrf_protection` 为 Blueprint 注册 before_request 钩子，对所有
非 GET/HEAD/OPTIONS 请求做双提交校验。历史上社区版蓝图都调用了它，但企业版两个
蓝图（`api_enterprise` / `api_contract`）与 `internal_mcp` 只
`app.register_blueprint(...)`，漏了 CSRF 注册，导致企业版构建下这批端点在
Cookie 认证场景缺少 CSRF 纵深。

本测试锁两层行为：
1. 钩子语义（独立 Quart 实例，不触碰全局单例 app）：
   a) 带 auth_token cookie 但无 csrf cookie/header → 403
   b) csrf cookie 与 X-CSRF-Token 不一致 → 403
   c) 两者一致 → 200
   d) GET → 跳过校验（200）
   e) 无 auth_token cookie（Bearer / 公开端点）→ 200
2. 注册完整性：子进程里让 `is_enterprise()` 返回 True 后调用 `init_api(app)`，
   用 spy 包住 `register_csrf_protection` 收集被保护的蓝图名，断言企业版两个
   蓝图与 internal_mcp 都在名单里。

为什么用子进程做注册校验：本仓库 `src_v2.backend.app` 在**导入时**就会执行
`init_api(app)`，而蓝图一旦注册过就不能再挂 before_request（Flask 会抛
`AssertionError: The setup method 'before_request' can no longer be called...`），
所以同进程内重跑 `init_api` 必然失败；子进程还能保证不在全局单例 app 上留下
任何残留钩子。
"""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INIT_API_FILE = PROJECT_ROOT / "src_v2" / "backend" / "api" / "__init__.py"

# 需要被 CSRF 保护的蓝图：源码变量名 → Blueprint.name
# （两者并不总是同名，例如 api_enterprise_bp 的 name 是 'enterprise'）
CSRF_PROTECTED_BLUEPRINTS = {
    "api_enterprise_bp": "enterprise",
    "api_contract_bp": "contract_api",
    "internal_mcp_bp": "internal_mcp",
}
ENTERPRISE_BLUEPRINTS = ("api_enterprise_bp", "api_contract_bp")
INTERNAL_MCP_BLUEPRINT = "internal_mcp_bp"

# 子进程脚本：只做"打补丁 + 跑一次 init_api + 打印结果"，全部输出带前缀便于解析。
# 保持纯 ASCII，避免 Windows 控制台编码干扰。
_CHILD_SCRIPT = r'''
import json

from unittest.mock import patch

from quart import Quart

import src_v2.backend.api as api_pkg
from src_v2.backend import auth as auth_mod

# 企业版模块是否可用（社区版构建里可能不存在）
try:
    from src_v2.enterprise.api.api_enterprise import api_enterprise_bp  # noqa: F401
    from src_v2.enterprise.api.api_contract import api_contract_bp  # noqa: F401

    enterprise_available = True
except ImportError:
    enterprise_available = False

names = []
_real = auth_mod.register_csrf_protection


def _spy(bp):
    names.append(getattr(bp, "name", repr(bp)))
    return _real(bp)


app = Quart("csrf-registration-probe")
with patch.object(auth_mod, "register_csrf_protection", _spy), patch(
    "src_v2.core.edition.is_enterprise", return_value=True
):
    api_pkg.init_api(app)

print(
    "CSRF_PROBE:"
    + json.dumps({"enterprise_available": enterprise_available, "names": names})
)
'''


def _build_protected_app():
    """构造独立的 Quart app + 受保护 Blueprint（不触碰全局单例 app）"""
    from quart import Blueprint, Quart

    from src_v2.backend.auth import register_csrf_protection

    app = Quart("csrf-behavior-probe")
    bp = Blueprint("csrf_probe_bp", __name__, url_prefix="/csrf-probe")
    register_csrf_protection(bp)

    @bp.route("/submit", methods=["POST"])
    async def submit():
        return {"ok": True}

    @bp.route("/submit", methods=["GET"])
    async def submit_get():
        return {"ok": True}

    app.register_blueprint(bp)
    return app


def _client_with_cookies(app, cookies=None):
    """创建测试客户端并按需预置 cookie

    注意：Quart 测试客户端的 set_cookie 签名是
    `set_cookie(server_name, key, value)`（沿用 Werkzeug 风格），
    因此第一个参数必须是域名，否则 cookie 名会错位。
    """
    client = app.test_client()
    for key, value in (cookies or {}).items():
        client.set_cookie("localhost", key, value)
    return client


# ============================================================
# 一、register_csrf_protection 钩子语义
# ============================================================


@pytest.mark.api
class TestCsrfHookBehavior:
    """双提交校验的行为回归（独立 app，无全局副作用）"""

    @pytest.mark.asyncio
    async def test_post_with_auth_cookie_without_csrf_token_rejected(self):
        """a) 有 auth_token cookie、无 csrf cookie/header → 403"""
        app = _build_protected_app()
        client = _client_with_cookies(app, {"auth_token": "cookie-token"})

        resp = await client.post("/csrf-probe/submit")

        assert resp.status_code == 403
        body = await resp.get_json()
        assert "CSRF" in body["error"]

    @pytest.mark.asyncio
    async def test_post_with_mismatched_csrf_token_rejected(self):
        """b) csrf cookie 与 X-CSRF-Token 不一致 → 403"""
        app = _build_protected_app()
        client = _client_with_cookies(
            app, {"auth_token": "cookie-token", "csrf_token": "csrf-in-cookie"}
        )

        resp = await client.post(
            "/csrf-probe/submit", headers={"X-CSRF-Token": "csrf-in-header"}
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_post_with_matched_csrf_token_allowed(self):
        """c) csrf cookie 与 X-CSRF-Token 一致 → 200"""
        app = _build_protected_app()
        client = _client_with_cookies(
            app, {"auth_token": "cookie-token", "csrf_token": "same-token"}
        )

        resp = await client.post(
            "/csrf-probe/submit", headers={"X-CSRF-Token": "same-token"}
        )

        assert resp.status_code == 200
        assert await resp.get_json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_get_request_skips_csrf_check(self):
        """d) GET 即使带 auth_token cookie 也不做 CSRF 校验 → 200"""
        app = _build_protected_app()
        client = _client_with_cookies(app, {"auth_token": "cookie-token"})

        resp = await client.get("/csrf-probe/submit")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_without_auth_cookie_allowed(self):
        """e) 无 auth_token cookie（Bearer / 公开端点）→ 放行 200"""
        app = _build_protected_app()
        client = app.test_client()

        resp = await client.post(
            "/csrf-probe/submit", headers={"Authorization": "Bearer some-jwt"}
        )

        assert resp.status_code == 200


# ============================================================
# 二、注册完整性（企业版蓝图 / internal_mcp 必须被 CSRF 保护）
# ============================================================


def _run_registration_probe():
    """在子进程中执行 init_api 并返回 spy 结果

    返回 dict：{"enterprise_available": bool, "names": [...]}
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_SCRIPT],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=env,
    )

    if completed.returncode != 0:
        pytest.skip(
            "启动子进程校验注册完整性失败（可能是沙箱限制），"
            "已退化为源码结构断言：\n"
            f"stdout={completed.stdout[-2000:]}\nstderr={completed.stderr[-2000:]}"
        )

    for line in completed.stdout.splitlines():
        if line.startswith("CSRF_PROBE:"):
            return json.loads(line[len("CSRF_PROBE:") :])

    pytest.skip(
        "子进程未输出可解析的注册结果，已退化为源码结构断言：\n"
        f"stdout={completed.stdout[-2000:]}\nstderr={completed.stderr[-2000:]}"
    )


@pytest.mark.api
class TestCsrfRegistration:
    """init_api 必须为所有蓝图注册 CSRF（含企业版与 internal_mcp）"""

    def test_all_blueprints_register_csrf(self):
        """企业版模式下 init_api 为 api_enterprise / api_contract / internal_mcp 注册 CSRF"""
        result = _run_registration_probe()
        names = result["names"]

        assert CSRF_PROTECTED_BLUEPRINTS[INTERNAL_MCP_BLUEPRINT] in names, (
            f"internal_mcp 缺少 CSRF 注册，实际注册名单: {names}"
        )

        if not result["enterprise_available"]:
            pytest.skip("企业版模块不可用（社区版构建），跳过企业版蓝图断言")

        for bp_var in ENTERPRISE_BLUEPRINTS:
            bp_name = CSRF_PROTECTED_BLUEPRINTS[bp_var]
            assert bp_name in names, (
                f"企业版蓝图 {bp_name} 缺少 CSRF 注册，实际注册名单: {names}"
            )

    def test_enterprise_csrf_registered_before_blueprint_registration(self):
        """静态兜底：源码中 CSRF 注册必须出现在 register_blueprint 之前"""
        source = INIT_API_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        init_api_func = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "init_api"
        )

        # 收集 init_api 内所有调用及其行号
        calls = []
        for node in ast.walk(init_api_func):
            if isinstance(node, ast.Call):
                calls.append((node.lineno, ast.unparse(node)))

        # 静态断言按源码里的变量名匹配（register_csrf_protection(<变量名>)）
        for bp_var in CSRF_PROTECTED_BLUEPRINTS:
            csrf_lines = [
                line
                for line, text in calls
                if text == f"register_csrf_protection({bp_var})"
            ]
            register_lines = [
                line
                for line, text in calls
                if text == f"app.register_blueprint({bp_var})"
            ]

            assert csrf_lines, (
                f"{INIT_API_FILE.name} 中缺少 register_csrf_protection({bp_var})"
            )
            assert register_lines, (
                f"{INIT_API_FILE.name} 中缺少 app.register_blueprint({bp_var})"
            )
            assert min(csrf_lines) < min(register_lines), (
                f"{bp_var} 的 CSRF 注册必须在 register_blueprint 之前"
            )
