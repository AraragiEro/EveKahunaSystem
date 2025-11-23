def init_api(app):
    from .EVE.api_asset import api_EVE_asset_bp
    from .api_login import api_auth_bp
    from .api_EVE import api_EVE_bp
    from .EVE.api_character import api_character_bp
    from .api_user import api_user_bp
    from .api_permission import api_permission_bp
    from .api_invite_code import api_invite_code_bp
    from .api_vip import api_vip_bp
    from .EVE.api_industry import api_industry_bp

    app.register_blueprint(api_EVE_asset_bp)
    app.register_blueprint(api_auth_bp)
    app.register_blueprint(api_EVE_bp)
    app.register_blueprint(api_character_bp)
    app.register_blueprint(api_user_bp)
    app.register_blueprint(api_permission_bp)
    app.register_blueprint(api_invite_code_bp)
    app.register_blueprint(api_vip_bp)
    app.register_blueprint(api_industry_bp)

    # 条件注册企业版 API
    # 仅在版本为企业版且模块存在时注册
    from src_v2.core.edition import is_enterprise
    from src_v2.core.log import logger
    
    if is_enterprise():
        try:
            from src_v2.enterprise.api.api_enterprise import api_enterprise_bp
            app.register_blueprint(api_enterprise_bp)
            logger.info("企业版 API 已注册")
        except ImportError as e:
            logger.warning(f"企业版 API 模块不存在，跳过注册: {e}")
        except Exception as e:
            logger.error(f"注册企业版 API 时发生错误: {e}")