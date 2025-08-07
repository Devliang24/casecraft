#!/usr/bin/env python3
"""
CaseCraft 调试脚本

独立的Python调试脚本，用于调试CaseCraft的核心功能，无需使用CLI。
可以在VSCode中直接F5调试，方便定位问题。

使用方法：
1. 直接运行: python debug_casecraft.py
2. VSCode调试: 设置断点后按F5
3. 单独测试某个功能: 修改main()函数中的调用
"""

import asyncio
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Dict, Any, Optional

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from casecraft.core.parsing.api_parser import APIParser
from casecraft.core.generation.llm_client import LLMClient
from casecraft.core.generation.test_generator import TestCaseGenerator
from casecraft.core.management.config_manager import ConfigManager
from casecraft.models.config import CaseCraftConfig, LLMConfig
from casecraft.utils.logging import configure_logging, get_logger


class DebugHelper:
    """调试辅助类"""
    
    def __init__(self):
        self.logger = get_logger("debug")
        # 配置日志为调试模式
        configure_logging(log_level="DEBUG", console_output=True)
    
    def print_separator(self, title: str) -> None:
        """打印分割线"""
        print(f"\n{'='*60}")
        print(f" {title}")
        print(f"{'='*60}")
    
    def print_json(self, data: Any, title: str = "JSON Data") -> None:
        """格式化打印JSON数据"""
        print(f"\n--- {title} ---")
        try:
            if isinstance(data, str):
                data = json.loads(data)
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"JSON格式化失败: {e}")
            print(data)
        print()
    
    def handle_exception(self, func_name: str, e: Exception) -> None:
        """处理异常"""
        print(f"\n❌ {func_name} 失败:")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print("\n完整堆栈跟踪:")
        traceback.print_exc()
        print()


async def test_config_loading(debug: DebugHelper) -> Optional[CaseCraftConfig]:
    """测试配置加载功能"""
    debug.print_separator("测试配置加载")
    
    try:
        # 设置测试环境变量
        import os
        os.environ["CASECRAFT_LLM_API_KEY"] = "db474e8a869844bbbdcf1a111a5eafa4.0SY1uazDVWJQZPHA"
        os.environ["CASECRAFT_LLM_MODEL"] = "glm-4.5-x"
        os.environ["CASECRAFT_LLM_BASE_URL"] = "https://open.bigmodel.cn/api/paas/v4"
        os.environ["CASECRAFT_LLM_TIMEOUT"] = "60"
        os.environ["CASECRAFT_LLM_MAX_RETRIES"] = "3"
        os.environ["CASECRAFT_PROCESSING_WORKERS"] = "1"
        
        print("✅ 设置测试环境变量")
        
        config_manager = ConfigManager()
        
        # 从环境变量加载配置
        config = config_manager.create_default_config()
        
        print("✅ 配置对象创建成功:")
        print(f"Model: {config.llm.model}")
        print(f"API Key: {config.llm.api_key[:10]}...****")
        print(f"Base URL: {config.llm.base_url}")
        print(f"Timeout: {config.llm.timeout}s")
        print(f"Workers: {config.processing.workers}")
        
        return config
        
    except Exception as e:
        debug.handle_exception("test_config_loading", e)
        return None


async def test_api_parsing(debug: DebugHelper) -> Optional[Dict]:
    """测试API解析功能"""
    debug.print_separator("测试API解析")
    
    try:
        # 检查测试文件是否存在
        test_file = Path("ecommerce_api_openapi.json")
        if not test_file.exists():
            print(f"❌ 测试文件不存在: {test_file}")
            return None
        
        print(f"✅ 找到测试文件: {test_file}")
        
        # 创建API解析器
        parser = APIParser()
        
        # 解析API文档
        print("🔄 解析API文档...")
        api_spec = await parser.parse_from_source(str(test_file))
        
        print("✅ API解析成功:")
        print(f"API标题: {api_spec.title}")
        print(f"API版本: {api_spec.version}")
        print(f"API描述: {api_spec.description or 'N/A'}")
        print(f"端点数量: {len(api_spec.endpoints)}")
        
        # 显示前几个端点
        print("\n前5个端点:")
        for i, endpoint in enumerate(api_spec.endpoints[:5]):
            print(f"{i+1}. {endpoint.method} {endpoint.path} - {endpoint.summary}")
            
        # 选择一个端点进行详细分析
        if api_spec.endpoints:
            endpoint = api_spec.endpoints[0]
            print(f"\n详细分析端点: {endpoint.method} {endpoint.path}")
            print(f"描述: {endpoint.description}")
            print(f"标签: {endpoint.tags}")
            if endpoint.parameters:
                print(f"参数数量: {len(endpoint.parameters)}")
            if endpoint.request_body:
                print("请求体: 存在")
            if endpoint.responses:
                print(f"响应定义: {list(endpoint.responses.keys())}")
        
        return {
            "api_spec": api_spec,
            "sample_endpoint": api_spec.endpoints[0] if api_spec.endpoints else None
        }
        
    except Exception as e:
        debug.handle_exception("test_api_parsing", e)
        return None


