import datetime
import jwt
from functools import wraps
from flask import request, jsonify, g
from quart import current_app as app

def verify_token(token: str):
    """验证JWT token"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def auth_required(f):
    """认证装饰器"""

    @wraps(f)
    async def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token or not token.startswith('Bearer '):
            return jsonify({'error': '缺少认证token'}), 401

        token = token.split(' ')[1]
        payload = verify_token(token)

        if not payload:
            return jsonify({'error': '无效的token'}), 401

        g.current_user = payload
        return await f(*args, **kwargs)

    return decorated_function
