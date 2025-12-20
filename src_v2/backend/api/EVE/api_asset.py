import asyncio
import traceback
from quart import Blueprint, jsonify, request, g
from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import permission_required
from src_v2.backend.api.permission_required import role_required
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.user.user_manager import UserManager
from src_v2.model.EVE.asset.asset_manager import AssetManager
from src_v2.core.log import logger
from src_v2.core.database.kahuna_database_utils_v2 import EveAssetPullMissionDBUtils
from src_v2.core.utils import get_beijing_utctime, KahunaException
from datetime import datetime, timezone, timedelta
from src_v2.model.EVE.market.market_manager import MarketManager

api_EVE_asset_bp = Blueprint('api_EVE_asset', __name__, url_prefix='/api/EVE/asset')

@api_EVE_asset_bp.route('/container/list', methods=['GET'])
@auth_required
async def get_container_list():
    try:
        res = []

        # for k, v in AssetManager.container_dict.items():
        #     res.append({
        #         'name': v.asset_name,
        #     })

        return jsonify({"status": 200, "data": res})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取容器列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取容器列表失败"}), 500

@api_EVE_asset_bp.route('/container/delete', methods=['POST'])
@auth_required
async def delete_container():
    try:
        data = await request.json
        id = data.get('id')
        # AssetManager.container_dict.pop(id)
        return jsonify({"status": 200, "message": "删除成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除容器失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除容器失败"}), 500

@api_EVE_asset_bp.route('/isEditCorpSettingAllowed', methods=['GET'])
@auth_required
async def is_edit_corp_setting_allowed():
    try:
        user_id = g.current_user["user_id"]
        roles = await permission_manager.get_user_roles(user_id)
        if "EveCorpDirector" in roles:
            return jsonify({"status": 200, "message": True})
        else:
            return jsonify({"status": 200, "message": False})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"检查公司设置编辑权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "检查公司设置编辑权限失败"}), 500

@api_EVE_asset_bp.route('/editCorpSetting', methods=['POST'])
@auth_required
@permission_required(["industry.asset.setting.changeCorpSetting:write"])
async def edit_corp_setting():
    try:
        user_id = g.current_user["user_id"]
        # TODO: 实现公司设置编辑逻辑
        return jsonify({"status": 200, "message": "编辑成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"编辑公司设置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "编辑公司设置失败"}), 500

@api_EVE_asset_bp.route('/editPersonalAssetSetting', methods=['POST'])
@auth_required
async def edit_personal_asset_setting():
    try:
        user_id = g.current_user["user_id"]

        asset_manager = AssetManager()
        data = await request.json
        allow_personal_asset = data.get('allow_personal_asset')

        # TODO: 实现个人资产设置编辑逻辑

        return jsonify({"status": 200, "message": "编辑成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"编辑个人资产设置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "编辑个人资产设置失败"}), 500

@api_EVE_asset_bp.route('/pullAssetOwners', methods=['GET'])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可使用资产功能。")
async def get_pull_asset_owners():
    try:
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
        return jsonify({"status": 200, "data": res})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取资产拉取主体列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产拉取主体列表失败"}), 500

@api_EVE_asset_bp.route('/createAssetPullMission', methods=['POST'])
@auth_required
async def create_asset_pull_mission():
    try:
        user_id = g.current_user["user_id"]

        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')
        active = data.get('active')

        await AssetManager().create_asset_pull_mission(user_id, asset_owner_type, asset_owner_id, active)
        return jsonify({"status": 200, "message": "创建成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建资产拉取任务失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建资产拉取任务失败"}), 500

@api_EVE_asset_bp.route('/getAssetPullMissions', methods=['GET'])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可拉取真实资产建筑。虚拟建筑可正常使用。")
async def get_asset_pull_missions():
    try:
        user_id = g.current_user["user_id"]
        
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        
        # 如果用户有admin角色，返回所有任务；否则返回用户自己的任务
        is_admin = "admin" in all_roles
        if is_admin:
            logger.info(f"管理员 {user_id} 获取所有资产拉取任务列表")
            missions = await AssetManager().get_all_asset_pull_mission_list()
        else:
            missions = await AssetManager().get_user_asset_pull_mission_list(user_id)
        
        return jsonify({"status": 200, "data": missions}), 200
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取资产拉取任务列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产拉取任务列表失败"}), 500

@api_EVE_asset_bp.route('/closeAssetPullMission', methods=['POST'])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可使用资产功能。")
async def close_asset_pull_mission():
    try:
        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')
        active = data.get('active')
        await AssetManager().change_asset_pull_mission_status(asset_owner_type, asset_owner_id, active)
        return jsonify({"status": 200, "message": "关闭成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"关闭资产拉取任务失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "关闭资产拉取任务失败"}), 500

@api_EVE_asset_bp.route('/startAssetPullMission', methods=['POST'])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可使用资产功能。")
async def start_asset_pull_mission():
    try:
        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')
        active = data.get('active')

        await AssetManager().change_asset_pull_mission_status(asset_owner_type, asset_owner_id, active)
        return jsonify({"status": 200, "message": "启动成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"启动资产拉取任务失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "启动资产拉取任务失败"}), 500