async def test_llm_client(debug: DebugHelper, config: CaseCraftConfig) -> Optional[LLMClient]:
    """测试LLM客户端功能"""
    debug.print_separator("测试LLM客户端")
    
    try:
        # 创建LLM客户端
        llm_client = LLMClient(config.llm)
        
        print("✅ LLM客户端创建成功:")
        print(f"Base URL: {llm_client.base_url}")
        print(f"Model: {config.llm.model}")
        print(f"Timeout: {config.llm.timeout}s")
        
        # 测试简单的LLM调用
        print("\n🔄 测试LLM调用...")
        test_prompt = "请用JSON格式返回一个简单的测试响应，包含status和message字段"
        system_prompt = "你是一个API测试助手，按要求返回JSON格式的响应"
        
        print(f"发送提示: {test_prompt}")
        
        response = await llm_client.generate(
            prompt=test_prompt,
            system_prompt=system_prompt
        )
        
        print("✅ LLM响应成功:")
        print(f"模型: {response.model}")
        print(f"完成原因: {response.finish_reason}")
        if response.usage:
            print(f"Token使用: {response.usage}")
        
        print("\n响应内容:")
        print(response.content)
        
        # 尝试解析响应为JSON
        try:
            parsed_response = json.loads(response.content)
            debug.print_json(parsed_response, "解析后的JSON响应")
        except:
            print("⚠️ 响应不是有效的JSON格式")
        
        return llm_client
        
    except Exception as e:
        debug.handle_exception("test_llm_client", e)
        return None


async def test_case_generation(debug: DebugHelper, api_data: Dict, llm_client: LLMClient) -> Optional[Dict]:
    """测试测试用例生成功能"""
    debug.print_separator("测试用例生成")
    
    try:
        if not api_data or not api_data.get("sample_endpoint"):
            print("❌ 需要有效的API端点数据")
            return None
        
        endpoint = api_data["sample_endpoint"]
        print(f"✅ 使用端点进行测试: {endpoint.method} {endpoint.path}")
        
        # 创建测试用例生成器
        generator = TestCaseGenerator(llm_client, api_version="1.0")
        
        print("\n🔄 生成测试用例...")
        print("这可能需要几秒钟时间...")
        
        # 生成测试用例
        result = await generator.generate_test_cases(endpoint)
        
        print("✅ 测试用例生成成功:")
        print(f"生成的测试用例数量: {len(result.test_cases.test_cases)}")
        
        if result.token_usage:
            print(f"Token使用情况:")
            print(f"  提示Token: {result.token_usage.prompt_tokens}")
            print(f"  完成Token: {result.token_usage.completion_tokens}")
            print(f"  总Token: {result.token_usage.total_tokens}")
        
        # 显示生成的测试用例
        print(f"\n生成的测试用例列表:")
        for i, test_case in enumerate(result.test_cases.test_cases):
            # 安全获取test_type值
            test_type = test_case.test_type.value if hasattr(test_case.test_type, 'value') else str(test_case.test_type)
            print(f"{i+1}. {test_case.name} ({test_type})")
            print(f"   期望状态: {test_case.expected_status}")
            print(f"   描述: {test_case.description[:100]}...")
            if test_case.tags:
                print(f"   标签: {', '.join(test_case.tags[:5])}")
            print()
        
        # 详细显示第一个测试用例
        if result.test_cases.test_cases:
            first_case = result.test_cases.test_cases[0]
            debug.print_json(first_case.model_dump(), "第一个测试用例详情")
        
        return {
            "test_collection": result.test_cases,
            "token_usage": result.token_usage
        }
        
    except Exception as e:
        debug.handle_exception("test_case_generation", e)
        return None


