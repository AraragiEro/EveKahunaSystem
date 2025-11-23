"""
SDE 解压模块
自动解压下载的数据包
"""
import os
import zipfile
from typing import Optional

from src_v2.core.config.config import config
from src_v2.core.log import logger
from src_v2.core.utils.path import TMP_PATH


class SDEExtractor:
    """SDE 数据包解压器"""
    
    def __init__(self):
        self.extract_path = config.get('SDE_BUILDER', 'Extract_Path',
                                      fallback=os.path.join(TMP_PATH, 'sde'))
        
        # 确保解压目录存在
        os.makedirs(self.extract_path, exist_ok=True)
    
    def is_valid_zip(self, zip_path: str) -> bool:
        """
        验证 ZIP 文件是否有效
        
        Args:
            zip_path: ZIP 文件路径
        
        Returns:
            是否有效
        """
        if not os.path.exists(zip_path):
            return False
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # 尝试读取文件列表，如果文件损坏会抛出异常
                zip_ref.testzip()
                # 检查是否有文件
                if len(zip_ref.namelist()) == 0:
                    logger.warning(f"ZIP 文件为空: {zip_path}")
                    return False
                return True
        except zipfile.BadZipFile:
            logger.error(f"无效的 ZIP 文件: {zip_path}")
            return False
        except Exception as e:
            logger.error(f"验证 ZIP 文件时出错: {zip_path}, 错误: {e}")
            return False
    
    def extract(self, zip_path: str, extract_to: Optional[str] = None) -> Optional[str]:
        """
        解压 ZIP 文件
        
        Args:
            zip_path: ZIP 文件路径
            extract_to: 解压目标目录，如果为 None 则使用默认目录
        
        Returns:
            解压后的目录路径，失败返回 None
        """
        if not os.path.exists(zip_path):
            logger.error(f"ZIP 文件不存在: {zip_path}")
            return None
        
        if extract_to is None:
            # 使用 ZIP 文件名（不含扩展名）作为解压目录名
            zip_name = os.path.splitext(os.path.basename(zip_path))[0]
            extract_to = os.path.join(self.extract_path, zip_name)
        
        # 如果目录已存在，先删除
        if os.path.exists(extract_to):
            logger.info(f"清理已存在的解压目录: {extract_to}")
            import shutil
            shutil.rmtree(extract_to)
        
        os.makedirs(extract_to, exist_ok=True)
        
        logger.info(f"开始解压: {zip_path} -> {extract_to}")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # 获取文件列表
                file_list = zip_ref.namelist()
                total_files = len(file_list)
                
                # 解压所有文件
                for i, file_name in enumerate(file_list):
                    zip_ref.extract(file_name, extract_to)
                    
                    # 每解压 100 个文件显示一次进度
                    if (i + 1) % 100 == 0 or (i + 1) == total_files:
                        logger.info(f"解压进度: {i + 1}/{total_files} 文件")
                
                logger.info(f"解压完成: {extract_to}")
                logger.info(f"共解压 {total_files} 个文件")
                
                return extract_to
        except zipfile.BadZipFile:
            logger.error(f"无效的 ZIP 文件: {zip_path}")
            return None
        except Exception as e:
            logger.error(f"解压文件时出错: {e}")
            # 清理失败的解压目录
            if os.path.exists(extract_to):
                try:
                    import shutil
                    shutil.rmtree(extract_to)
                except:
                    pass
            return None
    
    def verify_extracted_files(self, extract_dir: str) -> bool:
        """
        验证解压后的文件
        
        Args:
            extract_dir: 解压目录路径
        
        Returns:
            验证是否通过
        """
        if not os.path.exists(extract_dir):
            logger.error(f"解压目录不存在: {extract_dir}")
            return False
        
        # 检查是否有 JSONL 文件
        jsonl_files = [f for f in os.listdir(extract_dir) if f.endswith('.jsonl')]
        
        if not jsonl_files:
            logger.error(f"解压目录中没有找到 JSONL 文件: {extract_dir}")
            return False
        
        logger.info(f"验证通过，找到 {len(jsonl_files)} 个 JSONL 文件")
        return True

