import aiohttp
import os

class IconDownloader:
    
    @classmethod
    async def download_from_url2path(cls, url: str, save_path: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    content = await response.read()
                    if not os.path.exists(os.path.dirname(save_path)):
                        os.makedirs(os.path.dirname(save_path))
                    with open(save_path, 'wb') as f:
                        f.write(content)
                    return save_path
                else:
                    raise Exception(f"请求状态码: {response.status}")

