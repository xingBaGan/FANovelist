import json
import os
import sys
from pathlib import Path
from openai import AsyncOpenAI
import asyncio

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

async def generate_split_scenes():
    # 1. 载入 .env
    env_path = Path(__file__).resolve().parents[1] / ".env"
    api_key = None
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "DEEPSEEK_API_KEY":
                    api_key = v.strip()

    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
    
    if not api_key:
        print("错误：未找到 DEEPSEEK_API_KEY 环境变量！")
        return

    # 初始化 DeepSeek 客户端
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1"
    )

    # 2. 读取原始 prompts.json
    prompts_path = Path("workspace/prompts.json")
    with open(prompts_path, "r", encoding="utf-8") as f:
        original_data = json.load(f)

    character_designs = original_data.get("character_designs", {})
    style_suffix = original_data.get("style_suffix", "")
    original_scenes = original_data.get("scenes", [])

    print(f"原始大分镜数量: {len(original_scenes)}")

    # 3. 将 35 个大分镜分为更小的批次（例如 5 个大分镜一组）进行处理，彻底防止单次请求的 Output Token 超出限制
    batch_size = 5
    batches = [original_scenes[i:i + batch_size] for i in range(0, len(original_scenes), batch_size)]
    
    all_new_scenes = []
    scene_counter = 1

    for batch_idx, batch in enumerate(batches):
        print(f"\n正在通过 DeepSeek 处理第 {batch_idx + 1}/{len(batches)} 批大分镜...")
        
        system_prompt = f"""你是一个专业的视频分镜导演。你需要把一个已经拥有部分大场景（每个大场景为5s/10s/15s不等，总计长视频）的脚本，细化拆分为每段约3秒的小分镜，以提高视频的完播率和节奏感。

角色设定（请在提示词中复写这些设定）：
{json.dumps(character_designs, ensure_ascii=False, indent=2)}

画面风格统一后缀（请务必拼接到每个提示词的末尾）：
{style_suffix}

请严格按照以下规则细化：
1. 计算时长：解析 timestamp（例如 "00:05-00:15" 长度为10秒）。根据时长将其等分为约3秒一段的子区间（例如10秒可分为3段，每段约3.3秒）。
2. 时间轴首尾相接：子区间的时间标记必须符合 "MM:SS" 格式，且必须与前后的子分镜首尾相连。
3. 旁白合理拆分：将原旁白（narration）拆分为几句话，分给对应的子分镜。不要遗漏任何原旁白内容，也不要编造无关故事。
4. 提示词人设一致性：绘图提示词（prompt）必须是高度具体的场景描写。若画面中出现上述人物，必须一字不差地复写其“外貌设定”（例如写“一个16岁的清瘦少年...”，而不能只写“高飞”或“少年”），并在句末拼接风格后缀。
5. 提示词为Kolors优化的中文或英文画面描述。

请以 JSON 格式输出这批大分镜细化拆分后的子分镜列表。格式如下：
[
  {{
    "scene_id": "001",
    "timestamp": "00:00-00:03",
    "narration": "分段旁白",
    "prompt": "具体画面提示词，包含角色设定，拼接收尾风格"
  }},
  ...
]
"""

        user_content = f"需要拆分的原始大分镜数据如下：\n{json.dumps(batch, ensure_ascii=False, indent=2)}\n\n请直接输出 JSON 数组，不要带有 Markdown 的 ```json 标记包裹，确保是合法的 JSON 格式数据。"

        try:
            response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                max_tokens=4000
            )
            
            resp_text = response.choices[0].message.content.strip()
            # 移除可能存在的 Markdown 包裹标记
            if resp_text.startswith("```"):
                lines = resp_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                resp_text = "\n".join(lines).strip()

            batch_scenes = json.loads(resp_text)
            
            # 重新整理 scene_id 序列
            for s in batch_scenes:
                s["scene_id"] = f"{scene_counter:03d}"
                scene_counter += 1
                all_new_scenes.append(s)
                
            print(f"第 {batch_idx + 1} 批处理完成，拆分出 {len(batch_scenes)} 个子分镜。")

        except Exception as e:
            print(f"处理第 {batch_idx + 1} 批时发生错误: {e}")
            # 如果出错则打印返回的文本进行排查
            if 'resp_text' in locals():
                print(f"Raw Response:\n{resp_text[:500]}")
            return

    # 4. 保存为新的 prompts.json
    new_data = {
        "character_designs": character_designs,
        "style_suffix": style_suffix,
        "scenes": all_new_scenes
    }

    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 细化分镜生成成功！共生成 {len(all_new_scenes)} 个分镜图片提示词。")
    print(f"已写回: {prompts_path.resolve()}")

if __name__ == "__main__":
    asyncio.run(generate_split_scenes())
