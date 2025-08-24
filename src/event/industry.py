# import logger
import json
import os
from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime, timedelta
from time import sleep

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, BaseMessageComponent, Plain

# kahuna model
from ..service.asset_server import AssetManager
from ..service.character_server import CharacterManager
from ..service.industry_server.industry_analyse import IndustryAnalyser
from ..service.user_server.user_manager import UserManager
from ..service.evesso_server.eveesi import characters_character
from ..service.market_server import MarketManager, PriceService
from ..service.market_server.marker import MarketHistory, FRT_4H_STRUCTURE_ID, JITA_TRADE_HUB_STRUCTURE_ID, PIMI_STRUCTURE_LIST
from ..service.asset_server.asset_container import AssetContainer
from ..service.industry_server.industry_config import IndustryConfigManager, BPManager
from ..service.industry_server.structure import StructureManager
from ..service.industry_server.industry_manager import IndustryManager
from ..service.industry_server.industry_advice import IndustryAdvice
from ..service.industry_server.order import order_manager
from ..service.sde_service.utils import SdeUtils
from ..service.feishu_server.feishu_kahuna import FeiShuKahuna
from ..service.log_server import logger
from ..service.picture_render_server.picture_render import PictureRender
from ..service.industry_server.third_provider import provider_manager as pm
from ..service.config_server.config import config


from ..utils import (
    KahunaException,
    get_user_tmp_cache_prefix,
    get_beijing_utctime,
    get_debug_qq
)
from ..utils.path import TMP_PATH

