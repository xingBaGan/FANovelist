"""
本地 BGE-M3 嵌入模型封装，实现 graphiti-core 的 EmbedderClient 接口。

安装依赖:
    pip install FlagEmbedding torch

国内用户镜像加速:
    export HF_ENDPOINT=https://hf-mirror.com

与 graphiti 集成示例:
    from local_bge_m3 import BGEM3Embedder, BGEM3EmbedderConfig
    from graphiti_core import Graphiti

    config = BGEM3EmbedderConfig(device="cpu")
    embedder = BGEM3Embedder(config)

    graphiti = Graphiti(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
        embedder=embedder,
    )
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from graphiti_core.embedder.client import EmbedderClient, EmbedderConfig


class BGEM3EmbedderConfig(EmbedderConfig):
    """BGE-M3 本地嵌入模型配置。

    Fields:
        model_name:     HuggingFace 模型 ID，默认 BAAI/bge-m3
        device:         推理设备，cpu / cuda / mps
        batch_size:     每批处理的文本数量
        max_length:     最大 token 长度（BGE-M3 支持最长 8192）
        embedding_dim:  输出向量维度，BGE-M3 dense 维度固定为 1024
    """

    model_name: str = "BAAI/bge-m3"
    device: str = "cpu"
    batch_size: int = 32
    max_length: int = 8192
    embedding_dim: int = 1024


class BGEM3Embedder(EmbedderClient):
    """graphiti-core EmbedderClient 的本地 BGE-M3 实现。

    使用懒加载策略：首次调用 create / create_batch 时才载入模型，
    避免在不需要嵌入的场景中浪费内存。
    """

    def __init__(self, config: "BGEM3EmbedderConfig | None" = None) -> None:
        self.config: BGEM3EmbedderConfig = config or BGEM3EmbedderConfig()
        self._model: Any = None  # FlagEmbedding.BGEM3FlagModel，懒加载
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bge_m3")

    # ------------------------------------------------------------------
    # 私有工具方法
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """懒加载 BGE-M3 模型（线程安全：只需在 executor 内部调用）。"""
        if self._model is not None:
            return

        try:
            from FlagEmbedding import BGEM3FlagModel  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "FlagEmbedding 未安装。请运行: pip install FlagEmbedding torch"
            ) from exc

        # use_fp16=True 在 CPU 上同样有效，可略微降低内存占用
        self._model = BGEM3FlagModel(
            self.config.model_name,
            use_fp16=True,
            device=self.config.device,
        )

    def _embed_sync(self, texts: list) -> list:
        """同步嵌入，在专用线程池中执行以避免阻塞事件循环。

        Args:
            texts: 待嵌入的文本列表

        Returns:
            每条文本对应的 1024 维 dense 向量列表
        """
        self._load_model()

        output = self._model.encode(
            texts,
            batch_size=self.config.batch_size,
            max_length=self.config.max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        # output["dense_vecs"] 是 shape (N, 1024) 的 numpy 数组
        vecs = output["dense_vecs"]
        return [v.tolist() for v in vecs]

    # ------------------------------------------------------------------
    # EmbedderClient 接口实现
    # ------------------------------------------------------------------

    async def create(self, input_data) -> list:
        """将单条文本（或列表的第一条）嵌入为向量。

        graphiti-core 约定：input_data 通常是字符串，也可能是单元素列表。
        此处统一转为列表处理，返回第一条结果。
        """
        if isinstance(input_data, str):
            texts = [input_data]
        else:
            texts = list(input_data)

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            self._executor, self._embed_sync, texts
        )
        return results[0]

    async def create_batch(self, input_data_list: list) -> list:
        """批量嵌入文本列表。

        Args:
            input_data_list: 待嵌入的文本列表

        Returns:
            与输入顺序对应的向量列表
        """
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            self._executor, self._embed_sync, input_data_list
        )
        return results


# ----------------------------------------------------------------------
# 快速验证入口
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import numpy as np  # type: ignore[import-untyped]

    async def demo() -> None:
        print("=== BGE-M3 本地嵌入演示 ===\n")

        config = BGEM3EmbedderConfig(device="cpu", batch_size=8)
        embedder = BGEM3Embedder(config)

        texts = [
            "人工智能正在改变世界。",
            "Artificial intelligence is transforming the world.",
            "今天天气不错，适合去散步。",
        ]

        print("单条嵌入:")
        t0 = time.perf_counter()
        vec = await embedder.create(texts[0])
        t1 = time.perf_counter()
        print(f"  文本: {texts[0]}")
        print(f"  维度: {len(vec)}  耗时: {(t1 - t0) * 1000:.1f} ms\n")

        print("批量嵌入:")
        t0 = time.perf_counter()
        vecs = await embedder.create_batch(texts)
        t1 = time.perf_counter()
        print(f"  文本数: {len(vecs)}  维度: {len(vecs[0])}  耗时: {(t1 - t0) * 1000:.1f} ms")

        # 计算中英文语义相似度（应较高）vs 无关文本
        v0 = np.array(vecs[0])
        v1 = np.array(vecs[1])
        v2 = np.array(vecs[2])
        sim_01 = float(np.dot(v0, v1) / (np.linalg.norm(v0) * np.linalg.norm(v1)))
        sim_02 = float(np.dot(v0, v2) / (np.linalg.norm(v0) * np.linalg.norm(v2)))
        print(f"\n  余弦相似度 (中英文AI句): {sim_01:.4f}  (预期较高)")
        print(f"  余弦相似度 (AI vs 天气): {sim_02:.4f}  (预期较低)")

    asyncio.run(demo())
