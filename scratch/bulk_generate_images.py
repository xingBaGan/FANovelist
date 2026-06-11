#!/usr/bin/env python3
import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to python path to allow importing openharness
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load .env file automatically
def load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

load_env()

from openharness.config.settings import ImageGenerationConfig
from openharness.tools.image_generation_tool import ImageGenerationTool, ImageGenerationToolInput
from openharness.tools.base import ToolExecutionContext

async def generate_scene_image(tool: ImageGenerationTool, scene: dict, env_cfg: ImageGenerationConfig, sem: asyncio.Semaphore, stats: dict):
    scene_id = scene["scene_id"]
    prompt = scene["prompt"]
    output_path = f"workspace/crime_genius/generated_images/scene_{scene_id}.png"
    
    # Check if file already exists and is non-empty
    out_file = Path(output_path)
    if out_file.exists() and out_file.stat().st_size > 0:
        stats["skipped"] += 1
        return

    async with sem:
        print(f"[{scene_id}] 开始生成图片...")
        
        # Define context
        context = ToolExecutionContext(
            cwd=Path(__file__).resolve().parents[1],
            metadata={
                "image_generation_config": {
                    "provider": env_cfg.provider,
                    "model": env_cfg.model,
                    "api_key": env_cfg.api_key,
                    "base_url": env_cfg.base_url,
                    "comfyui_base_url": env_cfg.comfyui_base_url,
                }
            }
        )

        # Try comfyui first (as configured in .env)
        args_comfy = ImageGenerationToolInput(
            prompt=prompt,
            output_path=output_path,
            provider=env_cfg.provider or "auto",
            overwrite=True
        )
        
        success = False
        try:
            res = await tool.execute(args_comfy, context)
            if not res.is_error:
                print(f"[{scene_id}] 成功生成 (ComfyUI) -> {output_path}")
                success = True
                stats["comfyui"] += 1
            else:
                print(f"[{scene_id}] ComfyUI 生成失败，尝试 Fallback 到 SiliconFlow...")
        except Exception as e:
            print(f"[{scene_id}] ComfyUI 发生异常: {e}，尝试 Fallback 到 SiliconFlow...")

        # Fallback to SiliconFlow (openai provider)
        if not success:
            args_fallback = ImageGenerationToolInput(
                prompt=prompt,
                output_path=output_path,
                provider="openai",
                model="Kwai-Kolors/Kolors",
                overwrite=True
            )
            # Override context metadata for SiliconFlow
            context_fallback = ToolExecutionContext(
                cwd=Path(__file__).resolve().parents[1],
                metadata={
                    "image_generation_config": {
                        "provider": "openai",
                        "model": "Kwai-Kolors/Kolors",
                        "api_key": os.environ.get("OPENHARNESS_IMAGE_GENERATION_API_KEY") or os.environ.get("SILICONFLOW_API_KEY"),
                        "base_url": "https://api.siliconflow.cn/v1",
                    }
                }
            )
            try:
                res = await tool.execute(args_fallback, context_fallback)
                if not res.is_error:
                    print(f"[{scene_id}] 成功生成 (SiliconFlow) -> {output_path}")
                    success = True
                    stats["siliconflow"] += 1
                else:
                    print(f"[{scene_id}] ❌ 彻底生成失败: {res.output}")
                    stats["failed"] += 1
            except Exception as e:
                print(f"[{scene_id}] ❌ Fallback 发生异常: {e}")
                stats["failed"] += 1

async def main():
    prompts_path = Path("workspace/crime_genius/prompts.json")
    if not prompts_path.exists():
        print("错误：未找到 prompts.json！")
        return

    with open(prompts_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    scenes = data.get("scenes", [])
    if not scenes:
        print("没有可生成的分镜！")
        return

    # Ensure output dir exists
    Path("workspace/crime_genius/generated_images").mkdir(parents=True, exist_ok=True)

    tool = ImageGenerationTool()
    env_cfg = ImageGenerationConfig.from_env()

    # Semaphore to control concurrency (2 workers)
    sem = asyncio.Semaphore(2)
    stats = {"comfyui": 0, "siliconflow": 0, "skipped": 0, "failed": 0}

    print(f"开始批量生成分镜图片，共 {len(scenes)} 张...")
    
    # Run all tasks concurrently
    tasks = [generate_scene_image(tool, s, env_cfg, sem, stats) for s in scenes]
    await asyncio.gather(*tasks)

    print("\n================== 生成统计 ==================")
    print(f"总计分镜: {len(scenes)}")
    print(f" 跳过已存在: {stats['skipped']}")
    print(f" ComfyUI 成功: {stats['comfyui']}")
    print(f" SiliconFlow 成功: {stats['siliconflow']}")
    print(f" ❌ 失败: {stats['failed']}")
    print("===============================================")

if __name__ == "__main__":
    asyncio.run(main())
