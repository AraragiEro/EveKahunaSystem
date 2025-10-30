import asyncio
import multiprocessing
import queue
from asyncio import gather
from errno import ECHILD
from importlib.util import source_hash
from datetime import timedelta
import networkx as nx
import math
from cachetools import TTLCache
from tqdm import tqdm
from queue import Queue
from concurrent.futures import ProcessPoolExecutor, as_completed

from ...utils import roundup, KahunaException
from ..asset_server.asset_container import AssetContainer
from ..asset_server.asset_manager import AssetManager
from ..character_server.character_manager import CharacterManager
from ..user_server.user_manager import UserManager
from ..market_server.market_manager import MarketManager
from ..log_server import logger
from ..sde_service.utils import SdeUtils
from ..database_server.sqlalchemy.kahuna_database_utils import (
    BluerprintAssetCacheDBUtils
)
from .industry_config import IndustryConfigManager, MANU_SKILL_TIME_EFF, REAC_SKILL_TIME_EFF
from .running_job import RunningJobOwner
from .industry_utils import IdsUtils as IdsU
from .blueprint import BPManager
from .structure import StructureManager


HOUR_SECONDS = 3600
DAY_SECONDS = 24 * HOUR_SECONDS

class Work():
    """
    [(
        mater_eff,
        time_eff,
        runs,
        location_id,
        structure_id
    )]
    """
    mater_eff: float = 1
    time_eff: float = 1
    runs: int = 1
    location_id: int = 0
    structure_id: int = 0
    void_bp = False
    avaliable = False

    def __init__(self, type_id: int, mater_eff: float = 1, time_eff: float = 1, runs: int = 1,
                 location_id: int = 0, structure_id: int = 0, void_bp: bool = False):
        self.type_id = type_id
        self.mater_eff = mater_eff
        self.time_eff = time_eff
        self.runs = runs
        self.location_id = location_id
        self.structure_id = structure_id
        self.void_bp = void_bp
        self.avaliable = True
        self.support_index = set()

    def get_material_need(self):
        mater_dict = BPManager.get_bp_materials(self.type_id)
        res_dict = {}
        for key in mater_dict.keys():
            mater_eff = 1 if mater_dict[key] == 1 else self.mater_eff
            res_dict[key] = math.ceil(mater_dict[key] * mater_eff * self.runs)

        return res_dict


