import asyncio
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from quart import Blueprint, g, jsonify, request

from src_v2.backend.api.permission_required import permission_required, role_required
from src_v2.backend.auth import auth_required
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import EveAssetPullMissionDBUtils
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.user.user_manager import UserManager
from src_v2.core.utils import KahunaException, get_beijing_utctime
from src_v2.model.EVE.asset.asset_manager import AssetManager
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.model.EVE.market.market_manager import MarketManager

api_EVE_asset_bp = Blueprint(
    'api_EVE_asset', __name__, url_prefix='/api/EVE/asset')


# 请求数据模型
@dataclass
class DeleteContainerRequest:
    """删除容器请求"""
    id: str


@dataclass
class EditPersonalAssetSettingRequest:
    """编辑个人资产设置请求"""
    allow_personal_asset: bool


@dataclass
class CreateAssetPullMissionRequest:
    """创建资产拉取任务请求"""
    ownerType: str  # 'character' or 'corp'
    ownerId: int


@dataclass
class CloseAssetPullMissionRequest:
    """关闭资产拉取任务请求"""
    missionId: int


@dataclass
class StartAssetPullMissionRequest:
    """启动资产拉取任务请求"""
    missionId: int


@dataclass
class DeleteAssetPullMissionRequest:
    """删除资产拉取任务请求"""
    missionId: int


@dataclass
class PullAssetNowRequest:
    """立即拉取资产请求"""
    ownerType: str
    ownerId: int


@dataclass
class GetAssetPullMissionStatusRequest:
    """获取资产拉取任务状态请求"""
    missionId: int


@dataclass
class SearchContainerRequest:
    """搜索容器请求"""
    itemName: str
    quantity: int


@dataclass
class SaveAssetViewConfigRequest:
    """保存资产视图配置请求"""
    sid: str
    config: Dict[str, Any]


@dataclass
class CreateAssetViewRequest:
    """创建资产视图请求"""
    tag: str
    viewType: str
    config: Dict[str, Any]
    public: bool = False


@dataclass
class DeleteAssetViewRequest:
    """删除资产视图请求"""
    sid: str


# 响应数据模型
@dataclass
class ContainerListResponse:
    """容器列表响应"""
    status: int
    data: List[Dict[str, Any]]


@dataclass
class MessageResponse:
    """消息响应"""
    status: int
    message: str


@dataclass
class BooleanResponse:
    """布尔值响应"""
    status: int
    message: bool


@dataclass
class OwnerItem:
    """资产主体项"""
    owner_name: str
    owner_id: int
    owner_type: str


@dataclass
class PullAssetOwnersResponse:
    """资产拉取主体列表响应"""
    status: int
    data: List[OwnerItem]


@dataclass
class AssetPullMissionResponse:
    """资产拉取任务响应"""
    status: int
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


@dataclass
class AssetPullMissionListResponse:
    """资产拉取任务列表响应"""
    status: int
    data: List[Dict[str, Any]]


@dataclass
class AssetPullMissionStatusResponse:
    """资产拉取任务状态响应"""
    status: int
    data: Dict[str, Any]


@dataclass
class SearchContainerResponse:
    """搜索容器响应"""
    status: int
    data: List[Dict[str, Any]]


@dataclass
class AssetViewListResponse:
    """资产视图列表响应"""
    status: int
    data: List[Dict[str, Any]]


@dataclass
class AssetViewDataResponse:
    """资产视图数据响应"""
    status: int
    data: Dict[str, Any]


@dataclass
class CreateAssetViewResponse:
    """创建资产视图响应"""
    status: int
    data: Dict[str, Any]


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


@api_EVE_asset_bp.route('/container/list', methods=['GET'])
@auth_required
# @validate_response(ContainerListResponse)
async def get_container_list():
    """
    获取容器列表

    获取当前用户的容器列表。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回容器列表
            - status: 状态码 (200)
            - data: 容器列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": []
        }
    """
    try:
        res = []

        # for k, v in AssetManager.container_dict.items():
        #     res.append({
        #         'name': v.asset_name,
        #     })

        return {"status": 200, "data": res}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取容器列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取容器列表失败"}), 500


