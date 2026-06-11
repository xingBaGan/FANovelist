import json
from pathlib import Path

def main():
    prompts_path = Path("workspace/crime_genius/prompts.json")
    index_path = Path("workspace/crime_genius/index.html")

    if not prompts_path.exists():
        print("错误：未找到 prompts.json！")
        return

    with open(prompts_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenes = data.get("scenes", [])
    if not scenes:
        print("错误：scenes 列表为空！")
        return

    # 1. 生成 HTML Scene Divs
    divs = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        ts = scene["timestamp"]
        
        # 计算时长
        start_str, end_str = ts.split("-")
        def to_seconds(t_str):
            parts = t_str.strip().split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(parts[0])
            
        start = to_seconds(start_str)
        duration = to_seconds(end_str) - start

        # 默认首帧可见，其余的隐藏
        is_first = (scene_id == "001")
        opacity_style = " opacity: 1; visibility: visible;" if is_first else ""

        divs.append(
            f'    <div id="scene-{scene_id}" class="scene clip" data-start="{start}" data-duration="{duration}" data-track-index="0" style="{opacity_style}">\n'
            f'      <img class="scene-img" src="generated_images/scene_{scene_id}.png" alt="Scene {scene_id}">\n'
            f'    </div>'
        )

    scene_divs_html = "\n".join(divs)

    # 2. 构造 JS 场景数据
    js_scenes = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        ts = scene["timestamp"]
        narration = scene["narration"].replace('"', '\\"').replace('\n', ' ')
        
        start_str, end_str = ts.split("-")
        def to_seconds(t_str):
            parts = t_str.strip().split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(parts[0])
            
        start = to_seconds(start_str)
        duration = to_seconds(end_str) - start

        # 特殊词红字高亮逻辑（悬疑关键词如：柿子红了，深度处理，杀猪刀，通缉令，吸毒等）
        highlight_keywords = ["柿子红了", "被深度处理了", "杀猪刀", "抢劫", "通缉令", "山牙", "婴儿", "喂奶", "出狱", "吸毒", "犯罪天才", "猎人", "猎物", "光", "影"]
        highlighted_narration = narration
        for kw in highlight_keywords:
            if kw in highlighted_narration:
                highlighted_narration = highlighted_narration.replace(kw, f"<span class='highlight'>{kw}</span>")

        js_scenes.append({
            "id": scene_id,
            "start": start,
            "duration": duration,
            "text": highlighted_narration
        })

    js_scenes_json = json.dumps(js_scenes, ensure_ascii=False, indent=6)

    # 3. 构造完整 HTML 模板
    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>《罪全书》第一章：犯罪天才（HyperFrames 细化版）</title>
  <!-- 引入 Google Fonts 中文字体 Noto Serif SC 与英文字体 Outfit -->
  <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700;900&family=Outfit:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    * {{
      box-sizing: border-box;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      width: 1920px;
      height: 1080px;
      background-color: #050505;
      overflow: hidden;
      font-family: 'Noto Serif SC', 'Georgia', serif;
      color: #ffffff;
    }}

    #root {{
      position: relative;
      width: 1920px;
      height: 1080px;
      overflow: hidden;
    }}

    /* 场景基本布局 */
    .scene {{
      position: absolute;
      top: 0;
      left: 0;
      width: 1920px;
      height: 1080px;
      opacity: 0;
      visibility: hidden;
      overflow: hidden;
      background-color: #000;
    }}

    .scene-img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      transform: scale(1.0);
    }}

    /* 电影级暗角遮罩 */
    .vignette {{
      position: absolute;
      top: 0;
      left: 0;
      width: 1920px;
      height: 1080px;
      box-shadow: inset 0 0 200px rgba(0, 0, 0, 0.9);
      background: radial-gradient(circle, transparent 40%, rgba(0,0,0,0.4) 100%);
      pointer-events: none;
      z-index: 10;
    }}

    /* 胶片颗粒与质感叠加层 */
    .film-grain {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image: radial-gradient(rgba(255,255,255,0.05) 1px, transparent 0);
      background-size: 4px 4px;
      opacity: 0.15;
      pointer-events: none;
      z-index: 11;
    }}

    /* 字幕容器与样式 */
    .caption-container {{
      position: absolute;
      bottom: 90px;
      left: 50%;
      transform: translateX(-50%);
      width: 1500px;
      text-align: center;
      z-index: 20;
      pointer-events: none;
    }}

    .caption-box {{
      display: inline-block;
      padding: 15px 30px;
      background: rgba(0, 0, 0, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      backdrop-filter: blur(8px);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8);
      max-width: 100%;
      overflow: visible;
    }}

    .caption-text {{
      font-size: 44px;
      font-weight: 700;
      line-height: 1.5;
      letter-spacing: 2px;
      color: #f5f5f5;
      text-shadow: 0 2px 4px rgba(0,0,0,0.9);
      white-space: normal;
      word-wrap: break-word;
    }}

    /* 特殊标红词语 */
    .highlight {{
      color: #ff3b30;
      text-shadow: 0 0 8px rgba(255, 59, 48, 0.5);
      font-weight: 900;
    }}
  </style>
