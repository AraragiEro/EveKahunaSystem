from quart import jsonify


def ok(data=None, message=None, **kwargs):
    """成功响应

    Args:
        data: 响应数据
        message: 可选消息
        **kwargs: 额外字段

    Returns:
        Quart Response
    """
    resp = {"status": 200}
    if data is not None:
        resp["data"] = data
    if message is not None:
        resp["message"] = message
    resp.update(kwargs)
    return jsonify(resp)


def fail(message, status_code=500, code=None):
    """失败/错误响应

    Args:
        message: 错误信息
        status_code: HTTP 状态码，默认 500
        code: 可选的业务错误码

    Returns:
        (Response, status_code)
    """
    resp = {"status": status_code, "message": message}
    if code is not None:
        resp["code"] = code
    return jsonify(resp), status_code


def bad_request(message):
    """400 参数错误"""
    return fail(message, 400)


def unauthorized(message="未登录或 token 无效"):
    """401 未认证"""
    return fail(message, 401)


def forbidden(message="权限不足"):
    """403 无权限

    诊断留痕：403 不是异常，默认不会写进任何日志（且 hypercorn 未开 accesslog），
    线上排查"概率性 403"时这一行是唯一的后端痕迹。只记路径与原因文案。
    """
    try:
        from quart import request as _request
        from src_v2.core.log import logger
        logger.warning(f"[403] path={_request.path} message={message}")
    except Exception:
        pass
    return fail(message, 403)


def not_found(message="资源不存在"):
    """404 资源不存在"""
    return fail(message, 404)


def server_error(message="服务器内部错误"):
    """500 服务器错误"""
    return fail(message, 500)
