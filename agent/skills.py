"""
Skill 系统：发现、加载、管理可扩展的能力包。

每个 Skill 是 skills/ 目录下一个包含 skill.md 的子目录。
skill.md 格式：
  ---
  name: skill_name
  description: 一行描述
  ---
  详细指令内容...
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Skill:
    name: str
    description: str
    path: Path
    content: str
    file_path: Path = Path()
    tools: list[str] = field(default_factory=list)
    unavailable_tools: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Frontmatter 解析
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    """解析 skill.md 的 YAML frontmatter，返回 (meta_dict, body)。

    tools 字段保持 list[str] 类型，其余字段转为 str。
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    body = text[m.end():]
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, text
    result: dict[str, str | list[str]] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if k == "tools" and isinstance(v, list):
            result[k] = [str(t) for t in v]
        else:
            result[k] = str(v)
    return result, body


# ---------------------------------------------------------------------------
# Metadata 解析 + 运行时门控
# ---------------------------------------------------------------------------


def _parse_metadata(raw: str | None) -> dict:
    """解析 frontmatter metadata 字段为结构化 dict。

    兼容 JSON 字符串和 YAML 格式。解析失败返回空 dict。
    """
    if not raw:
        return {}
    raw = str(raw).strip()
    if not raw:
        return {}
    # 尝试 JSON（兼容 OpenClaw 格式）
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    # 回退 YAML
    try:
        result = yaml.safe_load(raw)
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError:
        return {}


def _check_runtime_eligibility(metadata: dict) -> tuple[bool, str]:
    """检查 skill 是否满足运行时约束。

    返回 (eligible, reason)。eligible=False 时 reason 说明不满足的原因。
    """
    if not metadata:
        return True, ""

    # OS 门控
    allowed_os = metadata.get("os")
    if allowed_os and isinstance(allowed_os, list):
        if sys.platform not in allowed_os:
            return False, f"不支持当前平台 {sys.platform}（需要: {allowed_os}）"

    requires = metadata.get("requires", {})
    if not isinstance(requires, dict):
        requires = {}

    # bins 门控：所有列出的二进制必须存在
    required_bins = requires.get("bins", [])
    if required_bins and isinstance(required_bins, list):
        missing = [b for b in required_bins if not shutil.which(str(b))]
        if missing:
            return False, f"缺少必要工具: {missing}"

    # anyBins 门控：至少一个存在
    any_bins = requires.get("anyBins", [])
    if any_bins and isinstance(any_bins, list):
        if not any(shutil.which(str(b)) for b in any_bins):
            return False, f"以下工具至少需要一个，但均未找到: {any_bins}"

    # env 门控：环境变量必须存在
    required_env = requires.get("env", [])
    if required_env and isinstance(required_env, list):
        missing_env = [e for e in required_env if not os.environ.get(str(e))]
        if missing_env:
            return False, f"缺少环境变量: {missing_env}"

    return True, ""


# ---------------------------------------------------------------------------
# SkillManager
# ---------------------------------------------------------------------------

