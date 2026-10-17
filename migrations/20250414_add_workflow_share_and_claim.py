"""
工作流分享功能数据库迁移脚本
创建日期: 2026-04-14

功能说明:
1. 在 eve_industry_plan 表中添加分享相关字段
2. 创建 eve_industry_plan_task_claim 表（任务接取记录）
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


def upgrade():
    """升级数据库"""

    # ===== 1. 修改 eve_industry_plan 表 =====

    # 添加新列
    op.add_column(
        "eve_industry_plan",
        sa.Column("public", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "eve_industry_plan", sa.Column("share_token", sa.Text(), nullable=True)
    )
    op.add_column(
        "eve_industry_plan",
        sa.Column("filter_snapshot", sa.JSON(), nullable=True, server_default="{}"),
    )

    # 创建索引
    op.create_index(
        "idx_plan_share_token", "eve_industry_plan", ["share_token"], unique=True
    )
    op.create_index(
        "idx_plan_public_user", "eve_industry_plan", ["public", "user_name"]
    )

    # 创建唯一约束
    op.create_unique_constraint(
        "uq_plan_share_token", "eve_industry_plan", ["share_token"]
    )

    print("✓ 添加分享字段到 eve_industry_plan 表成功")

    # ===== 2. 创建 eve_industry_plan_task_claim 表 =====

    op.create_table(
        "eve_industry_plan_task_claim",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_token", sa.Text(), nullable=False),
        sa.Column("workflow_item_key", sa.Text(), nullable=False),
        sa.Column("claimed_by", sa.Text(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), default=datetime.utcnow, nullable=False),
        sa.Column("status", sa.Text(), default="claimed"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_token", "workflow_item_key", name="uq_task_claim_per_item"
        ),
        sa.Index("idx_claim_plan_token", "plan_token"),
        sa.Index("idx_claim_claimed_by", "claimed_by"),
        sa.ForeignKeyConstraint(["claimed_by"], ["user.user_name"]),
    )

    print("✓ 创建 eve_industry_plan_task_claim 表成功")


def downgrade():
    """回滚数据库"""

    # ===== 1. 删除 eve_industry_plan_task_claim 表 =====
    op.drop_table("eve_industry_plan_task_claim")
    print("✓ 删除 eve_industry_plan_task_claim 表成功")

    # ===== 2. 恢复 eve_industry_plan 表 =====

    # 删除约束
    op.drop_constraint("uq_plan_share_token", "eve_industry_plan", type_="unique")

    # 删除索引
    op.drop_index("idx_plan_public_user", table_name="eve_industry_plan")
    op.drop_index("idx_plan_share_token", table_name="eve_industry_plan")

    # 删除列
    op.drop_column("eve_industry_plan", "filter_snapshot")
    op.drop_column("eve_industry_plan", "share_token")
    op.drop_column("eve_industry_plan", "public")

    print("✓ 移除分享字段成功")


# 允许直接运行脚本
if __name__ == "__main__":
    print("请使用 alembic 运行迁移:")
    print("  alembic upgrade head")
    print("或手动执行 upgrade() 函数")
