"""
智能推断规则常量
无需配置文件，直接在代码中定义所有推断规则
"""

# 业务关键性关键词（通用模式，非硬编码路径）
CRITICAL_KEYWORDS = {
    4: ['pay', 'charge', 'refund', 'transaction', 'wallet', 'balance', 'money', 'invoice', 'bill', 'transfer', 'withdraw', 'deposit'],  # 金融类
    3: ['auth', 'login', 'logout', 'register', 'token', 'password', 'credential', 'verify', 'signup', 'signin', 'refresh'],         # 认证类
    2: ['user', 'profile', 'account', 'customer', 'member', 'personal', 'setting', 'preference', 'privacy'],                        # 用户类
    1: ['admin', 'batch', 'bulk', 'import', 'export', 'config', 'manage', 'audit', 'log', 'report', 'analytic', 'permission']     # 管理类
}

# HTTP方法测试数量基准（DELETE第二多是重要要求）
METHOD_BASE_COUNTS = {
    'POST': 16,      # 最多测试用例（创建操作风险最高）
    'DELETE': 15,    # 第二多（删除操作需要特别关注）
    'PUT': 14,       # 完整更新
    'PATCH': 14,     # 部分更新
    'GET': 13,       # 查询操作
    'HEAD': 8,       # 头部查询
    'OPTIONS': 5     # 选项查询
}

# 复杂度评分权重
COMPLEXITY_WEIGHTS = {
    'path_params': 2,      # 路径参数权重
    'query_params': 1,     # 查询参数权重
    'request_body': 6,     # 请求体基础权重
    'nested_depth': 3,     # 嵌套深度权重
    'array_fields': 2,     # 数组字段权重
    'required_fields': 1   # 必填字段权重
}

# 测试类型比例分配
TEST_TYPE_RATIOS = {
    'simple': {'positive': 0.40, 'negative': 0.45, 'boundary': 0.15},      # 简单端点：正向40%，负向45%，边界15%
    'medium': {'positive': 0.35, 'negative': 0.45, 'boundary': 0.20},      # 中等复杂：正向35%，负向45%，边界20%
    'complex': {'positive': 0.35, 'negative': 0.40, 'boundary': 0.25}      # 复杂端点：正向35%，负向40%，边界25%
}

# 常见资源名词（用于过滤，避免干扰）
COMMON_PREFIXES = ['api', 'rest', 'v1', 'v2', 'v3', 'admin', 'public', 'private', 'internal', 'external']

# 资源名词中英文映射（常见的API资源翻译）
RESOURCE_TRANSLATIONS = {
    # 用户相关
    'user': '用户',
    'account': '账户',
    'profile': '用户信息',
    'customer': '客户',
    'member': '会员',
    
    # 商品相关
    'product': '商品',
    'item': '商品',
    'category': '分类',
    'catalog': '目录',
    'inventory': '库存',
    
    # 订单相关
    'order': '订单',
    'cart': '购物车',
    'checkout': '结账',
    'payment': '支付',
    'transaction': '交易',
    
    # 认证相关
    'auth': '认证',
    'login': '登录',
    'token': '令牌',
    'permission': '权限',
    'role': '角色',
    
    # 系统相关
    'config': '配置',
    'setting': '设置',
    'log': '日志',
    'report': '报告',
    'health': '健康检查',
    'status': '状态'
}

# 操作动词映射
OPERATION_VERBS = {
    'GET': {
        'collection': '获取',      # 获取列表
        'single': '获取',          # 获取详情
        'search': '搜索'           # 搜索
    },
    'POST': {
        'collection': '创建',      # 创建资源
        'action': '执行'           # 执行操作
    },
    'PUT': {
        'single': '更新',          # 完整更新
        'collection': '批量更新'   # 批量更新
    },
    'PATCH': {
        'single': '修改',          # 部分修改
        'collection': '批量修改'   # 批量修改
    },
    'DELETE': {
        'single': '删除',          # 删除单个
        'collection': '清空'       # 清空集合
    }
}

# 复杂度等级阈值
COMPLEXITY_THRESHOLDS = {
    'simple': 5,       # 简单：复杂度 <= 5
    'medium': 10,      # 中等：5 < 复杂度 <= 10
    'complex': float('inf')  # 复杂：复杂度 > 10
}

# 最小测试数量约束
MIN_TEST_COUNTS = {
    'positive': 2,     # 最少2个正向测试
    'negative': 3,     # 最少3个负向测试
    'boundary': 1      # 最少1个边界测试
}

# 最大测试数量约束（避免过度生成）
MAX_TEST_COUNTS = {
    'total': 30,       # 单个端点最多30个测试
    'positive': 12,    # 最多12个正向测试
    'negative': 15,    # 最多15个负向测试
    'boundary': 8      # 最多8个边界测试
}