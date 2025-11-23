#!/usr/bin/env python
"""
SDE 独立更新脚本
用于在服务器关闭后进行全量更新
"""
import asyncio
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src_v2.model.EVE.sde.sde_builder import SDEBuilder
from src_v2.core.log import logger


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='SDE 数据更新工具')
    parser.add_argument('--force', action='store_true', help='强制更新（即使版本相同）')
    parser.add_argument('--check-only', action='store_true', help='仅检查版本，不执行更新')
    parser.add_argument('--version', type=int, help='更新到指定版本号')
    
    args = parser.parse_args()
    
    builder = SDEBuilder()
    
    try:
        if args.check_only:
            # 仅检查版本
            logger.info("检查版本信息...")
            current = await builder.get_current_version()
            latest_info = await builder.get_latest_version()
            
            if current:
                logger.info(f"当前已安装版本: {current}")
            else:
                logger.info("当前未安装任何版本")
            
            if latest_info:
                latest = latest_info.get('buildNumber')
                release_date = latest_info.get('releaseDate')
                logger.info(f"最新可用版本: {latest} (发布日期: {release_date})")
                
                if current and latest:
                    if latest > current:
                        logger.info(f"发现新版本，建议更新: {current} -> {latest}")
                    else:
                        logger.info("已是最新版本")
            else:
                logger.warning("无法获取最新版本信息")
            
            return 0
        
        # 执行更新
        logger.info("开始 SDE 更新流程...")
        success = await builder.build(force=args.force, target_version=args.version)
        
        if success:
            logger.info("更新完成！")
            return 0
        else:
            logger.error("更新失败！")
            return 1
    
    except KeyboardInterrupt:
        logger.warning("用户中断更新")
        return 1
    except Exception as e:
        logger.error(f"更新过程中发生错误: {e}", exc_info=True)
        return 1
    finally:
        await builder.close()


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

