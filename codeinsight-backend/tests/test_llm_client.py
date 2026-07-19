"""
LLM 客户端单元测试

使用 unittest.mock 模拟 litellm 调用，避免实际 API 请求。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from codeinsight.llm import CostTracker, LLMClient, LLMConfig, LLMError
from codeinsight.llm.cost import get_cost_tracker

# ────────── Fixtures ──────────


@pytest.fixture
def llm_client():
    """创建 LLMClient 实例，使用 mock 配置"""
    config = LLMConfig(
        provider="claude",
        model="claude-3.5-sonnet-20241022",
        api_key="test-key",
        temperature=0.1,
        max_tokens=4096,
    )
    return LLMClient(config)


@pytest.fixture
def mock_acompletion():
    """模拟 litellm.acompletion 返回"""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"result": "test"}'
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    return mock_response


# ────────── LLMClient 基础 ──────────


class TestLLMClientInit:
    """初始化测试"""

    def test_init_with_config(self, llm_client):
        """使用指定配置初始化"""
        assert llm_client.config.provider == "claude"
        assert llm_client.config.model == "claude-3.5-sonnet-20241022"
        assert llm_client._model_name == "claude-3.5-sonnet-20241022"

    def test_init_without_config(self):
        """无配置时使用默认值"""
        client = LLMClient()
        assert client.config is not None
        assert client.config.provider in ("claude", "gpt", "ollama", "openai")
        assert client._model_name is not None

    def test_claude_model_resolution(self, llm_client):
        """Claude 模型名解析"""
        assert llm_client._model_name == "claude-3.5-sonnet-20241022"

    def test_gpt_model_resolution(self):
        """GPT 模型名解析"""
        config = LLMConfig(provider="gpt", model="gpt-4o", api_key="test-key")
        client = LLMClient(config)
        assert client._model_name == "gpt-4o"

    def test_ollama_model_resolution(self):
        """Ollama 模型名解析"""
        config = LLMConfig(provider="ollama", model="llama3.1:8b")
        client = LLMClient(config)
        assert client._model_name == "ollama/llama3.1:8b"

    def test_openai_model_resolution(self):
        """OpenAI 模型名解析（openai 应映射到 gpt 品类）"""
        config = LLMConfig(provider="openai", model="gpt-4o-mini", api_key="test-key")
        client = LLMClient(config)
        assert client._model_name == "gpt-4o-mini"

    def test_unsupported_provider(self):
        """不支持的提供商抛出异常"""
        config = LLMConfig(provider="claude", model="")
        config.provider = "unsupported"  # type: ignore[assignment]
        with pytest.raises(LLMError, match="Unsupported LLM provider"):
            LLMClient(config)

    def test_semaphore_default_concurrency(self):
        """Semaphore 默认并发数为 3"""
        client = LLMClient()
        assert client._semaphore._value == 3  # noqa: SLF001

    def test_semaphore_custom_concurrency(self):
        """Semaphore 支持自定义并发数"""
        config = LLMConfig(provider="claude", model="claude-3.5-sonnet-20241022", max_concurrency=5)
        client = LLMClient(config)
        assert client._semaphore._value == 5  # noqa: SLF001

    def test_semaphore_limits_concurrent_calls(self):
        """Semaphore 限制并发调用数"""
        config = LLMConfig(provider="claude", model="claude-3.5-sonnet-20241022", max_concurrency=2)
        client = LLMClient(config)

        # 模拟 litellm.acompletion 为延迟任务
        async def slow_acompletion(**kwargs):
            await asyncio.sleep(0.5)
            mock = MagicMock()
            mock.choices = [MagicMock()]
            mock.choices[0].message.content = "test"
            mock.usage.prompt_tokens = 10
            mock.usage.completion_tokens = 10
            return mock

        with patch("litellm.acompletion", slow_acompletion):

            async def run():
                tasks = [client.chat([{"role": "user", "content": "hi"}]) for _ in range(4)]
                start = time.monotonic()
                await asyncio.gather(*tasks)
                elapsed = time.monotonic() - start
                return elapsed

            # 4 个任务，并发数 2 → 至少需要 2 批（0.5 + 0.5 ≈ 1.0s）
            elapsed = asyncio.run(run())
            assert elapsed >= 1.0  # 2 批执行，每批 0.5s


class TestLLMClientConfig:
    """配置相关测试"""

    def test_get_api_kwargs(self, llm_client):
        """API 参数构建"""
        kwargs = llm_client._get_api_kwargs()
        assert kwargs["model"] == "claude-3.5-sonnet-20241022"
        assert kwargs["temperature"] == 0.1
        assert kwargs["max_tokens"] == 4096
        assert kwargs["api_key"] == "test-key"
        assert kwargs["num_retries"] == 3

    def test_get_api_kwargs_ollama(self):
        """Ollama API 参数"""
        config = LLMConfig(provider="ollama", model="llama3.1:8b", ollama_base_url="http://localhost:11434")
        client = LLMClient(config)
        kwargs = client._get_api_kwargs()
        assert kwargs["api_base"] == "http://localhost:11434"

    def test_get_model_key(self, llm_client):
        """模型 key 解析"""
        assert llm_client._get_model_key() == "claude-3.5-sonnet-20241022"

    def test_get_model_key_ollama(self):
        """Ollama 模型 key 去掉前缀"""
        config = LLMConfig(provider="ollama", model="llama3.1:8b")
        client = LLMClient(config)
        assert client._get_model_key() == "llama3.1:8b"


# ────────── LLMClient 核心功能 ──────────


@pytest.mark.asyncio
class TestLLMClientChat:
    """对话测试"""

    @patch("codeinsight.llm.client.litellm.acompletion")
    async def test_chat_basic(self, mock_acompletion, llm_client, mock_acompletion_result):
        """基本对话"""
        mock_acompletion.return_value = mock_acompletion_result
        result = await llm_client.chat([{"role": "user", "content": "hello"}])
        assert isinstance(result, dict)
        assert result["content"] == '{"result": "test"}'
        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["model"] == "claude-3.5-sonnet-20241022"

    @patch("codeinsight.llm.client.litellm.acompletion")
    async def test_chat_with_structured_response(self, mock_acompletion, llm_client, mock_acompletion_result):
        """带结构化解析的对话"""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            result: str

        mock_acompletion.return_value = mock_acompletion_result
        result = await llm_client.chat(
            [{"role": "user", "content": "hello"}],
            response_model=TestModel,
        )
        assert isinstance(result, TestModel)
        assert result.result == "test"

    @patch("codeinsight.llm.client.litellm.acompletion")
    async def test_chat_error(self, mock_acompletion, llm_client):
        """对话错误处理"""
        mock_acompletion.side_effect = Exception("API error")
        with pytest.raises(LLMError, match="LLM chat failed"):
            await llm_client.chat([{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
class TestLLMClientStream:
    """流式对话测试"""

    @patch("codeinsight.llm.client.litellm.acompletion")
    async def test_chat_stream(self, mock_acompletion, llm_client):
        """流式对话"""
        chunk1 = MagicMock()
        chunk1.choices[0].delta.content = "Hello"
        chunk2 = MagicMock()
        chunk2.choices[0].delta.content = " World"
        mock_acompletion.return_value.__aiter__.return_value = [chunk1, chunk2]

        chunks = []
        async for chunk in llm_client.chat_stream([{"role": "user", "content": "hello"}]):
            chunks.append(chunk)

        assert chunks == ["Hello", " World"]

    @patch("codeinsight.llm.client.litellm.acompletion")
    async def test_chat_stream_error(self, mock_acompletion, llm_client):
        """流式对话错误处理"""
        mock_acompletion.side_effect = Exception("Stream error")
        with pytest.raises(LLMError, match="LLM chat stream failed"):
            async for _ in llm_client.chat_stream([{"role": "user", "content": "hello"}]):
                pass


@pytest.mark.asyncio
class TestLLMClientFallback:
    """Provider 降级测试"""

    @patch("codeinsight.llm.client.litellm.acompletion")
    async def test_fallback_success(self, mock_acompletion, llm_client, mock_acompletion_result):
        """主 provider 失败后降级成功"""
        mock_acompletion.side_effect = [
            Exception("Claude error"),
            mock_acompletion_result,
        ]

        result = await llm_client.chat_with_fallback(
            [{"role": "user", "content": "hello"}],
            fallback_providers=["gpt"],
        )
        assert result["content"] == '{"result": "test"}'
        assert result["provider"] == "gpt"

    @patch("codeinsight.llm.client.litellm.acompletion")
    async def test_fallback_all_fail(self, mock_acompletion, llm_client):
        """所有 provider 均失败"""
        mock_acompletion.side_effect = Exception("All fail")
        with pytest.raises(LLMError, match="所有 Provider 均失败"):
            await llm_client.chat_with_fallback(
                [{"role": "user", "content": "hello"}],
                fallback_providers=["gpt"],
            )


@pytest.mark.asyncio
class TestLLMClientTaskRouting:
    """任务路由测试"""

    @patch("codeinsight.llm.client.litellm.acompletion")
    async def test_chat_for_task_default(self, mock_acompletion, llm_client, mock_acompletion_result):
        """默认任务路由"""
        mock_acompletion.return_value = mock_acompletion_result
        result = await llm_client.chat_for_task(
            [{"role": "user", "content": "hello"}],
            task_type="default",
        )
        assert result["content"] == '{"result": "test"}'


@pytest.mark.asyncio
class TestLLMClientEmbed:
    """嵌入测试"""

    @patch("codeinsight.llm.client.litellm.aembedding")
    async def test_embed(self, mock_aembedding, llm_client):
        """批量嵌入"""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
        mock_aembedding.return_value = mock_response

        result = await llm_client.embed(["hello"])
        assert result == [[0.1, 0.2, 0.3]]

    @patch("codeinsight.llm.client.litellm.aembedding")
    async def test_embed_error(self, mock_aembedding, llm_client):
        """嵌入错误处理"""
        mock_aembedding.side_effect = Exception("Embed error")
        with pytest.raises(LLMError, match="LLM embed failed"):
            await llm_client.embed(["hello"])


class TestLLMClientTokens:
    """Token 计数测试"""

    def test_count_tokens(self, llm_client):
        """Token 计数"""
        # 使用 _estimate_tokens 直接测试
        count = llm_client._estimate_tokens("hello world")
        assert count > 0

    def test_count_tokens_empty(self, llm_client):
        """空文本 Token 计数"""
        count = llm_client._estimate_tokens("")
        assert count == 0


# ────────── CostTracker ──────────


class TestCostTracker:
    """成本追踪器测试"""

    def test_record_and_daily_cost(self):
        """记录和日成本查询"""
        tracker = CostTracker()
        assert tracker.get_daily_cost() == 0.0

        tracker.record("claude-3.5-sonnet", "claude", 1000, 500, 0.01)
        assert tracker.get_daily_cost() == 0.01

    def test_cost_by_model(self):
        """按模型分组成本"""
        tracker = CostTracker()
        tracker.record("model-a", "claude", 1000, 500, 0.01)
        tracker.record("model-b", "gpt", 2000, 1000, 0.02)

        costs = tracker.get_cost_by_model()
        assert costs["model-a"] == 0.01
        assert costs["model-b"] == 0.02

    def test_cost_by_task(self):
        """按任务类型分组成本"""
        tracker = CostTracker()
        tracker.record("model-a", "claude", 1000, 500, 0.01, task_type="design_pattern")
        tracker.record("model-a", "claude", 2000, 1000, 0.02, task_type="architecture")

        costs = tracker.get_cost_by_task()
        assert costs["design_pattern"] == 0.01
        assert costs["architecture"] == 0.02

    def test_total_stats(self):
        """总统计"""
        tracker = CostTracker()
        tracker.record("model-a", "claude", 1000, 500, 0.01)
        tracker.record("model-a", "claude", 2000, 1000, 0.02)

        stats = tracker.get_total_stats()
        assert stats["total_records"] == 2
        assert stats["total_cost_usd"] == 0.03
        assert stats["total_prompt_tokens"] == 3000
        assert stats["total_completion_tokens"] == 1500

    def test_max_records(self):
        """最大记录数限制"""
        tracker = CostTracker(max_records=3)
        for _i in range(5):
            tracker.record("model", "provider", 100, 50, 0.01)
        assert len(tracker._records) == 3

    def test_clear(self):
        """清空记录"""
        tracker = CostTracker()
        tracker.record("model", "provider", 100, 50, 0.01)
        tracker.clear()
        assert tracker.get_daily_cost() == 0.0

    def test_global_singleton(self):
        """全局单例"""
        tracker1 = get_cost_tracker()
        tracker2 = get_cost_tracker()
        assert tracker1 is tracker2


# ────────── EmbeddingClient ──────────


@pytest.mark.asyncio
class TestEmbeddingClient:
    """嵌入客户端测试"""

    @patch("codeinsight.llm.client.litellm.aembedding")
    async def test_embed(self, mock_aembedding):
        """委托给 LLMClient 的嵌入"""
        from codeinsight.embedding.client import EmbeddingClient

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
        mock_aembedding.return_value = mock_response

        client = EmbeddingClient()
        result = await client.embed(["hello"])
        assert result == [[0.1, 0.2, 0.3]]

    @patch("codeinsight.llm.client.litellm.aembedding")
    async def test_embed_single(self, mock_aembedding):
        """单条嵌入"""
        from codeinsight.embedding.client import EmbeddingClient

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
        mock_aembedding.return_value = mock_response

        client = EmbeddingClient()
        result = await client.embed_single("hello")
        assert result == [0.1, 0.2, 0.3]

    @patch("codeinsight.llm.client.litellm.aembedding")
    async def test_embed_single_empty(self, mock_aembedding):
        """空嵌入抛出异常"""
        from codeinsight.embedding.client import EmbeddingClient

        mock_response = MagicMock()
        mock_response.data = []
        mock_aembedding.return_value = mock_response

        client = EmbeddingClient()
        with pytest.raises(LLMError, match="Empty embedding"):
            await client.embed_single("hello")


# ────────── 辅助：conftest 级别 fixture ──────────


@pytest.fixture
def mock_acompletion_result():
    """模拟 litellm.acompletion 成功返回"""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"result": "test"}'
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    return mock_response
