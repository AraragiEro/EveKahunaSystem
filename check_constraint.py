"""
检查数据库约束状态
"""

import asyncio
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


async def check_constraints():
    """检查约束状态"""
    database_url = f"postgresql+asyncpg://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    engine = create_async_engine(database_url)
    
    async with engine.begin() as session:
        print("当前数据库约束:")
        result = await session.execute(text("""
            SELECT 
                tc.constraint_name,
                kcu.column_name,
                kcu.ordinal_position
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
            pos = row[2]
            if name not in constraints:
                constraints[name] = []
            constraints[name].append((pos, col))
        
        for name, cols in sorted(constraints.items()):
            cols_str = ", ".join([c[1] for c in sorted(cols)])
            print(f"  - {name}: {cols_str}")
        
        # 检查现有记录
        print("\n当前接取记录:")
        result = await session.execute(text("""
            SELECT plan_token, workflow_item_key, claimed_by, claimed_quantity
            FROM eve_industry_plan_task_claim
            WHERE plan_token = 'wf_LfYnRNq8JkW61nvv'
            LIMIT 10
        """))
        
        count = 0
        for row in result:
            count += 1
            print(f"  - {row[0][:20]}... | {row[1][:30]}... | {row[2]} | {row[3]}线")
        
        if count == 0:
            print("  (无记录)")
        else:
            print(f"\n共 {count} 条记录")


if __name__ == "__main__":
    asyncio.run(check_constraints())
