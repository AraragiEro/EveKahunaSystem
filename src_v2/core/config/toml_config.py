"""
TOML 配置读取器，兼容 ConfigParser API
"""
import os
import sys
from typing import Any, Dict, Optional, Union

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # 兼容旧版本

try:
    import tomli_w
except ImportError:
    tomli_w = None

from ..log import logger


class SectionProxy:
    """Section 代理类，模拟 ConfigParser 的 SectionProxy"""
    
    def __init__(self, data: Dict[str, Any], section_name: str):
        self._data = data
        self._section_name = section_name
    
    def __getitem__(self, key: str) -> str:
        """获取配置值，转换为字符串"""
        if key not in self._data:
            raise KeyError(f"'{key}' not found in section '{self._section_name}'")
        value = self._data[key]
        return self._convert_to_string(value)
    
    def __contains__(self, key: str) -> bool:
        """检查键是否存在"""
        return key in self._data
    
    def get(self, key: str, fallback: Optional[str] = None) -> Optional[str]:
        """获取配置值，带默认值"""
        if key not in self._data:
            return fallback
        return self._convert_to_string(self._data[key])
    
    def keys(self):
        """返回所有键"""
        return self._data.keys()
    
    def values(self):
        """返回所有值（转换为字符串）"""
        return [self._convert_to_string(v) for v in self._data.values()]
    
    def items(self):
        """返回所有键值对（值转换为字符串）"""
        return [(k, self._convert_to_string(v)) for k, v in self._data.items()]
    
    def _convert_to_string(self, value: Any) -> str:
        """将值转换为字符串，布尔值转换为 'true'/'false'"""
        if isinstance(value, bool):
            return 'true' if value else 'false'
        elif value is None:
            return ''
        else:
            return str(value)
    
    def __iter__(self):
        """支持迭代"""
        return iter(self._data)
    
    def __len__(self):
        """返回键的数量"""
        return len(self._data)


class TomlConfigParser:
    """TOML 配置解析器，兼容 ConfigParser API"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self._data: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """加载 TOML 配置文件"""
        if not os.path.exists(self.config_path):
            logger.warning(f"配置文件不存在: {self.config_path}")
            self._data = {}
            return
        
        try:
            with open(self.config_path, 'rb') as f:
                self._data = tomllib.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            self._data = {}
    
    def __getitem__(self, section: str) -> SectionProxy:
        """获取配置节"""
        if section not in self._data:
            raise KeyError(f"Section '{section}' not found")
        return SectionProxy(self._data[section], section)
    
    def __contains__(self, section: str) -> bool:
        """检查节是否存在"""
        return section in self._data
    
    def get(self, section: str, key: str, fallback: Optional[str] = None) -> Optional[str]:
        """获取配置值"""
        if section not in self._data:
            return fallback
        section_data = self._data[section]
        if key not in section_data:
            return fallback
        value = section_data[key]
        if isinstance(value, bool):
            return 'true' if value else 'false'
        return str(value) if value is not None else fallback
    
    def getint(self, section: str, key: str, fallback: Optional[int] = None) -> Optional[int]:
        """获取整数值"""
        value = self.get(section, key)
        if value is None:
            return fallback
        try:
            return int(value)
        except (ValueError, TypeError):
            return fallback
    
    def getfloat(self, section: str, key: str, fallback: Optional[float] = None) -> Optional[float]:
        """获取浮点数值"""
        value = self.get(section, key)
        if value is None:
            return fallback
        try:
            return float(value)
        except (ValueError, TypeError):
            return fallback
    
    def getboolean(self, section: str, key: str, fallback: Optional[bool] = None) -> Optional[bool]:
        """获取布尔值"""
        value = self.get(section, key)
        if value is None:
            return fallback
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', 'on', '1')
        return bool(value)
    
    def sections(self) -> list:
        """返回所有节名"""
        return list(self._data.keys())
    
    def items(self, section: str) -> list:
        """返回节的键值对"""
        if section not in self._data:
            return []
        section_proxy = self[section]
        return list(section_proxy.items())
    
    def reload(self):
        """重新加载配置"""
        self._load_config()
    
    def update(self, section: str, key: str, value: Any):
        """更新配置值"""
        if section not in self._data:
            self._data[section] = {}
        
        # 转换值类型
        if isinstance(value, str):
            # 尝试转换为合适的类型
            if value.lower() in ('true', 'false'):
                self._data[section][key] = value.lower() == 'true'
            elif value.isdigit():
                self._data[section][key] = int(value)
            else:
                try:
                    float_val = float(value)
                    if '.' in value:
                        self._data[section][key] = float_val
                    else:
                        self._data[section][key] = int(value)
                except ValueError:
                    self._data[section][key] = value
        else:
            self._data[section][key] = value
        
        self._save_config()
    
    def _save_config(self):
        """保存配置到文件"""
        if tomli_w is None:
            logger.error("tomli-w 未安装，无法写入配置文件")
            return
        
        try:
            with open(self.config_path, 'wb') as f:
                tomli_w.dump(self._data, f)
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

