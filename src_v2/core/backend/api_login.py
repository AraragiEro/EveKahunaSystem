import datetime, jwt
import traceback

from quart import Quart, request, jsonify, g, Blueprint
from quart import current_app as app
from .auth import auth_required
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.core.user.user_manager import UserManager
from src.service.log_server import logger

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
    data = await request.get_json()
    username = data.get('username')
    logger.debug(f"username: {username}")
    password = data.get('password')
    logger.debug(f"password: {password}")
    invite_code = data.get('inviteCode')
    logger.debug(f"invite_code: {invite_code}")

    if invite_code != INVITE_CODE:
        return jsonify({'error': '邀请码错误'}), 400

    pass_hash = generate_password_hash(password)
    try:
        user = await UserManager().create_user(user_name=username, passwd_hash=pass_hash)

        return jsonify({})
    except Exception as e:
        return jsonify({"error": "注册失败"}), 401

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
    data = await request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    # user = users_db.get(username)
    try:
        passwd_hash = await UserManager().get_password_hash(username)
        if check_password_hash(passwd_hash, password) is False:
            return jsonify({'error': '用户名或密码错误'}), 401

        user = await UserManager().get_user(username)
        if not user:
            raise KeyError
        token = create_token(username, user.user_role)

        return jsonify({
            'token': token,
            'user': {
                'id': username,
                'username': username,
                'role': user.user_role,
                'permission': user.user_permission
            }
        })
    except Exception as e:
        logger.debug(traceback.format_exc(e))
        return jsonify({'error': '登录失败，请联系管理员'}), 401

@api_auth_bp.route('/me', methods=['GET'])
@auth_required
async def get_current_user():
    """获取当前用户信息"""
    user_id = g.current_user['user_id']
    user = await UserManager().get_user(user_id)
    
    return jsonify({
        'id': user_id,
        'username': user_id,
        'role': user.user_role,
        'permission': user.user_permission
    })

@api_auth_bp.route('/logout', methods=['POST'])
@auth_required
async def logout():
    """用户登出"""
    # 在实际应用中，可以将token加入黑名单
    return jsonify({'message': '登出成功'})