@api_EVE_asset_bp.route('/container/delete', methods=['POST'])
@auth_required
# @validate_request(DeleteContainerRequest)
# @validate_response(MessageResponse)
async def delete_container():
    """
    删除容器

    删除指定的容器。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - id (string, required): 容器ID

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "id": "container_id"
        }

    Example Response:
        {
            "status": 200,
            "message": "删除成功"
        }
    """
    try:
        data = await request.json
        id = data.get('id')
        # AssetManager.container_dict.pop(id)
        return {"status": 200, "message": "删除成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除容器失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除容器失败"}), 500


@api_EVE_asset_bp.route('/isEditCorpSettingAllowed', methods=['GET'])
@auth_required
# @validate_response(BooleanResponse)
async def is_edit_corp_setting_allowed():
    """
    检查公司设置编辑权限

    检查当前用户是否有编辑公司设置的权限（需要EveCorpDirector角色）。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回权限状态
            - status: 状态码 (200)
            - message: 是否有权限 (boolean)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "message": true
        }
    """
    try:
        user_id = g.current_user["user_id"]
        roles = await permission_manager.get_user_roles(user_id)
        if "EveCorpDirector" in roles:
            return {"status": 200, "message": True}
        else:
            return {"status": 200, "message": False}
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
# @validate_response(MessageResponse)
async def edit_corp_setting():
    """
    编辑公司设置

    编辑公司资产相关设置。需要相应的权限。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - 根据实际需求定义

    Responses:
        200: 编辑成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "message": "编辑成功"
        }
    """
    try:
        user_id = g.current_user["user_id"]
        # TODO: 实现公司设置编辑逻辑
        return {"status": 200, "message": "编辑成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"编辑公司设置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "编辑公司设置失败"}), 500


@api_EVE_asset_bp.route('/editPersonalAssetSetting', methods=['POST'])
@auth_required
# @validate_request(EditPersonalAssetSettingRequest)
# @validate_response(MessageResponse)
async def edit_personal_asset_setting():
    """
    编辑个人资产设置

    编辑当前用户的个人资产设置。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - allow_personal_asset (boolean, required): 是否允许个人资产

    Responses:
        200: 编辑成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "allow_personal_asset": true
        }

    Example Response:
        {
            "status": 200,
            "message": "编辑成功"
        }
    """
    try:
        user_id = g.current_user["user_id"]

        asset_manager = AssetManager()
        data = await request.json
        allow_personal_asset = data.get('allow_personal_asset')

        # TODO: 实现个人资产设置编辑逻辑

        return {"status": 200, "message": "编辑成功"}
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
# @validate_response(PullAssetOwnersResponse)
async def get_pull_asset_owners():
    """
    获取资产拉取主体列表

    获取当前用户可以拉取资产的主体列表，包括角色和公司。仅ALPHA订阅者可使用。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回主体列表
            - status: 状态码 (200)
            - data: 主体列表，每个元素包含主体名称、ID和类型 (array)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "owner_name": "Character Name",
                    "owner_id": 123456,
                    "owner_type": "character"
                },
                {
                    "owner_name": "Corporation Name",
                    "owner_id": 789012,
                    "owner_type": "corp"
                }
            ]
        }
    """
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
            # if character.corporation_id == main_character_corp_id:
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
        return {"status": 200, "data": res}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取资产拉取主体列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产拉取主体列表失败"}), 500


