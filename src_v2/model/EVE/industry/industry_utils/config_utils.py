# 标准库导入
import base64
import hashlib
import json
from datetime import datetime

# 第三方库导入
from cryptography.fernet import Fernet

# 本地导入 - 核心工具
from src_v2.core.config.config import config
from src_v2.core.database.connect_manager import get_postgres_manager as postgres_manager
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustrryPlanConfigFlowPresetDBUtils,
    EveIndustryPlanConfigFlowConfigDBUtils,
    EveIndustryPlanConfigFlowDBUtils,
)
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils as NAU
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.utils import KahunaException, logger

from .default_config import (  # 默认预设plan config list
    DEFAULT_ALL_CONFIG_FLOW_PRESET,
    DEFAULT_BLUEPRINT_CONFIG,
    DEFAULT_MATERIAL_CONFIG,
    DEFAULT_MAX_JOB_SPLIT_COUNT_CONFIG,
    DEFAULT_STRUCTURE_ASSIGN_CONFIG,
    DEFAULT_STRUCTURE_RIG_CONFIG,
)

VIRTUAL_STRUCTURE_DICT = {
    "虚拟-Sotiyo": 1,
    "虚拟-Tatara": 2,
    "虚拟-Raitaru": 3,
    "虚拟-Azbel": 4,
    "虚拟-Athanor": 5
}
VIRTUAL_STRUCTURE_ID_DICT = {
    1: "虚拟-Sotiyo",
    2: "虚拟-Tatara",
    3: "虚拟-Raitaru",
    4: "虚拟-Azbel",
    5: "虚拟-Athanor"
}


async def _migrate_structure_assign_conf_structure_id(config, config_value_dict):
    """向后兼容：为 StructureAssignConf 配置迁移 structure_id

    Args:
        config: 配置对象（数据库对象）
        config_value_dict: 需要更新的配置值字典（会被修改）

    Returns:
        bool: 是否成功迁移（找到并更新了 structure_id）
    """
    # 向后兼容：如果 structure_id 不存在，根据 structure_name 查找并更新配置
    if 'structure_id' not in config.config_value and 'structure_name' in config.config_value:
        structure_name = config.config_value['structure_name']
        structure_id = None

        # 检查是否为虚拟建筑
        if structure_name in VIRTUAL_STRUCTURE_DICT:
            structure_id = VIRTUAL_STRUCTURE_DICT[structure_name]
        else:
            # 从 Neo4j 中查找真实建筑
            try:
                structure_nodes = await NAU.get_structure_nodes()
                for node in structure_nodes:
                    if node.get('structure_name') == structure_name:
                        structure_id = node.get('structure_id')
                        break
            except Exception as e:
                logger.warning(f"查找建筑 {structure_name} 失败: {e}")

        # 如果找到了 structure_id，更新配置并保存
        if structure_id is not None:
            config.config_value['structure_id'] = structure_id
            await EveIndustryPlanConfigFlowConfigDBUtils.merge(config)
            config_value_dict['structure_id'] = structure_id
            return True
        # 如果找不到，跳过（不报错）
        return False
    return False


