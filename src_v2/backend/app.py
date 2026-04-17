# -*- coding: utf-8 -*-

from pathlib import Path

from quart import Quart, request, send_from_directory
from quart_schema import QuartSchema
from quart_schema.openapi import HttpSecurityScheme, Info

from src_v2.core.config.config import config
from src_v2.core.log import logger

from .api import init_api

app = Quart(__name__)
app.secret_key = config["APP"]["SECRET_KEY"]

# 配置请求体大小限制（50MB），用于支持大型配置保存
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# 根据配置决定是否启用API文档
enable_api_docs = config.getboolean("APP", "ENABLE_API_DOCS", fallback=True)
api_docs_path = config.get("APP", "API_DOCS_PATH", fallback="/api/docs")
api_openapi_path = config.get("APP", "API_OPENAPI_PATH", fallback="/api/openapi.json")

if enable_api_docs:
    # 初始化 QuartSchema 并配置 OpenAPI 文档
    QuartSchema(
        app,
        openapi_path=api_openapi_path,
        swagger_ui_path=api_docs_path,
        info=Info(
            title="KahunaBot API",
            version="1.4.0",
            description="KahunaBot API 接口文档 - EVE Online 工业规划与资产管理系统",
        ),
        security_schemes={
            "Bearer": HttpSecurityScheme(scheme="bearer", bearer_format="JWT")
        },
    )
    logger.info(
        "API文档已启用: UI路径=%s, OpenAPI路径=%s", api_docs_path, api_openapi_path
    )
else:
    logger.info("API文档已禁用（通过配置文件控制）")


init_api(app)


def serve_vue():
    """注册前端静态文件路由（用于生产模式）"""
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

    # 静态资源路由（CSS、JS、图片等）
    @app.route("/assets/<path:filename>")
    async def serve_static_assets(filename):
        """提供静态资源文件"""
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            return await send_from_directory(str(assets_dir), filename)
        return {"error": "Not found"}, 404

    # 提供 favicon
    @app.route("/favicon.ico")
    async def serve_favicon():
        """提供 favicon"""
        if (frontend_dist / "favicon.ico").exists():
            return await send_from_directory(str(frontend_dist), "favicon.ico")
        return {"error": "Not found"}, 404

    # SPA 路由：所有非 API 路由都返回 index.html
    # 注意：这个路由应该最后注册，作为 catch-all 路由
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    async def serve_vue_app(path):
        """提供 Vue SPA 应用"""
        # 检查请求路径，确保不拦截 API 路由和静态资源
        request_path = request.path

        # 如果请求的是 API 路由，返回 404（应该由 API 蓝图处理，如果到这里说明路由未匹配）
        # 注意：文档路径 /api/docs 和 /api/openapi.json 应该由 QuartSchema 处理，
        # 如果到达这里说明路由未匹配，返回 404
        if request_path.startswith("/api/"):
            return {"error": "API route not found"}, 404

        # 检查是否是静态资源请求（应该由上面的路由处理）
        if request_path.startswith("/assets/") or request_path == "/favicon.ico":
            return {"error": "Static resource not found"}, 404

        # 对于所有其他路由，返回 index.html（SPA 路由支持）
        if frontend_dist.exists() and (frontend_dist / "index.html").exists():
            return await send_from_directory(str(frontend_dist), "index.html")
        return {
            "error": "Frontend not built. Please run: cd src_v2/frontend && npm run build"
        }, 404


def get_app():
    """获取Quart应用实例，供ASGI服务器使用"""
    return app


async def init_backend():
    """初始化后端（已废弃，请使用get_app()获取app实例，然后通过hypercorn启动）"""
    return app
