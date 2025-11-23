"""
蓝图数据模型和特殊处理
将 blueprints.jsonl 拆解成4个表：IndustryBlueprints, IndustryActivities, 
IndustryActivityMaterials, IndustryActivityProducts
"""
from sqlalchemy import Column, Integer, Float, Index
from .database_manager import SDEModel
from .sde_config import ACTIVITY_ID_MAP


class IndustryBlueprints(SDEModel):
    """蓝图基本信息表"""
    __tablename__ = 'industryBlueprints'
    
    blueprintTypeID = Column(Integer, primary_key=True)  # blueprints.jsonl.blueprintTypeID
    maxProductionLimit = Column(Integer, nullable=True)  # blueprints.jsonl.maxProductionLimit


class IndustryActivities(SDEModel):
    """蓝图活动信息表"""
    __tablename__ = 'industryActivities'
    
    blueprintTypeID = Column(Integer, primary_key=True, nullable=False)  # blueprints.jsonl.blueprintTypeID
    activityID = Column(Integer, primary_key=True, nullable=False)  # 映射自 activities 的 key
    time = Column(Integer, nullable=False)  # 时间消耗
    
    # 创建普通索引
    __table_args__ = (
        Index('idx_activity', 'activityID'),
    )


class IndustryActivityMaterials(SDEModel):
    """蓝图原料信息表"""
    __tablename__ = 'industryActivityMaterials'
    
    blueprintTypeID = Column(Integer, primary_key=True, nullable=False)  # blueprints.jsonl.blueprintTypeID
    activityID = Column(Integer, primary_key=True, nullable=False)  # 活动类型id
    materialTypeID = Column(Integer, primary_key=True, nullable=False)  # 原料id
    quantity = Column(Integer, nullable=False)  # 原料数量


class IndustryActivityProducts(SDEModel):
    """蓝图产品信息表"""
    __tablename__ = 'industryActivityProducts'
    
    blueprintTypeID = Column(Integer, primary_key=True, nullable=False)  # blueprints.jsonl.blueprintTypeID
    activityID = Column(Integer, primary_key=True, nullable=False)  # 活动类型id
    productTypeID = Column(Integer, primary_key=True, nullable=False)  # 产品id
    quantity = Column(Integer, nullable=False)  # 产品数量
    probability = Column(Float, nullable=False)  # 概率


def process_blueprints_row(row: dict) -> tuple:
    """
    处理 blueprints.jsonl 的单行数据，拆解成4个表的数据
    
    Args:
        row: 从 JSONL 解析的原始数据
        
    Returns:
        返回4个列表的元组：
        - blueprints_records: IndustryBlueprints 记录列表（通常只有1条）
        - activities_records: IndustryActivities 记录列表
        - materials_records: IndustryActivityMaterials 记录列表
        - products_records: IndustryActivityProducts 记录列表
    """
    blueprint_type_id = row.get('blueprintTypeID')
    if not blueprint_type_id:
        # 如果没有 blueprintTypeID，跳过这条记录
        return [], [], [], []
    
    # 1. IndustryBlueprints 记录
    blueprints_records = [{
        'blueprintTypeID': blueprint_type_id,
        'maxProductionLimit': row.get('maxProductionLimit')
    }]
    
    # 2. 处理 activities
    activities_records = []
    materials_records = []
    products_records = []
    
    activities = row.get('activities', {})
    if not isinstance(activities, dict):
        return blueprints_records, activities_records, materials_records, products_records
    
    # 遍历每个活动
    for activity_key, activity_data in activities.items():
        # 将活动类型字符串映射为 activityID
        activity_id = ACTIVITY_ID_MAP.get(activity_key)
        if not activity_id:
            # 如果活动类型不在映射中，跳过该活动
            continue
        
        # 如果活动存在 time，创建 IndustryActivities 记录
        if 'time' in activity_data:
            activities_records.append({
                'blueprintTypeID': blueprint_type_id,
                'activityID': activity_id,
                'time': activity_data['time']
            })
        
        # 如果活动存在 materials，遍历创建 IndustryActivityMaterials 记录
        if 'materials' in activity_data and isinstance(activity_data['materials'], list):
            for material in activity_data['materials']:
                if isinstance(material, dict) and 'typeID' in material and 'quantity' in material:
                    materials_records.append({
                        'blueprintTypeID': blueprint_type_id,
                        'activityID': activity_id,
                        'materialTypeID': material['typeID'],
                        'quantity': material['quantity']
                    })
        
        # 如果活动存在 products，遍历创建 IndustryActivityProducts 记录
        if 'products' in activity_data and isinstance(activity_data['products'], list):
            for product in activity_data['products']:
                if isinstance(product, dict) and 'typeID' in product and 'quantity' in product:
                    # probability 可能不存在，默认为 1.0
                    probability = product.get('probability', 1.0)
                    products_records.append({
                        'blueprintTypeID': blueprint_type_id,
                        'activityID': activity_id,
                        'productTypeID': product['typeID'],
                        'quantity': product['quantity'],
                        'probability': probability
                    })
    
    return blueprints_records, activities_records, materials_records, products_records

