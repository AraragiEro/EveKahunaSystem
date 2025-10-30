import configparser
from configparser import ConfigParser
import os


from ..log import logger

# 获取当前脚本文件的完整路径
script_file_path = os.path.abspath(__file__)

# 获取脚本文件所在目录
script_dir = os.path.dirname(script_file_path)

# 初始化解析器
config = configparser.ConfigParser()
config.optionxform = str    # 保持键名大小写
config_path = os.path.join(script_dir, '../../../config.ini')
config.read(config_path)

def reload_config():
    config.read(config_path)

# 访问配置内容
# print(config['DEFAULT']['AppName'])  # 输出：MyApp
# print(config['Database']['Host'])  # 输出：localhost

# 转换为字典
# db_config = dict(config['Database'])
# print(db_config)  # 输出：{'host': 'localhost', 'port': '5432', 'user': 'admin', 'password': 'secret'}

# logger.debug("Config server loaded.")
# logger.debug(f"database type: {config['APP']['DBTYPE']}")

def update_config(section, key, value):
    filename = config_path

    # 如果节不存在，创建新的节
    if section not in config:
        config[section] = {}

    # 更新值
    config[section][key] = str(value)

    # 写入文件
    with open(filename, 'w', encoding='utf-8') as f:
        config.write(f)
