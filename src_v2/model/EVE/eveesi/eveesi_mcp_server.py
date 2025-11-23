from typing import Any
import httpx
import sys
import os

# 添加项目根目录到sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../.."))
print(f"添加路径: {project_root}")
sys.path.append(project_root)

from mcp.server.fastmcp import FastMCP

# 使用绝对导入替代相对导入
from src.service.evesso_server import eveesi


# Initialize FastMCP server
mcp = FastMCP("weather")

@mcp.tool()
async def universe_structures_structure(access_token: str, structure_id: int):
    """Retrieve detailed information about a specific EVE structure.

    Args:
        access_token : A valid access token for authentication with the ESI API.
        structure_id : The unique identifier of the structure to retrieve details about.
    """
    res = await eveesi.universe_structures_structure(access_token, structure_id)
    return res

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')