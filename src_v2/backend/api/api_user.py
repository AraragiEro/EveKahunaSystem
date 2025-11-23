from quart import Quart, request, jsonify, g, Blueprint, redirect
from src_v2.backend.auth import auth_required
from src_v2.core.log import logger
import traceback

from src_v2.core.user.user_manager import UserManager
from src_v2.model.EVE.character.character import Character
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.database.kahuna_database_utils_v2 import EvePublicCharacterInfoDBUtils, EveAuthedCharacterDBUtils
from src_v2.core.database.model import EveAliasCharacter as M_EveAliasCharacter
from src_v2.core.database.kahuna_database_utils_v2 import EveAliasCharacterDBUtils
from src_v2.model.EVE.eveesi import eveesi
from src_v2.core.utils import KahunaException

api_user_bp = Blueprint('api_user', __name__, url_prefix='/api/user')


@api_user_bp.route("/list", methods=["GET"])
@auth_required
async def get_character_list():
    try:
        character_list = await CharacterManager().get_user_all_characters(g.current_user["user_id"])

        character_list_dict = []
        for character in character_list:
            corp_data = await CharacterManager().get_corporation_data_by_corporation_id(character.corporation_id)
            if not corp_data:
                continue
            character_list_dict.append({
                "name": character.character_name,
                "expiresDate": character.expires_time,
                "corpId": character.corporation_id,
                "corpName": corp_data.name
            })
        return jsonify({"status": 200, "data": character_list_dict})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取角色列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取角色列表失败"}), 500

@api_user_bp.route("/deleteCharacter", methods=["POST"])
@auth_required
async def delete_character():
    try:
        data = await request.get_json()
        character_name = data.get("characterName")
        await CharacterManager().delete_character_by_character_name(character_name, g.current_user["user_id"])
        return jsonify({"status": 200, "message": "角色删除成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"删除角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除角色失败"}), 500

@api_user_bp.route("/getMainCharacter", methods=["GET"])
@auth_required
async def get_main_character():
    try:
        user_id = g.current_user["user_id"]
        main_character_id = await UserManager().get_main_character_id(user_id)
        main_character = await CharacterManager().get_character_by_character_id(main_character_id)
        if main_character.director:
            director = True
        else:
            director = False
        return jsonify({"status": 200, "mainCharacter": main_character.character_name, "director": director})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取主角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取主角色失败"}), 500

@api_user_bp.route("/setMainCharacter", methods=["POST"])
@auth_required
async def set_main_character():
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
        return jsonify({"status": 200, "message": "主角色设置成功", "director": director})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"设置主角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "设置主角色失败"}), 500

@api_user_bp.route('/isAliasCharacterSettingAvaliable', methods=['GET'])
@auth_required
async def is_alias_character_setting_avaliable():
    user_id = g.current_user["user_id"]
    try:
        # 获取用户主账号
        main_character_id = await UserManager().get_main_character_id(user_id)
        main_character = await CharacterManager().get_character_by_character_id(main_character_id)

        # 判断用户所在公司是否有绑定总监权限账号
        director_character_id = await CharacterManager().get_director_character_id_of_corporation(main_character.corporation_id)
        if not director_character_id:
            return jsonify({"status": 200, "isAliasCharacterSettingAvaliable": False})
        
        # 否则返回false
        # 有则返回true

        return jsonify({"status": 200, "isAliasCharacterSettingAvaliable": True})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"检查别名角色设置可用性失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "检查别名角色设置可用性失败"}), 500

@api_user_bp.route('/getSameTitleAliasCharacterList', methods=['POST'])
@auth_required
async def get_same_title_alias_character_list():
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
        logger.error(f"获取同title别名角色列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取同title别名角色列表失败"}), 500

@api_user_bp.route('/getAliasCharacterList', methods=['GET'])
@auth_required
async def get_alias_character_list():
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
        logger.error(f"获取别名角色列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取别名角色列表失败"}), 500

@api_user_bp.route('/searchCharacter', methods=['POST'])
@auth_required
async def search_character():
    """搜索角色（通过角色ID或角色名称）"""
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
                return jsonify({"status": 500, "message": str(e)}), 500
            except Exception as e:
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
                return jsonify({"status": 500, "message": str(e)}), 500
            except Exception as e:
                logger.error(f"搜索角色失败: {traceback.format_exc()}")
                return jsonify({"status": 500, "message": "搜索角色失败"}), 500
        
        return jsonify({"status": 200, "data": result})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"搜索角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "搜索角色失败"}), 500

@api_user_bp.route('/addAliasCharacters', methods=['POST'])
@auth_required
async def add_alias_characters():
    """添加选中的别名角色"""
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
                logger.error(f"添加角色 {character_id} 失败: {str(e)}")
                failed_list.append(str(character_id))
            except Exception as e:
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
        logger.error(f"添加别名角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加别名角色失败"}), 500

@api_user_bp.route('/saveAliasCharacters', methods=['POST'])
@auth_required
async def save_alias_characters():
    try:
        data = await request.get_json()
        aliasCharacterList = data.get("aliasCharacterList", [])
        for alias_character in aliasCharacterList:
            alias_character_obj = await EveAliasCharacterDBUtils.select_alias_character_by_character_id(alias_character["CharacterId"])
            if not alias_character:
                continue
            alias_character_obj.enabled = alias_character["Enabled"]
            await EveAliasCharacterDBUtils.save_obj(alias_character_obj)
        return jsonify({"status": 200, "message": "保存成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"保存别名角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存别名角色失败"}), 500