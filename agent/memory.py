"""
长期记忆管理。

MEMORY.md 格式：
  # 长期记忆

  ## 用户偏好
  - 偏好使用中文交流
  - 喜欢简洁的回答

  ## 项目约束
  - 所有 API 调用必须设置超时
"""

from __future__ import annotations

import re
from pathlib import Path


class MemoryManager:
    def __init__(self, memory_path: Path) -> None:
        self._path = memory_path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> str:
        """读取 MEMORY.md 全部内容。文件不存在时返回空字符串。"""
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8")

    def save(self, content: str) -> None:
        """覆盖写入 MEMORY.md。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(content, encoding="utf-8")

    def append(self, category: str, item: str) -> None:
        """向指定分类追加一条记忆。分类不存在时自动创建（追加到末尾）。"""
        content = self.load()

        if not content.strip():
            # 文件为空，创建初始结构
            content = f"# 长期记忆\n\n## {category}\n- {item}\n"
            self.save(content)
            return

        # 查找分类标题
        pattern = re.compile(r"^(## " + re.escape(category) + r")\s*$", re.MULTILINE)
        match = pattern.search(content)

        if match:
            # 分类存在，在该分类的最后一条记忆之后插入
            # 找到该分类下的所有条目末尾
            after_match = content[match.end():]
            # 找下一个 ## 标题或文件末尾
            next_section = re.search(r"^## ", after_match, re.MULTILINE)
            if next_section:
                insert_pos = match.end() + next_section.start()
                # 在下一个标题前插入
                new_content = content[:insert_pos].rstrip("\n") + f"\n- {item}\n" + content[insert_pos:]
            else:
                # 文件末尾
                new_content = content.rstrip("\n") + f"\n- {item}\n"
            self.save(new_content)
        else:
            # 分类不存在，追加到文件末尾
            new_content = content.rstrip("\n") + f"\n\n## {category}\n- {item}\n"
            self.save(new_content)

    def get_all(self) -> dict[str, list[str]]:
        """解析 MEMORY.md，返回 {分类: [记忆条目]} 字典。"""
        content = self.load()
        if not content.strip():
            return {}

        result: dict[str, list[str]] = {}
        current_category: str | None = None

        for line in content.splitlines():
            # 匹配 ## 分类标题
            cat_match = re.match(r"^## (.+)$", line)
            if cat_match:
                current_category = cat_match.group(1).strip()
                if current_category not in result:
                    result[current_category] = []
                continue

            # 匹配 - 条目
            item_match = re.match(r"^- (.+)$", line)
            if item_match and current_category is not None:
                result[current_category].append(item_match.group(1).strip())

        return result


def check_trigger_words(user_input: str, trigger_words: list[str]) -> bool:
    """检测用户输入是否包含触发关键词。"""
    lower_input = user_input.lower()
    for word in trigger_words:
        if word.lower() in lower_input:
            return True
    return False
