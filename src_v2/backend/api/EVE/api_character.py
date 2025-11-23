import datetime, jwt
import traceback

from quart import Quart, request, jsonify, g, Blueprint, redirect
from quart import current_app as app
from src_v2.backend.auth import auth_required, verify_token
from src_v2.core.database.connect_manager import redis_manager
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.core.user.user_manager import UserManager
from src_v2.core.log import logger

from src_v2.model.EVE.eveesi.oauth import get_auth_url, get_token
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.model.EVE.eveesi.eveesi import corporations_corporation_id

api_character_bp = Blueprint('api_character', __name__, url_prefix='/api/EVE/character')