calculate_lock = asyncio.Lock()
async def try_acquire_lock(lock, timeout=0.01):
    """尝试非阻塞地获取锁"""
    try:
        await asyncio.wait_for(lock.acquire(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False

def print_name_fuzz_list(event: AstrMessageEvent, type_name: str):
    fuzz_list = SdeUtils.fuzz_type(type_name, list_len=10)
    if fuzz_list:
        fuzz_rely = (f"你是否在寻找：\n")
        fuzz_rely += '\n'.join(fuzz_list)
        return event.plain_result(fuzz_rely)

def get_user(event: AstrMessageEvent):
    if get_debug_qq():
        user_qq = int(get_debug_qq())
    else:
        user_qq = int(event.get_sender_id())
    
    return user_qq

class AssetEvent():
    @staticmethod
    async def get_owner_id(owner_type: str, character_name: str, character) -> int:
        if owner_type == "corp":
            character_info = await characters_character(character.character_id)
            owner_id = int(character_info["corporation_id"])
        elif owner_type == "character":
            owner_id = character.character_id
        else:
            raise KahunaException("owner_type must be 'corp' or 'character'")

        return owner_id

    @classmethod
    async def refall(cls, event: AstrMessageEvent):
        await AssetManager.refresh_all_asset(force=True)

        return event.plain_result("执行完成")

    @staticmethod
    async def owner_add(event: AstrMessageEvent, owner_type: str, character_name: str):
        user_qq = get_user(event)
        character_name = " ".join(event.get_message_str().split(" ")[4:])
        character = CharacterManager.get_character_by_name_qq(character_name, user_qq)

        owner_id = await AssetEvent.get_owner_id(owner_type, character_name, character)

        asset = await AssetManager.create_asset(user_qq, owner_type, owner_id, character)
        return event.plain_result(f"库存已成功创建。\n"
                                  f"库存条目 {await asset.asset_item_count()}")

    @staticmethod
    async def owner_refresh(event: AstrMessageEvent, owner_type: str, character_name: str):
        user_qq = get_user(event)
        character_name = " ".join(event.get_message_str().split(" ")[4:])
        character = CharacterManager.get_character_by_name_qq(character_name, user_qq)

        owner_id = await AssetEvent.get_owner_id(owner_type, character_name, character)

        set = await AssetManager.refresh_asset(owner_type, owner_id)
        return event.plain_result("刷新完成")

    @staticmethod
    async def container_add(event: AstrMessageEvent, location_id: int, location_flag: str, target_qq: int, container_name: str):
        user_qq = get_user(event)

        main_character_id = UserManager.get_main_character_id(user_qq)
        main_character = CharacterManager.get_character_by_id(main_character_id)
        container = await AssetManager.add_container(target_qq, location_id, location_flag, container_name, user_qq, main_character.ac_token)
        print_info = (f"已授权 {target_qq} 使用属于 {user_qq} 的库存: {location_id}。\n")
        return event.plain_result(print_info)

    @staticmethod
    def container_ls(event: AstrMessageEvent):
        user_qq = get_user(event)

        print_str = "你可访问以下库存：\n"
        for container in AssetManager.container_dict.values():
            if (user_qq == container.asset_owner_qq):
                logger.info(f'{user_qq} == container.asset_owner_qq')
                print_str += f"{container}\n"
        return event.plain_result(print_str)

    @staticmethod
    async def container_find(event: AstrMessageEvent, secret_type: str):
        user_qq = get_user(event)
        secret_type = " ".join(event.get_message_str().split(" ")[3:])
        if SdeUtils.maybe_chinese(secret_type):
            type_id = SdeUtils.get_id_by_name(secret_type)
        else:
            type_id = SdeUtils.get_id_by_name(secret_type)
        if not type_id:
            return print_name_fuzz_list(event, secret_type)

        main_character_id = UserManager.get_main_character_id(user_qq)
        main_character = CharacterManager.get_character_by_id(main_character_id)
        container_info = await AssetContainer.find_container(secret_type, user_qq, main_character)

        print_info = f"找到{len(container_info)}个符合条件的库存空间。\n"
        for container in container_info:
            print_info += (f"\n建筑名：{container['name']} 数量：{container['exist_quantity']}\n"
                           f"建筑类型：{container['structure_type']}\n"
                           f"星系：{container['system']}\n"
                           f"添加库存指令：.asset container add {container['location_id']} {container['location_flag']} [授权目标qq] [库存空间别名]\n")
        return event.plain_result(print_info)

    @staticmethod
    async def container_settag(event: AstrMessageEvent, location_id_list: str, tag: str):
        user_qq = get_user(event)
            
        location_id_list = [int(lid) for lid in location_id_list.split(",")]
        success_list = await AssetManager.set_container_tag([(user_qq, location_id) for location_id in location_id_list], tag)

        print_str = "成功设置以下库存tag：\n"
        for container in success_list:
            print_str += f"{container.asset_location_id}: {container.tag}\n"


        return event.plain_result(print_str)


class IndsEvent:
    @staticmethod
    async def matcher_create(event: AstrMessageEvent, matcher_name: str, matcher_type: str):
        user_qq = get_user(event)
        if matcher_type not in IndustryConfigManager.matcher_type_set:
            raise KahunaException(f"matcher_type {matcher_type} must be {IndustryConfigManager.matcher_type_set}")
        matcher = await IndustryConfigManager.add_matcher(matcher_name, user_qq, matcher_type)

        return event.plain_result(f"已为用户 {user_qq} 添加适配器 {matcher.matcher_name}")

    @staticmethod
    async def matcher_del(event: AstrMessageEvent, matcher_name: str):
        user_qq = get_user(event)
        delete_matcher = await IndustryConfigManager.delete_matcher(matcher_name, user_qq)
        return event.plain_result(f"已删除工业系数匹配器： {delete_matcher.matcher_name}")

    @staticmethod
    def matcher_ls(event: AstrMessageEvent):
        user_qq = get_user(event)
        matcher_list = IndustryConfigManager.get_user_matcher(user_qq)

        res_str = f"您可以使用以下工业系数匹配器：\n"
        for matcher in matcher_list:
            res_str += f"  {matcher.matcher_type} type matcher: {matcher.matcher_name}\n"

        return event.plain_result(res_str)

    @staticmethod
    async def matcher_info(event: AstrMessageEvent, matcher_name: str):
        user_qq = get_user(event)
        matcher = IndustryConfigManager.matcher_dict.get(matcher_name, None)
        if not matcher or matcher.user_qq != user_qq:
            return event.plain_result("匹配器不存在。")

        res = f"{matcher.matcher_name}: type:{matcher.matcher_type}\n"

        for matcher_types, matcher_datas in matcher.matcher_data.items():
            prefix = ""
            res += f"{prefix}├── {matcher_types}:\n"
            for matcher_key, matcher_data in matcher_datas.items():
                prefix = "├── "
                if matcher.matcher_type == "structure":
                    matcher_data = (await StructureManager.get_structure(matcher_data)).name
                res += f"{prefix}├── {matcher_key}: {matcher_data}\n"

        return event.plain_result(res)

    @staticmethod
    async def matcher_set(event: AstrMessageEvent, matcher_name:str, matcher_key_type: str):
        config_data = event.get_message_str().split(" ")[5:]
        user_qq = get_user(event)

        matcher = IndustryConfigManager.get_matcher_of_user_by_name(matcher_name, user_qq)
        if not matcher:
            return event.plain_result("未找到匹配器，可用指令 .Inds matcher ls 查询可用匹配器")

        if matcher_key_type not in matcher.matcher_data:
            return event.plain_result(f"matcher_key_type匹配器关键字必须为: {[matcher.matcher_data.keys()]}")

        def check_match_key(match_key):
            # 确认信息方法
            if matcher_key_type == "bp" and not BPManager.get_bp_id_by_pbpname(matcher_key):
                return False, event.plain_result("{matcher_key}: 不存在的蓝图，请先使用sde type指令确认物品属性")
            elif matcher_key_type == "market_group" and SdeUtils.get_market_groupid_by_name(matcher_key) not in SdeUtils.get_market_group_tree():
                return False, event.plain_result(f"{matcher_key}: 不存在的市场类别，请先使用sde type指令确认物品属性")
            elif matcher_key_type == "group" and not SdeUtils.get_groupid_by_groupname(matcher_key):
                return False, event.plain_result(f"{matcher_key}: 不存在的组类别，请先使用sde type指令确认物品属性")
            elif matcher_key_type == "meta" and not SdeUtils.get_metadid_by_metaname(matcher_key):
                return False, event.plain_result(f"{matcher_key}: 不存在的组类别，请先使用sde type指令确认物品属性")
            return True, None

        if matcher.matcher_type == "bp" and len(config_data) >= 3 and config_data[-2].isdigit() and config_data[-1].isdigit():
            matcher_key = " ".join(config_data[:-2])
            mater_eff = float(f"{1 - (int(config_data[-2]) / 100):.2f}")
            time_eff = float(f"{1 - (int(config_data[-1]) / 100):.2f}")

            # 确认信息无误
            matche_key_check, res = check_match_key(matcher_key)
            if not matche_key_check:
                return res
            # 如果关键词类型为bp，标准化为英文
            if matcher_key_type == "bp":
                matcher_key = SdeUtils.get_name_by_id(SdeUtils.get_id_by_name(matcher_key))

            matcher.matcher_data[matcher_key_type][matcher_key] = {"mater_eff": mater_eff, "time_eff": time_eff}
            await matcher.insert_to_db()
            return event.plain_result("已配置，可以使用Inds matcher info 查看详情。")

        elif matcher.matcher_type == "structure" and len(config_data) >= 2 and config_data[-1].isdigit():
            matcher_key = " ".join(config_data[:-1])
            structure_id = int(config_data[-1])

            # 确认信息无误
            matche_key_check, res = check_match_key(matcher_key)
            if not matche_key_check:
                return res
            if matcher_key_type == "bp":
                matcher_key = SdeUtils.get_name_by_id(SdeUtils.get_id_by_name(matcher_key))

            character = CharacterManager.get_character_by_id(UserManager.get_main_character_id(user_qq))
            structure = await StructureManager.get_structure(structure_id, character.ac_token)
            if not structure:
                return event.plain_result("获取建筑信息失败")

            matcher.matcher_data[matcher_key_type][matcher_key] = structure.structure_id
            await matcher.insert_to_db()

            return event.plain_result("已配置，可以使用Inds matcher info 查看详情。")

        elif matcher.matcher_type == "prod_block" and len(config_data) >= 2:
            matcher_key = " ".join(config_data[:-1])
            block_level = int(config_data[-1])

            # 确认信息无误
            matche_key_check, res = check_match_key(matcher_key)
            if not matche_key_check:
                return res
            if matcher_key_type == "bp":
                matcher_key = SdeUtils.get_name_by_id(SdeUtils.get_id_by_name(matcher_key))

            matcher.matcher_data[matcher_key_type][matcher_key] = block_level
            await matcher.insert_to_db()

            return event.plain_result("已配置，可以使用Inds matcher info 查看详情。")

        return event.plain_result('matcher_type 未匹配分支。')

    @staticmethod
    async def matcher_unset(event: AstrMessageEvent, matcher_name:str, matcher_key_type: str):
        config_data = event.get_message_str().split(" ")[5:]
        user_qq = get_user(event)

        matcher = IndustryConfigManager.get_matcher_of_user_by_name(matcher_name, user_qq)
        if not matcher:
            return event.plain_result("未找到匹配器，可用指令 .Inds matcher ls 查询可用匹配器")

        if matcher.matcher_type in IndustryConfigManager.matcher_type_set:
            matcher_key = " ".join(config_data[:-1])

            if matcher_key_type not in matcher.matcher_data:
                return event.plain_result(f"matcher_key_type匹配器关键字必须为: {[matcher.matcher_data.keys()]}")
            if matcher_key in matcher.matcher_data[matcher_key_type]:
                matcher.matcher_data[matcher_key_type].pop(matcher_key)
                await matcher.insert_to_db()
            return event.plain_result("已配置，可以使用Inds matcher info 查看详情。")
        return event.plain_result('matcher_type 未匹配分支。')

    @staticmethod
    def structure_ls(event: AstrMessageEvent):
        structure_list = StructureManager.get_all_structure()
        print_list = []
        for structure in structure_list:
            print_list.append(f"id: {structure.structure_id}\n"
                              f"Type: {SdeUtils.get_name_by_id(structure.type_id)}\n"
                              f"Name: {structure.name}\n"
                              f"rig: {structure.mater_rig_level}-{structure.time_rig_level}\n")
        return event.plain_result("\n".join(print_list))

    @staticmethod
    async def structure_info(event: AstrMessageEvent, structure_id: int):
        user_qq = get_user(event)
        character = CharacterManager.get_character_by_id(UserManager.get_main_character_id(user_qq))
        structure = await StructureManager.get_structure(structure_id, character.ac_token)
        return event.plain_result(
            f"name: {structure.name}\n"
            f"id: {structure.structure_id}\n"
            f"type: {SdeUtils.get_name_by_id(structure.type_id)}\n"
            f"mater_rig_level: {structure.mater_rig_level}\n"
            f"time_rig_level: {structure.time_rig_level}\n"
            f"system: {structure.system}\n"
        )

    @staticmethod
    async def structure_set(event: AstrMessageEvent, structure_id: int, mater_rig_level: int, time_rig_level: int):
        if mater_rig_level < 0 or mater_rig_level > 2 \
            or time_rig_level < 0 or time_rig_level > 2:
            return event.plain_result("rig_level must be 0, 1 or 2")
        user_qq = get_user(event)
        character = CharacterManager.get_character_by_id(UserManager.get_main_character_id(user_qq))
        structrue = await StructureManager.get_structure(structure_id, character.ac_token)
        structrue.mater_rig_level = mater_rig_level
        structrue.time_rig_level = time_rig_level
        await structrue.insert_to_db()

        return event.plain_result(
            f"{structrue.name} {SdeUtils.get_name_by_id(structrue.type_id)} 已配置 "
            f"材料插等级{mater_rig_level} 时间插等级{time_rig_level}"
        )

    @staticmethod
    async def plan_setprod(event: AstrMessageEvent, plan_name: str):
        user_qq = get_user(event)
        config_data = event.get_message_str().split(" ")[4:]
        prod_name = " ".join(config_data[:-1])
        quantity = config_data[-1]
        if not quantity.isdigit():
            raise KahunaException("quantity must be digit")

        quantity = int(quantity)
        if not SdeUtils.get_id_by_name(prod_name):
            return print_name_fuzz_list(event, prod_name)
        user = UserManager.get_user(user_qq)
        await user.set_plan_product(plan_name, prod_name, quantity)
        res_str = (f"计划已添加，当前计划：\n"
                   f"{plan_name}:\n")
        for index, plan in enumerate(user.user_data.plan[plan_name]["plan"]):
            res_str += f"  |-{index + 1}.{plan[0]}: {plan[1]}\n"

        return event.plain_result(res_str)

    @staticmethod
    async def plan_setcycletime(event: AstrMessageEvent, plan_name:str, time_type: str, hour: int):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if time_type == 'reac':
            await user.set_reac_cycle_time(plan_name, hour)
        elif time_type == 'manu':
            await user.set_manu_cycle_time(plan_name, hour)
        else:
            return event.plain_result(f"args: [plan name] [reac/manu] [hour]")

        return event.plain_result(f"执行完成。计划{plan_name}的{time_type}最长流程时间已设置为{hour}小时")

    @staticmethod
    async def plan_create(event: AstrMessageEvent, plan_name: str,
                    bp_matcher_name: str, st_matcher_name: str, prod_block_matcher_name: str):
        user_qq = get_user(event)
        bp_matcher = IndustryConfigManager.get_matcher_of_user_by_name(bp_matcher_name, user_qq)
        st_matcher = IndustryConfigManager.get_matcher_of_user_by_name(st_matcher_name, user_qq)
        prod_block_matcher = IndustryConfigManager.get_matcher_of_user_by_name(prod_block_matcher_name, user_qq)
        user = UserManager.get_user(user_qq)
        await user.create_plan(plan_name, bp_matcher, st_matcher, prod_block_matcher)

        return event.plain_result("计划已创建")

    @staticmethod
    def plan_ls(event: AstrMessageEvent, plan_name: str):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)

        plan_detail = user.user_data.get_plan_detail(plan_name)

        return event.plain_result(plan_detail)

    @staticmethod
    async def plan_delprod(event: AstrMessageEvent, plan_name: str, index_list: str):
        user_qq = get_user(event)
        index_list = index_list.split(",")
        index_list = [int(index) for index in index_list]
        index_list.sort(reverse=True)

        user = UserManager.get_user(user_qq)
        for index in index_list:
            await user.delete_plan_prod(plan_name, index - 1)

        return event.plain_result("执行完成")

    @staticmethod
    async def plan_changeindex(event: AstrMessageEvent, plan_name: str, index: int, target_index: int):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)

        if not plan_name in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")

        plan_len = len(user.user_data.plan[plan_name]["plan"])
        if index < 1 or index > plan_len:
            raise KahunaException(f"index {index} out of range")
        if target_index < 1 or target_index > plan_len:
            raise KahunaException(f"target_index {target_index} out of range")

        plan = user.user_data.plan[plan_name]["plan"].pop(index - 1)
        user.user_data.plan[plan_name]["plan"].insert(target_index - 1, plan)
        await user.insert_to_db()

        return event.plain_result("执行完成。")

    @staticmethod
    async def plan_delplan(event: AstrMessageEvent, plan_name: str):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        await user.delete_plan(plan_name)

        return event.plain_result("执行完成")

    @staticmethod
    async def plan_hidecontainer(event: AstrMessageEvent, plan_name: str, container_id: int):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if plan_name not in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")

        await user.add_container_block(plan_name, container_id)
        return event.plain_result("执行完成")

    @staticmethod
    async def plan_unhidecontainer(event: AstrMessageEvent, plan_name: str, container_id: int):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if plan_name not in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")

        await user.del_container_block(plan_name, container_id)
        return event.plain_result("执行完成")

    @staticmethod
    async def plan_add_coop_user(event: AstrMessageEvent, plan_name: str, coop_qq: int):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if plan_name not in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")
        if not UserManager.user_exists(coop_qq):
            raise KahunaException(f"coop_qq {coop_qq} not exist")
        await user.add_plan_coop_user(plan_name, coop_qq)

        coop_user = UserManager.get_user(coop_qq)
        character_count = len(list(coop_user.user_data.alias.keys())) + 1 if user.main_character_id else 0

        return event.plain_result(f"已向计划{plan_name} 添加合作者 {coop_qq}的{character_count}个角色。")

    @staticmethod
    async def plan_del_coop_user(event: AstrMessageEvent, plan_name: str, coop_qq: int):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if plan_name not in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")
        if not UserManager.user_exists(coop_qq):
            raise KahunaException(f"coop_qq {coop_qq} not exist")

        await user.del_plan_coop_user(plan_name, coop_qq)

        return event.plain_result(f"已向计划{plan_name} 移除合作者 {coop_qq}")

    @staticmethod
    async def rp_plan(event: AstrMessageEvent, plan_name: str):
        if await try_acquire_lock(calculate_lock, 1):
            try:
                if AssetManager.refresh_flag:
                    yield event.plain_result('资产表正在刷新。刷新完成后会自动开始计算。请稍等。')
                    while AssetManager.refresh_flag:
                        await asyncio.sleep(1)
                    AssetManager.refresh_flag = False
                user_qq = get_user(event)

                user = UserManager.get_user(user_qq)
                if plan_name not in user.user_data.plan:
                    raise KahunaException(f"plan {plan_name} not exist")

                analyser = IndustryAnalyser.get_analyser_by_plan(user, plan_name)
                analyser.bp_block_level = 2
                report = await analyser.get_work_tree_data()

                spreadsheet = FeiShuKahuna.create_user_plan_spreadsheet(user_qq, plan_name)
                FeiShuKahuna.create_default_spreadsheet(spreadsheet)
                work_tree_sheet = FeiShuKahuna.get_worktree_sheet(spreadsheet)
                FeiShuKahuna.output_work_tree(work_tree_sheet, report['work'])
                material_sheet = FeiShuKahuna.get_material_sheet(spreadsheet)
                FeiShuKahuna.output_material_tree(material_sheet, report['material'])
                work_flow_sheet = FeiShuKahuna.get_workflow_sheet(spreadsheet)
                FeiShuKahuna.output_work_flow(work_flow_sheet, report['work_flow'])
                logistic_sheet = FeiShuKahuna.get_logistic_sheet(spreadsheet)
                FeiShuKahuna.output_logistic_plan(logistic_sheet, report['logistic'])

                # 删除不可写入json的多余部分
                report.pop('logistic')
                plan_cache = get_user_tmp_cache_prefix(user_qq) + f'{plan_name}_' + 'plan_report.json'
                with open(os.path.join(TMP_PATH, plan_cache), 'w') as file:
                    cache_dict = {
                        'date': get_beijing_utctime(datetime.now()).isoformat(),
                        'data': report
                    }
                    json.dump(cache_dict, file, indent=4)

                res_str = f"执行完成, 当前计划蓝图分解:{work_tree_sheet.url}\n"
                if report['finished_index']:
                    finished_str = ''.join([f"{data['name']} x {data['quantity']}\n" for data in report['finished_index']])
                    res_str += (
                        f"检测到以下目标已完成：\n"
                        f'{finished_str}'
                        "如需删除目标请使用指令："
                    )
                    yield event.plain_result(res_str)
                    await asyncio.sleep(0.5)
                    yield event.plain_result(f".工业 计划 删除产品 {plan_name} {','.join([str(data['index']) for data in report['finished_index']])}")
                else:
                    yield event.plain_result(res_str)
            finally:
                calculate_lock.release()
        else:
            yield event.plain_result("已有计算进行中，请稍候再试。")


    @staticmethod
    async def rp_mineral_analyse(
            event: AstrMessageEvent, plan_name: str,
            material_flag: str = 'buy',
            compress_flag: str = 'buy'
    ):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if plan_name not in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")
        if material_flag not in {'buy', 'sell'}:
            return event.plain_result("material_flag must be in {buy, sell}")
        if compress_flag not in {'buy', 'sell'}:
            return event.plain_result("compress_flag must be in {buy, sell}")

        plan_cache = get_user_tmp_cache_prefix(user_qq) + f'{plan_name}_' + 'plan_report.json'
        with open(os.path.join(TMP_PATH, plan_cache), 'r') as file:
            plan_data = json.load(file)
        report_time = datetime.fromisoformat(plan_data['date'])
        report = plan_data['data']

        # 化矿分析
        minedata = report['material']['矿石']
        minedata += report['material']['冰矿产物']
        material_list = [[data[0], data[3]] for data in minedata]

        ref_res = await IndustryAdvice.material_ref_advice(material_list, material_flag, compress_flag)
        need_d = ref_res['need']
        output_str = '采购清单：\n'
        for tid, data in need_d.items():
            output_str += f"{data['name']}\t{data['need']}\n"

        pic_path = await PictureRender.render_refine_result(ref_res)
        chain = [
            Image.fromFileSystem(pic_path),
            Plain(output_str)
        ]
        return event.chain_result(chain)

    @staticmethod
    async def rp_buy_list(event: AstrMessageEvent, plan_name: str):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)

        plan_cache = get_user_tmp_cache_prefix(user_qq) + f'{plan_name}_' + 'plan_report.json'
        with open(os.path.join(TMP_PATH, plan_cache), 'r') as file:
            plan_data = json.load(file)
        report_time = datetime.fromisoformat(plan_data['date'])
        report = plan_data['data']

        asset = await pm.get_all_assets()
        new_asset = {}
        for k, data in asset.items():
            new_asset[k] = {}
            for tid, quantity in data.items():
                new_asset[k][tid] = {
                    'id': tid,
                    'name': SdeUtils.get_name_by_id(tid),
                    'cn_name': SdeUtils.get_cn_name_by_id(tid),
                    'quantity': quantity
                }

        plan_cache = get_user_tmp_cache_prefix(user_qq) + f'{plan_name}_' + 'plan_report.json'
        with open(os.path.join(TMP_PATH, plan_cache), 'r') as file:
            plan_data = json.load(file)
        report_time = datetime.fromisoformat(plan_data['date'])
        report = plan_data['data']

        lack_material = report['material']
        buy_data = {}
        for k, data in report['material'].items():
            if not data:
                continue
            new_data = [
                {'id': d[0],
                 'icon': await PictureRender.get_eve_item_icon_base64(d[0]),
                 'name': d[1],
                 'cn_name': d[2],
                 'lack': d[3]} for d in data if d[3] > 0
            ]

            buy_data[k] = new_data

        output_path = await PictureRender.render_buy_list(buy_data, new_asset)
        chain = [
            Image.fromFileSystem(output_path)
        ]
        return event.chain_result(chain)

    @staticmethod
    async def rp_coop_pay(event: AstrMessageEvent, plan_name: str):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if plan_name not in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")

        plan_cache = get_user_tmp_cache_prefix(user_qq) + f'{plan_name}_' + 'plan_report.json'
        with open(os.path.join(TMP_PATH, plan_cache), 'r') as file:
            plan_data = json.load(file)
        report_time = datetime.fromisoformat(plan_data['date'])
        report = plan_data['data']

        coop_pay_data = report['coop_pay']
        pay_res = {}
        for cid, data in coop_pay_data.items():
            if data['total_duration'] == 0:
                continue
            cid = int(cid)
            character = CharacterManager.get_character_by_id(cid)
            work_time = data['total_duration'] / (24 * 60 * 60)
            pay_res[cid] = {
                'id': cid,
                'name': character.character_name,
                'portrait': await PictureRender.get_character_portrait_base64(cid),
                'work_time': work_time,
                'tex': data['total_tex'],
                'pay': data['total_tex'] + work_time * 1000000,
            }

        output_path = await PictureRender.render_coop_pay_report(pay_res)
        chain = [
            Image.fromFileSystem(output_path)
        ]
        return event.chain_result(chain)

    @staticmethod
    async def rp_t2mk(event: AstrMessageEvent, plan_name: str):
        if await try_acquire_lock(calculate_lock, 1):
            try:
                yield event.plain_result(f'开始计算t2常规市场数据，需要较长时间，完成前其他计算功能受到限制。')
                user_qq = get_user(event)
                user = UserManager.get_user(user_qq)
                if plan_name not in user.user_data.plan:
                    raise KahunaException(f"plan {plan_name} not exist")

                t2_ship_list = SdeUtils.get_t2_ship()
                t2_ship_id_list = [SdeUtils.get_id_by_name(name) for name in t2_ship_list]
                await MarketHistory.refresh_vale_market_history(t2_ship_id_list)

                # t2mk_data = IndustryAdvice.t2_ship_advice_report(user, plan_name)
                t2mk_dict = await IndustryAdvice.advice_report(user, plan_name, t2_ship_list)
                t2mk_data = [list(data.values()) for data in t2mk_dict.values()]

                asset_dict = {}
                sell_container_list = await AssetContainer.get_contain_id_by_qq_tag(user_qq, 'sell')
                sell_asset_result = await AssetManager.get_asset_in_container_list(
                    [container.asset_location_id for container in sell_container_list]
                )
                for asset in sell_asset_result:
                    if asset.type_id not in asset_dict:
                        asset_dict[asset.type_id] = asset.quantity
                    else:
                        asset_dict[asset.type_id] += asset.quantity
                for index, data in enumerate(t2mk_data):
                    t2mk_data[index].insert(3, asset_dict.get(data[0], 0))
                for tid in t2mk_dict.keys():
                    t2mk_dict[tid].update({'asset_exist': asset_dict.get(tid, 0)})

                plan_list = user.user_data.plan[plan_name]['plan']
                plan_dict = {SdeUtils.get_id_by_name(data[0]): data[1] for data in plan_list}
                for tid in t2mk_dict.keys():
                    t2mk_dict[tid].update({'plan_exist': plan_dict.get(int(tid), 0)})

                spreadsheet = FeiShuKahuna.create_user_plan_spreadsheet(user_qq, plan_name)
                t2_cost_sheet = FeiShuKahuna.get_t2_ship_market_sheet(spreadsheet)
                FeiShuKahuna.output_mk_sheet(t2_cost_sheet, t2mk_data)

                output_path = await PictureRender.rebder_mk_feature(t2mk_dict)
                res_str = f'报表详情 {t2_cost_sheet.url}'

                chain = [
                    Image.fromFileSystem(output_path),
                    Plain(res_str)
                ]
                yield event.chain_result(chain)
            finally:
                calculate_lock.release()
        else:
            yield event.plain_result("已有计算进行中，请稍候再试。")

    @staticmethod
    async def rp_battalship_mk(event: AstrMessageEvent, plan_name: str):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if plan_name not in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")

        battleship_list = SdeUtils.get_battleship()
        battalship_ship_id_list = [SdeUtils.get_id_by_name(name) for name in battleship_list]
        await MarketHistory.refresh_vale_market_history(battalship_ship_id_list)

        battalship_mk_dict = await IndustryAdvice.advice_report(user, plan_name, battleship_list)
        battalship_mk_data = [list(data.values()) for data in battalship_mk_dict.values()]

        asset_dict = {}
        sell_container_list = await AssetContainer.get_contain_id_by_qq_tag(user_qq, 'sell')
        sell_asset_result = await AssetManager.get_asset_in_container_list(
            [container.asset_location_id for container in sell_container_list]
        )
        for asset in sell_asset_result:
            if asset.type_id not in asset_dict:
                asset_dict[asset.type_id] = asset.quantity
            else:
                asset_dict[asset.type_id] += asset.quantity
        for index, data in enumerate(battalship_mk_data):
            battalship_mk_data[index].insert(3, asset_dict.get(data[0], 0))
        for tid in battalship_mk_dict.keys():
            battalship_mk_dict[tid].update({'asset_exist': asset_dict.get(tid, 0)})

        plan_list = user.user_data.plan[plan_name]['plan']
        plan_dict = {SdeUtils.get_id_by_name(data[0]): data[1] for data in plan_list}
        for tid in battalship_mk_dict.keys():
            battalship_mk_dict[tid].update({'plan_exist': plan_dict.get(int(tid), 0)})

        for data in battalship_mk_data:
            if data[-1] == 'Faction':
                if 'Navy' in data[1] or 'Fleet' in data[1]:
                    more_cost = 100000000
                else:
                    more_cost = 200000000
                data[6] += more_cost
                data[3] -= more_cost
                data[4] = data[3] / data[6]
                data[5] = data[10] * data[4]

        spreadsheet = FeiShuKahuna.create_user_plan_spreadsheet(user_qq, plan_name)
        battalship_mk_sheet = FeiShuKahuna.get_battleship_market_sheet(spreadsheet)
        FeiShuKahuna.output_mk_sheet(battalship_mk_sheet, battalship_mk_data)

        res_str = (f"执行完成, 当前计划条件战列市场分析:{battalship_mk_sheet.url}\n\n"
                   f"推荐制造：\n")
        for index, data in enumerate(battalship_mk_data[:10]):
            res_str += (f'{index + 1}.{data[1]}\n'
                        f'  利润率:{data[4]:.2%}\n'
                        f'  月利润:{data[5]:,.2f}\n'
                        f'  月销量:{data[11]:,}\n')

        return event.plain_result(res_str)

    @staticmethod
    async def rp_capcost(event: AstrMessageEvent, plan_name: str):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)
        if plan_name not in user.user_data.plan:
            raise KahunaException(f"plan {plan_name} not exist")

        with ThreadPoolExecutor(max_workers=1) as executor:
            ship_list = SdeUtils.get_capital_ship()
            plan = [[ship, 1] for ship in ship_list]
            future = executor.submit(IndustryAnalyser.get_cost_data, user, plan_name, plan)
            while not future.done():
                await asyncio.sleep(1)
            cost_data = future.result()

        spreadsheet = FeiShuKahuna.create_user_plan_spreadsheet(user_qq, plan_name)
        cost_sheet = FeiShuKahuna.get_cap_cost_sheet(spreadsheet)
        FeiShuKahuna.output_cost_sheet(cost_sheet, cost_data)

        return event.plain_result(f"执行完成, 当前计划条件旗舰成本:{cost_sheet.url}")

    @staticmethod
    async def rp_costdetail(event: AstrMessageEvent, plan_name: str, product: str, public= False):
        if await try_acquire_lock(calculate_lock, 1):
            try:
                if public:
                    user_qq = int(config['APP']['COST_PLAN_USER'])
                    plan_name = config['APP']['COST_PLAN_NAME']
                    product = ' '.join(event.get_message_str().split(" ")[1:])
                else:
                    user_qq = get_user(event)
                    product = ' '.join(event.get_message_str().split(" ")[4:])

                user = UserManager.get_user(user_qq)
                if plan_name not in user.user_data.plan:
                    raise KahunaException(f"plan {plan_name} not exist")

                if (type_id := SdeUtils.get_id_by_name(product)) is None:
                    return print_name_fuzz_list(event, product)

                detail_dict = await IndustryAnalyser.get_cost_detail(user, plan_name, product)
                detail_dict.update({'name': SdeUtils.get_name_by_id(type_id), 'cn_name': SdeUtils.get_cn_name_by_id(type_id)})
                spreadsheet = FeiShuKahuna.create_user_plan_spreadsheet(user_qq, plan_name)
                cost_sheet = FeiShuKahuna.get_detail_cost_sheet(spreadsheet)
                FeiShuKahuna.output_cost_detail_sheet(cost_sheet, detail_dict)

                detail_dict["type_id"] = type_id
                detail_dict["market_detail"] = (await PriceService.get_price_rouge(product, 'jita'))[1:]

                pic_path = await PictureRender.render_single_cost_pic(detail_dict)

                chain = [
                    Image.fromFileSystem(pic_path),
                    Plain(f"详情报表:{cost_sheet.url}")
                ]
                return event.chain_result(chain)
            finally:
                calculate_lock.release()
        else:
            return event.plain_result("已有成本计算进行中，请稍候再试。")

    @staticmethod
    async def rp_sell_list(event: AstrMessageEvent, price_type: str, corp: bool = False):
        if not corp:
            user_qq = get_user(event)
        else:
            user_qq = int(config['APP']['CORP_ASSET_USER'])

        sell_container_list = await AssetContainer.get_contain_id_by_qq_tag(user_qq, 'sell')
        sell_asset_result = await AssetManager.get_asset_in_container_list(
            [container.asset_location_id for container in sell_container_list]
        )
        sell_asset_list = list(sell_asset_result)

        sell_asset_list2 = [
            asset for asset in sell_asset_list if
            asset.location_flag == 'CorpSAG4' and SdeUtils.get_category_by_id(asset.type_id) == 'Ship'
        ]

        pic_path = await PictureRender.render_sell_list(sell_asset_list2, price_type)

        chain = [
            Image.fromFileSystem(pic_path)
        ]
        return event.chain_result(chain)

    @staticmethod
    async def rp_asset_statistic(event: AstrMessageEvent):
        user_qq = get_user(event)

        data = await IndustryAdvice.personal_asset_statistics(user_qq)
        pic_output = await PictureRender.render_asset_statistic_report(data)

        chain = [
            Image.fromFileSystem(pic_output)
        ]
        return event.chain_result(chain)

    @staticmethod
    async def rp_inventory_statistics(event: AstrMessageEvent):
        user_qq = get_user(event)

        data = await IndustryAdvice.personal_asset_statistics(user_qq)
        pic_output = await PictureRender.render_asset_statistic_report(data)

        chain = [
            Image.fromFileSystem(pic_output)
        ]
        return event.chain_result(chain)

    @staticmethod
    async def rp_order(event: AstrMessageEvent, location: str, is_buy_order=False):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)

        if location not in {'jita', 'frt'}:
            return event.plain_result("位置参数[1] 必须为 {jita, frt}")

        location_id = None
        alias_location = []
        if location == 'jita':
            location_id = JITA_TRADE_HUB_STRUCTURE_ID
            alias_location = PIMI_STRUCTURE_LIST
        elif location == 'frt':
            location_id = FRT_4H_STRUCTURE_ID
            alias_location = []
        else:
            event.plain_result("位置参数[1] 必须为 {jita, frt}")

        order_data = await order_manager.get_order_of_user(user)
        order_pic_data = await order_manager.filt_order_of_location_id(order_data, location_id,
                                                                       is_buy_order=is_buy_order,
                                                                       alias_location_list=alias_location)
        pic_output = await PictureRender.render_order_state({'order_data': order_pic_data}, is_buy_order=is_buy_order)

        chain = [
            Image.fromFileSystem(pic_output)
        ]
        return event.chain_result(chain)

    @staticmethod
    async def rp_month_order_statistic(event: AstrMessageEvent):
        user_qq = get_user(event)
        user = UserManager.get_user(user_qq)

        order_data = await order_manager.get_order_of_user(user)
        month_order_history = await order_manager.get_month_order_history_of_user(user)

        output_data = await order_manager.analyse_month_order_statistic(order_data, month_order_history)
        pic_output = await PictureRender.render_month_order_statistic(output_data)

        chain = [
            Image.fromFileSystem(pic_output)
        ]
        return event.chain_result(chain)

    @staticmethod
    async def refjobs(event: AstrMessageEvent):
        await IndustryManager.refresh_running_status(force=True)

        return event.plain_result("执行完成")

    @classmethod
    async def rp_moon_material_market(cls, event: AstrMessageEvent):
        args = event.get_message_str().split(" ")
        if args[-1].isdigit():
            moon_class = int(args[-1])
        else:
            moon_class = 0
        if moon_class not in {0, 4, 8, 16, 32, 64}:
            return event.plain_result(f"moon_class 必须为 [0, 4, 8, 16, 32, 64]")

        res_data, market_index_history = await IndustryAdvice.moon_material_state(moon_class)

        pic_output = await PictureRender.render_moon_material_state(res_data, market_index_history)

        chain = [
            Image.fromFileSystem(pic_output)
        ]
        return event.chain_result(chain)


