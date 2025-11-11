def init_api(app):
    from .EVE.api_asset import api_EVE_asset_bp
    from .api_login import api_auth_bp
    from .api_EVE import api_EVE_bp
    from .EVE.api_character import api_character_bp
    from .api_user import api_user_bp
    from .api_permission import api_permission_bp
    from .EVE.api_industry import api_industry_bp

    app.register_blueprint(api_EVE_asset_bp)
    app.register_blueprint(api_auth_bp)
    app.register_blueprint(api_EVE_bp)
    app.register_blueprint(api_character_bp)
    app.register_blueprint(api_user_bp)
    app.register_blueprint(api_permission_bp)
    app.register_blueprint(api_industry_bp)