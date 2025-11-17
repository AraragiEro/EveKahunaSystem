import asyncio
import traceback
from quart import Blueprint, jsonify, request, g
from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import permission_required
from src_v2.core.permission.permission_manager import permission_manager, rdm
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.model.EVE.character.character import Character
from src_v2.core.user.user_manager import UserManager
from src_v2.model.EVE.asset.asset_manager import AssetManager
from src_v2.core.log import logger
from src_v2.core.database.kahuna_database_utils_v2 import EveAssetPullMissionDBUtils
from src_v2.core.utils import get_beijing_utctime
from datetime import datetime, timezone, timedelta
from src_v2.core.database.model import EveAssetPullMission as M_EveAssetPullMission
# from ..service.asset_server.asset_manager import AssetManager

api_EVE_asset_bp = Blueprint('api_EVE_asset', __name__, url_prefix='/api/EVE/asset')

@api_EVE_asset_bp.route('/container/list', methods=['GET'])
@auth_required
async def get_container_list():
    res = []

    # for k, v in AssetManager.container_dict.items():
    #     res.append({
    #         'name': v.asset_name,
    #     })

    return res

@api_EVE_asset_bp.route('/container/delete', methods=['POST'])
@auth_required
async def delete_container():
    data = await request.json
    id = data.get('id')
    # AssetManager.container_dict.pop(id)
    return jsonify({'code': 200, 'message': '删除成功'})

@api_EVE_asset_bp.route('/isEditCorpSettingAllowed', methods=['GET'])
@auth_required
async def is_edit_corp_setting_allowed():
    user_id = g.current_user["user_id"]
    roles = await permission_manager.get_user_roles(user_id)
    if "EveCorpDirector" in roles:
        return jsonify({'code': 200, 'message': True})
    else:
        return jsonify({'code': 200, 'message': False})

@api_EVE_asset_bp.route('/editCorpSetting', methods=['POST'])
@auth_required
@permission_required(["industry.asset.setting.changeCorpSetting:write"])
async def edit_corp_setting():
    user_id = g.current_user["user_id"]

@api_EVE_asset_bp.route('/editPersonalAssetSetting', methods=['POST'])
@auth_required
async def edit_personal_asset_setting():
    user_id = g.current_user["user_id"]

    asset_manager = AssetManager()
    data = await request.json
    allow_personal_asset = data.get('allow_personal_asset')


    return jsonify({'code': 200, 'message': '编辑成功'})

@api_EVE_asset_bp.route('/pullAssetOwners', methods=['GET'])
@auth_required
async def get_pull_asset_owners():
    user_id = g.current_user["user_id"]
    characters = await CharacterManager().get_user_all_characters(user_id)
    main_character_id = await UserManager().get_main_character_id(user_id)
    main_character = await CharacterManager().get_character_by_character_id(main_character_id)
    # await main_character.refresh_character_token()
    main_character_corp_id = main_character.corporation_id
    corporation = await CharacterManager().get_corporation_data_by_corporation_id(main_character_corp_id)

    res = []
    for character in characters:
        if character.corporation_id == main_character_corp_id:
            res.append({
                'owner_name': character.character_name,
                'owner_id': character.character_id,
                'owner_type': 'character'
            })
    res.append({
        'owner_name': corporation.name,
        'owner_id': corporation.corporation_id,
        'owner_type': 'corp'
    })

    logger.info(f"res: {res}")
    return jsonify({'code': 200, 'data': res})

@api_EVE_asset_bp.route('/createAssetPullMission', methods=['POST'])
@auth_required
async def create_asset_pull_mission():
    user_id = g.current_user["user_id"]

    data = await request.json
    asset_owner_type = data.get('asset_owner_type')
    asset_owner_id = data.get('asset_owner_id')
    active = data.get('active')

    try:
        await AssetManager().create_asset_pull_mission(user_id, asset_owner_type, asset_owner_id, active)
    except Exception as e:
        return jsonify({'code': 400, 'message': str(e)})
    return jsonify({'code': 200, 'message': '创建成功'})

@api_EVE_asset_bp.route('/getAssetPullMissions', methods=['GET'])
@auth_required
async def get_asset_pull_missions():
    user_id = g.current_user["user_id"]

    try:
        missions = await AssetManager().get_user_asset_pull_mission_list(user_id)
        return jsonify({'code': 200, 'data': missions}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'code': 400, 'message': str(e)}), 400

@api_EVE_asset_bp.route('/closeAssetPullMission', methods=['POST'])
@auth_required
async def close_asset_pull_mission():
    data = await request.json
    asset_owner_type = data.get('asset_owner_type')
    asset_owner_id = data.get('asset_owner_id')
    active = data.get('active')
    try:
        await AssetManager().change_asset_pull_mission_status(asset_owner_type, asset_owner_id, active)
    except Exception as e:
        return jsonify({'code': 400, 'message': str(e)})
    return jsonify({'code': 200, 'message': '关闭成功'})

