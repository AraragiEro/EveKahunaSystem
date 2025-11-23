"""
pytest 配置文件
用于配置测试环境
"""
import sys
import os

# 添加项目路径到 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# plugin_path = os.path.join(project_root, 'data', 'plugins', 'kahuna_bot', 'src')

if project_root not in sys.path:
    sys.path.insert(0, project_root)