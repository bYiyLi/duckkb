"""测试 OpenAI 兼容 API 的模型可用性。"""

import asyncio
from openai import AsyncOpenAI


async def test_embedding_model(client: AsyncOpenAI) -> None:
    """测试 Qwen3-Embedding-8B 模型。"""
    print("=" * 60)
    print("测试 Embedding 模型: Qwen/Qwen3-Embedding-8B")
    print("=" * 60)

    try:
        response = await client.embeddings.create(
            model="Qwen/Qwen3-Embedding-8B",
            input="这是一个测试文本，用于验证 embedding 模型是否正常工作。",
        )
        print(f"✅ Embedding 创建成功!")
        print(f"   向量维度: {len(response.data[0].embedding)}")
        print(f"   向量前 5 个值: {response.data[0].embedding[:5]}")
        print(f"   模型: {response.model}")
        print(f"   总 tokens: {response.usage.total_tokens}")
    except Exception as e:
        print(f"❌ Embedding 测试失败: {e}")


async def test_chat_model(client: AsyncOpenAI) -> None:
    """测试 Qwen3.5-397B-A17B 模型。"""
    print("\n" + "=" * 60)
    print("测试 Chat 模型: Qwen/Qwen3.5-397B-A17B")
    print("=" * 60)

    try:
        response = await client.chat.completions.create(
            model="Qwen/Qwen3.5-397B-A17B",
            messages=[
                {"role": "system", "content": "你是一个有帮助的助手。"},
                {"role": "user", "content": "请用一句话介绍一下你自己。"},
            ],
            max_tokens=100,
        )
        print(f"✅ Chat 补全成功!")
        print(f"   模型: {response.model}")
        print(f"   回复: {response.choices[0].message.content}")
        print(f"   总 tokens: {response.usage.total_tokens}")
        print(f"   完成原因: {response.choices[0].finish_reason}")
    except Exception as e:
        print(f"❌ Chat 测试失败: {e}")


async def test_chat_stream(client: AsyncOpenAI) -> None:
    """测试流式 Chat 补全。"""
    print("\n" + "=" * 60)
    print("测试流式 Chat: Qwen/Qwen3.5-397B-A17B")
    print("=" * 60)

    try:
        stream = await client.chat.completions.create(
            model="Qwen/Qwen3.5-397B-A17B",
            messages=[
                {"role": "user", "content": "请数从 1 到 5。"},
            ],
            max_tokens=50,
            stream=True,
        )
        print("✅ 流式响应: ", end="", flush=True)
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print("\n   流式测试成功!")
    except Exception as e:
        print(f"\n❌ 流式 Chat 测试失败: {e}")


async def main() -> None:
    """主测试函数。"""
    client = AsyncOpenAI(
        api_key="sk-t64OIoCH78Mc8UfSmIOBIrK54671NI3qHEawBDe1iARaR4Cd",
        base_url="http://192.168.81.10:3000/v1",
    )

    print("开始测试 API 网关模型...")
    print(f"Base URL: {client.base_url}")
    print()

    await test_embedding_model(client)
    await test_chat_model(client)
    await test_chat_stream(client)

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
