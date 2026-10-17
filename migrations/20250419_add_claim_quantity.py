"""
工作流任务接取支持部分数量数据库迁移脚本
创建日期: 2026-04-19

功能说明:
1. 在 eve_industry_plan_task_claim 表中添加 claimed_quantity 字段
2. 修改唯一约束以支持多用户接取同一任务的不同数量
3. 保留现有数据（默认 claimed_quantity = 1）
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


def upgrade():
    """升级数据库"""

    # ===== 修改 eve_industry_plan_task_claim 表 =====

    # 1. 添加 claimed_quantity 列
    op.add_column(
        "eve_industry_plan_task_claim",
        sa.Column(
            "claimed_quantity",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    print("✓ 添加 claimed_quantity 字段成功")

    # 2. 删除旧唯一约束
    try:
        op.drop_constraint(
            "uq_task_claim_per_item", "eve_industry_plan_task_claim", type_="unique"
        )
        print("✓ 删除旧唯一约束 uq_task_claim_per_item 成功")
    except Exception as e:
        print(f"⚠ 删除旧约束时出错（可能不存在）: {e}")

    # 3. 创建新唯一约束（按用户+任务）
    op.create_unique_constraint(
        "uq_task_claim_per_user_item",
        "eve_industry_plan_task_claim",
        ["plan_token", "workflow_item_key", "claimed_by"],
    )

    print("✓ 创建新唯一约束 uq_task_claim_per_user_item 成功")

    print("\n✅ 数据库升级完成")


def downgrade():
    """回滚数据库"""

    # ===== 恢复 eve_industry_plan_task_claim 表 =====

    # 1. 删除新唯一约束
    try:
        op.drop_constraint(
            "uq_task_claim_per_user_item",
            "eve_industry_plan_task_claim",
            type_="unique",
        )
        print("✓ 删除新唯一约束 uq_task_claim_per_user_item 成功")
    except Exception as e:
        print(f"⚠ 删除新约束时出错: {e}")

    # 2. 恢复旧唯一约束
    op.create_unique_constraint(
        "uq_task_claim_per_item",
        "eve_industry_plan_task_claim",
        ["plan_token", "workflow_item_key"],
    )

    print("✓ 恢复旧唯一约束 uq_task_claim_per_item 成功")

    # 3. 删除 claimed_quantity 列
    op.drop_column("eve_industry_plan_task_claim", "claimed_quantity")

    print("✓ 删除 claimed_quantity 字段成功")

    print("\n✅ 数据库回滚完成")


# 允许直接运行脚本
if __name__ == "__main__":
    print("请使用 alembic 运行迁移:")
    print("  alembic upgrade head")
    print("  alembic downgrade -1")
    print("\n或手动执行 upgrade() / downgrade() 函数")