async def debug_full_generation(debug: DebugHelper) -> None:
    """端到端调试完整生成流程"""
    debug.print_separator("端到端完整流程调试")
    
    try:
        # 1. 加载配置
        print("步骤 1: 加载配置...")
        config = await test_config_loading(debug)
        if not config:
            print("❌ 配置加载失败，停止执行")
            return
        
        # 2. 解析API
        print("\n步骤 2: 解析API文档...")
        api_data = await test_api_parsing(debug)
        if not api_data:
            print("❌ API解析失败，停止执行")
            return
        
        # 3. 测试LLM客户端
        print("\n步骤 3: 测试LLM客户端...")
        llm_client = await test_llm_client(debug, config)
        if not llm_client:
            print("❌ LLM客户端测试失败，停止执行")
            return
        
        # 4. 生成测试用例
        print("\n步骤 4: 生成测试用例...")
        generation_result = await test_case_generation(debug, api_data, llm_client)
        if not generation_result:
            print("❌ 测试用例生成失败，停止执行")
            return
        
        # 5. 保存结果到文件
        print("\n步骤 5: 保存调试结果...")
        debug_output = {
            "api_info": {
                "title": api_data["api_spec"].title,
                "version": api_data["api_spec"].version,
                "endpoints_count": len(api_data["api_spec"].endpoints)
            },
            "generation_summary": {
                "test_cases_count": len(generation_result["test_collection"].test_cases),
                "token_usage": generation_result["token_usage"].dict() if generation_result["token_usage"] else None
            },
            "sample_test_case": generation_result["test_collection"].test_cases[0].dict() if generation_result["test_collection"].test_cases else None
        }
        
        # 保存调试结果
        output_file = "debug_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(debug_output, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 调试结果已保存到: {output_file}")
        print(f"✅ 完整流程调试成功！")
        
        # 关闭HTTP客户端
        await llm_client.client.aclose()
        
    except Exception as e:
        debug.handle_exception("debug_full_generation", e)


async def debug_specific_endpoint(debug: DebugHelper, endpoint_path: str = "/api/v1/auth/register") -> None:
    """调试特定的端点"""
    debug.print_separator(f"调试特定端点: {endpoint_path}")
    
    try:
        # 加载配置和API
        config = await test_config_loading(debug)
        api_data = await test_api_parsing(debug)
        
        if not config or not api_data:
            print("❌ 前置条件失败")
            return
        
        # 查找特定端点
        target_endpoint = None
        for endpoint in api_data["api_spec"].endpoints:
            if endpoint.path == endpoint_path:
                target_endpoint = endpoint
                break
        
        if not target_endpoint:
            print(f"❌ 未找到端点: {endpoint_path}")
            available_paths = [ep.path for ep in api_data["api_spec"].endpoints]
            print(f"可用端点: {available_paths[:10]}")
            return
        
        print(f"✅ 找到目标端点: {target_endpoint.method} {target_endpoint.path}")
        
        # 创建LLM客户端和生成器
        llm_client = LLMClient(config.llm)
        generator = TestCaseGenerator(llm_client, api_version="1.0")
        
        # 生成测试用例
        print(f"\n🔄 为端点生成测试用例...")
        result = await generator.generate_test_cases(target_endpoint)
        
        print(f"✅ 生成完成，共{len(result.test_cases.test_cases)}个测试用例")
        
        # 详细输出每个测试用例
        for i, test_case in enumerate(result.test_cases.test_cases):
            print(f"\n--- 测试用例 {i+1} ---")
            print(f"名称: {test_case.name}")
            # 安全获取test_type值
            test_type = test_case.test_type.value if hasattr(test_case.test_type, 'value') else str(test_case.test_type)
            print(f"类型: {test_type}")
            print(f"状态码: {test_case.expected_status}")
            print(f"描述: {test_case.description}")
            if test_case.body:
                print(f"请求体: {json.dumps(test_case.body, indent=2, ensure_ascii=False)}")
            if test_case.tags:
                print(f"标签: {', '.join(test_case.tags)}")
        
        await llm_client.client.aclose()
        
    except Exception as e:
        debug.handle_exception("debug_specific_endpoint", e)


def main():
    """主函数 - 在这里选择要运行的调试功能"""
    debug = DebugHelper()
    
    print("🚀 CaseCraft 调试工具启动")
    print("=" * 60)
    
    # 在这里选择要运行的调试功能
    # 取消注释相应的函数调用即可
    
    try:
        # 选择以下任意一个或多个函数进行调试:
        
        # 1. 测试单个组件
        # asyncio.run(test_config_loading(debug))
        # asyncio.run(test_api_parsing(debug))
        # config = asyncio.run(test_config_loading(debug))
        # if config:
        #     asyncio.run(test_llm_client(debug, config))
        
        # 2. 端到端完整流程测试 (推荐)
        # asyncio.run(debug_full_generation(debug))
        
        # 3. 调试特定端点
        asyncio.run(debug_specific_endpoint(debug, "/api/v1/auth/register"))
        # asyncio.run(debug_specific_endpoint(debug, "/api/v1/products/"))
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断了程序")
    except Exception as e:
        debug.handle_exception("main", e)
    
    print("\n🎯 调试完成!")


if __name__ == "__main__":
    main()