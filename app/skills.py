"""技能库：SKILL.md frontmatter + 关键词路由。见说明书第 9 章。

阶段 3：启动时只加载索引（name/description/trigger_keywords），
命中后再读正文注入，避免上下文爆炸。
"""
import yaml
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_skill_index: list[dict] = []


def load_skill_index() -> list[dict]:
    """扫描技能目录，解析 frontmatter，返回索引清单（含 body，但不展开）。"""
    global _skill_index
    if _skill_index:
        return _skill_index
    index = []
    if SKILLS_DIR.exists():
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                meta = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
                meta["path"] = str(skill_md)
                index.append(meta)
            except Exception:
                continue
    _skill_index = index
    return index


def _parse_frontmatter(text: str) -> dict:
    """解析 SKILL.md 的 YAML frontmatter，返回 meta（含 body）。"""
    if not text.startswith("---"):
        return {"name": "unknown", "description": "", "trigger_keywords": [], "body": text}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"name": "unknown", "description": "", "trigger_keywords": [], "body": text}
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    meta["body"] = parts[2].strip()
    meta.setdefault("name", "unknown")
    meta.setdefault("description", "")
    meta.setdefault("trigger_keywords", [])
    return meta


def _match_keyword(keyword: str, query: str) -> bool:
    """关键词匹配：先子串；纯中文关键词再尝试顺序字符匹配。

    顺序字符匹配覆盖「审查代码」vs「审查一下这段代码」这类非连续情况。
    """
    if keyword in query:
        return True
    if len(keyword) >= 2 and all("\u4e00" <= ch <= "\u9fff" for ch in keyword):
        pos = 0
        for ch in keyword:
            idx = query.find(ch, pos)
            if idx == -1:
                return False
            pos = idx + 1
        return True
    return False


def route_skills(query: str, index: list[dict] | None = None, max_skills: int = 2) -> list[dict]:
    """关键词粗筛：返回 trigger_keywords 命中的候选技能（最多 max_skills 个）。"""
    index = index if index is not None else load_skill_index()
    q = query.lower()
    matched = []
    for skill in index:
        keywords = skill.get("trigger_keywords", [])
        if any(kw and _match_keyword(kw.lower(), q) for kw in keywords):
            matched.append(skill)
    return matched[:max_skills]


def render_skills(skills: list[dict]) -> str:
    """把命中的技能渲染成注入 prompt 的文本。"""
    if not skills:
        return ""
    parts = []
    for s in skills:
        parts.append(f"## 技能：{s['name']}\n{s.get('description', '')}\n\n{s.get('body', '')}")
    return "\n\n【本次任务相关的技能说明】\n" + "\n\n---\n\n".join(parts)
