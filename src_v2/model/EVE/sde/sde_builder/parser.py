"""
SDE 解析模块
解析解压后的数据文件（JSON Lines 格式）
"""
import os
import json
from typing import Dict, List, Optional, Any, Iterator
from collections import defaultdict

from src_v2.core.config.config import config
from src_v2.core.log import logger


class SDEParser:
    """SDE 数据解析器"""
    
    # 支持的语言代码
    SUPPORTED_LANGUAGES = {'de', 'en', 'es', 'fr', 'ja', 'ko', 'ru', 'zh'}
    # 需要提取的语言
    EXTRACT_LANGUAGES = {'en', 'zh'}
    
    def __init__(self):
        # 获取白名单
        try:
            # 尝试从配置中获取白名单
            # TOML 列表会被转换为字符串，需要解析
            whitelist_str = config.get('SDE_BUILDER', 'Parse_Whitelist', fallback='[]')
            
            # 尝试解析为列表
            if isinstance(whitelist_str, str):
                import ast
                # 处理空字符串或空列表字符串
                if not whitelist_str.strip() or whitelist_str.strip() == '[]':
                    self.whitelist = []
                else:
                    try:
                        parsed = ast.literal_eval(whitelist_str)
                        self.whitelist = parsed if isinstance(parsed, list) else []
                    except (ValueError, SyntaxError) as e:
                        logger.warning(f"解析白名单字符串失败: {whitelist_str}, 错误: {e}")
                        self.whitelist = []
            elif isinstance(whitelist_str, list):
                # 如果已经是列表，直接使用
                self.whitelist = whitelist_str
            else:
                self.whitelist = []
        except Exception as e:
            logger.warning(f"解析白名单配置失败，使用空列表: {e}")
            self.whitelist = []
        
        # 验证白名单是列表类型
        if not isinstance(self.whitelist, list):
            logger.warning(f"白名单类型错误，期望列表，得到 {type(self.whitelist)}，使用空列表")
            self.whitelist = []
        
        # 记录白名单状态
        if self.whitelist:
            logger.info(f"SDE 解析器初始化，白名单: {self.whitelist} (共 {len(self.whitelist)} 项)")
        else:
            logger.info("SDE 解析器初始化，白名单为空（将只处理 _sde.jsonl）")
    
    def _is_multilang_dict(self, value: Any) -> bool:
        """
        判断值是否为多语言字典
        
        Args:
            value: 要检查的值
        
        Returns:
            是否为多语言字典
        """
        if not isinstance(value, dict):
            return False
        
        # 检查字典的 key 是否都是语言代码
        keys = set(value.keys())
        # 如果所有 key 都在支持的语言代码中，认为是多语言字典
        return len(keys) > 0 and keys.issubset(self.SUPPORTED_LANGUAGES)
    
    def _extract_multilang_field(self, field_name: str, value: Dict[str, str]) -> Dict[str, Any]:
        """
        提取多语言字段，拆分为 _en 和 _zh 两列
        
        Args:
            field_name: 字段名
            value: 多语言字典值
        
        Returns:
            包含 {field_name}_en 和 {field_name}_zh 的字典
        """
        result = {}
        result[f"{field_name}_en"] = value.get('en')
        result[f"{field_name}_zh"] = value.get('zh')
        return result
    
    def _infer_type(self, value: Any) -> str:
        """
        推断字段的 PostgreSQL 类型
        
        Args:
            value: 字段值
        
        Returns:
            类型名称
        """
        if isinstance(value, bool):
            return 'Boolean'
        elif isinstance(value, int):
            # 根据大小选择 Integer 或 BigInteger
            if -2147483648 <= value <= 2147483647:
                return 'Integer'
            else:
                return 'BigInteger'
        elif isinstance(value, float):
            return 'Float'
        elif isinstance(value, str):
            return 'Text'
        elif isinstance(value, list):
            return 'JSON'  # 使用 JSON 类型存储数组
        elif isinstance(value, dict):
            if self._is_multilang_dict(value):
                return 'Multilang'  # 特殊标记，会被拆分为两个 Text 列
            else:
                return 'JSON'  # 嵌套对象使用 JSON 类型
        else:
            return 'Text'  # 默认使用 Text
    
    def parse_file(self, file_path: str) -> Iterator[Dict[str, Any]]:
        """
        流式解析 JSONL 文件
        
        Args:
            file_path: JSONL 文件路径
        
        Yields:
            解析后的数据字典
        """
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return
        
        logger.info(f"开始解析文件: {file_path}")
        
        line_count = 0
        error_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        
                        # 处理多语言字段
                        processed_data = {}
                        for key, value in data.items():
                            if key == '_key':
                                # 保留主键
                                processed_data[key] = value
                            elif self._is_multilang_dict(value):
                                # 多语言字段，拆分为两个列
                                multilang_data = self._extract_multilang_field(key, value)
                                processed_data.update(multilang_data)
                            else:
                                # 普通字段，直接保留
                                processed_data[key] = value
                        
                        yield processed_data
                        line_count += 1
                        
                        # 每处理 10000 行显示一次进度
                        if line_count % 10000 == 0:
                            logger.debug(f"已解析 {line_count} 行")
                    
                    except json.JSONDecodeError as e:
                        error_count += 1
                        logger.warning(f"第 {line_num} 行 JSON 解析失败: {e}")
                        if error_count > 10:
                            logger.error(f"错误过多，停止解析: {file_path}")
                            break
                    except Exception as e:
                        error_count += 1
                        logger.warning(f"第 {line_num} 行处理失败: {e}")
                        if error_count > 10:
                            logger.error(f"错误过多，停止解析: {file_path}")
                            break
            
            logger.info(f"文件解析完成: {file_path}, 成功: {line_count}, 错误: {error_count}")
        
        except Exception as e:
            logger.error(f"解析文件时出错: {e}")
    
    def analyze_file_structure(self, file_path: str, sample_lines: int = 10) -> Dict[str, Any]:
        """
        分析文件结构，推断字段类型
        
        Args:
            file_path: JSONL 文件路径
            sample_lines: 采样行数
        
        Returns:
            包含字段类型信息的字典
        """
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return {}
        
        field_types = defaultdict(set)
        multilang_fields = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= sample_lines:
                        break
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        for key, value in data.items():
                            if key == '_key':
                                field_types[key].add(self._infer_type(value))
                            elif self._is_multilang_dict(value):
                                multilang_fields.add(key)
                                # 多语言字段会被拆分为两个 Text 列
                                field_types[f"{key}_en"].add('Text')
                                field_types[f"{key}_zh"].add('Text')
                            else:
                                field_types[key].add(self._infer_type(value))
                    except json.JSONDecodeError:
                        continue
            
            # 确定每个字段的最终类型（如果有多种类型，选择最通用的）
            result = {}
            for field, types in field_types.items():
                if 'Text' in types:
                    result[field] = 'Text'
                elif 'BigInteger' in types:
                    result[field] = 'BigInteger'
                elif 'Integer' in types:
                    result[field] = 'Integer'
                elif 'Float' in types:
                    result[field] = 'Float'
                elif 'Boolean' in types:
                    result[field] = 'Boolean'
                elif 'JSON' in types:
                    result[field] = 'JSON'
                else:
                    result[field] = 'Text'  # 默认
            
            logger.info(f"文件结构分析完成: {file_path}, 字段数: {len(result)}")
            if multilang_fields:
                logger.info(f"多语言字段: {multilang_fields}")
            
            return result
        
        except Exception as e:
            logger.error(f"分析文件结构时出错: {e}")
            return {}
    
    def get_files_to_parse(self, extract_dir: str) -> List[str]:
        """
        根据白名单获取需要解析的文件列表
        
        Args:
            extract_dir: 解压目录
        
        Returns:
            需要解析的文件路径列表
        """
        if not os.path.exists(extract_dir):
            logger.error(f"解压目录不存在: {extract_dir}")
            return []
        
        files_to_parse = []
        
        # 遍历目录中的所有 JSONL 文件
        for filename in os.listdir(extract_dir):
            if not filename.endswith('.jsonl'):
                continue
            
            # 获取文件名（不含扩展名）
            file_basename = os.path.splitext(filename)[0]
            
            # _sde.jsonl 始终处理
            if file_basename == '_sde':
                files_to_parse.append(os.path.join(extract_dir, filename))
                continue
            
            # 检查是否在白名单中
            # 空列表表示不解析任何文件（除了 _sde.jsonl）
            # 非空列表表示只解析白名单中的文件
            if self.whitelist and file_basename in self.whitelist:
                files_to_parse.append(os.path.join(extract_dir, filename))
            elif not self.whitelist:
                # 白名单为空，跳过所有文件（除了 _sde.jsonl，已在上面处理）
                logger.debug(f"白名单为空，跳过文件: {filename}")
            else:
                logger.debug(f"文件不在白名单中，跳过: {filename}")
        
        logger.info(f"找到 {len(files_to_parse)} 个文件需要解析")
        return files_to_parse