</head>
<body>

  <div id="root" data-composition-id="root" data-start="0" data-width="1920" data-height="1080">
    <!-- 音频轨道 -->
    <audio id="narration" src="audio/narration.mp3" data-start="0" data-duration="380" data-track-index="1"></audio>

    <!-- 电影感滤镜与暗角层 -->
    <div class="vignette"></div>
    <div class="film-grain"></div>

    <!-- 动态场景载入 -->
{scene_divs_html}

    <!-- 全局字幕叠加区 -->
    <div class="caption-container">
      <div class="caption-box" id="caption-box" style="opacity: 0;">
        <div class="caption-text" id="caption-text"></div>
      </div>
    </div>
  </div>

  <!-- 引入 GSAP 核心库 -->
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>
  <script>
    // 注册全局时间线
    window.__timelines = window.__timelines || {{}};
    const tl = gsap.timeline({{ paused: true }});
    window.__timelines["root"] = tl;

    // 动态生成子场景数据
    const scenes = {js_scenes_json};

    // 初始化字幕位置，避免 transform 冲突警告
    gsap.set("#caption-box", {{ y: 25, opacity: 0 }});

    // 编译所有的动画轨迹
    scenes.forEach((scene, index) => {{
      const id = scene.id;
      const start = scene.start;
      const duration = scene.duration;
      const end = start + duration;

      const sceneEl = `#scene-${{id}}`;
      const imgEl = `${{sceneEl}} .scene-img`;

      // 是否是需要设置 immediateRender: false 的非首场动画
      const isLater = index > 0;

      // 1. 场景可见性控制：在开始时显示，在结束时隐藏
      if (index === 0) {{
        tl.set(sceneEl, {{ visibility: "visible", opacity: 1 }}, 0);
      }} else {{
        // 后续帧通过淡入过渡（实现 crossfade）
        tl.set(sceneEl, {{ visibility: "visible" }}, start);
        tl.fromTo(sceneEl, 
          {{ opacity: 0 }}, 
          {{ opacity: 1, duration: 0.6, ease: "power2.out", immediateRender: false }}, 
          start
        );
      }}

      // 当前一帧完全被新一帧覆盖后，隐藏前一帧以节省 CPU 消耗
      if (index > 0) {{
        const prevSceneEl = `#scene-${{scenes[index - 1].id}}`;
        tl.set(prevSceneEl, {{ visibility: "hidden" }}, start + 0.61);
      }}

      // 2. Ken Burns 电影镜头漂移特效
      let fromVars = {{}}, toVars = {{}};
      const zoomRatio = 1.08;
      
      switch (index % 4) {{
        case 0: // 缓缓放大并向右下角推近
          fromVars = {{ scale: 1.0, x: 0, y: 0 }};
          toVars = {{ scale: zoomRatio, x: 30, y: 20, duration: duration, ease: "sine.out" }};
          break;
        case 1: // 从放大状态缓缓缩小并往左上角漂移
          fromVars = {{ scale: zoomRatio, x: -30, y: -20 }};
          toVars = {{ scale: 1.0, x: 0, y: 0, duration: duration, ease: "sine.out" }};
          break;
        case 2: // 缓缓放大并往左下角推近
          fromVars = {{ scale: 1.0, x: 0, y: 0 }};
          toVars = {{ scale: zoomRatio, x: -30, y: 20, duration: duration, ease: "sine.out" }};
          break;
        case 3: // 缓缓缩小并往右上角漂移
          fromVars = {{ scale: zoomRatio, x: 30, y: -20 }};
          toVars = {{ scale: 1.0, x: 0, y: 0, duration: duration, ease: "sine.out" }};
          break;
      }}

      toVars.immediateRender = !isLater;
      tl.fromTo(imgEl, fromVars, toVars, start);

      // 3. 字幕极其同步切换与淡入淡出
      tl.set("#caption-text", {{ 
        innerHTML: scene.text 
      }}, start);

      // 字幕入场动画
      tl.fromTo("#caption-box",
        {{ opacity: 0, y: 25 }},
        {{ opacity: 1, y: 0, duration: 0.5, ease: "power3.out", immediateRender: !isLater, overwrite: "auto" }},
        start
      );

      // 字幕离场动画 (在每幕结束前 0.4 秒淡出，如果是最后一幕则在最后淡出)
      const exitTime = index === scenes.length - 1 ? end - 0.5 : end - 0.4;
      tl.to("#caption-box",
        {{ opacity: 0, y: -15, duration: 0.3, ease: "power2.in", overwrite: "auto" }},
        exitTime
      );
      
      // 清空字幕与重置位置
      tl.set("#caption-text", {{ innerHTML: "" }}, end);
      tl.set("#caption-box", {{ y: 25 }}, end);
    }});

    // 最后一帧渐暗淡出到黑屏
    const totalEnd = 380;
    tl.to("#root", {{ opacity: 0, duration: 1.5, ease: "power2.out" }}, totalEnd - 1.5);
  </script>
</body>
</html>
"""

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✅ index.html 已成功生成于: {index_path.resolve()}")

if __name__ == "__main__":
    main()
