# -*- coding: utf-8 -*-
"""
版本检测装饰器
用于保护企业版专用的 API 端点
"""
from functools import wraps
from quart import jsonify
from . import is_enterprise

def enterprise_only(f):
    """
    装饰器：仅允许企业版访问
    
    如果社区版访问被装饰的端点，将返回 403 错误
    
    Usage:
        @enterprise_only
        @api_enterprise_bp.route('/dashboard')
        async def dashboard():
            return jsonify({'data': 'enterprise data'})
    """
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if not is_enterprise():
            return jsonify({
                'error': '此功能仅在企业版中可用',
                'code': 403
            }), 403
        return await f(*args, **kwargs)
    return decorated_function

