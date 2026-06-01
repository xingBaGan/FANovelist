"""System prompt template selector and auto-loader for OpenHarness."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Common English stopwords to ignore during matching
_ENGLISH_STOPWORDS = {
    "a", "an", "and", "the", "or", "but", "to", "for", "of", "with", "my", "i", 
    "you", "he", "she", "it", "they", "we", "in", "on", "at", "by", "from", 
    "about", "as", "into", "like", "through", "after", "before", "during", 
    "without", "under", "over", "is", "are", "was", "were", "be", "been", 
    "have", "has", "had", "do", "does", "did", "can", "could", "should", 
    "would", "will", "shall", "may", "might", "must", "want", "please", "help"
}

_last_notified_prompt_file: str | None = None


def _notify_prompt_loaded(message: str, file_path_str: str) -> None:
    """Notify the user once when a specific prompt template is loaded."""
    global _last_notified_prompt_file
    if _last_notified_prompt_file != file_path_str:
        _last_notified_prompt_file = file_path_str
        # Print a nice styled message to stderr so it's visible but doesn't corrupt stdout
        print(f"\033[94m[OpenHarness] {message}\033[0m", file=sys.stderr, flush=True)


def get_prompt_search_dirs(cwd: str | Path | None = None) -> list[Path]:
    """Get the directories where system prompt templates are stored."""
    dirs = []
    if cwd:
        cwd_path = Path(cwd).resolve()
        dirs.append(cwd_path / "prompts")
        dirs.append(cwd_path / ".openharness" / "prompts")
    else:
        try:
            cwd_path = Path.cwd().resolve()
            dirs.append(cwd_path / "prompts")
            dirs.append(cwd_path / ".openharness" / "prompts")
        except Exception:
            pass
    
    dirs.append(Path("~/.openharness/prompts").expanduser())
    return dirs


def find_prompt_template_by_name(name: str, cwd: str | Path | None = None) -> Path | None:
    """Find a prompt template file by name (e.g. 'my-system' or 'my-system.md')."""
    if not name or len(name) > 150 or "\n" in name:
        return None
        
    p = Path(name).expanduser()
    try:
        if p.is_file():
            return p.resolve()
    except Exception:
        pass
        
    search_dirs = get_prompt_search_dirs(cwd)
    for d in search_dirs:
        if not d.is_dir():
            continue
        for candidate in (name, f"{name}.md", f"{name}.txt"):
            p = d / candidate
            try:
                if p.is_file():
                    return p.resolve()
            except Exception:
                pass
    return None


def list_prompt_templates(cwd: str | Path | None = None) -> list[dict[str, str]]:
    """List all available system prompt templates in the search directories."""
    search_dirs = get_prompt_search_dirs(cwd)
    templates = []
    seen_names = set()
    
    for d in search_dirs:
        if not d.is_dir():
            continue
        try:
            for file_path in d.glob("*"):
                if file_path.suffix not in (".md", ".txt") or file_path.name.startswith("."):
                    continue
                name = file_path.stem
                if name in seen_names:
                    continue
                seen_names.add(name)
                
                desc = ""
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    for line in content.splitlines()[:10]:
                        line_strip = line.strip()
                        if line_strip.startswith("#"):
                            desc = re.sub(r"^#+\s*", "", line_strip)
                            break
                        elif line_strip.lower().startswith("description:"):
                            desc = line_strip[len("description:"):].strip()
                            break
                        elif line_strip.lower().startswith("- description:"):
                            desc = line_strip[len("- description:"):].strip()
                            break
                except Exception:
                    pass
                    
                templates.append({
                    "name": name,
                    "file": file_path.name,
                    "path": str(file_path),
                    "description": desc or "No description provided."
                })
        except Exception:
            pass
            
    return sorted(templates, key=lambda x: x["name"])


def tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase English words and Chinese characters."""
    lowered = text.lower()
    eng_tokens = re.findall(r"[a-z0-9_]+", lowered)
    cjk_chars = [c for c in lowered if "\u4e00" <= c <= "\u9fff"]
    
    tokens = set()
    for tok in eng_tokens:
        if tok not in _ENGLISH_STOPWORDS and len(tok) > 1:
            tokens.add(tok)
    for char in cjk_chars:
        tokens.add(char)
    return tokens


def score_prompt_template(user_prompt_tokens: set[str], file_path: Path) -> int:
    """Score a template file based on token overlap with the user prompt."""
    if not user_prompt_tokens:
        return 0
        
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(2000)
    except Exception:
        return 0
    
    filename_stem = file_path.stem
    filename_tokens = tokenize(filename_stem)
    
    lines = content.splitlines()
    header_tokens = set()
    body_tokens = set()
    
    for line in lines[:15]:
        stripped = line.strip()
        if stripped.startswith("#"):
            header_tokens.update(tokenize(stripped))
        elif ":" in stripped or "-" in stripped:
            header_tokens.update(tokenize(stripped))
        else:
            body_tokens.update(tokenize(stripped))
            
    for line in lines[15:]:
        body_tokens.update(tokenize(line))
        
    score = 0
    for token in user_prompt_tokens:
        if token in filename_tokens:
            score += 10
        elif token in header_tokens:
            score += 5
        elif token in body_tokens:
            score += 2
            
    return score


def find_best_matching_prompt_template(user_prompt: str, cwd: str | Path | None = None, threshold: int = 5) -> Path | None:
    """Analyze the user prompt and return the best matching template path if it exceeds the threshold."""
    if not user_prompt or len(user_prompt.strip()) < 3:
        return None
        
    # Ignore slash commands when auto-matching templates
    if user_prompt.strip().startswith("/"):
        return None
        
    user_tokens = tokenize(user_prompt)
    if not user_tokens:
        return None
        
    search_dirs = get_prompt_search_dirs(cwd)
    best_path = None
    best_score = 0
    
    for d in search_dirs:
        if not d.is_dir():
            continue
        try:
            for file_path in d.glob("*"):
                if file_path.suffix not in (".md", ".txt") or file_path.name.startswith("."):
                    continue
                score = score_prompt_template(user_tokens, file_path)
                if score > best_score:
                    best_score = score
                    best_path = file_path
        except Exception:
            pass
            
    if best_score >= threshold:
        return best_path
    return None
