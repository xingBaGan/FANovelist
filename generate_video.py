#!/usr/bin/env python3
"""
根据 prompts.json 中的时间戳和图片生成视频
"""

import json
import subprocess
import os
from pathlib import Path

def parse_timestamp(ts):
    """解析时间戳 'MM:SS-SS' 或 'MM:SS-MM:SS' 格式"""
    parts = ts.split('-')
    
    def to_seconds(t):
        if ':' in t:
            m, s = t.split(':')
            return int(m) * 60 + int(s)
        return int(t)
    
    start = to_seconds(parts[0])
    
    # 处理结束时间
    end_part = parts[1]
    if ':' in end_part:
        end = to_seconds(end_part)
    else:
        # 可能是秒数（相对于分钟）
        if len(parts[0].split(':')[0]) == len(end_part) or int(end_part) < 60:
            # 是秒数
            end = start // 60 * 60 + int(end_part)
        else:
            end = to_seconds(end_part)
    
    return start, end

import sys
from pathlib import Path

def main():
    # 默认路径
    prompts_path = Path('workspace/prompts.json')
    images_dir = Path('generated_images')
    audio_path = Path('audio/narration.mp3')
    output_path = Path('output.mp4')
    concat_file = Path('concat_list.txt')
    
    # 如果指定了项目路径参数
    if len(sys.argv) > 1:
        proj_dir = Path(sys.argv[1]).resolve()
        prompts_path = proj_dir / 'prompts.json'
        images_dir = proj_dir / 'generated_images'
        audio_path = proj_dir / 'audio' / 'narration.mp3'
        output_path = proj_dir / 'output.mp4'
        concat_file = proj_dir / 'concat_list.txt'
        print(f"检测到项目目录参数: {proj_dir}")

    # 读取 prompts.json
    if not prompts_path.exists():
        print(f"错误：未找到 prompts 文件: {prompts_path}")
        return

    with open(prompts_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    scenes = data['scenes']
    
    # 创建 ffmpeg 输入文件列表
    with open(concat_file, 'w') as f:
        for scene in scenes:
            scene_id = scene['scene_id']
            timestamp = scene['timestamp']
            
            start, end = parse_timestamp(timestamp)
            duration = end - start
            
            # 图片路径
            img_path = images_dir / f"scene_{scene_id}.png"
            
            if img_path.exists():
                # 使用 absolute path 并使用 duration 指令
                f.write(f"file '{img_path.resolve()}'\n")
                f.write(f"duration {duration}\n")
            else:
                print(f"警告: 图片不存在 {img_path}")
    
    # 获取音频时长
    if not audio_path.exists():
        print(f"错误：未找到音频文件: {audio_path}")
        return

    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
         '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)],
        capture_output=True, text=True
    )
    audio_duration = float(result.stdout.strip())
    
    print(f"音频时长: {audio_duration:.2f} 秒")
    print(f"场景数量: {len(scenes)}")
    
    # 计算总视频时长
    total_duration = 0
    for scene in scenes:
        start, end = parse_timestamp(scene['timestamp'])
        total_duration += (end - start)
    
    print(f"根据时间戳计算的视频时长: {total_duration:.2f} 秒")
    
    # 构建 ffmpeg 命令
    # 使用 concat demuxer 将图片序列合成视频
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', str(concat_file),
        '-i', str(audio_path),
        '-vf', 'fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p',
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-shortest',
        str(output_path)
    ]
    
    print("\n开始合成视频...")
    print(f"命令: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ 视频合成成功!")
        print(f"输出文件: {output_path}")
        
        # 检查文件大小
        if output_path.exists():
            size = output_path.stat().st_size / (1024 * 1024)
            print(f"文件大小: {size:.2f} MB")
    else:
        print("❌ 视频合成失败!")
        print("错误输出:", result.stderr)
    
    # 清理临时文件
    if concat_file.exists():
        concat_file.unlink()

if __name__ == '__main__':
    main()
