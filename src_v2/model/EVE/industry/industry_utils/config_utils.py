# 本地导入 - 核心工具
from src_v2.core.database.connect_manager import postgres_manager
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustryPlanConfigFlowConfigDBUtils,
    EveIndustryPlanConfigFlowDBUtils
)
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.utils import KahunaException

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

async def create_config_flow_config(user_id: str, data):
    """创建配置流配置
    
    Args:
        user_id: 用户ID
        data: 配置数据，包含 config_type 和 config_value
    """
    config_obj = EveIndustryPlanConfigFlowConfigDBUtils.get_obj()
    config_obj.id = None  # 确保ID为None，让数据库自动生成
    config_obj.user_name = user_id
    config_obj.config_type = data['config_type']
    config_obj.config_value = data['config_value']
    await EveIndustryPlanConfigFlowConfigDBUtils.save_obj(config_obj)


async def fetch_recommended_presets(user_id: str):
    """获取推荐预设
    
    Args:
        user_id: 用户ID
    """
    from ..config import DEFAULT_MATERIAL_CONFIG, DEFAULT_BLUEPRINT_CONFIG

    for config in DEFAULT_MATERIAL_CONFIG:
        config_obj = EveIndustryPlanConfigFlowConfigDBUtils.get_obj()
        config_obj.id = None  # 确保ID为None，让数据库自动生成
        config_obj.user_name = user_id
        config_obj.config_type = config['config_type']
        config_obj.config_value = config['config_value']
        await EveIndustryPlanConfigFlowConfigDBUtils.save_obj(config_obj)
    for config in DEFAULT_BLUEPRINT_CONFIG:
        config_obj = EveIndustryPlanConfigFlowConfigDBUtils.get_obj()
        config_obj.id = None  # 确保ID为None，让数据库自动生成
        config_obj.user_name = user_id
        config_obj.config_type = config['config_type']
        config_obj.config_value = config['config_value']
        await EveIndustryPlanConfigFlowConfigDBUtils.save_obj(config_obj)


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
    async with postgres_manager.get_session() as session:
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
        raise KahunaException(f"配置不存在")
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
            raise KahunaException(f"配置已存在")
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
            raise KahunaException(f"配置{config_id}不存在")
        config_list.append({
            "config_id": config.id,
            "config_type": config.config_type,
            "config_value": config.config_value
        })
        if config.config_type == 'StructureRigConfig':
            if config.config_value['structure_id'] in VIRTUAL_STRUCTURE_ID_DICT:
                config_list[-1]['config_value']['structure_name'] = VIRTUAL_STRUCTURE_ID_DICT[config.config_value['structure_id']]
            else:
                structure_info = await NIU.get_structure_node_by_id(config.config_value['structure_id'])
                config_list[-1]['config_value']['structure_name'] = structure_info.get('structure_name', None)
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

