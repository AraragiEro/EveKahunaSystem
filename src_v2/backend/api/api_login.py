import datetime, jwt
import traceback

from quart import Quart, request, jsonify, g, Blueprint
from quart import current_app as app
from src_v2.backend.auth import auth_required
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.core.user.user_manager import UserManager
from src.service.log_server import logger
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.utils import KahunaException

# app = Quart(__name__)
# app.config['SECRET_KEY'] = 'your-secret-key-here'
# QuartSchema(app)

api_auth_bp = Blueprint('api_auth', __name__, url_prefix='/api/auth')

# 用户数据库模拟（实际应用中应使用真实数据库）
# users_db = {
#     'admin': {
#         'password_hash': generate_password_hash('admin123'),
#         'role': 'admin',
#         'email': 'admin@example.com'
#     }
# }

INVITE_CODE = '123456'

@api_auth_bp.route('/signup', methods=['POST'])
async def signup():
    try:
        data = await request.get_json()
        username = data.get('username')
        logger.debug(f"username: {username}")
        password = data.get('password')
        logger.debug(f"password: {password}")
        invite_code = data.get('inviteCode')
        logger.debug(f"invite_code: {invite_code}")

        if invite_code != INVITE_CODE:
            return jsonify({"status": 400, "message": "邀请码错误"}), 400

        pass_hash = generate_password_hash(password)
        user = await UserManager().create_user(user_name=username, passwd_hash=pass_hash)

        return jsonify({"status": 200, "message": "注册成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"注册失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "注册失败"}), 500

def create_token(user_id: str, role: str):
    """创建JWT token"""
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

@api_auth_bp.route('/login', methods=['POST'])
async def login():
    """用户登录"""
    try:
        data = await request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({"status": 400, "message": "用户名和密码不能为空"}), 400
        
        passwd_hash = await UserManager().get_password_hash(username)
        if check_password_hash(passwd_hash, password) is False:
            return jsonify({"status": 401, "message": "用户名或密码错误"}), 401

        user = await UserManager().get_user(username)
        if not user:
            raise KeyError
        token = create_token(username, ",".join(await user.roles))

        return jsonify({
            "status": 200,
            "token": token,
            "user": {
                "id": username,
                "username": username,
                "roles": await user.roles
            }
        })
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"登录失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "登录失败，请联系管理员"}), 500

@api_auth_bp.route('/me', methods=['GET'])
@auth_required
async def get_current_user():
    """获取当前用户信息"""
    try:
        user_id = g.current_user['user_id']
        user = await UserManager().get_user(user_id)
        if not user:
            return jsonify({"status": 404, "message": "用户不存在"}), 404

        return jsonify({
            "status": 200,
            "id": user.user_name,
            "username": user.user_name,
            "roles": await user.roles,
        })
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取当前用户信息失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取当前用户信息失败"}), 500

@api_auth_bp.route('/logout', methods=['POST'])
@auth_required
async def logout():
    """用户登出"""
    try:
        # 在实际应用中，可以将token加入黑名单
        return jsonify({"status": 200, "message": "登出成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"登出失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "登出失败"}), 500


@api_auth_bp.route('/deleteAccount', methods=['POST'])
@auth_required
async def delete_account():
    """注销账号"""
    try:
        user_id = g.current_user["user_id"]
        main_character_id = await UserManager().get_main_character_id(user_id)
        # 删除用户所有角色相关数据
        
        # 删除用户角色数据
        await CharacterManager().delete_all_alias_characters_of_main_character(main_character_id)
        await CharacterManager().delete_all_character_of_user(user_id)

        # 删除用户数据
        await UserManager().delete_user(user_id)

        return jsonify({"status": 200, "message": "注销成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"注销账号失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "注销账号失败"}), 500