class SkillManager:
    def __init__(self, skills_dir: Path) -> None:
        self._dir = skills_dir
        self._skills: list[Skill] = []
        self._skills_dict: dict[str, Skill] = {}

    _SKIP_DIRS = {"examples", "templates"}

    def discover(self, available_tools: set[str] | None = None) -> list[Skill]:
        """递归扫描 skills/ 目录，返回所有已发现的 Skill。跳过 examples/templates 子目录。

        Args:
            available_tools: 当前可用的工具名集合。传入时会校验 skill 声明的 tools，
                过滤掉不存在的工具并记录到 unavailable_tools。
        """
        self._skills.clear()
        self._skills_dict.clear()
        if not self._dir.is_dir():
            return self._skills

        seen_parents: set[Path] = set()
        for f in sorted(self._dir.rglob("*")):
            if not (f.is_file() and f.name.lower() == "skill.md"):
                continue
            if f.parent in seen_parents:
                continue
            # 跳过 examples/templates 等子目录中的 skill
            if any(part.lower() in self._SKIP_DIRS for part in f.relative_to(self._dir).parts[:-1]):
                continue
            seen_parents.add(f.parent)
            skill = _load_skill(f)
            # 运行时门控
            eligible, reason = _check_runtime_eligibility(skill.metadata)
            if not eligible:
                warnings.warn(
                    f"Skill '{skill.name}' 不满足运行时约束，已跳过：{reason}",
                    stacklevel=2,
                )
                continue
            if available_tools is not None and skill.tools:
                unavailable = [t for t in skill.tools if t not in available_tools]
                if unavailable:
                    skill.unavailable_tools = unavailable
                    skill.tools = [t for t in skill.tools if t in available_tools]
                    warnings.warn(
                        f"Skill '{skill.name}' 声明了不可用的工具：{unavailable}",
                        stacklevel=2,
                    )
            self._add_skill(skill)

        return self._skills

    def _add_skill(self, skill: Skill) -> None:
        """添加 skill，遇到重复名称时发出警告并跳过。"""
        if skill.name in self._skills_dict:
            existing = self._skills_dict[skill.name]
            warnings.warn(
                f"发现重复 Skill 名称 '{skill.name}'："
                f"{skill.path} 与已有 {existing.path} 冲突，已跳过",
                stacklevel=3,
            )
            return
        self._skills.append(skill)
        self._skills_dict[skill.name] = skill

    @property
    def skills(self) -> list[Skill]:
        return self._skills

    def get_skill(self, name: str) -> Skill | None:
        return self._skills_dict.get(name)

    def get_skill_summaries(self, max_desc_len: int = 100) -> str:
        """返回所有 Skill 的摘要文本，用于注入 LLM 提示词。描述过长时截断。"""
        if not self._skills:
            return "(无可用 Skill)"
        lines = []
        for s in self._skills:
            desc = s.description or "(无描述)"
            # 合并多行描述为单行
            desc = " ".join(desc.split())
            if len(desc) > max_desc_len:
                desc = desc[:max_desc_len].rsplit("，", 1)[0].rstrip() + "…"
            tool_hint = ""
            if s.tools:
                tool_hint = f" [工具: {', '.join(s.tools)}]"
            lines.append(f"- {s.name}: {desc}{tool_hint}")
        return "\n".join(lines)

    def format_skills_catalog(
        self,
        max_desc_len: int = 100,
        max_skills: int = 50,
        max_chars: int = 10000,
    ) -> str:
        """生成 XML 格式的 skill 目录，用于注入 system prompt。

        三级预算控制：
        1. 完整格式（name + description + tools + location）
        2. 精简格式（name + location，砍描述和工具）
        3. 截断（二分搜索最大可用前缀）

        Args:
            max_desc_len: 描述最大字符数
            max_skills: 目录最多包含多少个 skill
            max_chars: 目录最大字符数
        """
        if not self._skills:
            return ""

        def _escape(s: str) -> str:
            return (s.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace('"', "&quot;"))

        def _format_full(skills: list[Skill]) -> str:
            lines = [
                "以下是可用的 Skill。当任务匹配某个 Skill 的描述时，使用 read_file 工具加载其文件获取详细指令。",
                "",
                "<available_skills>",
            ]
            for s in skills:
                desc = s.description or "(无描述)"
                desc = " ".join(desc.split())
                if len(desc) > max_desc_len:
                    desc = desc[:max_desc_len].rsplit("，", 1)[0].rstrip() + "…"
                lines.append("  <skill>")
                lines.append(f"    <name>{_escape(s.name)}</name>")
                lines.append(f"    <description>{_escape(desc)}</description>")
                if s.tools:
                    lines.append(f"    <tools>{_escape(', '.join(s.tools))}</tools>")
                lines.append(f"    <location>{_escape(str(s.file_path))}</location>")
                lines.append("  </skill>")
            lines.append("</available_skills>")
            return "\n".join(lines)

        def _format_compact(skills: list[Skill]) -> str:
            lines = [
                "以下是可用的 Skill。当任务匹配某个 Skill 名称时，使用 read_file 工具加载其文件获取详细指令。",
                "",
                "<available_skills>",
            ]
            for s in skills:
                lines.append("  <skill>")
                lines.append(f"    <name>{_escape(s.name)}</name>")
                lines.append(f"    <location>{_escape(str(s.file_path))}</location>")
                lines.append("  </skill>")
            lines.append("</available_skills>")
            return "\n".join(lines)

        # 第一级：按数量截断
        skills_pool = self._skills[:max_skills]
        truncated = len(self._skills) > max_skills

        # 第二级：完整格式是否超预算
        full_text = _format_full(skills_pool)
        if len(full_text) <= max_chars:
            return full_text

        # 第三级：精简格式
        compact_text = _format_compact(skills_pool)
        if len(compact_text) <= max_chars:
            return "⚠️ Skill 目录使用精简格式（描述已省略）。\n" + compact_text

        # 第四级：二分搜索最大可用前缀
        lo, hi = 0, len(skills_pool)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(_format_compact(skills_pool[:mid])) <= max_chars:
                lo = mid
            else:
                hi = mid - 1

        if lo == 0:
            return "⚠️ Skill 目录过大，无法注入。请减少 skill 数量或增加 max_prompt_chars 配置。"

        truncated = True
        result = _format_compact(skills_pool[:lo])
        return f"⚠️ Skill 目录已截断：包含 {lo}/{len(self._skills)} 个 skill（精简格式）。\n" + result


def _load_skill(skill_md_path: Path) -> Skill:
    """从 skill.md 加载一个 Skill。"""
    text = skill_md_path.read_text(encoding="utf-8")
    meta, _ = _parse_frontmatter(text)
    name = meta.get("name", skill_md_path.parent.name)
    description = meta.get("description", "")
    raw_tools = meta.get("tools", [])
    tools = raw_tools if isinstance(raw_tools, list) else []
    metadata = _parse_metadata(meta.get("metadata"))
    return Skill(
        name=name,
        description=description,
        path=skill_md_path.parent,
        content=text,
        file_path=skill_md_path,
        tools=tools,
        metadata=metadata,
    )