async def create_config_flow_config(user_id: str, data):
    """创建配置流配置

    Args:
        user_id: 用户ID
        data: 配置数据，包含 config_type 和 config_value
    """
    # 数据检查
    if "config_type" not in data or "config_value" not in data or not data['config_value']:
        raise KahunaException(
            "config_type 和 config_value 不能为空，且 config_value 不能为空")
    if data['config_type'] == 'StructureRigConfig':
        if "structure_id" not in data['config_value'] or "time_eff_level" not in data['config_value'] or "mater_eff_level" not in data['config_value']:
            raise KahunaException(
                "StructureRigConfig 的 structure_id、time_eff_level 和 mater_eff_level 不能为空")
    if data['config_type'] == 'StructureAssignConf':
        if "structure_id" not in data['config_value'] or "structure_name" not in data['config_value']:
            raise KahunaException(
                "StructureAssignConf 的 structure_id 和 structure_name 不能为空")
    if data['config_type'] == 'MaxJobSplitCountConf':
        if "judge_type" not in data['config_value']:
            raise KahunaException("MaxJobSplitCountConf 的 judge_type 不能为空")
        if data['config_value']['judge_type'] == 'count' and not data['config_value'].get('max_count', None):
            raise KahunaException("MaxJobSplitCountConf 的 max_count 不能为空")
        if data['config_value']['judge_type'] == 'time' and (not data['config_value'].get('max_time_day', None) and not data['config_value'].get('max_time_date', None)):
            raise KahunaException("MaxJobSplitCountConf 的 max_time_day 不能为空")
    if data['config_type'] == 'MaterialTagConf' and not data['config_value'].get('keyword_groups', None):
        raise KahunaException("MaterialTagConf 的 keyword_groups 不能为空")
    if data['config_type'] == 'DefaultBlueprintConf' and not data['config_value'].get('keyword_groups', None):
        raise KahunaException("DefaultBlueprintConf 的 keyword_groups 不能为空")
    if data['config_type'] == 'LoadAssetConf' and not data['config_value'].get('tag', None):
        raise KahunaException("LoadAssetConf 的 container_tag 不能为空")

    config_obj = EveIndustryPlanConfigFlowConfigDBUtils.get_obj()
    config_obj.id = None  # 确保ID为None，让数据库自动生成
    config_obj.user_name = user_id
    config_obj.config_type = data['config_type']
    config_obj.config_value = data['config_value']
    await EveIndustryPlanConfigFlowConfigDBUtils.save_obj(config_obj)


async def fetch_recommended_presets(user_id: str, preset_name: str = "default_bp_and_material"):
    """获取推荐预设

    Args:
        user_id: 用户ID
        preset_name: 预设名称

    Returns:
        dict: 包含创建和已存在数量的统计信息 {"created": int, "existing": int}
    """

    config_list = []
    if preset_name == "default_bp_and_material":
        config_list = [
            DEFAULT_MATERIAL_CONFIG,
            DEFAULT_BLUEPRINT_CONFIG,
            DEFAULT_STRUCTURE_ASSIGN_CONFIG,
            DEFAULT_STRUCTURE_RIG_CONFIG,
            DEFAULT_MAX_JOB_SPLIT_COUNT_CONFIG
        ]

    created_count = 0
    existing_count = 0

    # 创建不存在的配置
    for config in config_list:
        for config_item in config.values():
            # 检查是否已存在相同的配置
            existing_config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_user_name_and_config_type_and_config_value(
                user_id,
                config_item['config_type'],
                config_item['config_value']
            )

            if existing_config:
                # config_tag更新
                if existing_config.config_tag != config_item['config_tag']:
                    existing_config.config_tag = config_item['config_tag']
                    await EveIndustryPlanConfigFlowConfigDBUtils.merge(existing_config)
                # 配置已存在，跳过
                existing_count += 1
            else:
                # 配置不存在，创建新配置
                config_obj = EveIndustryPlanConfigFlowConfigDBUtils.get_obj()
                config_obj.id = None  # 确保ID为None，让数据库自动生成
                config_obj.user_name = user_id
                config_obj.config_type = config_item['config_type']
                config_obj.config_value = config_item['config_value']
                config_obj.config_tag = config_item['config_tag']
                await EveIndustryPlanConfigFlowConfigDBUtils.save_obj(config_obj)
                created_count += 1

    return {"created": created_count, "existing": existing_count}


async def modify_config_flow_config(user_id: str, data, is_admin: bool = False):
    """修改配置流配置

    Args:
        user_id: 用户ID
        data: 配置数据，包含 config_id 和 config_value
        is_admin: 是否为管理员，管理员可以绕过权限检查
    """
    config_id = data['config_id']
    config_obj = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
    if not config_obj:
        raise KahunaException(f"配置不存在")

    # 检查权限：只能修改自己的配置（管理员除外）
    if not is_admin and config_obj.user_name != user_id:
        raise KahunaException(f"无权修改此配置")

    # 更新配置值
    config_obj.config_value = data['config_value']

    # 更新配置标签（如果提供）
    if 'config_tag' in data:
        config_obj.config_tag = data['config_tag'] if data['config_tag'] else None

    await EveIndustryPlanConfigFlowConfigDBUtils.merge(config_obj)


