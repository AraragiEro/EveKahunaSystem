"""
EVE Online 实体常量定义

集中管理所有硬编码的 EVE 实体 ID（区域、星系、建筑、物品类型等），
避免在多个模块中重复定义，便于统一维护。
"""

# ==================== 区域 (Region) ====================
REGION_FORGE_ID = 10000002          # The Forge（吉他所在区域）
REGION_VALE_ID = 10000003           # Vale of the Silent（FRT 所在区域）
REGION_PLEX_ID = 19000001           # PLEX 专用虚拟区域

# ==================== 星系 (System) ====================
JITA_SYSTEM_ID = 30000142           # Jita
PERIMETER_SYSTEM_ID = 30000144      # Perimeter

# ==================== 建筑/空间站 (Structure/Station) ====================
JITA_TRADE_HUB_STRUCTURE_ID = 60003760   # Jita 4-4 贸易中心
FRT_4H_STRUCTURE_ID = 1053970513596      # FRT 4-H 建筑
S33RB_O_STRUCTURE_ID = 1045441547980     # S33RB-O 建筑
B_9C24_KEEPSTAR_ID = 1046831245129       # B-9C24 Keepstar

# 特殊建筑列表
PIMI_STRUCTURE_LIST = [
    1042508032148,
    1042499803831,
    1044752365771,
]

# ==================== 物品类型 (Type) ====================
PLEX_ID = 44992                     # PLEX（伊甸币）
