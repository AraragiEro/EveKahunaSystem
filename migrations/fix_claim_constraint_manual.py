"""
修复工作流任务接取表的唯一约束

用法:
    python migrations/fix_claim_constraint_manual.py
"""

import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# 数据库配置
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "192.168.5.2"),
    "port": os.getenv("POSTGRES_PORT", "62011"),
    "database": os.getenv("POSTGRES_DB", "kahunabot"),
    "user": os.getenv("POSTGRES_USER", "kahunabot"),
    "password": os.getenv("POSTGRES_PASSWORD", "kahunabot"),
}


async def fix_constraint():
    """修复数据库约束"""
    print("开始修复数据库约束...")
    
    # 创建直接连接
    database_url = f"postgresql+asyncpg://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    engine = create_async_engine(database_url)
    
    async with engine.begin() as session:
        # 1. 查看现有的约束
        print("\n1. 查看现有约束:")
        result = await session.execute(text("""
            SELECT 
                tc.constraint_name,
                kcu.column_name
            FROM 
                information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
            WHERE 
                tc.table_name = 'eve_industry_plan_task_claim'
                AND tc.constraint_type = 'UNIQUE'
            ORDER BY 
                tc.constraint_name,
                kcu.ordinal_position
        """))
        
        constraints = {}
        for row in result:
            name = row[0]
            col = row[1]
            if name not in constraints:
                constraints[name] = []
            constraints[name].append(col)
        
        for name, cols in constraints.items():
            print(f"   - {name}: {', '.join(cols)}")
        
        # 2. 删除旧约束（如果存在）
        print("\n2. 删除旧约束 uq_task_claim_per_item...")
        try:
            await session.execute(text("""
                ALTER TABLE eve_industry_plan_task_claim 
                DROP CONSTRAINT IF EXISTS uq_task_claim_per_item
            """))
            print("   [OK] 删除成功")
        except Exception as e:
            print(f"   [WARN] 删除失败（可能不存在）: {e}")
        
        # 3. 删除新约束（如果存在，避免重复创建）
        print("\n3. 删除新约束（如果存在）...")
        try:
            await session.execute(text("""
                ALTER TABLE eve_industry_plan_task_claim 
                DROP CONSTRAINT IF EXISTS uq_task_claim_per_user_item
            """))
            print("   [OK] 删除成功")
        except Exception as e:
            print(f"   [WARN] 删除失败: {e}")
        
        # 4. 创建新的唯一约束
        print("\n4. 创建新约束 uq_task_claim_per_user_item...")
        try:
            await session.execute(text("""
                ALTER TABLE eve_industry_plan_task_claim 
                ADD CONSTRAINT uq_task_claim_per_user_item 
                UNIQUE (plan_token, workflow_item_key, claimed_by)
            """))
            print("   [OK] 创建成功")
        except Exception as e:
            print(f"   [ERROR] 创建失败: {e}")
            raise
        
        # 5. 验证约束
        print("\n5. 验证约束:")
        result = await session.execute(text("""
            SELECT 
                tc.constraint_name,
                kcu.column_name
            FROM 
                information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
            WHERE 
                tc.table_name = 'eve_industry_plan_task_claim'
                AND tc.constraint_type = 'UNIQUE'
            ORDER BY 
                tc.constraint_name,
                kcu.ordinal_position
        """))
        
        constraints = {}
        for row in result:
            name = row[0]
            col = row[1]
            if name not in constraints:
                constraints[name] = []
            constraints[name].append(col)
        
        for name, cols in constraints.items():
            print(f"   - {name}: {', '.join(cols)}")
        
        print("\n✅ 约束修复完成！")
        return True


if __name__ == "__main__":
    result = asyncio.run(fix_constraint())
    sys.exit(0 if result else 1)