async def delete_config_flow_config(user_id: str, data):
    """删除配置流配置

    Args:
        user_id: 用户ID
        data: 包含 config_id 的数据
    """
    config_id = data['config_id']
    config_obj = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
    if not config_obj:
        raise KahunaException(f"配置不存在")

    user_config_list = []
    async for config in await EveIndustryPlanConfigFlowDBUtils.select_all_by_user_name(user_id):
        user_config_list.append(config)
    async with postgres_manager().get_session() as session:
        for config_list in user_config_list:
            if config_id in config_list.config_list:
                config_list.config_list.remove(config_id)
                await EveIndustryPlanConfigFlowDBUtils.merge(config_list, session)

        await EveIndustryPlanConfigFlowConfigDBUtils.delete_obj(config_obj)


async def get_config_flow_config_list(user_id: str):
    """获取配置流配置列表

    Args:
        user_id: 用户ID

    Returns:
        List[dict]: 配置列表
    """
    res_list = []
    async for config in await EveIndustryPlanConfigFlowConfigDBUtils.select_all_by_user_name(user_id):
        config_data = {
            "config_id": config.id,
            "config_tag": config.config_tag,
            "config_type": config.config_type,
            "config_value": config.config_value
        }
        if config.config_type == 'StructureRigConfig':
            if config.config_value['structure_id'] in VIRTUAL_STRUCTURE_ID_DICT:
                config_data['config_value'].update({
                    "structure_name": VIRTUAL_STRUCTURE_ID_DICT[config.config_value['structure_id']]
                })
            else:
                structure_info = await NIU.get_structure_node_by_id(config.config_value['structure_id'])
                config_data['config_value'].update({
                    "structure_name": structure_info.get('structure_name', None)
                })
        elif config.config_type == 'StructureAssignConf':
            # 向后兼容：迁移 structure_id
            await _migrate_structure_assign_conf_structure_id(config, config_data['config_value'])
        res_list.append(config_data)
    return res_list


async def add_config_to_plan(user_id: str, data):
    """添加配置到计划

    Args:
        user_id: 用户ID
        data: 包含 plan_name 和 config_id 的数据
    """
    plan_name = data['plan_name']
    config_id = data['config_id']
    config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
    if not config:
        raise KahunaException("配置不存在")
    plan_config_obj = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(user_id, plan_name)
    if not plan_config_obj:
        plan_config_obj = EveIndustryPlanConfigFlowDBUtils.get_obj()
        plan_config_obj.id = None  # 确保ID为None，让数据库自动生成
        plan_config_obj.user_name = user_id
        plan_config_obj.plan_name = plan_name
        plan_config_obj.config_list = [config_id]
        await EveIndustryPlanConfigFlowDBUtils.save_obj(plan_config_obj)
    else:
        if config_id in plan_config_obj.config_list:
            raise KahunaException("配置已存在")
        plan_config_obj.config_list.insert(0, config_id)
        await EveIndustryPlanConfigFlowDBUtils.merge(plan_config_obj)


