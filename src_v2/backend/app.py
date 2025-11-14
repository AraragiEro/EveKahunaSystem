# -*- coding: utf-8 -*-

import os
from quart import Quart, send_from_directory

app = Quart(__name__)
app.secret_key = "生成一个安全的随机密钥"  # 在生产环境中应使用强随机密钥

from .api import init_api

init_api(app)

# 静态文件路由
@app.route('/')
@app.route('/<path:path>')
async def serve_vue(path='index.html'):
    root_dir = os.path.join(os.path.dirname(__file__), '../frontend/dist')
    return await send_from_directory(root_dir, path)

async def init_server():
    """初始化服务器"""
    from src_v2.core.database.connect_manager import postgres_manager, redis_manager, neo4j_manager

    await postgres_manager.init()
    await redis_manager.init()
    await neo4j_manager.init()

def get_app():
    """获取Quart应用实例，供ASGI服务器使用"""
    return app

async def init_backend():
    """初始化后端（已废弃，请使用get_app()获取app实例，然后通过hypercorn启动）"""
    return app

