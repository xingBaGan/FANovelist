"""Tests for openharness.prompts.selector."""

from __future__ import annotations

import tempfile
from pathlib import Path

from openharness.config.settings import Settings
from openharness.prompts.context import build_runtime_system_prompt
from openharness.prompts.selector import (
    tokenize,
    score_prompt_template,
    find_prompt_template_by_name,
    list_prompt_templates,
    find_best_matching_prompt_template,
)


def test_tokenize():
    # Test English tokenization and stopword removal
    tokens_en = tokenize("Generate a suspence novel script!")
    assert "generate" in tokens_en
    assert "suspence" in tokens_en
    assert "novel" in tokens_en
    assert "script" in tokens_en
    assert "a" not in tokens_en  # Stopword

    # Test Chinese tokenization (character by character)
    tokens_zh = tokenize("我想写一个悬疑小说脚本")
    assert "我" in tokens_zh
    assert "想" in tokens_zh
    assert "写" in tokens_zh
    assert "悬" in tokens_zh
    assert "疑" in tokens_zh
    assert "脚" in tokens_zh
    assert "本" in tokens_zh


def test_find_and_list_prompt_templates():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        # Create two test prompt templates
        novel_prompt = prompts_dir / "novel-writer.md"
        novel_prompt.write_text(
            "# Role: Novel Writer 小说作家\n- Description: A professional suspense novel writer.\nGoal: Write novels",
            encoding="utf-8",
        )

        bug_prompt = prompts_dir / "bug-fixer.txt"
        bug_prompt.write_text(
            "Profile: Bug Fixer 调试程序\ndescription: Debug Python programs.",
            encoding="utf-8",
        )

        # 1. Test find_prompt_template_by_name
        found = find_prompt_template_by_name("novel-writer", cwd=tmp_path)
        assert found == novel_prompt.resolve()

        found_ext = find_prompt_template_by_name("novel-writer.md", cwd=tmp_path)
        assert found_ext == novel_prompt.resolve()

        found_bug = find_prompt_template_by_name("bug-fixer", cwd=tmp_path)
        assert found_bug == bug_prompt.resolve()

        # 2. Test list_prompt_templates
        templates = list_prompt_templates(cwd=tmp_path)
        assert len(templates) == 2
        
        # Check descriptions extraction
        novel_info = next(t for t in templates if t["name"] == "novel-writer")
        assert novel_info["description"] == "Role: Novel Writer 小说作家"

        bug_info = next(t for t in templates if t["name"] == "bug-fixer")
        assert bug_info["description"] == "Debug Python programs."


def test_scoring_and_auto_matching():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        novel_prompt = prompts_dir / "novel-writer.md"
        # Content contains Chinese words so a Chinese query can match
        novel_prompt.write_text(
            "# Role: Novel Writer 小说创作导演\n- Description: A professional suspense novel writer 小说扩写编写专家.",
            encoding="utf-8",
        )

        bug_prompt = prompts_dir / "bug-fixer.md"
        bug_prompt.write_text(
            "# Role: Bug Fixer\nDescription: Helps with debugging Python code and fixing errors.",
            encoding="utf-8",
        )

        # User wants to write a novel (in Chinese)
        match = find_best_matching_prompt_template("我想写一部悬疑小说脚本", cwd=tmp_path, threshold=4)
        assert match == novel_prompt.resolve()

        # User wants to fix code bugs (in English)
        match = find_best_matching_prompt_template("fix my python program crash with traceback error", cwd=tmp_path, threshold=4)
        assert match == bug_prompt.resolve()

        # No match when query is unrelated
        match = find_best_matching_prompt_template("make some coffee recipes", cwd=tmp_path, threshold=10)
        assert match is None


def test_integration_with_build_runtime_system_prompt():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        novel_prompt = prompts_dir / "novel-writer.md"
        novel_prompt.write_text(
            "# Role: Suspense Novel Writer 悬疑小说创作导演\nGoal: Help write dark secrets.",
            encoding="utf-8",
        )

        # Scenario 2: Explicit override using the template name
        settings_explicit = Settings(system_prompt="novel-writer")
        runtime_prompt_explicit = build_runtime_system_prompt(
            settings_explicit,
            cwd=tmp_path,
            latest_user_prompt="Hello",
            include_project_memory=False,
        )
        assert "# Role: Suspense Novel Writer" in runtime_prompt_explicit
