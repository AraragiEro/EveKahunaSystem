#!/usr/bin/env python3
"""
Neo4j 初始化脚本

用于初始化 Neo4j 数据库中的市场树和蓝图树数据。

使用方法:
    python init_neo4j.py              # 正常初始化（不清理现有数据）
    python init_neo4j.py --clean      # 清理现有数据后重新初始化
    python init_neo4j.py -c            # 同上（简写形式）
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def cleanup_resources():
    """清理所有资源"""
    from src_v2.core.database.connect_manager import postgres_manager, redis_manager, neo4j_manager
    from src_v2.model.EVE.sde.utils import SdeUtils
    
    try:
        # 关闭 Neo4j 连接
        await neo4j_manager.close()
        print("[清理] Neo4j 连接已关闭")
    except Exception as e:
        if "sys.meta_path is None" not in str(e) and "shutting down" not in str(e).lower():
            print(f"[清理] Neo4j 连接关闭时出错: {e}")
    
    try:
        # 关闭 SDE 数据库连接
        await SdeUtils.close_database()
        print("[清理] SDE 数据库连接已关闭")
    except Exception as e:
        print(f"[清理] SDE 数据库连接关闭时出错: {e}")
    
    try:
        # 关闭 PostgreSQL 连接
        await postgres_manager.close()
        print("[清理] PostgreSQL 连接已关闭")
    except Exception as e:
        print(f"[清理] PostgreSQL 连接关闭时出错: {e}")
    
    try:
        # 关闭 Redis 连接（如果有 close 方法）
        if hasattr(redis_manager, 'close'):
            await redis_manager.close()
            print("[清理] Redis 连接已关闭")
    except Exception as e:
        print(f"[清理] Redis 连接关闭时出错: {e}")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="初始化 Neo4j 数据库中的市场树和蓝图树数据"
    )
    parser.add_argument(
        "--clean", "-c",
        action="store_true",
        help="清理现有数据后重新初始化"
    )
    return parser.parse_args()


async def main():
    """主函数"""
    args = parse_args()
    
    print("=" * 60)
    print("Neo4j 初始化脚本")
    print("=" * 60)
    
    if args.clean:
        print("[模式] 清理模式：将清理现有数据后重新初始化")
    else:
        print("[模式] 正常模式：保留现有数据，仅初始化缺失的数据")
    
    print("\n[步骤 1/5] 初始化数据库连接...")
    
    try:
        # 初始化数据库连接
        from src_v2.core.database.connect_manager import postgres_manager, redis_manager, neo4j_manager
        from src_v2.model.EVE.sde.utils import SdeUtils
        
        await postgres_manager.init()
        print("  ✓ PostgreSQL 连接成功")
        
        await redis_manager.init()
        print("  ✓ Redis 连接成功")
        
        await neo4j_manager.init()
        print("  ✓ Neo4j 连接成功")
        
        await SdeUtils.init_database()
        print("  ✓ SDE 数据库连接成功")
        
    except Exception as e:
        print(f"  ✗ 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n[步骤 2/5] 初始化市场树...")
    
    try:
        from src_v2.model.EVE.industry.industry_utils import MarketTree
        
        await MarketTree.init_market_tree(clean=args.clean)
        print("  ✓ 市场树初始化完成")
        
    except Exception as e:
        print(f"  ✗ 市场树初始化失败: {e}")
        import traceback
        traceback.print_exc()
        await cleanup_resources()
        return 1
    
    print("\n[步骤 3/5] 链接类型到市场组...")
    
    try:
        await MarketTree.link_type_to_market_group(clean=args.clean)
        print("  ✓ 类型链接完成")
        
    except Exception as e:
        print(f"  ✗ 类型链接失败: {e}")
        import traceback
        traceback.print_exc()
        await cleanup_resources()
        return 1
    
    print("\n[步骤 4/5] 清理现有蓝图节点...")
    
    try:
        from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
        
        deleted_count = await NIU.delete_label_node("Blueprint")
        print(f"  ✓ 已清理 {deleted_count} 个 Blueprint 节点")
        
    except Exception as e:
        print(f"  ✗ 清理蓝图节点失败: {e}")
        import traceback
        traceback.print_exc()
        await cleanup_resources()
        return 1
    
    print("\n[步骤 5/5] 初始化蓝图数据...")
    
    try:
        from src_v2.model.EVE.industry.blueprint import BPManager
        
        await BPManager.init_bp_data_to_neo4j()
        print("  ✓ 蓝图数据初始化完成")
        
    except Exception as e:
        print(f"  ✗ 蓝图数据初始化失败: {e}")
        import traceback
        traceback.print_exc()
        await cleanup_resources()
        return 1
    
    print("\n" + "=" * 60)
    print("✓ 所有初始化步骤完成！")
    print("=" * 60)
    
    # 清理资源
    print("\n[清理] 正在关闭数据库连接...")
    await cleanup_resources()
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[中断] 收到键盘中断，正在退出...")
        try:
            asyncio.run(cleanup_resources())
        except Exception:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        try:
            asyncio.run(cleanup_resources())
        except Exception:
            pass
        sys.exit(1)

