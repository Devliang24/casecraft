"""
业务关键性分析器
基于通用模式评估API端点的业务关键性
"""

from typing import Dict, List
from .constants import CRITICAL_KEYWORDS
from .path_analyzer import PathAnalyzer


class CriticalityAnalyzer:
    """业务关键性分析器"""
    
    def __init__(self):
        """初始化关键性分析器"""
        self.path_analyzer = PathAnalyzer()
        
    def analyze(self, endpoint) -> int:
        """
        评估端点的业务关键性
        
        Args:
            endpoint: APIEndpoint对象
            
        Returns:
            关键性评分（0-6分）
        """
        path_lower = endpoint.path.lower()
        method_upper = endpoint.method.upper()
        score = 0
        
        # 1. 基于路径关键词评分
        keyword_score = self._evaluate_keyword_criticality(path_lower)
        score += keyword_score
        
        # 2. 基于HTTP方法的风险评估
        method_score = self._evaluate_method_risk(method_upper)
        score += method_score
        
        # 3. 基于路径特征加分
        feature_score = self._evaluate_path_features(endpoint.path)
        score += feature_score
        
        # 4. 基于OpenAPI信息增强评分
        openapi_score = self._evaluate_openapi_info(endpoint)
        score += openapi_score
        
        # 限制最大分数
        return min(int(score), 10)
    
    def get_priority(self, endpoint, test_type: str) -> str:
        """Get priority level based on endpoint and test type.
        
        Args:
            endpoint: API endpoint
            test_type: Test type (positive/negative/boundary)
            
        Returns:
            Priority level (P0/P1/P2)
        """
        score = self.analyze(endpoint)
        method = endpoint.method.upper()
        
        # Priority determination logic
        if test_type == "positive":
            # DELETE operations are always P0 for positive tests
            if method == "DELETE":
                return "P0"
            # High criticality POST operations are P0
            if method == "POST" and score >= 5:
                return "P0"
            # Other positive tests are P1
            return "P1"
        
        elif test_type == "negative":
            # Critical operations or high-score endpoints get P1
            if method in ["DELETE", "POST"] or score >= 7:
                return "P1"
            # Other negative tests are P2
            return "P2"
        
        # Boundary tests are typically P2
        return "P2"
    
    def _evaluate_keyword_criticality(self, path_lower: str) -> int:
        """
        基于关键词评估关键性
        
        Args:
            path_lower: 小写的API路径
            
        Returns:
            关键词匹配得分
        """
        max_score = 0
        
        # 遍历所有关键词组
        for weight, keywords in CRITICAL_KEYWORDS.items():
            for keyword in keywords:
                # 使用词根匹配，支持变形
                if self._keyword_matches(keyword, path_lower):
                    max_score = max(max_score, weight)
                    break  # 找到匹配就跳出该权重组
        
        return max_score
    
    def _keyword_matches(self, keyword: str, path: str) -> bool:
        """
        检查关键词是否匹配路径
        
        Args:
            keyword: 关键词
            path: 路径（小写）
            
        Returns:
            是否匹配
        """
        # 精确匹配
        if keyword in path:
            return True
        
        # 复数形式匹配
        if f"{keyword}s" in path:
            return True
        
        # 进行时形式匹配
        if f"{keyword}ing" in path:
            return True
        
        # 过去式形式匹配（简单规则）
        if f"{keyword}ed" in path:
            return True
        
        # 第三人称单数形式匹配
        if keyword.endswith('y') and f"{keyword[:-1]}ies" in path:
            return True
        
        return False
    
    def _evaluate_method_risk(self, method: str) -> int:
        """
        基于HTTP方法评估风险等级
        
        Args:
            method: HTTP方法
            
        Returns:
            方法风险得分
        """
        # HTTP方法风险权重
        method_risks = {
            'DELETE': 2,    # 删除操作风险最高
            'POST': 1.5,    # 创建操作风险较高
            'PUT': 1.5,     # 完整更新风险较高
            'PATCH': 1,     # 部分更新风险中等
            'GET': 0,       # 查询操作风险最低
            'HEAD': 0,      # 头部查询风险最低
            'OPTIONS': 0    # 选项查询风险最低
        }
        
        return method_risks.get(method, 0)
    
    def _evaluate_path_features(self, path: str) -> float:
        """
        基于路径特征评估关键性
        
        Args:
            path: API路径
            
        Returns:
            特征得分
        """
        score = 0.0
        
        # 有路径参数：通常操作特定资源，风险较高
        if '{' in path or ':' in path:
            score += 0.5
        
        # 路径深度：嵌套越深，复杂度越高
        depth = len([p for p in path.split('/') if p and not p.startswith('{')])
        if depth > 3:
            score += 0.5
        
        # 特殊路径段
        path_lower = path.lower()
        if any(segment in path_lower for segment in ['admin', 'internal', 'private']):
            score += 1.0
        
        return score
    
    def _evaluate_openapi_info(self, endpoint) -> float:
        """
        基于OpenAPI信息评估关键性
        
        Args:
            endpoint: APIEndpoint对象
            
        Returns:
            OpenAPI信息得分
        """
        score = 0.0
        
        # 检查tags中的关键信息
        if hasattr(endpoint, 'tags') and endpoint.tags:
            for tag in endpoint.tags:
                tag_lower = tag.lower()
                # 重要标签加分
                if any(keyword in tag_lower for keyword in ['auth', 'payment', 'admin', 'security']):
                    score += 0.5
        
        # 检查summary和description中的关键信息
        text_content = ""
        if hasattr(endpoint, 'summary') and endpoint.summary:
            text_content += endpoint.summary.lower()
        if hasattr(endpoint, 'description') and endpoint.description:
            text_content += " " + endpoint.description.lower()
        
        if text_content:
            # 检查描述中的风险关键词
            risk_keywords = ['critical', 'important', 'sensitive', 'secure', 'private', 'confidential']
            for keyword in risk_keywords:
                if keyword in text_content:
                    score += 0.3
                    break
        
        return score
    
    def get_criticality_level(self, score: int) -> str:
        """
        根据得分获取关键性等级
        
        Args:
            score: 关键性评分
            
        Returns:
            关键性等级描述
        """
        if score >= 6:
            return "极高"
        elif score >= 4:
            return "高"
        elif score >= 2:
            return "中"
        elif score >= 1:
            return "低"
        else:
            return "极低"
    
    def analyze_detailed(self, endpoint) -> Dict:
        """
        详细分析端点关键性
        
        Args:
            endpoint: APIEndpoint对象
            
        Returns:
            详细的分析结果
        """
        path_lower = endpoint.path.lower()
        
        # 计算各个维度的得分
        keyword_score = self._evaluate_keyword_criticality(path_lower)
        method_score = self._evaluate_method_risk(endpoint.method.upper())
        feature_score = self._evaluate_path_features(endpoint.path)
        openapi_score = self._evaluate_openapi_info(endpoint)
        
        total_score = min(int(keyword_score + method_score + feature_score + openapi_score), 10)
        
        return {
            'total_score': total_score,
            'level': self.get_criticality_level(total_score),
            'breakdown': {
                'keyword_score': keyword_score,
                'method_score': method_score,
                'feature_score': feature_score,
                'openapi_score': openapi_score
            },
            'matched_keywords': self._get_matched_keywords(path_lower),
            'risk_factors': self._get_risk_factors(endpoint)
        }
    
    def _get_matched_keywords(self, path_lower: str) -> List[str]:
        """
        获取匹配的关键词列表
        
        Args:
            path_lower: 小写路径
            
        Returns:
            匹配的关键词列表
        """
        matched = []
        for weight, keywords in CRITICAL_KEYWORDS.items():
            for keyword in keywords:
                if self._keyword_matches(keyword, path_lower):
                    matched.append(f"{keyword}(权重{weight})")
        return matched
    
    def _get_risk_factors(self, endpoint) -> List[str]:
        """
        获取风险因素列表
        
        Args:
            endpoint: APIEndpoint对象
            
        Returns:
            风险因素描述列表
        """
        factors = []
        
        # HTTP方法风险
        method = endpoint.method.upper()
        if method == 'DELETE':
            factors.append("DELETE操作：数据删除风险")
        elif method in ['POST', 'PUT', 'PATCH']:
            factors.append(f"{method}操作：数据修改风险")
        
        # 路径特征风险
        if '{' in endpoint.path:
            factors.append("包含路径参数：特定资源操作")
        
        # 业务领域风险
        path_lower = endpoint.path.lower()
        if any(kw in path_lower for kw in ['pay', 'transaction', 'money']):
            factors.append("金融相关：资金安全风险")
        elif any(kw in path_lower for kw in ['auth', 'login', 'token']):
            factors.append("认证相关：安全认证风险")
        elif any(kw in path_lower for kw in ['user', 'profile', 'account']):
            factors.append("用户相关：隐私数据风险")
        
        return factors