import os
from .toml_config import TomlConfigParser
from ..log import logger

# 获取当前脚本文件的完整路径
script_file_path = os.path.abspath(__file__)

# 获取脚本文件所在目录
script_dir = os.path.dirname(script_file_path)

# 初始化 TOML 解析器
config_path = os.path.join(script_dir, '../../../config.toml')
# 向后兼容：如果 config.toml 不存在，尝试使用 config.ini
if not os.path.exists(config_path):
    config_path_ini = os.path.join(script_dir, '../../../config.ini')
    if os.path.exists(config_path_ini):
        logger.warning(f"config.toml 不存在，使用 config.ini: {config_path_ini}")
        config_path = config_path_ini
        # 如果使用 INI，回退到旧的 ConfigParser
        import configparser
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(config_path)
        
        def reload_config():
            config.read(config_path)
        
        def update_config(section, key, value):
            if section not in config:
                config[section] = {}
            config[section][key] = str(value)
            with open(config_path, 'w', encoding='utf-8') as f:
                config.write(f)
    else:
        logger.error(f"配置文件不存在: config.toml 或 config.ini")
        config = TomlConfigParser(config_path)
        
        def reload_config():
            config.reload()
        
        def update_config(section, key, value):
            config.update(section, key, value)
else:
    config = TomlConfigParser(config_path)
    
    def reload_config():
        config.reload()
    
    def update_config(section, key, value):
        config.update(section, key, value)

# 访问配置内容
# print(config['DEFAULT']['AppName'])  # 输出：MyApp
# print(config['Database']['Host'])  # 输出：localhost

# 转换为字典
# db_config = dict(config['Database'])
# print(db_config)  # 输出：{'host': 'localhost', 'port': '5432', 'user': 'admin', 'password': 'secret'}

# logger.debug("Config server loaded.")
# logger.debug(f"database type: {config['APP']['DBTYPE']}")
