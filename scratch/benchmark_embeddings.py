"""
本地 BGE-M3 vs SiliconFlow BGE-M3 嵌入性能基准测试。

用法:
    python benchmark_embeddings.py                       # 仅跑本地
    python benchmark_embeddings.py --api-key sk-xxxxx    # 同时跑 SiliconFlow
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
import time
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# 将 scratch 目录加入 sys.path，以便直接导入 local_bge_m3
# ---------------------------------------------------------------------------
_SCRATCH_DIR = Path(__file__).parent.resolve()
if str(_SCRATCH_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRATCH_DIR))


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Benchmark: 本地 BGE-M3
# ---------------------------------------------------------------------------

def benchmark_local_bge_m3(texts: list[str], n_runs: int = 3) -> dict:
    """对本地 BGE-M3 模型进行延迟与吞吐量基准测试。

    Args:
        texts:  待嵌入的文本列表
        n_runs: 重复运行次数，取平均值

    Returns:
        包含 latency_ms、throughput_texts_per_sec、embedding_dim 的字典
    """
    from local_bge_m3 import BGEM3Embedder, BGEM3EmbedderConfig  # type: ignore[import]

    config = BGEM3EmbedderConfig(device="cpu", batch_size=32)
    embedder = BGEM3Embedder(config)

    async def _run() -> tuple[list[list[float]], float]:
        t0 = time.perf_counter()
        vecs = await embedder.create_batch(texts)
        elapsed = time.perf_counter() - t0
        return vecs, elapsed

    latencies: list[float] = []
    last_vecs: list[list[float]] = []

    for i in range(n_runs):
        vecs, elapsed = asyncio.run(_run())
        latencies.append(elapsed)
        last_vecs = vecs
        print(f"  [本地] 第 {i + 1}/{n_runs} 轮: {elapsed * 1000:.1f} ms")

    avg_latency_ms = (sum(latencies) / len(latencies)) * 1000
    throughput = len(texts) / (sum(latencies) / len(latencies))

    return {
        "backend": "local BGE-M3",
        "latency_ms": avg_latency_ms,
        "latency_per_text_ms": avg_latency_ms / max(len(texts), 1),
        "throughput_texts_per_sec": throughput,
        "embedding_dim": len(last_vecs[0]) if last_vecs else 0,
        "n_texts": len(texts),
        "n_runs": n_runs,
        "embeddings": last_vecs,
    }


# ---------------------------------------------------------------------------
# Benchmark: SiliconFlow BGE-M3
# -----------------------------------------------------------

def benchmark_siliconflow_bge_m3(texts: list[str], api_key, n_runs: int = 3) -> dict:
    """对 SiliconFlow 托管的 BGE-M3 API 进行延迟与吞吐量基准测试。

    Args:
        texts:   待嵌入的文本列表
        api_key: SiliconFlow API 密钥
        n_runs取平均值

    Returns:
        包含 latency_ms、throughput_texts_per_sec、embedding_dim 的字典
    """
    try:
        import httpx  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("httpx 未安装。请运行: pip install httpx") from exc

    def _call_api() -> tuple[list[list[float]], float]:
        t0 = time.perf_counter()
        resp = httpx.post(
            "https://api.siliconflow.cn/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": "BAAI/bge-m3", "input": texts},
            timeout=30,
        )
        resp.raise_for_status()
        elapsed = time.perf_counter() - t0
        embeddings = [item["embedding"] for item in resp.json()["data"]]
        return embeddings, elapsed

    latencies: list[float] = []
    last_embeddings: list[list[float]] = []

    for i in range(n_runs):
        embeddings, elapsed = _call_api()
        latencies.append(elapsed)
        last_embeddings = embeddings
        print(f"  [SiliconFlow] 第 {i + 1}/{n_runs} 轮: {elapsed * 1000:.1f} ms")

    avg_latency_ms = (sum(latencies) / len(latencies)) * 1000
    throughput = len(texts) / (sum(latencies) / len(latencies))

    return {
        "backend": "SiliconFlow BGE-M3",
        "latency_ms": avg_latency_ms,
        "latency_per_text_ms": avg_latency_ms / max(len(texts), 1),
        "throughput_texts_per_sec": throughput,
        "embedding_dim": len(last_embeddings[0]) if last_embeddings else 0,
        "n_texts": len(texts),
        "n_runs": n_runs,
        "embeddings": last_embeddings,
    }


# ---------------------------------------------------------------------------
# 语义质量评估
# ---------------------------------------------------------------------------

def measure_semantic_quality(
    embedder_func: Callable[[list[str]], list[list[float]]],
    text_pairs: list[tuple[str, str, bool]],
) -> dict:
    """通过余弦相似度评估嵌入的语义质量。

    Args:
        embedder_func: 接受文本列表、返回向量列表的同步函数
        text_pairs:    三元组列表 (text_a, text_b, is_similar)
                       is_similar=True 表示语义相近对，False 表示无关对

    Returns:
        包含 avg_positive_similarity、avg_negative_similarity 的字典
    """
    all_texts: list[str] = []
    for ta, tb, _ in text_pairs:
        all_texts.append(ta)
        all_texts.append(tb)

    all_vecs = embedder_func(all_texts)

    positive_sims: list[float] = []
    negative_sims: list[float] = []

    for idx, (_, _, is_similar) in enumerate(text_pairs):
        va = all_vecs[idx * 2]
        vb = all_vecs[idx * 2 + 1]
        sim = _cosine_similarity(va, vb)
        if is_similar:
            positive_sims.append(sim)
        else:
            negative_sims.append(sim)

    avg_pos = sum(positive_sims) / len(positive_sims) if positive_sims else 0.0
    avg_neg = sum(negative_sims) / len(negative_sims) if negative_sims else 0.0

    return {
        "avg_positive_similarity": avg_pos,
        "avg_negative_similarity": avg_neg,
        "separation": avg_pos - avg_neg,
        "n_positive_pairs": len(positive_sims),
        "n_negative_pairs": len(negative_sims),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="BGE-M3 嵌入性能基准测试")
    parser.add_argument("--api-key", default="", help="SiliconFlow API 密钥（留空则跳过云端测试）")
    parser.add_argument("--n-runs", type=int, default=3, help="每项测试的重复次数（默认 3）")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # 测试文本 —— 中文小说相关语料，涵盖语义相近与无关对
    # ------------------------------------------------------------------
    benchmark_texts = [
        "她轻轻推开窗，月光如水倾泻而入。",
        "The moonlight streamed in as she gently opened the window.",
        "他握紧剑柄，眼神变得无比坚定。",
        "He tightened his grip on the sword hilt, his gaze unwavering.",
        "这座古城在战火中化为废墟，只剩断壁残垣。",
        "今天的午饭是番茄炒鸡蛋，味道还不错。",
        "AI 大模型正在重塑整个软件行业。",
        "春天来了，樱花开了，公园里游人如织。",
    ]

    # 语义质量测试对：(文本A, 文本B, 是否语义相近)
    quality_pairs: list[tuple[str, str, bool]] = [
        # 相近对（翻译等价）
        ("她轻轻推开窗，月光如水倾泻而入。",
         "The moonlight streamed in as she gently opened the window.",
         True),
        ("人工智能正在改变软件开发方式。",
         "AI is transforming the way software is built.",
         True),
        ("他在战场上浴血奋战，誓死保卫家园。",
         "He fought with his life on the battlefield, defending his homeland.",
         True),
        # 无关对
        ("她轻轻推开窗，月光如水倾泻而入。",
         "今天股市大涨，沪指突破三千点。",
         False),
        ("AI 大模型正在重塑整个软件行业。",
         "春天来了，桃花又开了。",
         False),
        ("他握紧剑柄，眼神变得无比坚定。",
         "这道红烧肉炖得软烂入味，十分下饭。",
         False),
    ]

    results: list[dict] = []

    # ------------------------------------------------------------------
    # 本地 BGE-M3
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  测试: 本地 BGE-M3")
    print("=" * 60)
    try:
        local_result = benchmark_local_bge_m3(benchmark_texts, n_runs=args.n_runs)

        # 构造同步 embedder_func 供质量评估使用
        from local_bge_m3 import BGEM3Embedder, BGEM3EmbedderConfig  # type: ignore[import]

        _local_embedder = BGEM3Embedder(BGEM3EmbedderConfig(device="cpu"))

        def _local_embed_sync(texts: list[str]) -> list[list[float]]:
            return asyncio.run(_local_embedder.create_batch(texts))

        local_quality = measure_semantic_quality(_local_embed_sync, quality_pairs)
        local_result["quality"] = local_quality
        results.append(local_result)
        print(f"  -> 质量 (正对相似度): {local_quality['avg_positive_similarity']:.4f}")
        print(f"  -> 质量 (负对相似度): {local_quality['avg_negative_similarity']:.4f}")
    except Exception as exc:
        print(f"  [跳过] 本地测试失败: {exc}")
        local_result = None

    # ------------------------------------------------------------------
    # SiliconFlow BGE-M3
    # ------------------------------------------------------------------
    sf_result = None
    if args.api_key:
        print("\n" + "=" * 60)
        print("  测试: SiliconFlow BGE-M3")
        print("=" * 60)
        try:
            sf_result = benchmark_siliconflow_bge_m3(
                benchmark_texts, api_key=args.api_key, n_runs=args.n_runs
            )

            def _sf_embed_sync(texts: list[str]) -> list[list[float]]:
                import httpx  # type: ignore[import-untyped]

                resp = httpx.post(
                    "https://api.siliconflow.cn/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {args.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": "BAAI/bge-m3", "input": texts},
                    timeout=30,
                )
                resp.raise_for_status()
                return [item["embedding"] for item in resp.json()["data"]]

            sf_quality = measure_semantic_quality(_sf_embed_sync, quality_pairs)
            sf_result["quality"] = sf_quality
            results.append(sf_result)
            print(f"  -> 质量 (正对相似度): {sf_quality['avg_positive_similarity']:.4f}")
            print(f"  -> 质量 (负对相似度): {sf_quality['avg_negative_similarity']:.4f}")
        except Exception as exc:
            print(f"  [跳过] SiliconFlow 测试失败: {exc}")
    else:
        print("\n[提示] 未提供 --api-key，跳过 SiliconFlow 测试。")

    # ---------------------------------------------------------
    # 对比报表
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("  对比报表")
    print("=" * 72)
    header = f"{'后端':<22} {'延迟(ms)':<14} {'ms/条':<12} {'吞吐(条/秒)':<14} {'正对相似':<12} {'负对相似':<12}"
    print(header)
    print("-" * 72)

    for r in results:
        q = r.get("quality", {})
        row = (
            f"{r['backend']:<22} "
            f"{r['latency_ms']:<14.1f} "
            f"{r['latency_per_text_ms']:<12.1f} "
            f"{r['throughput_texts_per_sec']:<14.1f} "
            f"{q.get('avg_positive_similarity', float('nan')):<12.4f} "
            f"{q.get('avg_negative_similarity', float('nan')):<12.4f}"
        )
        print(row)

    print("")

    # ------------------------------------------------------------------
    # 权衡说明
    # ------------------------------------------------------------------
    print("""
权衡说明:
  本地 BGE-M3:
    + 无网络延迟，数据隐私有保障，无 API 费用
    + 适合高吞吐批处理场景
    - 首次加载模型需要几秒钟（约 2-5s，后续调用无此开销）
    - 需要本地 CPU/GPU 资源，内存占用约 2-4 GB
    - 需要提前下载模型权重（约 2 GB，国内可用 HF_ENDPOINT 镜像）

  SiliconFlow BGE-M3:
    + 无需本地资源，即开即用
    + 适合低频调用或无 GPU 环境
    - 有网络往返延迟（通常 100-500 ms）
    - 受 API 限速和配额限制
    - 生产环境需要支付 API 费用

  模型一致性:
    两者均使用相同的 BAAI/bge-m3 权重，语义质量理论上完全一致；
    若实测分数略有差异，主要来自量化精度（fp16 vs fp32）的微小误差。
""")


if __name__ == "__main__":
    main()
