"""
API路径分析器
使用轻量级方法分析API路径的语义信息
"""

import re
import inflect
from typing import List, Dict, Optional
from .constants import COMMON_PREFIXES


class PathAnalyzer:
    """轻量级API路径分析器"""
    
    def __init__(self):
        """初始化路径分析器"""
        self.inflect_engine = inflect.engine()
        # 路径分隔符正则表达式
        self.path_separator = re.compile(r'[/_-]')
        # 版本号正则表达式
        self.version_pattern = re.compile(r'/v\d+/')
        # 参数占位符正则表达式
        self.param_pattern = re.compile(r'\{[^}]+\}')
        
    def analyze(self, path: str, method: str) -> Dict:
        """
        分析API路径和HTTP方法，提取语义信息
        
        Args:
            path: API路径，如 "/api/v1/users/{id}"
            method: HTTP方法，如 "GET"
            
        Returns:
            分析结果字典，包含资源、特征等信息
        """
        # 清理路径：移除版本号
        path_clean = self.version_pattern.sub('/', path.lower())
        
        # 分割路径为segments
        segments = self._split_path(path_clean)
        
        # 提取资源名（转换为单数形式）
        resources = self._extract_resources(segments)
        
        # 分析路径特征
        features = {
            'resources': resources,
            'primary_resource': resources[-1] if resources else None,
            'is_collection': self._is_collection_endpoint(path, segments),
            'has_path_params': self._has_path_parameters(path),
            'resource_depth': len(resources),
            'is_nested': len(resources) > 1,
            'path_segments': segments,
            'operation_type': self._infer_operation_type(method, path, resources)
        }
        
        return features
    
    def _split_path(self, path: str) -> List[str]:
        """
        分割路径为segments
        
        Args:
            path: 清理后的路径
            
        Returns:
            路径段列表
        """
        # 使用正则分割路径
        parts = self.path_separator.split(path)
        
        # 过滤空字符串和参数占位符
        segments = []
        for part in parts:
            part = part.strip()
            if part and not part.startswith('{') and not self.param_pattern.match(part):
                segments.append(part)
        
        return segments
    
    def _extract_resources(self, segments: List[str]) -> List[str]:
        """
        从路径segments中提取资源名
        
        Args:
            segments: 路径段列表
            
        Returns:
            资源名列表（单数形式）
        """
        resources = []
        
        for segment in segments:
            # 跳过常见前缀
            if segment in COMMON_PREFIXES:
                continue
                
            # 转换复数为单数
            singular = self.inflect_engine.singular_noun(segment)
            resource_name = singular if singular else segment
            
            # 添加到资源列表
            if resource_name not in resources:
                resources.append(resource_name)
        
        return resources
    
    def _is_collection_endpoint(self, path: str, segments: List[str]) -> bool:
        """
        判断是否是集合操作端点
        
        Args:
            path: 原始路径
            segments: 路径段列表
            
        Returns:
            是否为集合操作
        """
        # 如果路径包含参数，通常是单个资源操作
        if self._has_path_parameters(path):
            return False
        
        # 检查最后一个segment是否为复数
        if segments:
            last_segment = segments[-1]
            return bool(self.inflect_engine.singular_noun(last_segment))
        
        return False
    
    def _has_path_parameters(self, path: str) -> bool:
        """
        检查路径是否包含参数
        
        Args:
            path: API路径
            
        Returns:
            是否包含路径参数
        """
        return '{' in path or ':' in path
    
    def _infer_operation_type(self, method: str, path: str, resources: List[str]) -> str:
        """
        推断操作类型
        
        Args:
            method: HTTP方法
            path: API路径
            resources: 资源列表
            
        Returns:
            操作类型描述
        """
        method_upper = method.upper()
        has_params = self._has_path_parameters(path)
        
        if method_upper == 'GET':
            return 'single' if has_params else 'collection'
        elif method_upper == 'POST':
            return 'create'
        elif method_upper in ['PUT', 'PATCH']:
            return 'update'
        elif method_upper == 'DELETE':
            return 'single' if has_params else 'collection'
        else:
            return 'other'
    
    def get_resource_hierarchy(self, path: str) -> List[Dict[str, str]]:
        """
        获取资源层级结构
        
        Args:
            path: API路径
            
        Returns:
            资源层级信息列表
        """
        # 清理路径
        path_clean = self.version_pattern.sub('/', path.lower())
        
        # 分割并分析每个部分
        parts = self.path_separator.split(path_clean)
        hierarchy = []
        
        i = 0
        while i < len(parts):
            part = parts[i].strip()
            if not part or part in COMMON_PREFIXES:
                i += 1
                continue
            
            # 检查是否为资源名
            if not part.startswith('{'):
                resource_info = {
                    'name': part,
                    'singular': self.inflect_engine.singular_noun(part) or part,
                    'is_collection': bool(self.inflect_engine.singular_noun(part)),
                    'has_id': False
                }
                
                # 检查下一个部分是否为ID参数
                if i + 1 < len(parts) and parts[i + 1].strip().startswith('{'):
                    resource_info['has_id'] = True
                    i += 1  # 跳过ID参数
                
                hierarchy.append(resource_info)
            
            i += 1
        
        return hierarchy