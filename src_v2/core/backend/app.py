# -*- coding: utf-8 -*-

import os
from importlib import reload
from quart import Quart, send_from_directory, request, redirect, url_for, render_template
from quart_auth import QuartAuth, login_required, login_user, logout_user, current_user, AuthUser

from .api_asset import api_asset_bp
from .api_login import api_auth_bp

app = Quart(__name__)
app.secret_key = "生成一个安全的随机密钥"  # 在生产环境中应使用强随机密钥

app.register_blueprint(api_asset_bp)
app.register_blueprint(api_auth_bp)

# 静态文件路由
@app.route('/')
@app.route('/<path:path>')
async def serve_vue(path='index.html'):
    root_dir = os.path.join(os.path.dirname(__file__), '../frontend/dist')
    return await send_from_directory(root_dir, path)

async def init_backend():
    return await app.run_task(debug=True, port=9527)

