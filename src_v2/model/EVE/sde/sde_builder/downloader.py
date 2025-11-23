"""
SDE 下载模块
从官方网站下载最新的 SDE 数据包
"""
import os
import aiohttp
import aiofiles
from typing import Optional, Dict
from datetime import datetime
from tqdm import tqdm

from src_v2.core.config.config import config
from src_v2.core.log import logger
from src_v2.core.utils.path import DOWNLOAD_RESOURCE_PATH


class SDEDownloader:
    """SDE 数据包下载器"""
    
    def __init__(self):
        self.latest_version_url = config.get('SDE_BUILDER', 'Latest_Version_URL', 
                                             fallback='https://developers.eveonline.com/static-data/tranquility/latest.jsonl')
        self.latest_download_url = config.get('SDE_BUILDER', 'Latest_Download_URL',
                                              fallback='https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip')
        download_path = config.get('SDE_BUILDER', 'Download_Path', 
                                   fallback=os.path.join(DOWNLOAD_RESOURCE_PATH, 'sde'))
        self.download_path = str(download_path) if download_path else os.path.join(DOWNLOAD_RESOURCE_PATH, 'sde')
        
        # 确保下载目录存在
        os.makedirs(self.download_path, exist_ok=True)
    
    async def get_latest_version(self) -> Optional[Dict]:
        """
        获取最新版本信息
        
        Returns:
            包含 buildNumber 和 releaseDate 的字典，失败返回 None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.latest_version_url, ssl=False, 
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        text = await response.text()
                        # JSONL 格式，每行一个 JSON 对象
                        for line in text.strip().split('\n'):
                            if line.strip():
                                import json
                                data = json.loads(line)
                                if data.get('_key') == 'sde':
                                    logger.info(f"获取到最新版本: buildNumber={data.get('buildNumber')}, "
                                              f"releaseDate={data.get('releaseDate')}")
                                    return data
                        logger.warning("未找到 SDE 版本信息")
                        return None
                    else:
                        logger.error(f"获取版本信息失败，状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"获取最新版本信息时出错: {e}")
            return None
    
    async def download(self, url: Optional[str] = None, target_build_number: Optional[int] = None) -> Optional[str]:
        """
        下载 SDE 数据包
        
        Args:
            url: 下载 URL，如果为 None 则使用最新版本 URL
            target_build_number: 目标版本号，用于生成文件名
        
        Returns:
            下载文件的本地路径，失败返回 None
        """
        if url is None:
            url = self.latest_download_url
        
        # 生成文件名
        if target_build_number:
            filename = f"eve-online-static-data-{target_build_number}-jsonl.zip"
        else:
            # 使用时间戳作为文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"eve-online-static-data-latest-{timestamp}.zip"
        
        file_path = os.path.join(self.download_path, filename)
        
        # 检查文件是否已存在
        if os.path.exists(file_path):
            logger.info(f"文件已存在，跳过下载: {file_path}")
            return file_path
        
        logger.info(f"开始下载 SDE 数据包: {url}")
        logger.info(f"保存路径: {file_path}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=False, 
                                     timeout=aiohttp.ClientTimeout(total=3600)) as response:
                    if response.status == 200:
                        total_size = int(response.headers.get('Content-Length', 0))
                        downloaded = 0
                        
                        # 创建进度条
                        if total_size > 0:
                            # 有文件大小信息，显示进度条
                            progress_bar = tqdm(
                                total=total_size,
                                unit='B',
                                unit_scale=True,
                                unit_divisor=1024,
                                desc="下载 SDE 数据包",
                                ncols=100,
                                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
                            )
                        else:
                            # 没有文件大小信息，显示不确定进度条
                            progress_bar = tqdm(
                                unit='B',
                                unit_scale=True,
                                unit_divisor=1024,
                                desc="下载 SDE 数据包",
                                ncols=100,
                                bar_format='{l_bar}{bar}| {n_fmt} [{elapsed}, {rate_fmt}]'
                            )
                        
                        try:
                            async with aiofiles.open(file_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(8192):
                                    await f.write(chunk)
                                    downloaded += len(chunk)
                                    # 更新进度条
                                    progress_bar.update(len(chunk))
                            
                            progress_bar.close()
                            
                            # 格式化文件大小显示
                            if total_size > 0:
                                size_mb = total_size / (1024 * 1024)
                                logger.info(f"SDE 数据包下载完成: {file_path} ({size_mb:.2f} MB)")
                            else:
                                size_mb = downloaded / (1024 * 1024)
                                logger.info(f"SDE 数据包下载完成: {file_path} ({size_mb:.2f} MB)")
                            
                            return file_path
                        except Exception as e:
                            progress_bar.close()
                            logger.error(f"下载过程中出错: {e}")
                            raise
                    else:
                        logger.error(f"下载失败，状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"下载 SDE 数据包时出错: {e}")
            # 清理失败的文件
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return None
    
    async def download_latest(self) -> Optional[str]:
        """
        下载最新版本的 SDE 数据包
        
        Returns:
            下载文件的本地路径，失败返回 None
        """
        # 先获取版本信息
        version_info = await self.get_latest_version()
        if version_info:
            build_number = version_info.get('buildNumber')
            return await self.download(target_build_number=build_number)
        else:
            # 如果获取版本信息失败，直接下载最新版本
            return await self.download()

