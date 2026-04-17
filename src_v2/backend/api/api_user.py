import traceback
import uuid
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from quart import Quart, request, jsonify, g, Blueprint, redirect

from src_v2.backend.auth import auth_required
from src_v2.core.log import logger
from src_v2.core.database.connect_manager import get_redis_manager as rdm

from src_v2.core.user.user_manager import UserManager
from src_v2.model.EVE.character.character import Character
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.database.kahuna_database_utils_v2 import (
    EvePublicCharacterInfoDBUtils,
    EveAuthedCharacterDBUtils,
    UserQQBindingDBUtils,
)
from src_v2.core.database.model import EveAliasCharacter as M_EveAliasCharacter
from src_v2.core.database.kahuna_database_utils_v2 import EveAliasCharacterDBUtils
from src_v2.model.EVE.eveesi import eveesi
from src_v2.core.utils import KahunaException

api_user_bp = Blueprint('api_user', __name__, url_prefix='/api/user')


# 请求数据模型
@dataclass
class DeleteCharacterRequest:
    """删除角色请求"""
    characterName: str


@dataclass
class SetMainCharacterRequest:
    """设置主角色请求"""
    characterName: str


@dataclass
class SearchCharacterRequest:
    """搜索角色请求"""
    inputType: str  # 'characterId' or 'characterName'
    inputValue: str


@dataclass
class AddAliasCharactersRequest:
    """添加别名角色请求"""
    characterIds: List[int]


@dataclass
class AliasCharacterItem:
    """别名角色项"""
    CharacterId: int
    Enabled: bool


@dataclass
class SaveAliasCharactersRequest:
    """保存别名角色请求"""
    aliasCharacterList: List[AliasCharacterItem]


# 响应数据模型
@dataclass
class CharacterItem:
    """角色项"""
    name: str
    expiresDate: Optional[str] = None
    corpId: Optional[int] = None
    corpName: Optional[str] = None


@dataclass
class CharacterListResponse:
    """角色列表响应"""
    status: int
    data: List[CharacterItem]


@dataclass
class MessageResponse:
    """消息响应"""
    status: int
    message: str


@dataclass
class MainCharacterResponse:
    """主角色响应"""
    status: int
    mainCharacter: str
    director: bool


@dataclass
class SetMainCharacterResponse:
    """设置主角色响应"""
    status: int
    message: str
    director: bool


@dataclass
class AliasCharacterSettingAvailableResponse:
    """别名角色设置可用性响应"""
    status: int
    isAliasCharacterSettingAvaliable: bool


@dataclass
class AliasCharacterItemResponse:
    """别名角色项响应"""
    CharacterId: int
    CharacterName: str
    Enabled: bool


@dataclass
class AliasCharacterListResponse:
    """别名角色列表响应"""
    status: int
    data: List[AliasCharacterItemResponse]


@dataclass
class SearchCharacterItem:
    """搜索角色项"""
    CharacterId: int
    CharacterName: str


@dataclass
class SearchCharacterResponse:
    """搜索角色响应"""
    status: int
    data: List[SearchCharacterItem]


@dataclass
class AddAliasCharactersResponse:
    """添加别名角色响应"""
    status: int
    message: str
    failedList: List[str]
    aliasCharacterList: List[AliasCharacterItemResponse]


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


QQ_BIND_REDIS_PREFIX = "kahunasystem:qq_bind"


def _build_qq_bind_key(bind_uuid: str) -> str:
    return f"{QQ_BIND_REDIS_PREFIX}:{bind_uuid}"


@api_user_bp.route("/qqBinding", methods=["GET"])
@auth_required
async def get_qq_binding():
    """获取当前用户 QQ 绑定"""
    user_id = g.current_user["user_id"]
    try:
        binding = await UserQQBindingDBUtils.select_by_user_name(user_id)
        user_qq = int(binding.user_qq) if binding else None
        return {"status": 200, "userQQ": user_qq}
    except Exception:
        traceback.print_exc()
        logger.error(f"获取 QQ 绑定失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取 QQ 绑定失败"}), 500