class MarketEvent:
    @staticmethod
    async def market_reforder(event: AstrMessageEvent):
        res_log = await MarketManager.refresh_market(force=True)

        return event.plain_result(res_log)

    @staticmethod
    async def market_set_ac(event: AstrMessageEvent):
        user_qq = get_user(event)
        character_name = ' '.join(event.get_message_str().split(" ")[2:])
        character = CharacterManager.get_character_by_name_qq(character_name, user_qq)
        await MarketManager.set_ac_character(character.character_id)
        return event.plain_result(f"设置市场访问角色为 {character_name}")

    @staticmethod
    async def market_reinit(event: AstrMessageEvent):
        MarketManager.init_market()
        return event.plain_result("初始化市场完成。")

class SdeEvent():
    @staticmethod
    def type(event: AstrMessageEvent, ):
        message_str = event.get_message_str()
        type_name = " ".join(message_str.split(" ")[2:])

        type_id = SdeUtils.get_id_by_name(type_name)
        if type_id:
            market_tree_str = '\n  ↓\n'.join(SdeUtils.get_market_group_list(type_id))
            print_str = (f"enname: {SdeUtils.get_name_by_id(type_id)}\n"
                         f"zhname: {SdeUtils.get_cn_name_by_id(type_id)}\n"
                         f"type_id: {type_id}\n"
                         f"group: {SdeUtils.get_groupname_by_id(type_id)}\n"
                         f"category: {SdeUtils.get_category_by_id(type_id)}\n"
                         f"meta: {SdeUtils.get_metaname_by_typeid(type_id)}\n"
                         f"market_tree: \n{market_tree_str}\n")
            return event.plain_result(print_str)
        else:
            fuzz_list = SdeUtils.fuzz_type(type_name)
            if fuzz_list:
                fuzz_rely = (f"物品 {type_name} 不存在于数据库\n"
                             f"你是否在寻找：\n")
                fuzz_rely += '\n'.join(fuzz_list)
                return event.plain_result(fuzz_rely)

    @staticmethod
    def findtype(event: AstrMessageEvent, ):
        message_str = event.get_message_str()
        type_name = " ".join(message_str.split(" ")[2:])
        fuzz_list = SdeUtils.fuzz_type(type_name, list_len=10)
        if fuzz_list:
            fuzz_rely = (f"你是否在寻找：\n")
            fuzz_rely += '\n'.join(fuzz_list)
            return event.plain_result(fuzz_rely)

    @staticmethod
    def type_id(event: AstrMessageEvent, type_id: int):
        name = SdeUtils.get_name_by_id(type_id)
        if name:
            market_tree_str = '\n  ↓\n'.join(SdeUtils.get_market_group_list(type_id))
            print_str = (f"enname: {SdeUtils.get_name_by_id(type_id)}\n"
                         f"zhname: {SdeUtils.get_cn_name_by_id(type_id)}\n"
                         f"type_id: {type_id}\n"
                         f"group: {SdeUtils.get_groupname_by_id(type_id)}\n"
                         f"category: {SdeUtils.get_category_by_id(type_id)}\n"
                         f"meta: {SdeUtils.get_metaname_by_typeid(type_id)}\n"
                         f"market_tree: \n{market_tree_str}\n")
            return event.plain_result(print_str)
        else:
            return event.plain_result('id不存在于数据库')