class IndustryAnalyser():
    analyser_cache = TTLCache(maxsize=10, ttl=60 * 60) # {plan_name: analyser}

    def __init__(self, owner_qq: int = 0, cal_type="work"):
        self.cal_type = cal_type
        self.owner_qq = owner_qq
        self.market = MarketManager.get_market_by_type('jita')

        # 运行中使用的设置
        self.bp_graph: nx.DiGraph = nx.MultiDiGraph()
        self.anaed_set = set()
        self.bp_node_actually_need_quantity_dict = {}
        self.bp_node_total_need_quantity_dict = {}
        self.actually_need_work_list_dict = {}
        self.total_need_work_list_dict = {}
        self.running_job = {}  # { type_id: runs }
        self.target_container = set()
        self.hide_container = set()
        self.asset_dict = {}

        self.bp_runs_dict = {}
        self.user_jobs_dict = {}
        self.bp_quantity_dict = {}
        self.have_bpo = {}

        self.job_asset_check_dict = {}

        self.global_graph = nx.MultiDiGraph()
        self.work_graph = nx.MultiDiGraph()

        self.analysed_status = False

        self.bp_block_level = 2

        # 需要持久化的设置
        self.plan_name = None
        self.plan_list = None
        # self.cal_type = "work"  # "work"会根据蓝图实际输出计算成本，"cost"则不会，输出的是长期情况下的最小成本
        # self.owner_qq = 0
        self.bp_matcher = None
        self.st_matcher = None
        self.pd_block_matcher = None

        self.manu_lines = 0
        self.reac_lines = 0

        self.manu_cycle_time = 24
        self.reac_cycle_time = 24

    def set_matchers(self, bp_matcher, st_matcher, pd_block_matcher):
        self.bp_matcher = bp_matcher
        self.st_matcher = st_matcher
        self.pd_block_matcher = pd_block_matcher

    def in_pd_block(self, type_id: int) -> bool:
        matcher = self.pd_block_matcher
        if matcher is None:
            raise KahunaException("pd_block matcher must be set.")

        structure_id = None
        invType_data = SdeUtils.get_invtpye_node_by_id(type_id)
        if not invType_data:
            raise KahunaException(f"{type_id} 不存在于数据库，请联系管理员。")

        # bp
        bp_id = BPManager.get_bp_id_by_prod_typeid(type_id)
        bp_name = SdeUtils.get_name_by_id(bp_id)
        if bp_name in matcher.matcher_data["bp"] and matcher.matcher_data["bp"][bp_name] <= self.bp_block_level:
            return True

        # 找到符合条件的最小市场分类
        mklist = SdeUtils.get_market_group_list(type_id)
        mk_block = False
        largest_index = 0
        for market_group, _ in matcher.matcher_data["market_group"].items():
            if market_group in mklist and matcher.matcher_data["market_group"][market_group] <= self.bp_block_level:
                mk_block = mk_block or True
        if mk_block:
            return True

        group = SdeUtils.get_groupname_by_id(type_id)
        if group in matcher.matcher_data["group"] and matcher.matcher_data["group"][group] <= self.bp_block_level:
            return True

        meta = SdeUtils.get_metaname_by_typeid(type_id)
        if meta in matcher.matcher_data["meta"] and matcher.matcher_data["meta"][meta] <= self.bp_block_level:
            return True

        category = SdeUtils.get_category_by_id(type_id)
        if category in matcher.matcher_data["category"] and matcher.matcher_data["category"][category] <= self.bp_block_level:
            return True

        return False
        raise KahunaException(f"typeid: {type_id} 无建筑分配，请配置匹配器。")

    async def get_running_job(self):
        if not self.target_container:
            raise KahunaException("target_structure must be set.")

        self.running_job = {}
        self.using_bp = await RunningJobOwner.get_using_bp_set()

        user_character_dict = {}
        target_character = []
        user = UserManager.get_user(self.owner_qq)
        main_character = user.main_character_id
        usr_character = [c.character_id for c in CharacterManager.get_user_all_characters(user.user_qq)]
        usr_alias = [cid for cid in user.user_data.alias.keys()]
        target_character += usr_character
        target_character += usr_alias
        user_character_dict[main_character] = usr_character + usr_alias

        # 合作者的角色list
        if self.plan_name:
            for coop_user in list(user.user_data.plan[self.plan_name]["coop_user"]):
                coop_uobj = UserManager.get_user(coop_user)
                main_character = coop_uobj.main_character_id
                coop_character = [c.character_id for c in CharacterManager.get_user_all_characters(coop_user)]
                coop_alias = [cid for cid in coop_uobj.user_data.alias.keys()]
                target_character += coop_character
                target_character += coop_alias
                user_character_dict[main_character] = coop_character + coop_alias
        self.user_jobs_dict = {cid: [] for cid in user_character_dict.keys()}

        result = await RunningJobOwner.get_job_with_starter(target_character)
        
        for job in result:
            if job.output_location_id in self.target_container:
                if not job.product_type_id in self.running_job:
                    self.running_job[job.product_type_id] = 0
                self.running_job[job.product_type_id] += job.runs
                
                # 记录每个主角色下属的job，用具计算收益分配
                for main_c, character_list in user_character_dict.items():
                    if job.installer_id in character_list:
                        self.user_jobs_dict[main_c].append(job)

    def get_target_container(self):
        container_list = AssetManager.get_user_container(self.owner_qq)
        self.target_container = set(container.asset_location_id for container in container_list
                                    if (container.tag in {"manu", "reac"} and
                                        container.asset_location_id not in self.hide_container))

    async def get_asset_in_container(self):
        if not self.target_container:
            raise KahunaException("target_structure must be set.")

        result = await AssetManager.get_asset_in_container_list(list(self.target_container))
        for asset in result:
            if asset.type_id not in self.asset_dict:
                self.asset_dict[asset.type_id] = 0
                self.job_asset_check_dict[asset.type_id] = 0
            self.asset_dict[asset.type_id] += asset.quantity
            self.job_asset_check_dict[asset.type_id] += asset.quantity

    def get_work_tree(self, work_list: list, dg: nx.DiGraph = None):
        """
        :param work_list: [(target_id, quantity)]
        :return:
        """
        work_list = [(SdeUtils.get_id_by_name(target), quantity) for target, quantity in work_list]
        # queue: [type_id, node_id, quanqity]
        bfs_queue = [(index, data[0], 1) for index, data in enumerate(work_list)]

        dg.add_node("root")
        dg.add_nodes_from([type_id for type_id, _ in work_list])
        dg.add_edges_from(
            [("root", data[0], {"index": index + 1, "quantity": data[1]})
             for index, data in enumerate(work_list)])

        self.bfs_bp_tree(bfs_queue, dg)
        memo = {}
        root_depth = self.longest_path_dag('root', memo)
        self.update_layer_depth('root')
        return dg

    # 递归计算最长路径，并添加备忘录优化
    def longest_path_dag(self, node, memo):
        if node in memo:  # 如果已经计算过，直接返回
            return memo[node]

        # 如果是叶子节点（出度为 0），深度为 0
        if self.bp_graph.out_degree(node) == 0:
            memo[node] = 1
            self.bp_graph.nodes[node]['depth'] = 1
            return 1

        # 计算所有子节点中的最大路径
        max_depth = 0
        for succ in self.bp_graph.successors(node):
            try:
                max_depth = max(max_depth, self.longest_path_dag(succ, memo))
            except RecursionError:
                raise KahunaException(f'node: {node}')

        # 加入自身节点长度，然后存入备忘录
        memo[node] = max_depth + 1
        self.bp_graph.nodes[node]['depth'] = memo[node]
        return memo[node]

    def update_layer_depth(self, node):
        if node != 'root' and self.bp_graph.nodes[node]['depth'] != 1:
            depth= 100
            for pre in self.bp_graph.predecessors(node):
                depth = min(depth, self.bp_graph.nodes[pre]['depth'])
            self.bp_graph.nodes[node]['depth'] = depth - 1

        for suss in self.bp_graph.successors(node):
            self.update_layer_depth(suss)

    def bfs_bp_tree(self, bfs_queue: list, dg: nx.DiGraph = None):
        """
        递归处理生成蓝图节点。
        每个节点代表一种材料，每种target需要的材料存储在节点与节点之间的边关系
        """
        while bfs_queue:
            index, type_id, quantity = bfs_queue.pop(0)
            dg.add_node(type_id)
            # 没有蓝图信息 或 在分解黑名单
            if (bp_materials := BPManager.get_bp_materials(type_id)) is None or self.in_pd_block(type_id):
                self.anaed_set.add((index, type_id))
                continue
            dg.add_nodes_from([child_id for child_id in bp_materials.keys()])
            dg.add_edges_from(
                [(type_id, child_id, {"index": index, "quantity": quantity})
                 for child_id, quantity in bp_materials.items()]
            )

            bfs_queue = bfs_queue + [(index, child_id, quantity) for child_id, quantity in bp_materials.items()
                                     if (index, child_id) not in self.anaed_set]
            self.anaed_set.update([(index, child) for child in bp_materials.keys()])

    async def get_runs_list_by_bpasset(self, total_runs_needed: int, source_id: int, user_qq: int, work_cache: dict) -> list:
        # 缓存
        if source_id in work_cache:
            return work_cache[source_id]
        if source_id == "root":
            return [Work(1, 1, total_runs_needed, 0, 0)]
        """ 根据库存蓝图生成工作序列 """
        manu_skill_time_eff = MANU_SKILL_TIME_EFF
        reac_skill_time_eff = REAC_SKILL_TIME_EFF
        active_id = BPManager.get_action_id(source_id)
        if active_id == 1:
            cycle_time = self.manu_cycle_time * HOUR_SECONDS
        elif active_id == 11:
            cycle_time = self.reac_cycle_time * HOUR_SECONDS
        else:
            raise KahunaException("暂不支持制造和反应外的流程安排。")

        # 1. 分配建筑
        structure_id = IndustryConfigManager.allocate_structure(source_id, self.st_matcher)
        structure = await StructureManager.get_structure(structure_id)
        st_mater_eff, st_time_eff = IndustryConfigManager.get_structure_mater_time_eff(structure.type_id)
        st_mater_rig_eff, st_time_rig_eff = IndustryConfigManager.get_structure_rig_mater_time_eff(structure)

        # 2. 蓝图统计
        # owner_qq可用的蓝图仓库，即container_tag为bp的仓库，需要存在于目标建筑?
        bp_container_list = []
        bp_container_list += await AssetContainer.get_contain_id_by_qq_tag(user_qq, "bp")
        bp_container_list += await AssetContainer.get_contain_id_by_qq_tag(user_qq, "manu")
        bp_container_list += await AssetContainer.get_contain_id_by_qq_tag(user_qq, "reac")
        bp_container_list = [container.asset_location_id for container in bp_container_list]

        # 根据source_id获得user_qq所属的所有蓝图
        owner_id_set = set(character.character_id for character in CharacterManager.get_user_all_characters(user_qq))
        for character in CharacterManager.get_user_all_characters(user_qq):
            if character.director:
                owner_id_set.add(character.corp_id)
        bp_id = BPManager.get_bp_id_by_prod_typeid(source_id)
        avaliable_bpc_asset = await BluerprintAssetCacheDBUtils.select_bpc_by_type_id_and_location_id(bp_id, bp_container_list)
        avaliable_bpo_asset = await BluerprintAssetCacheDBUtils.select_bpo_by_type_id_and_location_id(bp_id, bp_container_list)

        # 可用的拷贝序列 [(runs, material_efficiency, time_efficiency, item_id, structure_id, location_id)]
        avaliable_bpc_list = [(bp.runs, bp.material_efficiency, bp.time_efficiency, bp.item_id, bp.location_id, structure_id)\
                              for bp in avaliable_bpc_asset if bp.item_id not in self.using_bp]
        avaliable_bpc_list.sort(key=lambda x: (x[1], x[0]), reverse=True)

        # 可用的原图序列 [(quantity, material_efficiency, time_efficiency, structure_id, location_id)]
        avaliable_bpo_count = {}
        for bpo in avaliable_bpo_asset:
            if bpo.item_id in self.using_bp:
                continue
            if (bpo.material_efficiency, bpo.time_efficiency, bpo.location_id) not in avaliable_bpo_count:
                avaliable_bpo_count[(bpo.material_efficiency, bpo.time_efficiency, bpo.location_id)] = 0
            if bpo.quantity < 0:
                avaliable_bpo_count[(bpo.material_efficiency, bpo.time_efficiency, bpo.location_id)] += 1
            else:
                avaliable_bpo_count[(bpo.material_efficiency, bpo.time_efficiency, bpo.location_id)] += bpo.quantity

        avaliable_bpo_count_list = [[v, k[0], k[1], k[2], structure_id] for k, v in avaliable_bpo_count.items()]
        avaliable_bpo_count_list.sort(key=lambda x: x[1], reverse=True)

        # 保存蓝图库存数量，只计算一次
        if source_id not in self.bp_quantity_dict:
            self.bp_quantity_dict[source_id] = len(avaliable_bpc_list)
            if len(avaliable_bpo_count_list) > 0:
                self.bp_quantity_dict[source_id] += sum([i[0] for i in avaliable_bpo_count_list])
                self.have_bpo[source_id] = True
        if source_id not in self.bp_runs_dict:
            self.bp_runs_dict[source_id] = sum([bp[0] for bp in avaliable_bpc_list])

        # 3. 计算工作序列
        # 时间系数包含 建筑[建筑+插件] 技能(按照默认值计算) 蓝图[用于最大轮数计算，不算蓝图]
        # 材料系数包含 建筑[建筑+插件] 蓝图
        # 默认蓝图效率
        matcher_bp_name = None
        if SdeUtils.get_name_by_id(bp_id) in self.bp_matcher.matcher_data['bp']:
            matcher_bp_name = SdeUtils.get_name_by_id(bp_id)
        elif SdeUtils.get_cn_name_by_id(bp_id) in self.bp_matcher.matcher_data['bp']:
            matcher_bp_name = SdeUtils.get_cn_name_by_id(bp_id)
        if not matcher_bp_name:
            default_bp_meter_eff, default_bp_time_eff = IndustryConfigManager.get_default_bp_mater_time_eff(source_id)
        else:
            default_bp_meter_eff = self.bp_matcher.matcher_data['bp'][matcher_bp_name]['mater_eff']
            default_bp_time_eff = self.bp_matcher.matcher_data['bp'][matcher_bp_name]['time_eff']
        time_eff = st_time_eff * st_time_rig_eff * (manu_skill_time_eff if active_id != 11 else reac_skill_time_eff)
        mater_eff = st_mater_eff * st_mater_rig_eff
        production_time = BPManager.get_production_time(source_id)
        max_runs = math.ceil((cycle_time / time_eff) / production_time)


        work_list = []
        used_bp = set()
        # 使用优先级：
        # 按照最大周期使用蓝图直到蓝图归零或流程归零
        # 流程未归零则创造虚空流程
        for bpo in avaliable_bpo_count_list:
            w_time_eff = time_eff * (1 - bpo[2] / 100)
            max_runs = math.ceil((cycle_time / w_time_eff) / production_time)
            while bpo[0] > 0 and total_runs_needed > 0:
                if total_runs_needed >= max_runs:
                    work_list.append(Work(source_id,
                                          mater_eff * (1 - bpo[1] / 100),
                                          w_time_eff,
                                          max_runs, bpo[3], bpo[4]))
                    total_runs_needed -= max_runs
                    bpo[0] -= 1
                    used_bp.add(bpo[3])
                else:
                    work_list.append(Work(source_id,
                                          mater_eff * (1 - bpo[1] / 100),
                                          w_time_eff,
                                          total_runs_needed, bpo[3], bpo[4]))
                    total_runs_needed = 0
                    break

        # 上面步骤执行完还没归零，则从小到大使用直到归零
        # 若蓝图使用完还没归零，则创造虚空拷贝，方便计算缺失流程。
        # 剩余流程大于最大蓝图流程，不考虑时间直接拉满。
        # 剩余流程大于最大蓝图流程，找到小于剩余最大流程的从大到小匹配直到剩余流程归0
        for bpc in avaliable_bpc_list:
            if total_runs_needed > 0 and total_runs_needed >= bpc[0]:
                work_list.append(Work(source_id,
                                      mater_eff * (1 - bpc[1] / 100),
                                      time_eff * (1 - bpc[2] / 100),
                                      bpc[0], bpc[4], bpc[5]))
                total_runs_needed -= bpc[0]
                used_bp.add(bpc[3])
        avaliable_bpc_list.sort(key=lambda x: x[0])
        for bpc in avaliable_bpc_list:
            if bpc[3] in used_bp:
                continue
            if total_runs_needed > 0:
                if bpc[0] < total_runs_needed:
                    work_list.append(Work(source_id,
                                          mater_eff * (1 - bpc[1] / 100),
                                          time_eff * (1 - bpc[2] / 100),
                                          bpc[0], bpc[4], bpc[5]))
                    total_runs_needed -= bpc[0]
                else:
                    work_list.append(Work(source_id,
                                          mater_eff * (1 - bpc[1] / 100),
                                          time_eff * (1 - bpc[2] / 100),
                                          total_runs_needed, bpc[4], bpc[5]))
                    total_runs_needed = 0

        # 按照单蓝图可生产最大流程处理
        max_production = min(BPManager.get_productionmax_by_bpid(bp_id),
                             math.ceil(30 * 24 * 60 * 60 / (time_eff * default_bp_time_eff * production_time)))
        while total_runs_needed > 0:
            if total_runs_needed >= max_production:
                work_list.append(Work(source_id,
                                      mater_eff * default_bp_meter_eff,
                                      time_eff * default_bp_time_eff,
                                      max_production, structure_id, structure_id, void_bp=True))
                total_runs_needed -= max_production
            else:
                work_list.append(Work(source_id,
                                      mater_eff * default_bp_meter_eff,
                                      time_eff * default_bp_time_eff,
                                      total_runs_needed, structure_id, structure_id, void_bp=True))
                total_runs_needed = 0

        work_list.sort(key=lambda x: x.runs)
        work_cache[source_id] = work_list
        return work_list

    async def calculate_work_bpnode_quantity(self, child_id: int, cache_dict: dict):
        """
        计算工作蓝图节点数量（实际执行模式）
        
        参数：
            typeid (int): 蓝图类型ID
        """
        # 在图内则返回数据
        if child_id in self.work_graph.nodes and child_id in self.global_graph:
            return self.work_graph.nodes[child_id], self.global_graph.nodes[child_id]
        self.work_graph.add_node(child_id)
        self.global_graph.add_node(child_id)
        if child_id == "root":
            self.work_graph.nodes[child_id].update({
                'quantity': 1,
                'index_quantity': [[index, data[1]] for index, data in enumerate(self.plan_list)],
                'work_list': [],
                'is_material': False
            })
            self.global_graph.nodes[child_id].update({
                'quantity': 1,
                'index_quantity': [[index, data[1]] for index, data in enumerate(self.plan_list)],
                'work_list': [],
                'is_material': False
            })
            return self.work_graph.nodes[child_id], self.global_graph.nodes[child_id]

        need_cal_edge = [edge for edge in self.bp_graph.in_edges(child_id, data=True)]
        # 当前[fathern, child, data]
        # 改为[father, [index], child, quantity]
        tmp_dict = {}
        for edge in need_cal_edge:
            if edge[0] not in tmp_dict:
                tmp_dict[edge[0]] = [[], edge[1], edge[2]['quantity']]
            tmp_dict[edge[0]][0].append(edge[2]['index'])
        need_cal_edge_new = [[k]+v for k, v in tmp_dict.items()]
        need_cal_edge_new.sort(key=lambda x: min(x[1]))

        # 制造中占位符
        running_count = self.running_job.get(child_id, 0)
        # 库存占位符
        exist_count = self.asset_dict.get(child_id, 0)
        product_count = BPManager.get_bp_product_quantity_typeid(child_id)
        running_quantity = running_count * product_count
        # 记录资产数量,用于处理每个index的节点状态
        avaliable_asset = exist_count

        actually_index_need = {}
        total_index_need = {}
        # for edge in need_cal_edge:
        for edge in need_cal_edge_new:
            index_list = edge[1]
            father_id = edge[0]
            bp_need_quantity = edge[3]
            # index = edge[2]["index"]

            father_work_node, father_global_node = await self.calculate_work_bpnode_quantity(father_id, cache_dict)

            # root节点特殊处理
            if father_id == "root":
                matching_edges = [edge[2] for edge in need_cal_edge if edge[2]['index'] in index_list]
                total_index_need.update({edge['index']: edge['quantity'] for edge in matching_edges})
                actually_index_need.update({edge['index']: edge['quantity'] for edge in matching_edges})
                continue

            # if 'index_quantity' not in father_work_node:
            #     print(f'{father_id}:{father_work_node}')
            father_actually_need_list = father_work_node['index_quantity']
            father_total_need_list = father_global_node['index_quantity']

            # 获取生产参数, 不处理父节点的工作数据
            father_product_quantity = 1 if father_id == "root" else BPManager.get_bp_product_quantity_typeid(father_id)
            # chunk_runs = 1 if father_id == "root" else BPManager.get_chunk_runs(father_id)  # 每轮工作最大流程数

            # father工作list
            father_work_list = father_work_node['work_list']
            father_total_work_list = father_global_node['work_list']

            # 分index计算实际需求，可能是小数。
            # 实际部分
            child_used_sum = 0
            father_production_sum = 0
            work_list_len = len(father_work_list)
            work_i = 0
            single_actually_index_need = {index: 0 for index, _ in father_actually_need_list}
            for index, father_need in father_actually_need_list:
                if index not in actually_index_need:
                    actually_index_need[index] = 0
                if father_need > 0:
                    # 遍历工作直到满足index需求数量
                    while father_production_sum < father_need and work_i < work_list_len:
                        father_production_sum += father_work_list[work_i].runs * father_product_quantity
                        # 如果需求为1，不吃材料加成
                        child_used_sum += \
                            math.ceil(father_work_list[work_i].runs * bp_need_quantity * \
                            (1 if bp_need_quantity == 1 else father_work_list[work_i].mater_eff))
                        father_work_list[work_i].support_index.add(index)
                        # 设计上是刚好的，最后再加1会越界
                        if work_i < work_list_len - 1:
                            work_i += 1
                    father_work_list[work_i].support_index.add(index)
                    # 如果有超出部分，计算部分蓝图的消耗
                    if father_production_sum > father_need:
                        if work_i >= work_list_len:
                            raise KahunaException(f"{father_id} work cant cover need.")
                        father_production_sum -= father_need
                        bp_used_ratio = father_production_sum / father_work_list[work_i].runs / father_product_quantity
                        # 如果需求为1，不吃材料加成
                        child_less = math.floor(bp_used_ratio * father_work_list[work_i].runs * bp_need_quantity * \
                                     (1 if bp_need_quantity == 1 else father_work_list[work_i].mater_eff))
                        actually_index_need[index] += (child_used_sum - child_less)
                        single_actually_index_need[index] = (child_used_sum - child_less)
                        child_used_sum = child_less
                    elif father_production_sum == father_need:
                        actually_index_need[index] += child_used_sum
                        single_actually_index_need[index] = child_used_sum
                        child_used_sum = 0
                        father_production_sum = 0
                    else:
                        raise KahunaException("安排的工作无法处理需求")
            if child_used_sum > 0:
                last_index = father_actually_need_list[-1][0]
                actually_index_need[last_index] += child_used_sum
                single_actually_index_need[last_index] += child_used_sum

            # 全体部分
            child_used_sum = 0
            father_production_sum = 0
            work_list_len = len(father_total_work_list)
            work_i = 0
            single_total_index_need = {index: 0 for index, _ in father_total_need_list}
            for index, father_need in father_total_need_list:
                if index not in total_index_need:
                    total_index_need[index] = 0
                    single_total_index_need[index] = 0
                if father_need > 0:
                    # 遍历工作直到满足index需求数量
                    while father_production_sum < father_need and work_i < work_list_len:
                        father_production_sum += father_total_work_list[work_i].runs * father_product_quantity
                        # 如果需求为1，不吃材料加成
                        child_used_sum += father_total_work_list[work_i].runs * bp_need_quantity * \
                                          (1 if bp_need_quantity == 1 else father_total_work_list[work_i].mater_eff)
                        if work_i < work_list_len - 1:
                            work_i += 1
                    # 如果有超出部分，计算部分蓝图的消耗
                    if father_production_sum > father_need:
                        if work_i >= work_list_len:
                            raise KahunaException(f"{father_id} work cant cover need.")
                        father_production_sum -= father_need
                        bp_used_ratio = father_production_sum / father_total_work_list[work_i].runs / father_product_quantity

                        # 如果需求为1，不吃材料加成
                        child_less = bp_used_ratio * father_total_work_list[work_i].runs * bp_need_quantity * \
                                     (1 if bp_need_quantity == 1 else father_total_work_list[work_i].mater_eff)
                        total_index_need[index] += (child_used_sum - child_less)
                        single_total_index_need[index] = (child_used_sum - child_less)
                        child_used_sum = child_less
                    elif father_production_sum == father_need:
                        total_index_need[index] += child_used_sum
                        single_total_index_need[index] = child_used_sum
                        child_used_sum = 0
                        father_production_sum = 0
                    else:
                        raise KahunaException("安排的工作无法覆盖需求")

            for index, quantity in single_actually_index_need.items():
                # 计算资产是否满足父节点需求
                if quantity  == 0:
                    # 已完成
                    status = 1
                elif quantity <= avaliable_asset:
                    # 满足
                    avaliable_asset -= quantity
                    status = 2
                elif quantity:
                    # 不满足
                    avaliable_asset = 0
                    status = 3
                self.work_graph.add_edge(father_id, child_id, index=index, quantity=quantity, status=status)
            for index, quantity in single_total_index_need.items():
                self.global_graph.add_edge(father_id, child_id, index=index, quantity=quantity)

        # 备份记录一次该类型资产总数，用于父节点判断状态

        # 计算工作流
        is_material = False
        child_actually_total_quantity = math.ceil(sum([quantity for quantity in actually_index_need.values()]))
        child_actually_total_quantity = math.ceil(child_actually_total_quantity - running_quantity - exist_count)
        child_total_quantity = sum([quantity for quantity in total_index_need.values()])
        if BPManager.get_bp_id_by_prod_typeid(child_id) and not self.in_pd_block(child_id):
            child_product_quantity = BPManager.get_bp_product_quantity_typeid(child_id)
            child_actually_total_runs = math.ceil(child_actually_total_quantity / child_product_quantity)
            child_total_runs = math.ceil(child_total_quantity / child_product_quantity)

            child_actually_worklist = await self.get_runs_list_by_bpasset(child_actually_total_runs, child_id, self.owner_qq, self.actually_need_work_list_dict)
            child_total_worklist = await self.get_runs_list_by_bpasset(child_total_runs, child_id, self.owner_qq, self.total_need_work_list_dict)
        else:
            child_actually_worklist = []
            child_total_worklist = []
            is_material = True

        # 更新actually_index_need
        actually_index_quantity = sorted(list([k, v] for k, v in actually_index_need.items()), key=lambda x: x[0])
        need_to_minus = running_quantity + exist_count
        for index, _ in enumerate(actually_index_quantity):
            if actually_index_quantity[index][1] > need_to_minus:
                actually_index_quantity[index][1] -= need_to_minus
                break
            else:
                need_to_minus -= actually_index_quantity[index][1]
                actually_index_quantity[index][1] = 0

        child_eiv_cost = await IdsU.get_eiv_cost(child_id, child_total_quantity, self.owner_qq, self.st_matcher)
        logistic_data = await IdsU.get_logistic_need_data(self.owner_qq, child_id, self.st_matcher, child_actually_total_quantity)
        self.work_graph.nodes[child_id].update({
            'quantity': child_actually_total_quantity,
            'work_list': child_actually_worklist,
            'index_quantity': actually_index_quantity,
            'is_material': is_material,
            'logistic': logistic_data,
        })
        self.global_graph.nodes[child_id].update({
            'quantity': child_total_quantity,
            'work_list': child_total_worklist,
            'index_quantity': sorted(list([k, v] for k, v in total_index_need.items()), key=lambda x: x[0]),
            'is_material': is_material
        })
        if self.global_graph.nodes[child_id]['is_material']:
            self.global_graph.nodes[child_id].update({'buy_cost': child_total_quantity * (await self.market.get_type_order_rouge(child_id))[0]})
        else:
            self.global_graph.nodes[child_id].update({'eiv_cost': child_eiv_cost})

        return self.work_graph.nodes[child_id], self.global_graph.nodes[child_id]

    def update_work_avaliable(self):
        asset_dict = self.job_asset_check_dict
        work_check_dict = {}
        for node in self.work_graph.nodes():
            if 'work_list' not in self.work_graph.nodes[node]:
                continue
            work_list = self.work_graph.nodes[node]['work_list']
            for work in work_list:
                IdsU.input_work_checkpoint(work_check_dict, work)

        for needed_child, needed_data in work_check_dict.items():
            needed_data.sort(key=lambda x: x['min_index'])
            for needed in needed_data:
                if needed['quantity'] > asset_dict.get(needed_child, 0):
                    needed['work'].avaliable = False
                else:
                    asset_dict[needed_child] -= needed['quantity']


    """ 计算核心入口函数 """
    async def analyse_progress_work_type(self, work_list: list[list[str, int]]) -> dict:
        if not self.bp_matcher or not self.st_matcher or not self.pd_block_matcher:
            raise KahunaException("matcher must be set in BpAnalyser.")

        # 获取目标库存、正在运行的工作、库存内的资产
        self.get_target_container()
        await self.get_running_job()
        await self.get_asset_in_container()

        accept_worklist = []
        for work in work_list:
            if SdeUtils.get_id_by_name(work[0]) and BPManager.get_bp_id_by_prod_typeid(SdeUtils.get_id_by_name(work[0])):
                accept_worklist.append(work)

        self.get_work_tree(accept_worklist, self.bp_graph)

        nodes_without_outgoing_edges = [node for node, degree in self.bp_graph.out_degree() if degree == 0]
        res_dict = {}
        cache_dict = {}
        for node in nodes_without_outgoing_edges:
            res_dict[node] = await self.calculate_work_bpnode_quantity(node, cache_dict)

        ''' 更新工作流的材料是否满足 '''
        self.update_work_avaliable()

        self.analysed_status = True
        return res_dict

    def clean_analyser(self):
        self.bp_graph.clear()
        self.anaed_set.clear()
        self.bp_node_actually_need_quantity_dict.clear()
        self.bp_node_total_need_quantity_dict.clear()
        self.actually_need_work_list_dict.clear()
        self.total_need_work_list_dict.clear()
        self.running_job.clear()
        self.target_container.clear()
        self.asset_dict.clear()

        self.global_graph.clear()
        self.work_graph.clear()

        self.bp_runs_dict.clear()
        self.bp_quantity_dict.clear()
        self.have_bpo.clear()

        self.analysed_status = False

    def set_plan_list(self, plan_list):
        self.plan_list = plan_list

    @classmethod
    def create_analyser_by_plan(cls, user, plan_name: str):
        plan_dict = user.user_data.plan[plan_name]
        bp_matcher = IndustryConfigManager.get_matcher_of_user_by_name(plan_dict["bp_matcher"], user.user_qq)
        st_matcher = IndustryConfigManager.get_matcher_of_user_by_name(plan_dict["st_matcher"], user.user_qq)
        prod_block_matcher = IndustryConfigManager.get_matcher_of_user_by_name(plan_dict["prod_block_matcher"], user.user_qq)

        analyser = IndustryAnalyser(user.user_qq, "work")
        analyser.plan_name = plan_name
        analyser.set_matchers(bp_matcher, st_matcher, prod_block_matcher)
        analyser.set_plan_list(plan_dict["plan"])
        analyser.manu_cycle_time = plan_dict['manucycletime']
        analyser.reac_cycle_time = plan_dict["reaccycletime"]
        analyser.hide_container = set(plan_dict["container_block"])
        # analyser.manu_lines = plan_dict["manulinenum"]
        # analyser.reac_lines = plan_dict["reaclinenum"]

        return analyser

    @classmethod
    def get_analyser_by_plan(cls, user, plan_name):
        return cls.create_analyser_by_plan(user, plan_name)

    async def get_work_tree_data(self):
        self.clean_analyser()
        if not self.analysed_status:
            await self.analyse_progress_work_type(self.plan_list)

        result_dict = {
            'work': {},
            'material': {"矿石": [],
                         '冰矿产物': [],
                        "行星工业": [],
                        "燃料块": [],
                        "元素": [],
                        "气云": [],
                        "杂货": [],
                        "反应物": []},
            'work_flow': {},
            'logistic': {},
            'coop_pay': {},
            'finished_index': []
        }

        res = await self.get_work_node_data(result_dict)

        return res

    async def get_work_node_data(self, result_dict):
        for node in self.bp_graph.nodes():
            if node == 'root':
                 continue
            layer = self.bp_graph.nodes[node]['depth']

            if layer == 1:
                await self.add_material_data(node, result_dict['material'])
            else:
                self.add_work_data(node, result_dict['work'])

        res = {i+1:[] for i in range(self.bp_graph.nodes['root']['depth'] - 1)}
        top_layer = self.bp_graph.nodes['root']['depth'] - 1
        finished_index = []
        for node, data in result_dict['work'].items():
            layer = self.bp_graph.nodes[node]['depth']
            if self.bp_graph.has_edge('root', node):
                res[top_layer].append(data)
                if self.work_graph.nodes[node]['quantity'] == 0 and self.running_job.get(node, 0) == 0:
                    finished_index.append({
                        'id': node,
                        'index': self.bp_graph['root'][node][0]['index'],
                        'name': SdeUtils.get_cn_name_by_id(node),
                        'quantity': self.bp_graph['root'][node][0]['quantity']
                    })
                continue
            res[layer].append(data)
        finished_index.sort(key=lambda x: x['index'], reverse=True)
        result_dict['finished_index'] = finished_index
        result_dict['work'] = res


        self.get_workflow_data(result_dict['work_flow'])
        await self.get_transport_data(result_dict['logistic'])
        await self.get_coop_pay(result_dict['coop_pay'])

        return result_dict

    def get_workflow_data(self, res_dict: dict):
        top_layer = self.bp_graph.nodes['root']['depth'] - 1
        layer_list = sorted([i + 2 for i in range(top_layer - 1)], reverse=True)

        manu_list = []
        reac_list = []

        for layer in layer_list:
            layer_reac = []
            layer_manu = []
            layer_nodes = list([node, data] for node, data in self.work_graph.nodes(data=True) if self.bp_graph.nodes[node]['depth'] == layer)
            for node, data in layer_nodes:
                node_work = {}
                work_list = data['work_list']
                if len(work_list) == 0:
                    continue
                for work in work_list:
                    if not work.avaliable:
                        continue
                    if work.void_bp:
                        continue
                    if work.runs not in node_work:
                        node_work[work.runs] = 0
                    node_work[work.runs] += 1
                if len(node_work) > 0:
                    work_output = [['', k, v] for k, v in node_work.items()]
                    work_output.sort(key=lambda x: x[1], reverse=True)
                    work_output[0][0] = SdeUtils.get_name_by_id(node)
                    action_id = BPManager.get_action_id(node)
                    if action_id == 1:
                        layer_manu += work_output
                    elif action_id == 11:
                        layer_reac += work_output
            manu_list += layer_manu
            reac_list += layer_reac

        res_dict['manu_flow'] = manu_list
        res_dict['reac_flow'] = reac_list

    async def get_transport_data(self, logistic_dict: dict):
        node_list = [node for node in self.work_graph.nodes() if node != 'root']
        main_chara = CharacterManager.get_character_by_id(UserManager.get_main_character_id(self.owner_qq))
        ac_token = await main_chara.ac_token
        # 获取需求
        structure_need_dict = {}
        for node in node_list:
            node_data = self.work_graph.nodes[node]
            work_list = node_data['work_list']
            for work in work_list:
                if not work.avaliable:
                    continue
                material_need = work.get_material_need()
                structure = await StructureManager.get_structure(work.structure_id, ac_token)
                if structure not in structure_need_dict:
                    structure_need_dict[structure] = {}
                struc_need_dict = structure_need_dict[structure]
                for child_id, quantity in material_need.items():
                    if child_id not in struc_need_dict:
                        struc_need_dict[child_id] = 0
                    struc_need_dict[child_id] += quantity
        logistic_dict['need'] = structure_need_dict

        # 获取供给
        structure_provide_dict = {}
        asset_res = await AssetManager.get_asset_in_container_list(list(self.target_container))
        for asset in asset_res:
            if asset.type_id not in self.work_graph.nodes():
                continue
            if asset.location_id not in self.target_container:
                continue
            structure_id = (await StructureManager.get_structure_id_from_location_id(asset.location_id))[0]
            structure = await StructureManager.get_structure(structure_id, ac_token)
            if not structure:
                logger.error(f'type {SdeUtils.get_name_by_id(asset.type_id)} '
                             f'location structure[{structure_id}] access error. location_id is {asset.location_id}|strcture_id is {structure_id}')
                continue
            if structure not in structure_provide_dict:
                structure_provide_dict[structure] = {}
            if asset.type_id not in structure_provide_dict[structure]:
                structure_provide_dict[structure][asset.type_id] = 0
            structure_provide_dict[structure][asset.type_id] += asset.quantity
        logistic_dict['provide'] = structure_provide_dict

        # 处理自供给
        for struct, struct_need in structure_need_dict.items():
            for type_id, quantity in struct_need.items():
                if (struct not in structure_provide_dict or
                        type_id not in structure_provide_dict[struct]):
                    continue
                if structure_provide_dict[struct][type_id] >= quantity:
                    structure_provide_dict[struct][type_id] -= quantity
                    struct_need[type_id] = 0
                else:
                    struct_need[type_id] -= structure_provide_dict[struct][type_id]
                    structure_provide_dict[struct].pop(type_id)

        transport_dict = {}
        # 处理异地供给
        for need_struct, struct_need in structure_need_dict.items():
            for type_id, quantity in struct_need.items():
                for prov_struct, struct_provide in structure_provide_dict.items():
                    if (type_id not in struct_provide or
                            struct_provide[type_id] == 0 or
                            struct_need[type_id] == 0 or
                            need_struct == prov_struct):
                        continue
                    if (prov_struct.name, need_struct.name, type_id) not in transport_dict:
                        transport_dict[(prov_struct.name, need_struct.name, type_id)] = 0
                    if struct_provide[type_id] >= quantity:
                        transport_dict[(prov_struct.name, need_struct.name, type_id)] += quantity
                        struct_provide[type_id] -= quantity
                        struct_need[type_id] = 0
                    else:
                        transport_dict[(prov_struct.name, need_struct.name, type_id)] += struct_provide[type_id]
                        struct_need[type_id] -= struct_provide[type_id]
                        struct_provide[type_id] = 0
        logistic_dict['transport'] = transport_dict

    async def get_coop_pay(self, coop_pay_dict: dict):
        for cid, job_data in self.user_jobs_dict.items():
            if cid not in coop_pay_dict:
                coop_pay_dict[cid] = {
                    'total_duration': 0,
                    'total_tex': 0,
                    'total_manu_duration': 0,
                    'total_reac_duration': 0
                }

            for job in job_data:
                coop_pay_dict[cid]['total_duration'] += job.duration
                if job.activity_id == 11:
                    coop_pay_dict[cid]['total_reac_duration'] += job.duration
                elif coop_pay_dict[cid]['total_manu_duration'] == 1:
                    coop_pay_dict[cid]['total_manu_duration'] += job.duration
                coop_pay_dict[cid]['total_tex'] += job.cost

    async def add_material_data(self, type_id, result_dict):
        # 获取 Group 和 Category 信息
        group = SdeUtils.get_groupname_by_id(type_id)
        category = SdeUtils.get_category_by_id(type_id)
        mk_list = SdeUtils.get_market_group_list(type_id)
        work_node = self.work_graph.nodes[type_id]
        global_node = self.global_graph.nodes[type_id]
        market = MarketManager.get_market_by_type('jita')
        max_buy, min_sell = await market.get_type_order_rouge(type_id)

        missing = work_node['quantity'] if work_node['quantity'] >= 0 else 0
        redundant = - work_node['quantity'] if work_node['quantity'] < 0 else 0

        data = [
            type_id, # tid
            SdeUtils.get_name_by_id(type_id), # name
            SdeUtils.get_cn_name_by_id(type_id), # 名称
            missing, # 缺失
            redundant, # 冗余
            global_node['quantity'], # 总需求
            self.asset_dict.get(type_id, 0), # 库存
            max_buy, # jita收单
            min_sell, # jita 出单
            max_buy * missing, # 收单价格
            min_sell * missing - max_buy * missing, # 扫单差
            0, # 已挂单
            0, # 已收到
            '| '.join([f'{x}:{y:,}' for x, y in work_node['index_quantity'] if y != 0]), # 详情
        ]

        # 根据 group 或 category 进行判断和分类
        if group == "Mineral":
            result_dict["矿石"].append(data)
        elif group == 'Ice Product':
            result_dict['冰矿产物'].append(data)
        elif group == "Fuel Block":
            result_dict["燃料块"].append(data)
        elif group == "Moon Materials":
            result_dict["元素"].append(data)
        elif group == "Harvestable Cloud":
            result_dict["气云"].append(data)
        elif category == "Planetary Commodities":
            result_dict["行星工业"].append(data)
        elif 'Reaction Materials' in mk_list:
            result_dict['反应物'].append(data)
        else:
            result_dict["杂货"].append(data)

    def add_work_data(self, type_id, result_dict):
        work_node = self.work_graph.nodes[type_id]
        global_node = self.global_graph.nodes[type_id]
        production_quantity = BPManager.get_bp_product_quantity_typeid(type_id)
        action_id = BPManager.get_action_id(type_id)
        if self.have_bpo.get(type_id, False):
            bp_count = f'{self.bp_runs_dict.get(type_id, 0)}{"+无限"}'
        else:
            bp_count = self.bp_runs_dict.get(type_id, 0)

        data = [
            'M' if action_id == 1 else 'R',         # 类型
            type_id,                                # id
            SdeUtils.get_name_by_id(type_id),       # name
            SdeUtils.get_cn_name_by_id(type_id),    # 中文名
            self.asset_dict.get(type_id, 0),        # 库存
            work_node['quantity'],                  # 缺失
            global_node['quantity'],                # 总需求
            self.running_job.get(type_id, 0) * production_quantity,
            sum([job.runs for job in work_node['work_list']]),
            sum([job.runs for job in global_node['work_list']]),
            self.bp_quantity_dict.get(type_id, 0),
            bp_count,                               # 蓝图数量
            self.get_status(type_id)
        ]

        result_dict[type_id] = data

    def get_status(self, type_id):
        work_node = self.work_graph.nodes[type_id]
        work_list = work_node['work_list']

        out_edge = list(self.work_graph.out_edges(type_id, data=True))

        status_dict = {}
        for _, _, data in out_edge:
            if data['index'] not in status_dict:
                status_dict[data['index']] = 1
            status_dict[data['index']]  = max(data['status'], status_dict[data['index']])

        status_list = []
        for index, status in status_dict.items():
            if status == 1:
                status_str = None
            elif status == 2:
                status_str = 'O'
            elif status == 3:
                status_str = 'x'
            status_list.append((index, status_str))

        sorted(status_list, key=lambda x: x[0])
        res = '| '.join([f"{index}:{status}" for index, status in status_list if status])

        return res

    @classmethod
    async def async_progress_work_type(cls, user, plan_name, plan_list):
        from ..server_init import init_server_service
        await init_server_service(log=False)

        analyser: IndustryAnalyser = cls.create_analyser_by_plan(user, plan_name)
        analyser.bp_block_level = 1
        await analyser.analyse_progress_work_type(plan_list)
        material_cost = 0
        for node in [node for node, degree in analyser.global_graph.out_degree() if degree == 0]:
            if node == 'root':
                continue
            material_cost += analyser.global_graph.nodes[node]['buy_cost']

        eiv_cost = 0
        for node in [node for node, degree in analyser.global_graph.out_degree() if degree != 0]:
            if node == 'root':
                continue
            eiv_cost += analyser.global_graph.nodes[node]['eiv_cost']

        return [plan_list[0][0], material_cost, eiv_cost, material_cost + eiv_cost]
        # return analyser, plan_list

    @classmethod
    def progress_work_type(cls, user, plan_name, plan_list):
        return asyncio.run(cls.async_progress_work_type(user, plan_name, plan_list))

    cost_data_cache = TTLCache(maxsize=100, ttl=60 * 60)
    @classmethod
    def get_cost_data(cls, user, plan_name: str, plan_list, batch_size=None):
        """ 如何在緩存内，直接提取 """
        if (user.user_qq, plan_name, str(plan_list)) in cls.cost_data_cache:
            return cls.cost_data_cache[(user.user_qq, plan_name, str(plan_list))]
        """ 计算planlist中的材料成本，用于批量计算 """
        def chunks(lst, n):
            """按指定大小将列表分块"""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        cpu_count = multiprocessing.cpu_count()
        # 如果没有指定batch_size，根据CPU数量和列表长度计算合适的批次大小
        if batch_size is None:
            batch_size = max(2, cpu_count - 1)
        logger.info(f'get_cost_data: batch_size = {batch_size}')
        cost_dict = {}
        total_plans = len(plan_list)

        with tqdm(total=total_plans, desc="成本计算", unit="个", ascii='=-') as pbar:
            for batch in chunks(plan_list, batch_size):
                with ProcessPoolExecutor(max_workers=min(6, cpu_count)) as executor:
                    futures = [
                        executor.submit(cls.progress_work_type, user, plan_name, [plan])
                        for plan in batch
                    ]

                    for future in futures:
                        result = future.result()
                        cost_dict[result[0]] = result[1:]
                        pbar.update()

        cls.cost_data_cache[(user.user_qq, plan_name, str(plan_list))] = cost_dict
        return cost_dict

    @classmethod
    async def get_cost_detail(cls, user, plan_name: str, product: str):
        analyser = cls.create_analyser_by_plan(user, plan_name)
        analyser.bp_block_level = 1
        await analyser.analyse_progress_work_type([[product, 1]])

        res = {'material': {}, 'group_detail': {}}

        material_dict = res['material']
        total_cost = 0
        for node in [node for node, degree in analyser.global_graph.out_degree() if degree == 0]:
            if node == 'root':
                continue
            cost = analyser.global_graph.nodes[node]['buy_cost']
            material_dict[node] = [cost]
            total_cost += cost

        eiv_cost = 0
        for node in [node for node, degree in analyser.global_graph.out_degree() if degree != 0]:
            if node == 'root':
                continue
            eiv_cost += analyser.global_graph.nodes[node]['eiv_cost']
        total_cost += eiv_cost
        res['eiv'] = [eiv_cost, eiv_cost / total_cost]
        res['type_id'] = SdeUtils.get_id_by_name(product)
        res['total_cost'] = total_cost
        res['jita_price'] = await analyser.market.get_type_order_rouge(res['type_id'])
        for node, data in material_dict.items():
            data.append(data[0] / total_cost)

        res['group_detail'] = {'矿石': [0], '燃料块': [0], '元素': [0], '气云': [0], '行星工业': [0], '冰矿产物': [0], '杂货': [0]}
        group_dict = res['group_detail']
        for node, data in material_dict.items():
            group = SdeUtils.get_groupname_by_id(node)
            category = SdeUtils.get_category_by_id(node)
            # 根据 group 或 category 进行判断和分类
            if group == "Mineral":
                group_dict["矿石"][0] += data[0]
            elif group == 'Ice Product':
                group_dict['冰矿产物'][0] += data[0]
            elif group == "Fuel Block":
                group_dict['燃料块'][0] += data[0]
            elif group == "Moon Materials":
                group_dict['元素'][0] += data[0]
            elif group == "Harvestable Cloud":
                group_dict['气云'][0] += data[0]
            elif category == "Planetary Commodities":
                group_dict['行星工业'][0] += data[0]
            else:
                group_dict["杂货"][0] += data[0]
        for group, data in group_dict.items():
            data.append(data[0] / total_cost)

        return res
