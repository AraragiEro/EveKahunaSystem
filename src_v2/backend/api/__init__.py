def init_api(app):
    from src_v2.backend.auth import register_csrf_protection, register_service_auth
    from src_v2.core.log import logger

    from .EVE.api_asset import api_EVE_asset_bp
    from .api_login import api_auth_bp
    from .api_EVE import api_EVE_bp
    from .EVE.api_character import api_character_bp
    from .api_user import api_user_bp
    from .api_permission import api_permission_bp
    from .api_invite_code import api_invite_code_bp
    from .api_vip import api_vip_bp
    from .EVE.api_industry import api_industry_bp
    from .api_public import api_public_bp
    from .api_statistics import api_statistics_bp
    from .api_message_board import api_message_board_bp
    from .EVE.api_home import api_home_bp
    from .EVE.api_price_estimator import api_price_estimator_bp
    from .EVE.api_pi import api_pi_bp
    from .EVE.api_lp import api_lp_bp
    from .api_astrbot import api_astrbot_bp
    from .api_admin_system import api_admin_system_bp
    from .api_admin_esi import api_admin_esi_bp

    register_csrf_protection(api_EVE_asset_bp)
    app.register_blueprint(api_EVE_asset_bp)
    register_csrf_protection(api_auth_bp)
    app.register_blueprint(api_auth_bp)
    register_csrf_protection(api_EVE_bp)
    app.register_blueprint(api_EVE_bp)
    register_csrf_protection(api_character_bp)
    app.register_blueprint(api_character_bp)
    register_csrf_protection(api_user_bp)
    app.register_blueprint(api_user_bp)
    register_csrf_protection(api_permission_bp)
    app.register_blueprint(api_permission_bp)
    register_csrf_protection(api_invite_code_bp)
    app.register_blueprint(api_invite_code_bp)
    register_csrf_protection(api_vip_bp)
    app.register_blueprint(api_vip_bp)
    register_csrf_protection(api_industry_bp)
    app.register_blueprint(api_industry_bp)
    register_csrf_protection(api_public_bp)
    app.register_blueprint(api_public_bp)
    register_csrf_protection(api_statistics_bp)
    app.register_blueprint(api_statistics_bp)
    register_csrf_protection(api_message_board_bp)
    app.register_blueprint(api_message_board_bp)
    register_csrf_protection(api_home_bp)
    app.register_blueprint(api_home_bp)
    register_csrf_protection(api_price_estimator_bp)
    app.register_blueprint(api_price_estimator_bp)
    register_csrf_protection(api_pi_bp)
    app.register_blueprint(api_pi_bp)
    register_csrf_protection(api_lp_bp)
    app.register_blueprint(api_lp_bp)
    register_csrf_protection(api_astrbot_bp)
    # 服务间认证：调用方是 QQ 机器人容器，无法交互式登录，改用共享服务密钥
    register_service_auth(api_astrbot_bp, "api_astrbot")
    app.register_blueprint(api_astrbot_bp)
    register_csrf_protection(api_admin_system_bp)
    app.register_blueprint(api_admin_system_bp)
    register_csrf_protection(api_admin_esi_bp)
    app.register_blueprint(api_admin_esi_bp)

    # 注册内部 MCP API 路由
    try:
        from .internal_mcp import internal_mcp_bp

        # 服务间认证：调用方是 MCP 中间件（X-Internal-API-Key）
        register_service_auth(internal_mcp_bp, "internal_mcp")
        # 防御纵深：本蓝图走服务密钥认证、调用方不带 auth_token cookie，
        # register_csrf_protection 对无 auth_token cookie 的请求自动放行，
        # 因此不会影响服务间调用，只是补齐与其他蓝图一致的纵深。
        register_csrf_protection(internal_mcp_bp)
        app.register_blueprint(internal_mcp_bp)
        logger.info("内部 MCP API 路由已注册")
    except Exception as e:
        logger.warning(f"内部 MCP API 路由注册失败: {e}")

    # 条件注册企业版 API
    # 仅在版本为企业版且模块存在时注册
    from src_v2.core.edition import is_enterprise

    if is_enterprise():
        try:
            from src_v2.enterprise.api.api_enterprise import api_enterprise_bp

            # 防御纵深：企业版蓝图与社区版蓝图保持一致的 CSRF 保护
            register_csrf_protection(api_enterprise_bp)
            app.register_blueprint(api_enterprise_bp)
            from src_v2.enterprise.api.api_contract import api_contract_bp

            register_csrf_protection(api_contract_bp)
            app.register_blueprint(api_contract_bp)
            # Load astrbot service to trigger _astrbot_* registration.
            from src_v2.enterprise.api import api_astrbot_service  # noqa: F401

            logger.info("企业版 API 已注册")

        except ImportError as e:
            logger.warning(f"企业版 API 模块不存在，跳过注册: {e}")
        except Exception as e:
            logger.error(f"注册企业版 API 时发生错误: {e}")
