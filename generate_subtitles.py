#!/usr/bin/env python3
"""
根据 prompts.json 生成 SRT 字幕文件
"""

import json
import os

def parse_timestamp(ts):
    """解析时间戳 'MM:SS-SS' 或 'MM:SS-MM:SS' 格式，返回秒数"""
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

def seconds_to_srt_time(seconds):
    """将秒数转换为 SRT 时间格式: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

import sys
from pathlib import Path

def main():
    # 默认路径
    prompts_path = Path('workspace/prompts.json')
    srt_path = Path('audio/subtitles.srt')
    
    # 如果指定了项目路径参数
    if len(sys.argv) > 1:
        proj_dir = Path(sys.argv[1])
        prompts_path = proj_dir / 'prompts.json'
        srt_path = proj_dir / 'audio' / 'subtitles.srt'
        # 确保音频目录存在
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"检测到项目目录参数: {proj_dir}")

    # 读取 prompts.json
    if not prompts_path.exists():
        print(f"错误：未找到 prompts 文件: {prompts_path}")
        return

    with open(prompts_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    scenes = data['scenes']
    
    # 生成 SRT 字幕
    srt_lines = []
    subtitle_index = 1
    
    for scene in scenes:
        timestamp = scene['timestamp']
        narration = scene['narration']
        
        start, end = parse_timestamp(timestamp)
        
        # SRT 格式
        srt_lines.append(str(subtitle_index))
        srt_lines.append(f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}")
        srt_lines.append(narration)
        srt_lines.append("")  # 空行
        
        subtitle_index += 1
    
    # 保存 SRT 文件
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_lines))
    
    print(f"✅ 字幕文件已生成: {srt_path}")
    print(f"共 {len(scenes)} 条字幕")
    
    # 显示前5条字幕示例
    print("\n前5条字幕预览:")
    for i, scene in enumerate(scenes[:5], 1):
        start, end = parse_timestamp(scene['timestamp'])
        print(f"{i}. [{start}s-{end}s] {scene['narration'][:30]}...")

if __name__ == '__main__':
    main()