@api_EVE_asset_bp.route('/deleteAssetPullMission', methods=['DELETE'])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可使用资产功能。")
async def delete_asset_pull_mission():
    try:
        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')

        mission_obj = await EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type(asset_owner_id, asset_owner_type)
        if not mission_obj:
            return jsonify({"status": 400, "message": "任务不存在"}), 400
        await EveAssetPullMissionDBUtils.delete_obj(mission_obj)
        return jsonify({"status": 200, "message": "删除成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除资产拉取任务失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除资产拉取任务失败"}), 500

async def start_pull_asset_now(asset_owner_type: str, asset_owner_id: int):
    asset_status_key = f'asset_pull_mission_status:{asset_owner_type}:{asset_owner_id}'
    await rdm().r.hset(asset_status_key, mapping={
        'status': 'pulling',
        'total_page': 0,
        'finished_page': 0,
        "step_name": "",
        "step_progress": 0,
        "is_indeterminate": 0
    })
    try:
        await AssetManager().pull_asset_now(asset_owner_type, asset_owner_id)
        await rdm().r.hset(asset_status_key, mapping={
            'status': 'success',
            'total_page': 0,
            'finished_page': 0,
            "step_name": "",
            "step_progress": 0,
            "is_indeterminate": 0
        })
    except Exception as e:
        await rdm().r.hset(asset_status_key, mapping={
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
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可使用资产功能。")
async def pull_asset_now():
    try:
        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')
        
        asset_status_key = f'asset_pull_mission_status:{asset_owner_type}:{asset_owner_id}'
        status = await rdm().r.hget(asset_status_key, "status")
        if status == 'pulling':
            return jsonify({"status": 400, "message": "任务正在拉取中"}), 400

        # 获取上次拉取时间（异步操作）
        last_pull_time_str = await rdm().r.get(f"asset_pull_mission_last_pull_time:{asset_owner_type}:{asset_owner_id}")
        
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
                    return jsonify({"status": 400, "message": "每15分钟只能拉取一次"}), 400
            except (ValueError, AttributeError) as e:
                logger.warning(f"解析上次拉取时间失败: {e}")

        asyncio.create_task(start_pull_asset_now(asset_owner_type, asset_owner_id))

        # 设置本次拉取时间（异步操作）
        await rdm().r.set(f"asset_pull_mission_last_pull_time:{asset_owner_type}:{asset_owner_id}", get_beijing_utctime(datetime.now()).isoformat())
        return jsonify({"status": 200, "message": "任务启动成功"}), 200
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"启动资产拉取失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "启动资产拉取失败"}), 500

@api_EVE_asset_bp.route('/getAssetPullMissionStatus', methods=['POST'])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可使用资产功能。")
async def get_asset_pull_mission_status():
    try:
        user_id = g.current_user["user_id"]
        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')
        
        asset_status_key = f'asset_pull_mission_status:{asset_owner_type}:{asset_owner_id}'

        status = await rdm().r.hget(asset_status_key, "status")
        step_name = await rdm().r.hget(asset_status_key, "step_name")
        step_progress = await rdm().r.hget(asset_status_key, "step_progress")
        is_indeterminate = await rdm().r.hget(asset_status_key, "is_indeterminate")

        return jsonify({"status": 200, "data": {'status': status, 'step_name': step_name, 'step_progress': step_progress, 'is_indeterminate': is_indeterminate}})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取资产拉取任务状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产拉取任务状态失败"}), 500


@api_EVE_asset_bp.route('/searchContainerByItemNameAndQuantity', methods=['POST'])
@auth_required
async def search_container_by_item_name_and_quantity():
    try:
        current_user_id = g.current_user["user_id"]
        data = await request.json
        item_name = data.get('item_name')
        
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        
        # 如果用户有admin角色，允许通过 user_name 参数指定要搜索的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(f"管理员 {current_user_id} 搜索用户 {user_id} 的容器: {item_name}")
        else:
            user_id = current_user_id
        
        output = await AssetManager().search_container_by_item_name(user_id, item_name)
        return jsonify({"status": 200, "data": output})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"搜索容器失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "搜索容器失败"}), 500


@api_EVE_asset_bp.route('/getAssetViewList', methods=['GET'])
@auth_required
async def get_asset_view_list():
    try:
        current_user_id = g.current_user["user_id"]
        
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        
        # 如果用户有admin角色，允许通过 user_name 参数指定要查询的用户
        is_admin = "admin" in all_roles
        user_name = request.args.get('user_name')
        if is_admin and user_name:
            logger.info(f"管理员 {current_user_id} 获取用户 {user_name} 的资产视图列表")
            target_user_id = user_name
        else:
            target_user_id = current_user_id
        
        output = await AssetManager().get_asset_view_of_user(target_user_id)
        return jsonify({"status": 200, "data": output})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取资产视图列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产视图列表失败"}), 500

@api_EVE_asset_bp.route('/getAssetViewData', methods=['GET'])
@auth_required
async def get_asset_view_data():
    try:
        user_id = g.current_user["user_id"]

        # GET 请求从查询参数中获取数据
        asset_view_sid = request.args.get('asset_view_sid')
        logger.info(f"获取资产视图sid: {asset_view_sid}")
        if not asset_view_sid:
            return jsonify({"status": 400, "message": "缺少参数 asset_view_sid"}), 400
        asset_view_obj = await AssetManager().get_asset_view_by_sid(asset_view_sid)
        
        if asset_view_obj.view_type == 'statistics':
            output = await AssetManager().get_asset_statistics_data(asset_view_sid)
        else:
            output = await AssetManager().get_asset_view_data(asset_view_sid)
            # 出售视图增加价格
            if asset_view_obj.view_type == 'sell':
                await MarketManager().update_jita_price()
                output = await AssetManager().fill_sell_price_data(output, asset_view_obj.config)

        return jsonify({"status": 200, "data": output, "view_type": asset_view_obj.view_type, "config": asset_view_obj.config})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取资产视图数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产视图数据失败"}), 500

@api_EVE_asset_bp.route('/saveAssetViewConfig', methods=['POST'])
@auth_required
async def save_asset_view_config():
    try:
        current_user_id = g.current_user["user_id"]
        data = await request.json
        sid = data.get('sid')
        
        if not sid:
            return jsonify({"status": 400, "message": "缺少参数 sid"}), 400
        
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        
        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_name = data["user_name"]
            logger.info(f"管理员 {current_user_id} 修改用户 {user_name} 的资产视图配置: {sid}")
        else:
            user_name = current_user_id
        
        # 只传递存在的参数，使用 None 表示不更新该字段
        update_data = {}
        if 'tag' in data:
            update_data['tag'] = data.get('tag')
        if 'public' in data:
            update_data['public'] = data.get('public')
        if 'filter' in data:
            update_data['filter_list'] = data.get('filter')
        if 'view_type' in data:
            update_data['view_type'] = data.get('view_type')
        if 'config' in data:
            update_data['config'] = data.get('config')
        if 'container_list' in data:
            container_list = data.get('container_list')
            # 验证container_list格式
            if container_list is not None:
                if not isinstance(container_list, list):
                    return jsonify({"status": 400, "message": "container_list 必须是列表"}), 400
                for item in container_list:
                    if not isinstance(item, dict) or 'container_id' not in item or 'owner_id' not in item:
                        return jsonify({"status": 400, "message": "container_list 格式错误，应为 [{container_id, owner_id}, ...]"}), 400
            update_data['container_list'] = container_list
        
        await AssetManager().save_asset_view_config(
            user_name=user_name,
            sid=sid,
            is_admin=is_admin,
            **update_data
        )
        return jsonify({"status": 200, "message": "保存成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存资产视图配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存资产视图配置失败"}), 500

@api_EVE_asset_bp.route('/createAssetView', methods=['POST'])
@auth_required
async def create_asset_view():
    try:
        current_user_id = g.current_user["user_id"]
        data = await request.json
        container_list = data.get('container_list')
        tag = data.get('tag')
        
        if not container_list or not isinstance(container_list, list) or len(container_list) == 0:
            return jsonify({"status": 400, "message": "缺少参数 container_list 或列表为空"}), 400
        
        # 验证container_list格式
        for item in container_list:
            if not isinstance(item, dict) or 'container_id' not in item or 'owner_id' not in item:
                return jsonify({"status": 400, "message": "container_list 格式错误，应为 [{container_id, owner_id}, ...]"}), 400
        
        if not tag or not tag.strip():
            return jsonify({"status": 400, "message": "缺少参数 tag 或标签为空"}), 400
        
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        
        # 如果用户有admin角色，允许通过 user_name 参数指定要为哪个用户创建资产视图
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_name = data["user_name"]
            logger.info(f"管理员 {current_user_id} 为用户 {user_name} 创建资产视图: {tag}")
        else:
            user_name = current_user_id
        
        await AssetManager().create_asset_view_from_container_list(user_name, container_list, tag.strip())
        return jsonify({"status": 200, "message": "创建监控成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建资产视图失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建资产视图失败"}), 500

@api_EVE_asset_bp.route('/deleteAssetView', methods=['DELETE'])
@auth_required
async def delete_asset_view():
    try:
        current_user_id = g.current_user["user_id"]
        data = await request.json
        sid = data.get('sid')
        
        if not sid:
            return jsonify({"status": 400, "message": "缺少参数 sid"}), 400
        
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        
        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_name = data["user_name"]
            logger.info(f"管理员 {current_user_id} 删除用户 {user_name} 的资产视图: {sid}")
        else:
            user_name = current_user_id
        
        await AssetManager().delete_asset_view(user_name, sid, is_admin=is_admin)
        return jsonify({"status": 200, "message": "删除成功"})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除资产视图失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除资产视图失败"}), 500