@api_EVE_asset_bp.route('/createAssetPullMission', methods=['POST'])
@auth_required
# @validate_request(CreateAssetPullMissionRequest)
# @validate_response(AssetPullMissionResponse)
async def create_asset_pull_mission():
    """
    创建资产拉取任务

    创建新的资产拉取任务，用于从指定主体（角色或公司）拉取资产数据。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - ownerType (string, required): 主体类型，可选值: character, corp
        - ownerId (integer, required): 主体ID

    Responses:
        200: 创建成功
            - status: 状态码 (200)
            - data: 创建的任务信息 (object)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "ownerType": "character",
            "ownerId": 123456
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "missionId": 1,
                "ownerType": "character",
                "ownerId": 123456
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]

        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')
        active = data.get('active')

        await AssetManager().create_asset_pull_mission(user_id, asset_owner_type, asset_owner_id, active)
        return {"status": 200, "message": "创建成功"}
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
# @validate_response(AssetPullMissionListResponse)
async def get_asset_pull_missions():
    """
    获取资产拉取任务列表

    获取当前用户的资产拉取任务列表。管理员可以获取所有任务。仅ALPHA订阅者可拉取真实资产建筑。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回任务列表
            - status: 状态码 (200)
            - data: 任务列表 (array)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "missionId": 1,
                    "ownerType": "character",
                    "ownerId": 123456,
                    "status": "running"
                }
            ]
        }
    """
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

        return {"status": 200, "data": missions}
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
# @validate_response(MessageResponse)
async def close_asset_pull_mission():
    """
    关闭资产拉取任务

    关闭指定的资产拉取任务。仅ALPHA订阅者可使用。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - asset_owner_type (string, required): 主体类型
        - asset_owner_id (integer, required): 主体ID
        - active (boolean, required): 是否激活

    Responses:
        200: 关闭成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "asset_owner_type": "character",
            "asset_owner_id": 123456,
            "active": false
        }

    Example Response:
        {
            "status": 200,
            "message": "关闭成功"
        }
    """
    try:
        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')
        active = data.get('active')
        await AssetManager().change_asset_pull_mission_status(asset_owner_type, asset_owner_id, active)
        return {"status": 200, "message": "关闭成功"}
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
# @validate_response(MessageResponse)
async def start_asset_pull_mission():
    """
    启动资产拉取任务

    启动指定的资产拉取任务。仅ALPHA订阅者可使用。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - asset_owner_type (string, required): 主体类型
        - asset_owner_id (integer, required): 主体ID
        - active (boolean, required): 是否激活

    Responses:
        200: 启动成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "asset_owner_type": "character",
            "asset_owner_id": 123456,
            "active": true
        }

    Example Response:
        {
            "status": 200,
            "message": "启动成功"
        }
    """
    try:
        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')
        active = data.get('active')

        await AssetManager().change_asset_pull_mission_status(asset_owner_type, asset_owner_id, active)
        return {"status": 200, "message": "启动成功"}
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
# @validate_response(MessageResponse)
async def delete_asset_pull_mission():
    """
    删除资产拉取任务

    永久删除指定的资产拉取任务。仅ALPHA订阅者可使用。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - asset_owner_type (string, required): 主体类型
        - asset_owner_id (integer, required): 主体ID

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 任务不存在
            - status: 状态码 (400)
            - message: 错误信息 (string)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        403: 非总监无法删除公司资产拉取任务
            - status: 状态码 (403)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "asset_owner_type": "character",
            "asset_owner_id": 123456
        }

    Example Response:
        {
            "status": 200,
            "message": "删除成功"
        }
    """
    try:
        data = await request.json
        asset_owner_type = data.get('asset_owner_type')
        asset_owner_id = data.get('asset_owner_id')

        # 如果是公司资产拉取任务，检查主角色是否有总监权限
        if asset_owner_type == 'corp':
            user_id = g.current_user["user_id"]
            main_character_id = await UserManager().get_main_character_id(user_id)
            main_character = await CharacterManager().get_character_by_character_id(main_character_id)
            if not main_character.director:
                return jsonify({"status": 403, "message": "非总监无法删除公司资产拉取任务"}), 403

        mission_obj = await EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type(asset_owner_id, asset_owner_type)
        if not mission_obj:
            return jsonify({"status": 400, "message": "任务不存在"}), 400
        await EveAssetPullMissionDBUtils.delete_obj(mission_obj)
        return {"status": 200, "message": "删除成功"}
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
        # 任务成功完成后，更新Redis中的 last_pull_time
        await rdm().r.set(
            f"asset_pull_mission_last_pull_time:{asset_owner_type}:{asset_owner_id}",
            get_beijing_utctime(datetime.now()).isoformat()
        )
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
# @validate_response(MessageResponse)
async def pull_asset_now():
    """
    立即拉取资产

    立即从指定主体拉取资产数据。仅ALPHA订阅者可使用。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - ownerType (string, required): 主体类型，可选值: character, corp
        - ownerId (integer, required): 主体ID

    Responses:
        200: 拉取成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "ownerType": "character",
            "ownerId": 123456
        }

    Example Response:
        {
            "status": 200,
            "message": "拉取成功"
        }
    """
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
                last_pull_time = datetime.fromisoformat(
                    last_pull_time_str.replace('Z', '+00:00'))
                # 获取当前北京时间（与存储的格式一致）
                current_time = get_beijing_utctime(datetime.now())
                # 确保时区一致
                if last_pull_time.tzinfo is None:
                    last_pull_time = last_pull_time.replace(
                        tzinfo=timezone.utc)
                if current_time.tzinfo is None:
                    current_time = current_time.replace(tzinfo=timezone.utc)
                # 计算时间差
                time_diff = current_time - last_pull_time
                if time_diff < timedelta(minutes=15):
                    return jsonify({"status": 400, "message": "每15分钟只能拉取一次"}), 400
            except (ValueError, AttributeError) as e:
                logger.warning(f"解析上次拉取时间失败: {e}")

        # 立即设置状态为 'pulling'，防止重复触发
        await rdm().r.hset(asset_status_key, 'status', 'pulling')
        
        # 启动异步任务（任务完成后会更新 last_pull_time）
        asyncio.create_task(start_pull_asset_now(
            asset_owner_type, asset_owner_id))
        
        return {"status": 200, "message": "任务启动成功"}
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
# @validate_request(GetAssetPullMissionStatusRequest)
# @validate_response(AssetPullMissionStatusResponse)
async def get_asset_pull_mission_status():
    """
    获取资产拉取任务状态

    获取指定资产拉取任务的当前状态。仅ALPHA订阅者可使用。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - missionId (integer, required): 任务ID

    Responses:
        200: 成功返回任务状态
            - status: 状态码 (200)
            - data: 任务状态信息 (object)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "missionId": 1
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "status": "running",
                "progress": 50
            }
        }
    """
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

        return {"status": 200, "data": {'status': status, 'step_name': step_name, 'step_progress': step_progress, 'is_indeterminate': is_indeterminate}}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取资产拉取任务状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产拉取任务状态失败"}), 500


@api_EVE_asset_bp.route('/searchContainerByItemNameAndQuantity', methods=['POST'])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可使用资产功能。")
# @validate_request(SearchContainerRequest)
# @validate_response(SearchContainerResponse)
async def search_container_by_item_name_and_quantity():
    """
    根据物品名称和数量搜索容器

    搜索包含指定物品名称且数量满足要求的容器。仅ALPHA订阅者可使用。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - itemName (string, required): 物品名称
        - quantity (integer, required): 最小数量

    Responses:
        200: 成功返回搜索结果
            - status: 状态码 (200)
            - data: 匹配的容器列表 (array)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "itemName": "物品名称",
            "quantity": 100
        }

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "containerId": 123,
                    "itemName": "物品名称",
                    "quantity": 150
                }
            ]
        }
    """
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
            logger.info(
                f"管理员 {current_user_id} 搜索用户 {user_id} 的容器: {item_name}")
        else:
            user_id = current_user_id

        output = await AssetManager().search_container_by_item_name(user_id, item_name)
        return {"status": 200, "data": output}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"搜索容器失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "搜索容器失败"}), 500


@api_EVE_asset_bp.route('/getAssetViewList', methods=['GET'])
@auth_required
# @validate_response(AssetViewListResponse)
async def get_asset_view_list():
    """
    获取资产视图列表

    获取当前用户创建的所有资产视图列表。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回视图列表
            - status: 状态码 (200)
            - data: 资产视图列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "sid": "view_id",
                    "tag": "视图标签",
                    "view_type": "sell"
                }
            ]
        }
    """
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
        return {"status": 200, "data": output}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取资产视图列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产视图列表失败"}), 500


@api_EVE_asset_bp.route('/getAssetViewData', methods=['GET'])
@auth_required
# @validate_response(AssetViewDataResponse)
async def get_asset_view_data():
    """
    获取资产视图数据

    获取指定资产视图的数据。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Parameters:
        - sid (query, string, required): 资产视图SID

    Responses:
        200: 成功返回视图数据
            - status: 状态码 (200)
            - data: 资产视图数据 (object)
        404: 视图不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "items": [...],
                "total": 1000
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]

        # GET 请求从查询参数中获取数据
        asset_view_sid = request.args.get('asset_view_sid')
        logger.info(f"获取资产视图sid: {asset_view_sid}")
        if not asset_view_sid:
            return jsonify({"status": 400, "message": "缺少参数 asset_view_sid"}), 400
        asset_view_obj = await AssetManager().get_asset_view_by_sid(asset_view_sid)

        if asset_view_obj.view_type == 'statistics':
            output = await AssetManager().get_asset_statistics_data(user_id, asset_view_sid)
        else:
            output = await AssetManager().get_asset_view_data(asset_view_sid)
            # 出售视图增加价格
            if asset_view_obj.view_type == 'sell':
                await MarketManager().update_jita_price()
                output = await AssetManager().fill_sell_price_data(output, asset_view_obj.config)

        return {"status": 200, "data": output, "view_type": asset_view_obj.view_type, "config": asset_view_obj.config}
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取资产视图数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取资产视图数据失败"}), 500