async def get_config_flow_list(user_id: str, plan_name: str):
    """获取计划配置流列表

    Args:
        user_id: 用户ID
        plan_name: 计划名称

    Returns:
        List[dict]: 配置流列表
    """
    plan_config_flow_obj = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(user_id, plan_name)
    if not plan_config_flow_obj:
        return []

    config_id_list = plan_config_flow_obj.config_list
    config_list = []
    for config_id in config_id_list:
        config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
        if not config:
            logger.warning(f"配置{config_id}不存在")
            continue
        config_list.append({
            "config_id": config.id,
            "config_tag": config.config_tag,
            "config_type": config.config_type,
            "config_value": config.config_value
        })
        if config.config_type == 'StructureRigConfig':
            if config.config_value['structure_id'] in VIRTUAL_STRUCTURE_ID_DICT:
                config_list[-1]['config_value']['structure_name'] = VIRTUAL_STRUCTURE_ID_DICT[config.config_value['structure_id']]
            else:
                structure_info = await NIU.get_structure_node_by_id(config.config_value['structure_id'])
                config_list[-1]['config_value']['structure_name'] = structure_info.get(
                    'structure_name', None)
        elif config.config_type == 'StructureAssignConf':
            # 向后兼容：迁移 structure_id
            await _migrate_structure_assign_conf_structure_id(config, config_list[-1]['config_value'])
    return config_list


async def delete_config_from_plan(user_id: str, data):
    """从计划中删除配置

    Args:
        user_id: 用户ID
        data: 包含 plan_name 和 config_id 的数据
    """
    plan_name = data['plan_name']
    config_id = data['config_id']
    plan_config_flow_obj = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(user_id, plan_name)
    if not plan_config_flow_obj:
        raise KahunaException(f"配置不存在")
    plan_config_flow_obj.config_list.remove(config_id)
    await EveIndustryPlanConfigFlowDBUtils.merge(plan_config_flow_obj)


async def save_config_flow_to_plan(user_id: str, plan_name: str, data):
    """保存配置流到计划

    Args:
        user_id: 用户ID
        plan_name: 计划名称
        data: 包含 config_list 的数据
    """
    config_id_list = [d["config_id"] for d in data["config_list"]]
    config_flow_obj = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(user_id, plan_name)
    if not config_flow_obj:
        config_flow_obj = EveIndustryPlanConfigFlowDBUtils.get_obj()
        config_flow_obj.id = None  # 确保ID为None，让数据库自动生成
        config_flow_obj.user_name = user_id
        config_flow_obj.plan_name = plan_name
        config_flow_obj.config_list = config_id_list
        await EveIndustryPlanConfigFlowDBUtils.save_obj(config_flow_obj)
    else:
        config_flow_obj.config_list = config_id_list
        await EveIndustryPlanConfigFlowDBUtils.merge(config_flow_obj)


async def create_default_config_flow_preset(user_id: str):
    # 首先检查default配置是否都创建了
    await fetch_recommended_presets(user_id)

    # 获取用户所有config
    config_list = await get_config_flow_config_list(user_id)
    config_d = {
        c["config_tag"]: c for c in config_list
    }

    # 将预设的config_tag转为config_list
    preset_config_id_list = []
    for config_tag in DEFAULT_ALL_CONFIG_FLOW_PRESET:
        if config_tag in config_d:
            preset_config_id_list.append(config_d[config_tag])
    # 保存预设
    await save_config_flow_preset(user_id, "默认配置预设", preset_config_id_list)


async def save_config_flow_preset(user_id: str, preset_name: str, config_list):
    """保存配置流预设

    Args:
        user_id: 用户ID
        preset_name: 预设名称
        config_list: 配置列表（包含config_id的对象列表）

    Returns:
        None
    """
    # 提取 config_id 数组
    config_id_list = [d["config_id"] for d in config_list]

    # 检查预设名是否已存在（同一用户）
    existing_preset = await EveIndustrryPlanConfigFlowPresetDBUtils.select_by_user_name_and_preset_name(user_id, preset_name)

    # 创建预设对象
    preset_obj = EveIndustrryPlanConfigFlowPresetDBUtils.get_obj()
    if existing_preset:
        # 如果存在，使用merge方法更新
        preset_obj.id = existing_preset.id
    else:
        # 如果不存在，创建新记录
        preset_obj.id = None  # 确保ID为None，让数据库自动生成

    preset_obj.user_name = user_id
    preset_obj.preset_name = preset_name
    preset_obj.config_list = config_id_list
    await EveIndustrryPlanConfigFlowPresetDBUtils.merge(preset_obj)


