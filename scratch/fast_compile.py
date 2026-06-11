import json
import subprocess
import os
from pathlib import Path

def main():
    workspace_dir = Path("workspace")
    prompts_file = workspace_dir / "prompts.json"
    concat_file = Path("scratch/concat_list.txt")
    audio_file = Path("audio/narration.mp3")
    srt_file = Path("audio/subtitles.srt")
    output_file = Path("output.mp4")

    # 1. 读取分镜与时间参数
    print("正在解析 prompts.json...")
    with open(prompts_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    scenes = data.get("scenes", [])
    if not scenes:
        print("错误：未找到 scenes 配置！")
        return

    # 2. 生成 FFmpeg concat 列表
    concat_lines = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        ts = scene["timestamp"]
        
        # 解析时间差获取时长
        start_str, end_str = ts.split("-")
        def to_seconds(t_str):
            parts = t_str.strip().split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(parts[0])
            
        duration = to_seconds(end_str) - to_seconds(start_str)
        
        img_path = Path(f"generated_images/scene_{scene_id}.png").resolve()
        if not img_path.exists():
            print(f"警告：图片 {img_path} 不存在，跳过！")
            continue

        concat_lines.append(f"file '{img_path}'")
        concat_lines.append(f"duration {duration}")

    # FFmpeg concat 规范：最后一行需要重复声明最后一张图且不加 duration
    if scenes:
        last_id = scenes[-1]["scene_id"]
        last_path = Path(f"generated_images/scene_{last_id}.png").resolve()
        concat_lines.append(f"file '{last_path}'")

    # 写入临时文件
    os.makedirs("scratch", exist_ok=True)
    with open(concat_file, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_lines) + "\n")
    print(f"已生成 FFmpeg 拼接列表：{concat_file}")

    # 3. 构造 FFmpeg 合成指令
    # 使用 scale=1280:720 统一分辨率防止报错
    # 如果字幕文件存在，直接使用 subtitles 滤镜硬烧录字幕
    video_filter = "scale=1280:720,format=yuv420p"

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-i", str(audio_file),
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_file)
    ]

    print("正在调用 FFmpeg 合成音视频...")
    print(f"执行命令: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0:
        print(f"\n✅ 视频极速合成成功！输出路径: {output_file.resolve()}")
    else:
        print(f"\n❌ FFmpeg 合成失败，错误日志：\n{result.stderr}")

if __name__ == "__main__":
    main()