@api_EVE_asset_bp.route('/saveAssetViewConfig', methods=['POST'])
@auth_required
# @validate_request(SaveAssetViewConfigRequest)
# @validate_response(MessageResponse)
async def save_asset_view_config():
    """
    保存资产视图配置

    保存指定资产视图的配置信息。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - sid (string, required): 资产视图SID
        - config (object, required): 视图配置

    Responses:
        200: 保存成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "sid": "view_id",
            "config": {...}
        }

    Example Response:
        {
            "status": 200,
            "message": "保存成功"
        }
    """
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
            logger.info(
                f"管理员 {current_user_id} 修改用户 {user_name} 的资产视图配置: {sid}")
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
                    if not isinstance(item, dict) or 'container_id' not in item or 'owner_id' not in item or 'location_flag' not in item:
                        return jsonify({"status": 400, "message": "container_list 格式错误，应为 [{container_id, owner_id, location_flag}, ...]"}), 400
            update_data['container_list'] = container_list

        await AssetManager().save_asset_view_config(
            user_name=user_name,
            sid=sid,
            is_admin=is_admin,
            **update_data
        )
        return {"status": 200, "message": "保存成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存资产视图配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存资产视图配置失败"}), 500


@api_EVE_asset_bp.route('/createAssetView', methods=['POST'])
@auth_required
# @validate_request(CreateAssetViewRequest)
# @validate_response(CreateAssetViewResponse)
async def create_asset_view():
    """
    创建资产视图

    创建新的资产视图，用于查看和管理资产数据。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - tag (string, required): 视图标签
        - viewType (string, required): 视图类型
        - config (object, required): 视图配置
        - public (boolean, optional): 是否公开，默认false

    Responses:
        200: 创建成功
            - status: 状态码 (200)
            - data: 创建的视图信息 (object)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "tag": "视图标签",
            "viewType": "sell",
            "config": {...},
            "public": false
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "sid": "view_id",
                "tag": "视图标签"
            }
        }
    """
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
        return {"status": 200, "message": "创建监控成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建资产视图失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建资产视图失败"}), 500


@api_EVE_asset_bp.route('/deleteAssetView', methods=['DELETE'])
@auth_required
# @validate_request(DeleteAssetViewRequest)
# @validate_response(MessageResponse)
async def delete_asset_view():
    """
    删除资产视图

    删除指定的资产视图。

    Tags:
        - EVE资产管理

    Security:
        - Bearer: []

    Request Body:
        - sid (string, required): 资产视图SID

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "sid": "view_id"
        }

    Example Response:
        {
            "status": 200,
            "message": "删除成功"
        }
    """
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
        return {"status": 200, "message": "删除成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除资产视图失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除资产视图失败"}), 500
