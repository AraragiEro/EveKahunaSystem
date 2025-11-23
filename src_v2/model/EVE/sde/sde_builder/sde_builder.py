"""
SDE Builder 主控制器
协调各模块完成完整的 SDE 数据构建流程
"""
import os
import asyncio
from typing import Optional

from src_v2.core.log import logger
from .database_manager import SDEDatabaseManager, SDEModel
from .downloader import SDEDownloader
from .extractor import SDEExtractor
from .parser import SDEParser
from .importer import SDEImporter


class SDEBuilder:
    """SDE 数据构建器主控制器"""
    
    def __init__(self):
        self.db_manager = SDEDatabaseManager()
        self.downloader = SDEDownloader()
        self.extractor = SDEExtractor()
        self.parser = SDEParser()
        self.importer = SDEImporter(self.db_manager, self.parser)
    
    async def init_database(self):
        """初始化数据库和表结构"""
        logger.info("初始化 SDE 数据库")
        await self.db_manager.init()
        logger.info("SDE 数据库初始化完成")
    
    async def get_current_version(self) -> Optional[int]:
        """
        获取当前已安装的版本号
        
        Returns:
            版本号，如果未安装返回 None
        """
        return await self.importer.get_current_version()
    
    async def get_latest_version(self) -> Optional[dict]:
        """
        获取最新可用版本号
        
        Returns:
            包含版本信息的字典，失败返回 None
        """
        return await self.downloader.get_latest_version()
    
    async def check_update(self) -> bool:
        """
        检查是否有新版本可用
        
        Returns:
            是否有新版本
        """
        current = await self.get_current_version()
        latest_info = await self.get_latest_version()
        
        if not latest_info:
            logger.warning("无法获取最新版本信息")
            return False
        
        latest = latest_info.get('buildNumber')
        
        if current is None:
            logger.info("当前未安装任何版本，需要更新")
            return True
        
        if latest and latest > current:
            logger.info(f"发现新版本: 当前 {current} -> 最新 {latest}")
            return True
        else:
            logger.info(f"已是最新版本: {current}")
            return False
    
    async def build(self, force: bool = False, target_version: Optional[int] = None) -> bool:
        """
        执行完整的构建流程（下载→解压→解析→导入）
        
        Args:
            force: 是否强制更新（即使版本相同）
            target_version: 目标版本号，如果为 None 则使用最新版本
        
        Returns:
            是否成功
        """
        try:
            logger.info("=" * 60)
            logger.info("开始 SDE 数据构建流程")
            logger.info("=" * 60)
            
            # 步骤1: 检查版本
            if not force:
                if target_version:
                    current = await self.get_current_version()
                    if current and current == target_version:
                        logger.info(f"当前已安装目标版本 {target_version}，跳过更新")
                        return True
                else:
                    has_update = await self.check_update()
                    if not has_update:
                        logger.info("已是最新版本，跳过更新")
                        return True
            
            # 步骤2: 下载数据包（带重试机制）
            logger.info("步骤 1/4: 下载 SDE 数据包")
            max_retries = 3
            zip_path = None
            
            for attempt in range(max_retries):
                if attempt > 0:
                    logger.info(f"重试下载 (第 {attempt + 1}/{max_retries} 次)")
                
                if target_version:
                    # 下载指定版本
                    url = f"https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-{target_version}-jsonl.zip"
                    zip_path = await self.downloader.download(url, target_version)
                else:
                    # 下载最新版本
                    zip_path = await self.downloader.download_latest()
                
                if not zip_path:
                    logger.error("下载失败")
                    if attempt < max_retries - 1:
                        logger.info("等待 5 秒后重试...")
                        await asyncio.sleep(5)
                        continue
                    return False
                
                # 验证 ZIP 文件有效性
                logger.info("验证下载的 ZIP 文件...")
                if self.extractor.is_valid_zip(zip_path):
                    logger.info("ZIP 文件验证通过")
                    break
                else:
                    logger.warning(f"ZIP 文件无效，删除并重新下载: {zip_path}")
                    # 删除无效的 ZIP 文件
                    try:
                        if os.path.exists(zip_path):
                            os.remove(zip_path)
                            logger.info(f"已删除无效的 ZIP 文件: {zip_path}")
                    except Exception as e:
                        logger.warning(f"删除无效 ZIP 文件失败: {e}")
                    
                    zip_path = None
                    if attempt < max_retries - 1:
                        logger.info("等待 5 秒后重新下载...")
                        await asyncio.sleep(5)
                    else:
                        logger.error("达到最大重试次数，下载失败")
                        return False
            
            if not zip_path:
                logger.error("下载失败")
                return False
            
            # 步骤3: 解压数据包
            logger.info("步骤 2/4: 解压 SDE 数据包")
            extract_dir = self.extractor.extract(zip_path)
            if not extract_dir:
                logger.error("解压失败")
                # 如果解压失败，可能是 ZIP 文件损坏，尝试重新下载
                if os.path.exists(zip_path):
                    logger.warning("解压失败，可能是 ZIP 文件损坏，尝试重新下载...")
                    try:
                        os.remove(zip_path)
                        logger.info(f"已删除损坏的 ZIP 文件: {zip_path}")
                    except Exception as e:
                        logger.warning(f"删除损坏 ZIP 文件失败: {e}")
                    
                    # 重新下载一次
                    logger.info("重新下载 ZIP 文件...")
                    if target_version:
                        url = f"https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-{target_version}-jsonl.zip"
                        zip_path = await self.downloader.download(url, target_version)
                    else:
                        zip_path = await self.downloader.download_latest()
                    
                    if zip_path and self.extractor.is_valid_zip(zip_path):
                        logger.info("重新下载成功，再次尝试解压...")
                        extract_dir = self.extractor.extract(zip_path)
                        if not extract_dir:
                            logger.error("重新下载后解压仍然失败")
                            return False
                    else:
                        logger.error("重新下载失败或文件仍然无效")
                        return False
                else:
                    return False
            
            # 验证解压文件
            if not self.extractor.verify_extracted_files(extract_dir):
                logger.error("解压文件验证失败")
                return False
            
            # 步骤4: 初始化数据库（如果需要）
            logger.info("步骤 3/4: 初始化数据库")
            await self.init_database()
            
            # 步骤5: 导入数据
            logger.info("步骤 4/4: 导入数据到数据库")
            success = await self.importer.full_update(extract_dir)
            
            if success:
                # 更新配置文件中的版本号
                latest_info = await self.get_latest_version()
                if latest_info:
                    build_number = latest_info.get('buildNumber')
                    if build_number:
                        from src_v2.core.config.config import update_config
                        update_config('SDE_BUILDER', 'Current_Build_Number', str(build_number))
                        logger.info(f"已更新配置文件中的版本号: {build_number}")
                
                logger.info("=" * 60)
                logger.info("SDE 数据构建完成！")
                logger.info("=" * 60)
            else:
                logger.error("数据导入失败")
            
            return success
        
        except Exception as e:
            logger.error(f"SDE 数据构建失败: {e}", exc_info=True)
            return False
    
    async def update(self, force: bool = False, target_version: Optional[int] = None) -> bool:
        """
        执行更新操作（build 的别名）
        
        Args:
            force: 是否强制更新
            target_version: 目标版本号
        
        Returns:
            是否成功
        """
        return await self.build(force=force, target_version=target_version)
    
    async def close(self):
        """关闭数据库连接"""
        await self.db_manager.close()

