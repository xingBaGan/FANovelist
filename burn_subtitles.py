#!/usr/bin/env python3
"""
使用 drawtext 滤镜将字幕烧录到视频中
"""

import json
import subprocess
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
        if len(parts[0].split(':')[0]) == len(end_part) or int(end_part) < 60:
            end = start // 60 * 60 + int(end_part)
        else:
            end = to_seconds(end_part)
    
    return start, end

def escape_text(text):
    """转义 drawtext 滤镜中的特殊字符"""
    # 转义 ffmpeg drawtext 中的特殊字符
    text = text.replace('\\', '\\\\')
    text = text.replace("'", "\\'")
    text = text.replace(':', '\\:')
    text = text.replace('[', '\\[')
    text = text.replace(']', '\\]')
    return text

import sys
from pathlib import Path

def main():
    # 默认路径
    prompts_path = Path('workspace/prompts.json')
    input_video = Path('output.mp4')
    output_video = Path('output_final.mp4')
    
    # 如果指定了项目路径参数
    if len(sys.argv) > 1:
        proj_dir = Path(sys.argv[1]).resolve()
        prompts_path = proj_dir / 'prompts.json'
        input_video = proj_dir / 'output.mp4'
        output_video = proj_dir / 'output_final.mp4'
        print(f"检测到项目目录参数: {proj_dir}")

    # 读取 prompts.json
    if not prompts_path.exists():
        print(f"错误：未找到 prompts 文件: {prompts_path}")
        return

    with open(prompts_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    scenes = data['scenes']
    
    # 构建 drawtext 滤镜链
    drawtext_filters = []
    
    for scene in scenes:
        timestamp = scene['timestamp']
        narration = scene['narration']
        
        start, end = parse_timestamp(timestamp)
        duration = end - start
        
        # 转义文本
        escaped_text = escape_text(narration)
        
        # 构建 drawtext 滤镜
        # 使用系统默认中文字体
        filter_str = (
            f"drawtext=fontfile=/System/Library/Fonts/PingFang.ttc:"
            f"text='{escaped_text}':"
            f"fontcolor=white:"
            f"fontsize=36:"
            f"box=1:"
            f"boxcolor=black@0.5:"
            f"boxborderw=10:"
            f"x=(w-text_w)/2:"
            f"y=h-text_h-80:"
            f"enable='between(t\\,{start}\\,{end})'"
        )
        
        drawtext_filters.append(filter_str)
    
    # 组合所有滤镜
    vf_chain = ','.join(drawtext_filters)
    
    print(f"正在烧录字幕到视频...")
    print(f"共 {len(scenes)} 条字幕")
    
    # 确保输入视频存在
    if not input_video.exists():
        print(f"错误：未找到输入视频: {input_video}")
        return

    # 构建 ffmpeg 命令
    cmd = [
        'ffmpeg', '-y',
        '-i', str(input_video),
        '-vf', vf_chain,
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '23',
        '-c:a', 'copy',
        str(output_video)
    ]
    
    print(f"命令长度: {len(' '.join(cmd))} 字符")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ 字幕烧录成功!")
        print(f"输出文件: {output_video}")
        
        if output_video.exists():
            size = output_video.stat().st_size / (1024 * 1024)
            print(f"文件大小: {size:.2f} MB")
    else:
        print("❌ 字幕烧录失败!")
        print("错误:", result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)

if __name__ == '__main__':
    main()