async def get_config_flow_presets(user_id: str):
    """获取用户所有预设列表

    Args:
        user_id: 用户ID

    Returns:
        List[dict]: 预设列表，每个元素包含 {id, preset_name, config_list}
    """
    preset_list = []
    async for preset in await EveIndustrryPlanConfigFlowPresetDBUtils.select_all_by_user_name(user_id):
        preset_list.append({
            "id": preset.id,
            "preset_name": preset.preset_name,
            "config_list": preset.config_list
        })
    return preset_list


async def load_config_flow_preset(user_id: str, preset_id: int, plan_name: str):
    """加载预设到计划

    Args:
        user_id: 用户ID
        preset_id: 预设ID
        plan_name: 计划名称

    Returns:
        None
    """
    # 获取预设
    preset_obj = await EveIndustrryPlanConfigFlowPresetDBUtils.select_by_id(preset_id)
    if not preset_obj:
        raise KahunaException(f"预设不存在")

    # 检查权限：只能加载自己的预设
    if preset_obj.user_name != user_id:
        raise KahunaException(f"无权加载此预设")

    # 获取预设的 config_list
    config_id_list = preset_obj.config_list

    # 构建 config_list 格式（与 save_config_flow_to_plan 兼容）
    # 需要将 config_id_list 转换为包含 config_id 的对象列表
    config_list_data = [{"config_id": config_id}
                        for config_id in config_id_list]

    # 调用 save_config_flow_to_plan 应用到当前计划
    await save_config_flow_to_plan(user_id, plan_name, {"config_list": config_list_data})


def _get_encryption_key() -> bytes:
    """从配置文件中获取加密密钥并转换为Fernet可用的格式

    Returns:
        bytes: Fernet加密密钥（32字节，URL-safe base64编码）
    """
    try:
        secret_key = config.get('APP', 'SECRET_KEY', fallback='')
        if not secret_key:
            raise KahunaException(
                "配置文件中未找到 SECRET_KEY，请在 config.toml 的 [APP] 部分配置 SECRET_KEY")

        # 使用SHA256哈希将任意长度的密钥转换为32字节的密钥
        key_hash = hashlib.sha256(secret_key.encode('utf-8')).digest()
        # Fernet需要URL-safe base64编码的密钥
        fernet_key = base64.urlsafe_b64encode(key_hash)
        return fernet_key
    except KeyError:
        raise KahunaException(
            "配置文件中未找到 [APP] 部分或 SECRET_KEY，请在 config.toml 中配置")
    except Exception as e:
        raise KahunaException(f"获取加密密钥失败: {str(e)}")


def encode_share_code(config_id_list: list) -> str:
    """加密分享代码

    Args:
        config_id_list: config_id列表

    Returns:
        str: 加密后的分享代码（base64编码）
    """
    try:
        # 获取加密密钥
        key = _get_encryption_key()
        fernet = Fernet(key)

        # 将config_id_list转换为JSON字符串
        json_str = json.dumps(config_id_list)

        # 使用Fernet加密
        encrypted = fernet.encrypt(json_str.encode('utf-8'))

        # 返回base64编码的加密数据
        return encrypted.decode('utf-8')
    except KahunaException:
        raise
    except Exception as e:
        raise KahunaException(f"加密分享代码失败: {str(e)}")


def decode_share_code(share_code: str) -> list:
    """解密分享代码

    Args:
        share_code: 加密后的分享代码（base64编码）

    Returns:
        list: config_id列表
    """
    try:
        # 获取加密密钥
        key = _get_encryption_key()
        fernet = Fernet(key)

        # 解密数据
        decrypted = fernet.decrypt(share_code.encode('utf-8'))

        # 解析JSON
        config_id_list = json.loads(decrypted.decode('utf-8'))
        return config_id_list
    except KahunaException:
        raise
    except Exception as e:
        raise KahunaException(f"解密分享代码失败: {str(e)}")