@api_user_bp.route("/qqBinding/create", methods=["POST"])
@auth_required
async def create_qq_binding():
    """创建 QQ 绑定指令"""
    user_id = g.current_user["user_id"]
    try:
        bind_uuid = uuid.uuid4().hex
        redis_key = _build_qq_bind_key(bind_uuid)
        await rdm().redis.set(redis_key, user_id)
        await rdm().redis.expire(redis_key, 300)
        instruction = f".绑定kahunasystem {bind_uuid}"
        return {
            "status": 200,
            "uuid": bind_uuid,
            "instruction": instruction,
            "expireSeconds": 300
        }
    except Exception:
        traceback.print_exc()
        logger.error(f"创建 QQ 绑定指令失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建 QQ 绑定指令失败"}), 500


@api_user_bp.route("/qqBinding/unbind", methods=["POST"])
@auth_required
async def unbind_qq():
    """解绑 QQ"""
    user_id = g.current_user["user_id"]
    try:
        await UserQQBindingDBUtils.delete_by_user_name(user_id)
        return {"status": 200, "message": "QQ 解绑成功"}
    except Exception:
        traceback.print_exc()
        logger.error(f"QQ 解绑失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "QQ 解绑失败"}), 500


@api_user_bp.route("/list", methods=["GET"])
@auth_required
# @validate_response(CharacterListResponse)
async def get_character_list():
    """
    获取角色列表
    
    获取当前用户的所有EVE角色列表，包括角色名称、过期时间、公司ID和公司名称。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回角色列表
            - status: 状态码 (200)
            - data: 角色列表，每个元素包含角色名称、过期时间、公司ID和公司名称 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "name": "Character Name",
                    "expiresDate": "2024-12-31T23:59:59",
                    "corpId": 123456,
                    "corpName": "Corporation Name"
                }
            ]
        }
    """
    try:
        character_list = await CharacterManager().get_user_all_characters(g.current_user["user_id"])

        character_list_dict = []
        for character in character_list:
            corp_data = await CharacterManager().get_corporation_data_by_corporation_id(character.corporation_id)
            if not corp_data:
                continue
            character_list_dict.append({
                "name": character.character_name,
                "characterId": character.character_id,
                "expiresDate": character.expires_time,
                "corpId": character.corporation_id,
                "corpName": corp_data.name
            })
        return {"status": 200, "data": character_list_dict}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取角色列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取角色列表失败"}), 500

@api_user_bp.route("/deleteCharacter", methods=["POST"])
@auth_required
# @validate_request(DeleteCharacterRequest)
# @validate_response(MessageResponse)
async def delete_character():
    """
    删除角色
    
    删除指定的EVE角色。只能删除当前用户自己的角色。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Request Body:
        - characterName (string, required): 要删除的角色名称

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "characterName": "Character Name"
        }

    Example Response:
        {
            "status": 200,
            "message": "角色删除成功"
        }
    """
    try:
        data = await request.get_json()
        character_name = data.get("characterName")
        await CharacterManager().delete_character_by_character_name(character_name, g.current_user["user_id"])
        return {"status": 200, "message": "角色删除成功"}
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除角色失败"}), 500

@api_user_bp.route("/getMainCharacter", methods=["GET"])
@auth_required
# @validate_response(MainCharacterResponse)
async def get_main_character():
    """
    获取主角色
    
    获取当前用户的主角色信息，包括角色名称和是否为总监。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回主角色信息
            - status: 状态码 (200)
            - mainCharacter: 主角色名称 (string)
            - director: 是否为总监 (boolean)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "mainCharacter": "Character Name",
            "director": true
        }
    """
    try:
        user_id = g.current_user["user_id"]
        main_character_id = await UserManager().get_main_character_id(user_id)
        main_character = await CharacterManager().get_character_by_character_id(main_character_id)
        if main_character.director:
            director = True
        else:
            director = False
        return {"status": 200, "mainCharacter": main_character.character_name, "director": director}
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取主角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取主角色失败"}), 500

@api_user_bp.route("/setMainCharacter", methods=["POST"])
@auth_required
# @validate_request(SetMainCharacterRequest)
# @validate_response(SetMainCharacterResponse)
async def set_main_character():
    """
    设置主角色
    
    设置当前用户的主角色。设置后会自动刷新角色token并检查是否为总监。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Request Body:
        - characterName (string, required): 要设置为主角色的角色名称

    Responses:
        200: 设置成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
            - director: 是否为总监 (boolean)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "characterName": "Character Name"
        }

    Example Response:
        {
            "status": 200,
            "message": "主角色设置成功",
            "director": true
        }
    """
    user_id = g.current_user["user_id"]
    data = await request.get_json()
    character_name = data.get("characterName")
    try:
        await UserManager().set_main_character(user_id, character_name)
        character_obj = await EveAuthedCharacterDBUtils.select_character_by_character_name(character_name)
        character = Character.from_db_obj(character_obj)
        await character.refresh_character_token()
        if character.director:
            director = True
        else:
            director = False
        return {"status": 200, "message": "主角色设置成功", "director": director}
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"设置主角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "设置主角色失败"}), 500

@api_user_bp.route('/isAliasCharacterSettingAvaliable', methods=['GET'])
@auth_required
# @validate_response(AliasCharacterSettingAvailableResponse)
async def is_alias_character_setting_avaliable():
    """
    检查别名角色设置可用性
    
    检查当前用户所在公司是否有绑定总监权限账号，以确定是否可以设置别名角色。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回可用性
            - status: 状态码 (200)
            - isAliasCharacterSettingAvaliable: 是否可用 (boolean)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "isAliasCharacterSettingAvaliable": true
        }
    """
    user_id = g.current_user["user_id"]
    try:
        # 获取用户主账号
        main_character_id = await UserManager().get_main_character_id(user_id)
        main_character = await CharacterManager().get_character_by_character_id(main_character_id)

        # 判断用户所在公司是否有绑定总监权限账号
        director_character_id = await CharacterManager().get_director_character_id_of_corporation(main_character.corporation_id)
        if not director_character_id:
            return {"status": 200, "isAliasCharacterSettingAvaliable": False}
        
        # 否则返回false
        # 有则返回true

        return {"status": 200, "isAliasCharacterSettingAvaliable": True}
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"检查别名角色设置可用性失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "检查别名角色设置可用性失败"}), 500

@api_user_bp.route('/getSameTitleAliasCharacterList', methods=['POST'])
@auth_required
# @validate_response(AliasCharacterListResponse)
async def get_same_title_alias_character_list():
    """
    获取同title别名角色列表
    
    刷新并获取与主角色同title的别名角色列表。会先刷新公司内所有公开角色信息，然后更新同title别名角色。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回别名角色列表
            - status: 状态码 (200)
            - data: 别名角色列表，每个元素包含角色ID、角色名称和启用状态 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "CharacterId": 123456,
                    "CharacterName": "Character Name",
                    "Enabled": false
                }
            ]
        }
    """
    user_id = g.current_user["user_id"]
    try:
        main_character_id = await UserManager().get_main_character_id(user_id)
        main_character = await CharacterManager().get_character_by_character_id(main_character_id)
        await CharacterManager().refresh_all_public_characters_info_of_corporation(main_character.ac_token, main_character.corporation_id)

        same_title_character_list = []
        async for character in await EvePublicCharacterInfoDBUtils.select_character_info_by_characterid_with_same_title(main_character_id):
            same_title_character_list.append(character)
        await UserManager().update_same_title_alias_characters(same_title_character_list, main_character_id)
        alias_character_list = await UserManager().get_alias_character_list(main_character_id)
            
        return jsonify({
            "status": 200,
            "data": [{
                "CharacterId": alias_character.alias_character_id,
                "CharacterName": alias_character.character_name,
                "Enabled": alias_character.enabled
            } for alias_character in alias_character_list]
        })
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取同title别名角色列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取同title别名角色列表失败"}), 500

@api_user_bp.route('/getAliasCharacterList', methods=['GET'])
@auth_required
# @validate_response(AliasCharacterListResponse)
async def get_alias_character_list():
    """
    获取别名角色列表
    
    获取当前用户主角色的所有别名角色列表。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回别名角色列表
            - status: 状态码 (200)
            - data: 别名角色列表，每个元素包含角色ID、角色名称和启用状态 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "CharacterId": 123456,
                    "CharacterName": "Character Name",
                    "Enabled": true
                }
            ]
        }
    """
    user_id = g.current_user["user_id"]
    main_character_id = await UserManager().get_main_character_id(user_id)
    try:
        alias_character_list = await UserManager().get_alias_character_list(main_character_id)
        return jsonify({
            "status": 200,
            "data": [{
                "CharacterId": alias_character.alias_character_id,
                "CharacterName": alias_character.character_name,
                "Enabled": alias_character.enabled
            } for alias_character in alias_character_list]
        })
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取别名角色列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取别名角色列表失败"}), 500

@api_user_bp.route('/searchCharacter', methods=['POST'])
@auth_required
# @validate_request(SearchCharacterRequest)
# @validate_response(SearchCharacterResponse)
async def search_character():
    """
    搜索角色（通过角色ID或角色名称）
    
    根据角色ID或角色名称搜索EVE角色。支持通过角色ID精确搜索或通过角色名称模糊搜索。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Request Body:
        - inputType (string, required): 搜索类型，可选值: characterId, characterName
        - inputValue (string, required): 搜索值，角色ID（数字）或角色名称

    Responses:
        200: 成功返回搜索结果
            - status: 状态码 (200)
            - data: 搜索结果列表，每个元素包含角色ID和角色名称 (array)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "inputType": "characterName",
            "inputValue": "Character"
        }

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "CharacterId": 123456,
                    "CharacterName": "Character Name"
                }
            ]
        }
    """
    try:
        user_id = g.current_user["user_id"]
        data = await request.get_json()
        input_type = data.get("inputType")  # 'characterId' or 'characterName'
        input_value = data.get("inputValue", "").strip()
        
        if not input_value:
            return jsonify({"status": 400, "message": "请输入搜索值"}), 400
        
        from src_v2.model.EVE.eveesi.esi_api.character import characters_character
        from src_v2.core.database.kahuna_database_utils_v2 import EvePublicCharacterInfoDBUtils
        
        result = []
        
        if input_type == 'characterId':
            # 如果是数字，尝试作为character_id查询
            try:
                character_id = int(input_value)
                character_info = await characters_character(character_id)
                if character_info:
                    result.append({
                        "CharacterId": character_info.get("character_id", character_id),
                        "CharacterName": character_info.get("name", "")
                    })
            except ValueError:
                return jsonify({"status": 400, "message": "角色ID必须是数字"}), 400
            except KahunaException as e:
                traceback.print_exc()
                return jsonify({"status": 500, "message": str(e)}), 500
            except Exception as e:
                traceback.print_exc()
                logger.error(f"搜索角色失败: {traceback.format_exc()}")
                return jsonify({"status": 500, "message": "搜索角色失败"}), 500
        else:  # characterName
            try:
                main_character_id = await UserManager().get_main_character_id(user_id)
                main_character = await CharacterManager().get_character_by_character_id(main_character_id)
                search_result = await eveesi.search(main_character.ac_token, main_character.character_id, ["character"], input_value)
                if search_result:
                    character_id_list = search_result.get("character", [])
                    for character_id in character_id_list:
                        character_info = await characters_character(character_id)
                        if character_info:
                            result.append({
                                "CharacterId": character_info.get("character_id", character_id),
                                "CharacterName": character_info.get("name", "")
                            })
            except KahunaException as e:
                traceback.print_exc()
                return jsonify({"status": 500, "message": str(e)}), 500
            except Exception as e:
                traceback.print_exc()
                logger.error(f"搜索角色失败: {traceback.format_exc()}")
                return jsonify({"status": 500, "message": "搜索角色失败"}), 500
        
        return {"status": 200, "data": result}
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"搜索角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "搜索角色失败"}), 500

@api_user_bp.route('/addAliasCharacters', methods=['POST'])
@auth_required
# @validate_request(AddAliasCharactersRequest)
# @validate_response(AddAliasCharactersResponse)
async def add_alias_characters():
    """
    添加选中的别名角色
    
    批量添加别名角色。如果角色已存在则跳过，添加失败的角色会记录在failedList中。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Request Body:
        - characterIds (array, required): 角色ID列表

    Responses:
        200: 添加完成
            - status: 状态码 (200)
            - message: 成功消息，包含添加成功的数量 (string)
            - failedList: 添加失败的角色ID列表 (array)
            - aliasCharacterList: 更新后的别名角色列表 (array)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "characterIds": [123456, 789012]
        }

    Example Response:
        {
            "status": 200,
            "message": "成功添加 2 个角色",
            "failedList": [],
            "aliasCharacterList": [
                {
                    "CharacterId": 123456,
                    "CharacterName": "Character Name",
                    "Enabled": false
                }
            ]
        }
    """
    try:
        user_id = g.current_user["user_id"]
        data = await request.get_json()
        character_ids = data.get("characterIds", [])  # 角色ID列表
        
        if not character_ids:
            return jsonify({"status": 400, "message": "请至少选择一个角色"}), 400
        
        main_character_id = await UserManager().get_main_character_id(user_id)
        
        from src_v2.model.EVE.eveesi.esi_api.character import characters_character
        from src_v2.core.database.kahuna_database_utils_v2 import EveAliasCharacterDBUtils
        from src_v2.core.database.model import EveAliasCharacter as M_EveAliasCharacter
        
        added_count = 0
        failed_list = []
        
        for character_id in character_ids:
            try:
                # 检查是否已存在
                existing = await EveAliasCharacterDBUtils.select_alias_character_by_character_id(character_id)
                if existing:
                    continue  # 已存在，跳过
                
                # 获取角色信息
                character_info = await characters_character(character_id)
                if not character_info:
                    failed_list.append(str(character_id))
                    continue
                
                # 添加别名角色
                await EveAliasCharacterDBUtils.save_obj(M_EveAliasCharacter(
                    alias_character_id=character_id,
                    main_character_id=main_character_id,
                    character_name=character_info.get("name", ""),
                    enabled=False
                ))
                added_count += 1
            except KahunaException as e:
                traceback.print_exc()
                logger.error(f"添加角色 {character_id} 失败: {str(e)}")
                failed_list.append(str(character_id))
            except Exception as e:
                traceback.print_exc()
                logger.error(f"添加角色 {character_id} 失败: {traceback.format_exc()}")
                failed_list.append(str(character_id))
        
        # 刷新别名角色列表
        alias_character_list = await UserManager().get_alias_character_list(main_character_id)
        
        return jsonify({
            "status": 200,
            "message": f"成功添加 {added_count} 个角色",
            "failedList": failed_list,
            "aliasCharacterList": [{
                "CharacterId": alias_character.alias_character_id,
                "CharacterName": alias_character.character_name,
                "Enabled": alias_character.enabled
            } for alias_character in alias_character_list]
        })
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"添加别名角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加别名角色失败"}), 500

@api_user_bp.route('/saveAliasCharacters', methods=['POST'])
@auth_required
# @validate_request(SaveAliasCharactersRequest)
# @validate_response(MessageResponse)
async def save_alias_characters():
    """
    保存别名角色
    
    批量保存别名角色的启用状态。

    Tags:
        - 用户角色管理

    Security:
        - Bearer: []

    Request Body:
        - aliasCharacterList (array, required): 别名角色列表，每个元素包含CharacterId和Enabled

    Responses:
        200: 保存成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "aliasCharacterList": [
                {
                    "CharacterId": 123456,
                    "Enabled": true
                }
            ]
        }

    Example Response:
        {
            "status": 200,
            "message": "保存成功"
        }
    """
    try:
        data = await request.get_json()
        aliasCharacterList = data.get("aliasCharacterList", [])
        for alias_character in aliasCharacterList:
            alias_character_obj = await EveAliasCharacterDBUtils.select_alias_character_by_character_id(alias_character["CharacterId"])
            if not alias_character:
                continue
            alias_character_obj.enabled = alias_character["Enabled"]
            await EveAliasCharacterDBUtils.save_obj(alias_character_obj)
        return {"status": 200, "message": "保存成功"}
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存别名角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存别名角色失败"}), 500