@api_EVE_asset_bp.route('/startAssetPullMission', methods=['POST'])
@auth_required
async def start_asset_pull_mission():
    data = await request.json
    asset_owner_type = data.get('asset_owner_type')
    asset_owner_id = data.get('asset_owner_id')
    active = data.get('active')

    try:
        await AssetManager().change_asset_pull_mission_status(asset_owner_type, asset_owner_id, active)
    except Exception as e:
        return jsonify({'code': 400, 'message': str(e)})
    return jsonify({'code': 200, 'message': '启动成功'})

@api_EVE_asset_bp.route('/deleteAssetPullMission', methods=['DELETE'])
@auth_required
async def delete_asset_pull_mission():
    data = await request.json
    asset_owner_type = data.get('asset_owner_type')
    asset_owner_id = data.get('asset_owner_id')

    mission_obj = await EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type(asset_owner_id, asset_owner_type)
    if not mission_obj:
        return jsonify({'code': 400, 'message': '任务不存在'})
    await EveAssetPullMissionDBUtils.delete_obj(mission_obj)
    return jsonify({'code': 200, 'message': '删除成功'})

async def start_pull_asset_now(asset_owner_type: str, asset_owner_id: int):
    asset_status_key = f'asset_pull_mission_status:{asset_owner_type}:{asset_owner_id}'
    await rdm.r.hset(asset_status_key, mapping={
        'status': 'pulling',
        'total_page': 0,
        'finished_page': 0,
        "step_name": "",
        "step_progress": 0,
        "is_indeterminate": 0
    })
    try:
        await AssetManager().pull_asset_now(asset_owner_type, asset_owner_id)
        await rdm.r.hset(asset_status_key, mapping={
            'status': 'success',
            'total_page': 0,
            'finished_page': 0,
            "step_name": "",
            "step_progress": 0,
            "is_indeterminate": 0
        })
    except Exception as e:
        await rdm.r.hset(asset_status_key, mapping={
            'status': 'failed',
            'total_page': 0,
            'finished_page': 0,
            "step_name": "",
            "step_progress": 0,
            "is_indeterminate": 0
        })
        raise e

@api_EVE_asset_bp.route('/pullAssetNow', methods=['POST'])
@auth_required
async def pull_asset_now():
    data = await request.json
    asset_owner_type = data.get('asset_owner_type')
    asset_owner_id = data.get('asset_owner_id')
    
    # 获取上次拉取时间（异步操作）
    last_pull_time_str = await rdm.r.get(f"asset_pull_mission_last_pull_time:{asset_owner_type}:{asset_owner_id}")
    
    # 如果存在上次拉取时间，检查是否在15分钟内
    if last_pull_time_str:
        try:
            # 将字符串转换为 datetime 对象
            last_pull_time = datetime.fromisoformat(last_pull_time_str.replace('Z', '+00:00'))
            # 获取当前北京时间（与存储的格式一致）
            current_time = get_beijing_utctime(datetime.now())
            # 确保时区一致
            if last_pull_time.tzinfo is None:
                last_pull_time = last_pull_time.replace(tzinfo=timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
            # 计算时间差
            time_diff = current_time - last_pull_time
            if time_diff < timedelta(minutes=15):
                return jsonify({'code': 400, 'message': '每15分钟只能拉取一次'}), 400
        except (ValueError, AttributeError) as e:
            logger.warning(f"解析上次拉取时间失败: {e}")

    asyncio.create_task(start_pull_asset_now(asset_owner_type, asset_owner_id))

    # 设置本次拉取时间（异步操作）
    await rdm.r.set(f"asset_pull_mission_last_pull_time:{asset_owner_type}:{asset_owner_id}", get_beijing_utctime(datetime.now()).isoformat())
    return jsonify({'code': 200, 'message': '任务启动成功'}), 200

@api_EVE_asset_bp.route('/getAssetPullMissionStatus', methods=['POST'])
@auth_required
async def get_asset_pull_mission_status():
    user_id = g.current_user["user_id"]
    data = await request.json
    asset_owner_type = data.get('asset_owner_type')
    asset_owner_id = data.get('asset_owner_id')
    
    asset_status_key = f'asset_pull_mission_status:{asset_owner_type}:{asset_owner_id}'

    status = await rdm.r.hget(asset_status_key, "status")
    step_name = await rdm.r.hget(asset_status_key, "step_name")
    step_progress = await rdm.r.hget(asset_status_key, "step_progress")
    is_indeterminate = await rdm.r.hget(asset_status_key, "is_indeterminate")

    logger.info(f"'status': {status}, 'step_name': {step_name}, 'step_progress': {step_progress}")
    return jsonify({'code': 200, 'data': {'status': status, 'step_name': step_name, 'step_progress': step_progress, 'is_indeterminate': is_indeterminate}})


@api_EVE_asset_bp.route('/searchContainerByItemNameAndQuantity', methods=['POST'])
@auth_required
async def search_container_by_item_name_and_quantity():
    user_id = g.current_user["user_id"]
    data = await request.json
    item_name = data.get('item_name')
    try:
        output = await AssetManager().search_container_by_item_name(user_id, item_name)
        return jsonify({'data': output, "status": 200})
    except Exception as e:
        return jsonify({'error': str(e)}), 400