async def delete_config_flow_preset(user_id: str, preset_id: int):
    """删除配置流预设

    Args:
        user_id: 用户ID
        preset_id: 预设ID

    Returns:
        None
    """
    # 获取预设
    preset_obj = await EveIndustrryPlanConfigFlowPresetDBUtils.select_by_id(preset_id)
    if not preset_obj:
        raise KahunaException("预设不存在")

    # 检查权限：只能删除自己的预设
    if preset_obj.user_name != user_id:
        raise KahunaException("无权删除此预设")

    # 删除预设
    await EveIndustrryPlanConfigFlowPresetDBUtils.delete_obj(preset_obj)


async def update_config_flow_preset_name(user_id: str, preset_id: int, preset_name: str):
    """更新配置流预设名称

    Args:
        user_id: 用户ID
        preset_id: 预设ID
        preset_name: 新预设名称（1-20字符）

    Returns:
        None
    """
    # 验证预设名称长度
    if not preset_name or len(preset_name.strip()) == 0:
        raise KahunaException("预设名称不能为空")
    if len(preset_name) > 20:
        raise KahunaException("预设名称长度不能超过20字符")

    preset_name = preset_name.strip()

    # 获取预设
    preset_obj = await EveIndustrryPlanConfigFlowPresetDBUtils.select_by_id(preset_id)
    if not preset_obj:
        raise KahunaException("预设不存在")

    # 检查权限：只能修改自己的预设
    if preset_obj.user_name != user_id:
        raise KahunaException("无权修改此预设")

    # 检查是否存在同名预设（排除当前预设）
    existing_preset = await EveIndustrryPlanConfigFlowPresetDBUtils.select_by_user_name_and_preset_name(user_id, preset_name)
    if existing_preset and existing_preset.id != preset_id:
        raise KahunaException(f"预设名称 '{preset_name}' 已存在")

    # 更新预设名称
    preset_obj.preset_name = preset_name
    await EveIndustrryPlanConfigFlowPresetDBUtils.merge(preset_obj)


async def share_config_flow_preset(user_id: str, preset_id: int) -> str:
    """分享配置流预设（生成分享代码）

    Args:
        user_id: 用户ID
        preset_id: 预设ID

    Returns:
        str: 分享代码
    """
    # 获取预设
    preset_obj = await EveIndustrryPlanConfigFlowPresetDBUtils.select_by_id(preset_id)
    if not preset_obj:
        raise KahunaException("预设不存在")

    # 检查权限：只能分享自己的预设
    if preset_obj.user_name != user_id:
        raise KahunaException("无权分享此预设")

    # 获取config_id_list并加密
    config_id_list = preset_obj.config_list
    share_code = encode_share_code(config_id_list)
    return share_code


async def load_shared_config_flow_preset(user_id: str, share_code: str):
    """载入分享的配置流预设（解密并复制config）

    Args:
        user_id: 用户ID
        share_code: 分享代码

    Returns:
        list: 创建的config列表
    """
    # 解密分享代码
    config_id_list = decode_share_code(share_code)

    # 按顺序处理config，检查是否已存在，不存在则新建，存在则复用
    saved_config_ids = []
    created_configs = []

    for config_id in config_id_list:
        config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
        if not config:
            logger.warning(f"配置 {config_id} 不存在，跳过")
            continue

        # 跳过LoadAssetConf类型
        if config.config_type == 'LoadAssetConf':
            logger.info(f"跳过LoadAssetConf类型配置: {config_id}")
            continue

        # 检查是否已存在相同的配置
        existing_config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_user_name_and_config_type_and_config_value(
            user_id,
            config.config_type,
            config.config_value
        )

        if existing_config:
            # 配置已存在，使用已存在的id
            saved_config_id = existing_config.id
            logger.info(f"配置已存在，使用已存在的配置ID: {saved_config_id}")

            # 如果config_tag不同，更新config_tag
            if existing_config.config_tag != config.config_tag:
                existing_config.config_tag = config.config_tag
                await EveIndustryPlanConfigFlowConfigDBUtils.merge(existing_config)
        else:
            # 配置不存在，创建新config
            new_config_obj = EveIndustryPlanConfigFlowConfigDBUtils.get_obj()
            new_config_obj.id = None  # 确保ID为None，让数据库自动生成
            new_config_obj.user_name = user_id
            new_config_obj.config_type = config.config_type
            new_config_obj.config_value = config.config_value
            new_config_obj.config_tag = config.config_tag
            await EveIndustryPlanConfigFlowConfigDBUtils.save_obj(new_config_obj)
            saved_config_id = new_config_obj.id
            logger.info(f"创建新配置，ID: {saved_config_id}")

        # 保存id（按顺序）
        saved_config_ids.append(saved_config_id)
        created_configs.append({
            "config_id": saved_config_id,
            "config_type": config.config_type,
            "config_tag": config.config_tag
        })

    # 使用保存的id按照顺序保存preset
    if saved_config_ids:
        # 生成预设名称（带时间戳避免重复）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        preset_name = f"分享的预设_{timestamp}"

        # 构建config_list格式（包含config_id的对象列表）
        preset_config_list = [{"config_id": config_id}
                              for config_id in saved_config_ids]

        # 保存preset
        await save_config_flow_preset(user_id, preset_name, preset_config_list)
        logger.info(f"成功保存预设: {preset_name}，包含 {len(saved_config_ids)} 个配置")

    return created_configs


async def get_config_flow_preset_detail(user_id: str, preset_id: int):
    """获取配置流预设详情（包含完整config_list）

    Args:
        user_id: 用户ID
        preset_id: 预设ID

    Returns:
        dict: {preset_name: str, config_list: List[ConfigObject]}
    """
    # 获取预设
    preset_obj = await EveIndustrryPlanConfigFlowPresetDBUtils.select_by_id(preset_id)
    if not preset_obj:
        raise KahunaException("预设不存在")

    # 检查权限：只能获取自己的预设详情
    if preset_obj.user_name != user_id:
        raise KahunaException("无权访问此预设")

    # 获取config_list
    config_id_list = preset_obj.config_list
    config_list = []
    for config_id in config_id_list:
        config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
        if not config:
            logger.warning(f"配置{config_id}不存在")
            continue
        config_data = {
            "config_id": config.id,
            "config_tag": config.config_tag,
            "config_type": config.config_type,
            "config_value": config.config_value
        }
        if config.config_type == 'StructureRigConfig':
            if config.config_value['structure_id'] in VIRTUAL_STRUCTURE_ID_DICT:
                config_data['config_value'].update({
                    "structure_name": VIRTUAL_STRUCTURE_ID_DICT[config.config_value['structure_id']]
                })
            else:
                structure_info = await NIU.get_structure_node_by_id(config.config_value['structure_id'])
                config_data['config_value'].update({
                    "structure_name": structure_info.get('structure_name', None)
                })
        elif config.config_type == 'StructureAssignConf':
            # 向后兼容：迁移 structure_id
            await _migrate_structure_assign_conf_structure_id(config, config_data['config_value'])
        config_list.append(config_data)

    return {
        "preset_name": preset_obj.preset_name,
        "config_list": config_list
    }


async def save_config_flow_preset_config(user_id: str, preset_id: int, config_list: list):
    """保存配置流预设配置

    Args:
        user_id: 用户ID
        preset_id: 预设ID
        config_list: 配置列表（包含config_id的对象列表）

    Returns:
        None
    """
    # 获取预设
    preset_obj = await EveIndustrryPlanConfigFlowPresetDBUtils.select_by_id(preset_id)
    if not preset_obj:
        raise KahunaException("预设不存在")

    # 检查权限：只能保存自己的预设配置
    if preset_obj.user_name != user_id:
        raise KahunaException("无权保存此预设配置")

    # 提取 config_id 数组
    config_id_list = [d["config_id"] for d in config_list]

    # 更新预设的config_list
    preset_obj.config_list = config_id_list
    await EveIndustrryPlanConfigFlowPresetDBUtils.merge(preset_obj)
