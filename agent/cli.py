"""
交互式 CLI：REPL 主循环。

功能：
- rich 美化输出（Panel 聊天框、Markdown 渲染、语法高亮）
- 斜杠命令（/help /exit /session /history /clear /tools /cd /config /chat /model）
- readline 历史（跨会话持久化）
- 流式输出最终回答
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Windows 启用 ANSI 转义码支持
if sys.platform == "win32":
    os.system("")
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich import box

from .config import AgentConfig
from .loop import AgentLoop, ToolCallEvent, ToolResultEvent
from .memory import MemoryManager, check_trigger_words
from .session import Session, SessionManager
from .skills import SkillManager
from .tools import TOOL_REGISTRY

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Rich Console
# ---------------------------------------------------------------------------

_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "dim": "dim",
    "bot": "bold cyan",
    "user": "bold white",
})

console = Console(theme=_theme)

# ---------------------------------------------------------------------------
# 斜杠命令列表（补全 + readline 共用单一数据源）
# ---------------------------------------------------------------------------

SLASH_COMMANDS = [
    "/help", "/exit", "/quit", "/chat",
    "/session new", "/session list", "/session load ",
    "/session info", "/session delete ",
    "/history", "/clear", "/tools", "/config", "/model",
    "/memory", "/memory clear", "/memory edit",
    "/memory stats", "/memory search ", "/memory extract",
    "/memory today", "/memory day ",
    "/mcp", "/mcp tools",
    "/skills", "/skills reload",
    "/think", "/cd",
]


def _find_slash_matches(chars: list[str]) -> list[str]:
    """返回当前输入匹配的所有斜杠命令列表。"""
    text = "".join(chars)
    if not text:
        return []
    return [c for c in SLASH_COMMANDS if c.startswith(text) and c != text]


# ---------------------------------------------------------------------------
# readline 历史
# ---------------------------------------------------------------------------


def _setup_readline(history_path: Path) -> None:
    try:
        import readline as rl
        history_path.parent.mkdir(parents=True, exist_ok=True)
        if history_path.exists():
            rl.read_history_file(str(history_path))
        rl.set_history_length(1000)

        def completer(text: str, state: int) -> str | None:
            options = [c for c in SLASH_COMMANDS if c.startswith(text)]
            return options[state] if state < len(options) else None

        rl.set_completer(completer)
        rl.parse_and_bind("tab: complete")

        import atexit
        atexit.register(rl.write_history_file, str(history_path))
    except (ImportError, OSError):
        pass


# ---------------------------------------------------------------------------
# 逐字符输入（输入时显示，回车后清除）
# ---------------------------------------------------------------------------


def _read_line(prompt: str = "> ") -> str | None:
    """
    逐字符读取一行输入。
    - 输入时实时回显字符
    - 回车后清除当前行
    - 返回输入内容，Ctrl+C 返回 None，Ctrl+D 抛出 EOFError
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()

    if sys.platform == "win32":
        return _read_line_win()
    else:
        return _read_line_unix()


def _char_width(ch: str) -> int:
    """返回字符的显示宽度（中文/全角=2，其他=1）。"""
    import unicodedata
    eaw = unicodedata.east_asian_width(ch)
    return 2 if eaw in ("W", "F") else 1


def _str_width(s: str) -> int:
    """返回字符串的显示宽度。"""
    return sum(_char_width(c) for c in s)


def _redraw_line(prompt: str, chars: list[str], cursor_pos: int, hint: str = "") -> None:
    """重绘整行：清除当前行，显示 prompt + 内容 + 灰色 hint，光标定位到 cursor_pos。"""
    hint_part = f"\033[2;36m{hint}\033[0m" if hint else ""
    sys.stdout.write(f"\r\033[K{prompt}{''.join(chars)}{hint_part}")
    tail_width = sum(_char_width(c) for c in chars[cursor_pos:]) + _str_width(hint)
    if tail_width > 0:
        sys.stdout.write(f"\033[{tail_width}D")
    sys.stdout.flush()


def _redraw_all(prompt: str, chars: list[str], cursor_pos: int,
                matches: list[str] | None = None, menu_idx: int = -1,
                old_menu_lines: int = 0) -> int:
    """重绘输入行 + 候选菜单，返回菜单占用行数。"""
    new_menu_lines = len(matches) if matches and len(matches) >= 2 else 0
    if old_menu_lines > 0:
        sys.stdout.write(f"\033[{old_menu_lines}A")
    sys.stdout.write(f"\r\033[J")
    # 输入行 + 内联提示（只显示后缀）
    cur_len = len("".join(chars))
    full_match = matches[menu_idx] if matches and 0 <= menu_idx < len(matches) else ""
    hint = full_match[cur_len:] if full_match else ""
    hint_part = f"\033[2;36m{hint}\033[0m" if hint else ""
    sys.stdout.write(f"{prompt}{''.join(chars)}{hint_part}")
    tail_width = sum(_char_width(c) for c in chars[cursor_pos:]) + _str_width(hint)
    if tail_width > 0:
        sys.stdout.write(f"\033[{tail_width}D")
    # 竖排菜单
    if new_menu_lines:
        for i, m in enumerate(matches):
            name = m.rstrip()
            if i == menu_idx:
                sys.stdout.write(f"\n\033[1;36m> {name}\033[0m")
            else:
                sys.stdout.write(f"\n  {name}")
        sys.stdout.write(f"\033[{new_menu_lines}A")
    sys.stdout.flush()
    return new_menu_lines


def _read_line_win() -> str | None:
    """Windows: 使用 msvcrt 逐字符读取。"""
    import msvcrt

    prompt = "> "
    chars: list[str] = []
    cursor_pos = 0
    menu_matches: list[str] | None = None
    menu_idx = -1
    menu_lines = 0

    while True:
        ch = msvcrt.getwch()

        if ch in ("\r", "\n"):  # 回车
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            return "".join(chars)

        elif ch == "\x03":  # Ctrl+C
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            raise KeyboardInterrupt

        elif ch == "\x04":  # Ctrl+D
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            raise EOFError

        elif ch in ("\x08", "\x7f"):  # 退格
            if cursor_pos > 0:
                chars.pop(cursor_pos - 1)
                cursor_pos -= 1
                if cursor_pos == len(chars) and "".join(chars).startswith("/"):
                    matches = _find_slash_matches(chars)
                    hint_idx = 0 if matches else -1
                else:
                    matches = None
                    hint_idx = -1
                menu_lines = _redraw_all(prompt, chars, cursor_pos, matches, hint_idx, menu_lines)
                menu_matches = matches
                menu_idx = hint_idx

        elif ch == "\t":  # Tab — 确认选中项
            if menu_matches and menu_idx >= 0 and cursor_pos == len(chars):
                chars[:] = list(menu_matches[menu_idx])
                cursor_pos = len(chars)
                menu_lines = _redraw_all(prompt, chars, cursor_pos, None, -1, menu_lines)
                menu_matches = None
                menu_idx = -1

        elif ch == "\xe0":  # 扩展键前缀
            ch2 = msvcrt.getwch()
            if ch2 == "H":  # 上箭头
                if menu_matches and len(menu_matches) >= 2:
                    menu_idx = (menu_idx - 1) % len(menu_matches)
                    menu_lines = _redraw_all(prompt, chars, cursor_pos, menu_matches, menu_idx, menu_lines)
            elif ch2 == "P":  # 下箭头
                if menu_matches and len(menu_matches) >= 2:
                    menu_idx = (menu_idx + 1) % len(menu_matches)
                    menu_lines = _redraw_all(prompt, chars, cursor_pos, menu_matches, menu_idx, menu_lines)
            elif ch2 == "K":  # 左箭头
                if cursor_pos > 0:
                    cursor_pos -= 1
                    width = _char_width(chars[cursor_pos])
                    sys.stdout.write(f"\033[{width}D")
                    sys.stdout.flush()
                    menu_lines = _redraw_all(prompt, chars, cursor_pos, None, -1, menu_lines)
                    menu_matches = None
                    menu_idx = -1
            elif ch2 == "M":  # 右箭头
                if cursor_pos < len(chars):
                    width = _char_width(chars[cursor_pos])
                    cursor_pos += 1
                    sys.stdout.write(f"\033[{width}C")
                    sys.stdout.flush()
                    if cursor_pos == len(chars) and "".join(chars).startswith("/"):
                        matches = _find_slash_matches(chars)
                        hint_idx = 0 if matches else -1
                    else:
                        matches = None
                        hint_idx = -1
                    menu_lines = _redraw_all(prompt, chars, cursor_pos, matches, hint_idx, menu_lines)
                    menu_matches = matches
                    menu_idx = hint_idx

        else:
            chars.insert(cursor_pos, ch)
            cursor_pos += 1
            if cursor_pos == len(chars) and "".join(chars).startswith("/"):
                matches = _find_slash_matches(chars)
                hint_idx = 0 if matches else -1
            else:
                matches = None
                hint_idx = -1
            menu_lines = _redraw_all(prompt, chars, cursor_pos, matches, hint_idx, menu_lines)
            menu_matches = matches
            menu_idx = hint_idx


def _read_line_unix() -> str | None:
    """Unix: 使用 tty/termios 逐字符读取。"""
    import tty
    import termios

    prompt = "> "
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        chars: list[str] = []
        cursor_pos = 0
        menu_matches: list[str] | None = None
        menu_idx = -1
        menu_lines = 0

        while True:
            ch = sys.stdin.read(1)

            if ch in ("\r", "\n"):  # 回车
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                return "".join(chars)

            elif ch == "\x03":  # Ctrl+C
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                raise KeyboardInterrupt

            elif ch == "\x04":  # Ctrl+D
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                raise EOFError

            elif ch in ("\x7f", "\x08"):  # 退格
                if cursor_pos > 0:
                    chars.pop(cursor_pos - 1)
                    cursor_pos -= 1
                    if cursor_pos == len(chars) and "".join(chars).startswith("/"):
                        matches = _find_slash_matches(chars)
                        hint_idx = 0 if matches else -1
                    else:
                        matches = None
                        hint_idx = -1
                    menu_lines = _redraw_all(prompt, chars, cursor_pos, matches, hint_idx, menu_lines)
                    menu_matches = matches
                    menu_idx = hint_idx

            elif ch == "\t":  # Tab — 确认选中项
                if menu_matches and menu_idx >= 0 and cursor_pos == len(chars):
                    chars[:] = list(menu_matches[menu_idx])
                    cursor_pos = len(chars)
                    menu_lines = _redraw_all(prompt, chars, cursor_pos, None, -1, menu_lines)
                    menu_matches = None
                    menu_idx = -1

            elif ch == "\x1b":  # 转义序列
                seq = sys.stdin.read(2)
                if seq == "[A":  # 上箭头
                    if menu_matches and len(menu_matches) >= 2:
                        menu_idx = (menu_idx - 1) % len(menu_matches)
                        menu_lines = _redraw_all(prompt, chars, cursor_pos, menu_matches, menu_idx, menu_lines)
                elif seq == "[B":  # 下箭头
                    if menu_matches and len(menu_matches) >= 2:
                        menu_idx = (menu_idx + 1) % len(menu_matches)
                        menu_lines = _redraw_all(prompt, chars, cursor_pos, menu_matches, menu_idx, menu_lines)
                elif seq == "[C":  # 右箭头
                    if cursor_pos < len(chars):
                        width = _char_width(chars[cursor_pos])
                        cursor_pos += 1
                        sys.stdout.write(f"\033[{width}C")
                        sys.stdout.flush()
                        if cursor_pos == len(chars) and "".join(chars).startswith("/"):
                            matches = _find_slash_matches(chars)
                            hint_idx = 0 if matches else -1
                        else:
                            matches = None
                            hint_idx = -1
                        menu_lines = _redraw_all(prompt, chars, cursor_pos, matches, hint_idx, menu_lines)
                        menu_matches = matches
                        menu_idx = hint_idx
                elif seq == "[D":  # 左箭头
                    if cursor_pos > 0:
                        cursor_pos -= 1
                        width = _char_width(chars[cursor_pos])
                        sys.stdout.write(f"\033[{width}D")
                        sys.stdout.flush()
                        menu_lines = _redraw_all(prompt, chars, cursor_pos, None, -1, menu_lines)
                        menu_matches = None
                        menu_idx = -1

            else:
                chars.insert(cursor_pos, ch)
                cursor_pos += 1
                if cursor_pos == len(chars) and "".join(chars).startswith("/"):
                    matches = _find_slash_matches(chars)
                    hint_idx = 0 if matches else -1
                else:
                    matches = None
                    hint_idx = -1
                menu_lines = _redraw_all(prompt, chars, cursor_pos, matches, hint_idx, menu_lines)
                menu_matches = matches
                menu_idx = hint_idx
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ---------------------------------------------------------------------------
# CLI 主类
# ---------------------------------------------------------------------------

VERSION = "0.3.2"
BOT_NAME = "南北绿豆"

HELP_TEXT = """\
[bold]可用命令：[/bold]

  [cyan]/help[/cyan]                显示此帮助
  [cyan]/exit[/cyan], [cyan]/quit[/cyan]         退出程序
  [cyan]/chat[/cyan]                进入多行聊天框模式（/send 发送，/cancel 取消）
  [cyan]/session new[/cyan]         创建新 Session
  [cyan]/session list[/cyan]        列出所有 Session
  [cyan]/session load[/cyan] <id>   切换到指定 Session
  [cyan]/session info[/cyan]        显示当前 Session 信息
  [cyan]/session delete[/cyan] <id> 删除指定 Session
  [cyan]/history[/cyan]             显示当前对话历史（摘要）
  [cyan]/clear[/cyan]               清空当前对话历史（不删除文件）
  [cyan]/tools[/cyan]               列出所有可用工具
  [cyan]/skills[/cyan]              列出所有可用 Skill
  [cyan]/skills reload[/cyan]       重新扫描 Skill 目录
  [cyan]/memory[/cyan]              显示当前长期记忆
  [cyan]/memory clear[/cyan]        清空长期记忆（需确认）
  [cyan]/memory edit[/cyan]         用外部编辑器打开 MEMORY.md
  [cyan]/memory stats[/cyan]        显示 observation 统计
  [cyan]/memory search[/cyan] <q>   搜索历史记忆
  [cyan]/memory extract[/cyan]      手动提取当前 session 记忆
  [cyan]/memory today[/cyan]        显示今天的每日记忆
  [cyan]/memory day[/cyan] <date>   显示指定日期的记忆
  [cyan]/config[/cyan]              显示当前配置
  [cyan]/model[/cyan]               查看/切换模型（/model <编号或名称>）
  [cyan]/think[/cyan]               切换思考过程显示/隐藏
  [cyan]/cd[/cyan] <path>           切换工作目录
  [cyan]/mcp[/cyan]                查看 MCP Server 状态和工具列表

[dim]直接输入内容即向 Agent 发送消息。
按 Ctrl+C 或 Ctrl+D 退出。[/dim]"""


class CLI:
    def __init__(
        self,
        config: AgentConfig,
        session: Session,
        session_mgr: SessionManager,
        skill_manager: SkillManager | None = None,
        memory_manager: MemoryManager | None = None,
        memory_search: Any | None = None,
        extractor: Any | None = None,
        observation_store: Any | None = None,
        mcp_manager: Any | None = None,
        orchestrator: Any | None = None,
    ) -> None:
        self._config = config
        self._session = session
        self._session_mgr = session_mgr
        self._skill_manager = skill_manager
        self._memory_manager = memory_manager
        self._memory_search = memory_search
        self._extractor = extractor
        self._observation_store = observation_store
        self._mcp_manager = mcp_manager
        self._orchestrator = orchestrator
        self._loop: AgentLoop | None = None
        self._running = True
        self._show_thinking = True

    def _reset_loop(self) -> None:
        """Session 切换后重建 loop。"""
        from .llm import LLMClient
        llm = LLMClient(self._config.llm)
        self._loop = AgentLoop(
            self._config, self._session, llm,
            self._skill_manager, self._memory_manager, self._memory_search,
            self._mcp_manager,
        )
        if self._orchestrator:
            self._loop.tool_ctx.orchestrator = self._orchestrator

    def run(self) -> None:
        """进入交互式 REPL。"""
        history_path = self._config.resolved_session_dir() / ".input_history"
        _setup_readline(history_path)
        self._reset_loop()

        self._print_banner()

        while self._running:
            try:
                # 显示后台待处理消息（MCP 连接完成等）
                self._flush_pending_messages()
                # 逐字符读取，输入时显示，回车后清除
                prompt = "🔍> " if self._show_thinking else "> "
                user_input = _read_line(prompt)
                if user_input is None:
                    continue
                user_input = user_input.strip()
            except KeyboardInterrupt:
                console.print()
                self._sys_print("按 Ctrl+D 退出，或输入 /exit")
                continue
            except EOFError:
                console.print()
                try:
                    self._on_session_end()
                except Exception:
                    pass
                self._sys_print("再见！")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                self._handle_slash(user_input)
            else:
                self._handle_message(user_input)

    # ------------------------------------------------------------------
    # 斜杠命令处理
    # ------------------------------------------------------------------

    def _handle_slash(self, cmd: str) -> None:
        parts = cmd.split(maxsplit=2)
        verb = parts[0].lower()

        if verb in ("/exit", "/quit"):
            self._on_session_end()
            self._sys_print("再见！")
            self._running = False

        elif verb == "/help":
            console.print(Panel(HELP_TEXT, title="帮助", border_style="cyan", box=box.ROUNDED))

        elif verb == "/session":
            self._handle_session_cmd(parts[1:] if len(parts) > 1 else [])

        elif verb == "/history":
            self._print_history()

        elif verb == "/clear":
            self._clear_history()

        elif verb == "/tools":
            self._print_tools()

        elif verb == "/skills":
            self._handle_skills_cmd(parts[1:] if len(parts) > 1 else [])

        elif verb == "/memory":
            self._handle_memory_cmd(parts[1:] if len(parts) > 1 else [])

        elif verb == "/config":
            self._print_config()

        elif verb == "/model":
            self._handle_model_cmd(parts[1] if len(parts) > 1 else None)

        elif verb == "/chat":
            self._enter_chat_box()

        elif verb == "/think":
            self._show_thinking = not self._show_thinking
            status = "显示" if self._show_thinking else "隐藏"
            self._sys_print(f"思考过程已设为{status}")

        elif verb == "/mcp":
            self._handle_mcp_cmd(parts[1:] if len(parts) > 1 else [])

        elif verb == "/cd":
            if len(parts) < 2:
                self._err_print("用法：/cd <路径>")
            else:
                self._change_dir(parts[1])

        else:
            self._err_print(f"未知命令：{verb}（输入 /help 查看可用命令）")

    def _handle_session_cmd(self, args: list[str]) -> None:
        if not args:
            self._err_print("用法：/session new | list | load <id> | info | delete <id>")
            return

        sub = args[0].lower()

        if sub == "new":
            self._new_session()
        elif sub == "list":
            self._list_sessions()
        elif sub == "load":
            if len(args) < 2:
                self._err_print("用法：/session load <session-id>")
            else:
                self._load_session(args[1])
        elif sub == "info":
            self._session_info()
        elif sub == "delete":
            if len(args) < 2:
                self._err_print("用法：/session delete <session-id>")
            else:
                self._delete_session(args[1])
        else:
            self._err_print(f"未知 session 子命令：{sub}")

    def _save_model_to_config(self) -> None:
        """将当前模型选择写回 config.yaml 和 .env，使其成为下次启动的默认模型。"""
        import yaml
        cfg_path = self._config.config_path
        if not cfg_path.exists():
            return
        try:
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            llm_data = data.setdefault("llm", {})
            llm_data["model"] = self._config.llm.model
            llm_data["provider"] = self._config.llm.provider
            llm_data["base_url"] = self._config.llm.base_url
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception as e:
            self._err_print(f"写入配置文件失败：{e}")
            return

        # 同步更新 .env（环境变量优先级高于 config.yaml，不更新则重启后会被覆盖）
        env_path = self._config.project_root / ".env"
        if not env_path.exists():
            return
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
            updates = {
                "AGENT_MODEL": self._config.llm.model,
                "AGENT_BASE_URL": self._config.llm.base_url,
                "AGENT_API_KEY": self._config.llm.api_key,
            }
            changed_keys = set(updates.keys())
            new_lines: list[str] = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#") or "=" not in stripped:
                    new_lines.append(line)
                    continue
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}\n")
                    changed_keys.discard(key)
                else:
                    new_lines.append(line)
            # 追加 .env 中原本没有的 key
            for key in changed_keys:
                new_lines.append(f"{key}={updates[key]}\n")
            env_path.write_text("".join(new_lines), encoding="utf-8")
        except Exception as e:
            self._err_print(f"写入 .env 失败：{e}")

    def _handle_model_cmd(self, arg: str | None) -> None:
        """处理 /model 命令：显示或切换模型。"""
        from .config import ModelPreset

        models = self._config.llm.models
        current = self._config.llm.model

        # 无参数：显示当前模型和可选列表
        if arg is None:
            table = Table(title="模型选择", box=box.SIMPLE_HEAVY, show_lines=False)
            table.add_column("编号", style="cyan", no_wrap=True)
            table.add_column("模型", style="bold")
            table.add_column("Provider")
            table.add_column("状态")

            for i, m in enumerate(models, 1):
                status = "[green]当前[/green]" if m.name == current else ""
                table.add_row(str(i), m.name, m.provider or "-", status)

            console.print(table)
            if models:
                self._sys_print("用法：/model <编号或名称> 切换模型，也可直接输入自定义模型名")
            else:
                self._sys_print("未配置预设模型。用法：/model <模型名> 直接切换")
            return

        # 有参数：尝试切换
        target = arg.strip()

        # 先按编号匹配
        preset: ModelPreset | None = None
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(models):
                preset = models[idx]
            else:
                self._err_print(f"编号超出范围（1-{len(models)}）")
                return

        # 再按名称匹配
        if preset is None:
            for m in models:
                if m.name == target:
                    preset = m
                    break

        if preset:
            self._config.llm.model = preset.name
            if preset.provider:
                self._config.llm.provider = preset.provider
            if preset.base_url:
                self._config.llm.base_url = preset.base_url
            if preset.api_key:
                self._config.llm.api_key = preset.api_key
            self._reset_loop()
            self._save_model_to_config()
            self._sys_print(f"已切换到模型：{preset.name}（provider={self._config.llm.provider}）")
        else:
            # 自定义模型名，只改 model
            self._config.llm.model = target
            self._reset_loop()
            self._save_model_to_config()
            self._sys_print(f"已切换到模型：{target}（provider 和 base_url 未变）")

    # ------------------------------------------------------------------
    # Agent 消息处理
    # ------------------------------------------------------------------

    def _handle_message(self, user_input: str) -> None:
        console.print()

        # 触发词检测
        if self._memory_manager and self._config.memory.enabled:
            if check_trigger_words(user_input, self._config.memory.trigger_words):
                user_input += "\n\n[系统提示] 用户希望记住某些信息，请使用 write_memory 工具将其保存到长期记忆。"

        # 显示用户消息（聊天框）
        console.print(Panel(
            user_input,
            title="[bold]You[/bold]",
            title_align="left",
            border_style="white",
            box=box.ROUNDED,
            padding=(0, 1),
        ))

        content_parts: list[str] = []
        try:
            if self._show_thinking:
                # 流式输出模式：实时显示思考过程 + 逐 token 输出
                sys.stdout.write("\033[s")
                sys.stdout.flush()

                for label, token in self._loop.stream_run(
                    user_input,
                    on_tool_call=self._on_tool_call,
                    on_tool_result=self._on_tool_result,
                ):
                    if label == "reasoning":
                        sys.stdout.write(f"\033[2;36m{token}\033[0m")
                    else:
                        sys.stdout.write(token)
                    sys.stdout.flush()
                    content_parts.append(token)
                sys.stdout.write("\n")
                sys.stdout.flush()

                # 流式输出完成后，用 Panel 重新渲染最终回答
                answer = "".join(content_parts).strip()
                if answer:
                    sys.stdout.write("\033[u\033[J")
                    sys.stdout.flush()

                    md = Markdown(answer)
                    console.print(Panel(
                        md,
                        title=f"[bold cyan]{BOT_NAME}[/bold cyan]",
                        title_align="left",
                        border_style="cyan",
                        box=box.ROUNDED,
                        padding=(0, 1),
                    ))
            else:
                # 简洁模式：spinner + 完整回答 Panel
                with console.status(f"[bold cyan]{BOT_NAME} 思考中...[/bold cyan]", spinner="dots"):
                    for label, token in self._loop.stream_run(
                        user_input,
                        on_tool_call=self._on_tool_call,
                        on_tool_result=self._on_tool_result,
                    ):
                        content_parts.append(token)

                # 渲染完整回答（Markdown）
                answer = "".join(content_parts).strip()
                if answer:
                    md = Markdown(answer)
                    console.print(Panel(
                        md,
                        title=f"[bold cyan]{BOT_NAME}[/bold cyan]",
                        title_align="left",
                        border_style="cyan",
                        box=box.ROUNDED,
                        padding=(0, 1),
                    ))

        except KeyboardInterrupt:
            console.print()
            partial = "".join(content_parts).strip()
            if partial:
                console.print(Panel(
                    Markdown(partial),
                    title=f"[bold cyan]{BOT_NAME}[/bold cyan] [dim](中断)[/dim]",
                    title_align="left",
                    border_style="yellow",
                    box=box.ROUNDED,
                    padding=(0, 1),
                ))
            self._sys_print("已中断。")
        except (KeyboardInterrupt, EOFError):
            # 让 Ctrl+C / Ctrl+D 传播到外层 run() 的对应 handler
            raise
        except Exception as e:
            self._err_print(f"Agent 出错：{e}")

        # 自动保存
        if self._config.session.auto_save:
            try:
                self._session_mgr.save_session(self._session)
            except Exception as e:
                self._err_print(f"Session 保存失败：{e}")

    def _on_tool_call(self, event: ToolCallEvent) -> None:
        if not self._show_thinking:
            return
        # 多 agent 工具特殊展示
        if event.name == "spawn_agent":
            agent = event.arguments.get("agent", "?")
            task = event.arguments.get("task", "")[:40]
            console.print(f"  ⏳ 启动 agent: [bold]{agent}[/bold] — {task}")
            return
        args_str = json.dumps(event.arguments, ensure_ascii=False)
        if len(args_str) > 120:
            args_str = args_str[:120] + "..."
        console.print(f"  ⏳ {event.name}  {args_str}")

    def _on_tool_result(self, event: ToolResultEvent) -> None:
        if not self._show_thinking:
            return
        # 多 agent 工具特殊展示
        if event.name == "check_agent_status":
            try:
                result = json.loads(event.result)
                status = result.get("status", "?")
                agent = result.get("agent", "?")
                status_icon = {
                    "pending": "…",
                    "running": "⏳",
                    "completed": "✅",
                    "failed": "❌",
                    "timeout": "⏰",
                    "cancelled": "⏹",
                    "expired": "⌛",
                }
                icon = status_icon.get(status, "❓")
                console.print(f"  {icon} {agent}: {status}")
            except (json.JSONDecodeError, KeyError):
                console.print(f"  ✓ {event.result[:200]}")
            return
        if event.name == "spawn_agent":
            try:
                result = json.loads(event.result)
                task_id = result.get("task_id", "?")
                status = result.get("status", "?")
                console.print(f"  📋 task_id: {task_id} ({status})")
            except (json.JSONDecodeError, KeyError):
                console.print(f"  ✓ {event.result[:200]}")
            return
        result = event.result
        if len(result) > 200:
            result = result[:200] + "..."
        console.print(f"  ✓ {result}")

    # ------------------------------------------------------------------
    # 多行聊天框
    # ------------------------------------------------------------------

    def _enter_chat_box(self) -> None:
        """多行聊天框模式：逐行输入，/send 发送，/cancel 取消。"""
        console.print(Panel(
            "[dim]逐行输入内容，输入完成后发送：\n"
            "  /send    发送消息\n"
            "  /cancel  取消[/dim]",
            title="[bold]聊天框[/bold]",
            border_style="magenta",
            box=box.ROUNDED,
        ))
        lines: list[str] = []
        while True:
            try:
                line = console.input("[dim]... [/dim]")
            except KeyboardInterrupt:
                console.print()
                self._sys_print("已取消。")
                return
            except EOFError:
                console.print()
                self._sys_print("已取消。")
                return

            if line.strip() == "/send":
                break
            if line.strip() == "/cancel":
                self._sys_print("已取消。")
                return
            lines.append(line)

        message = "\n".join(lines).strip()
        if not message:
            self._err_print("消息为空，未发送。")
            return

        self._handle_message(message)

    # ------------------------------------------------------------------
    # Session 操作
    # ------------------------------------------------------------------

    def _new_session(self) -> None:
        self._session_mgr.save_session(self._session)
        self._session = self._session_mgr.new_session(
            work_dir=str(self._loop.tool_ctx.work_dir)
        )
        self._reset_loop()
        self._sys_print(f"已创建新 Session：{self._session.id}")

    def _list_sessions(self) -> None:
        metas = self._session_mgr.list_sessions()
        if not metas:
            self._sys_print("暂无 Session 记录。")
            return
        table = Table(title="Session 列表（最近在前）", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("ID", style="yellow", no_wrap=True)
        table.add_column("标题", max_width=30)
        table.add_column("更新时间")
        table.add_column("状态")
        for m in metas:
            marker = "[bold cyan]当前[/bold cyan]" if m.id == self._session.id else ""
            title = m.title or "(无标题)"
            table.add_row(m.id, title[:30], m.updated_at, marker)
        console.print(table)

    def _load_session(self, session_id: str) -> None:
        try:
            self._session_mgr.save_session(self._session)
            self._session = self._session_mgr.load_session(session_id)
            self._reset_loop()
            title = self._session.title or "(无标题)"
            self._sys_print(f"已切换到 Session：{session_id}（{title}）")
        except FileNotFoundError:
            self._err_print(f"Session 不存在：{session_id}")

    def _session_info(self) -> None:
        s = self._session
        msg_count = len([m for m in s.messages if m.get("role") in ("user", "assistant")])
        table = Table(title="当前 Session 信息", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("字段", style="cyan", no_wrap=True)
        table.add_column("值")
        table.add_row("ID", s.id)
        table.add_row("标题", s.title or "(无标题)")
        table.add_row("创建时间", s.created_at)
        table.add_row("更新时间", s.updated_at)
        table.add_row("工作目录", str(self._loop.tool_ctx.work_dir))
        table.add_row("消息轮数", str(msg_count // 2))
        console.print(table)

    def _delete_session(self, session_id: str) -> None:
        if session_id == self._session.id:
            self._err_print("不能删除当前正在使用的 Session，请先切换到其他 Session。")
            return
        ok = self._session_mgr.delete_session(session_id)
        if ok:
            self._sys_print(f"已删除 Session：{session_id}")
        else:
            self._err_print(f"Session 不存在：{session_id}")

    # ------------------------------------------------------------------
    # Skill 操作
    # ------------------------------------------------------------------

    def _handle_skills_cmd(self, args: list[str]) -> None:
        if self._skill_manager is None:
            self._err_print("Skill 系统未初始化。")
            return

        if args and args[0].lower() == "reload":
            from .tools import TOOL_REGISTRY
            self._skill_manager.discover(available_tools=set(TOOL_REGISTRY.keys()))
            self._sys_print(f"已重新扫描 Skill 目录，发现 {len(self._skill_manager.skills)} 个 Skill。")
            return

        self._print_skills()

    def _print_skills(self) -> None:
        if self._skill_manager is None:
            self._err_print("Skill 系统未初始化。")
            return

        skills = self._skill_manager.skills
        if not skills:
            self._sys_print("暂无可用 Skill。")
            return

        table = Table(title=f"可用 Skills（共 {len(skills)} 个）", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("名称", style="bold", no_wrap=True)
        table.add_column("描述")
        for s in skills:
            desc = s.description or "(无描述)"
            table.add_row(s.name, desc)
        console.print(table)

    # ------------------------------------------------------------------
    # 后台消息
    # ------------------------------------------------------------------

    def _flush_pending_messages(self) -> None:
        """显示 MCP 等后台线程积累的待处理消息。"""
        if self._mcp_manager and self._mcp_manager.pending_messages:
            for msg in self._mcp_manager.pending_messages:
                self._sys_print(msg)
            self._mcp_manager.pending_messages.clear()

    # ------------------------------------------------------------------
    # MCP 操作
    # ------------------------------------------------------------------

    def _handle_mcp_cmd(self, args: list[str]) -> None:
        if self._mcp_manager is None:
            self._sys_print("MCP 未启用（未配置 mcp_servers 或 mcp 包未安装）。")
            return

        if args and args[0].lower() == "tools":
            self._print_mcp_tools()
            return

        self._print_mcp_status()

    def _print_mcp_status(self) -> None:
        statuses = self._mcp_manager.get_status()
        if not statuses:
            self._sys_print("无 MCP Server 配置。")
            return

        table = Table(title="MCP Servers", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("Server", style="bold", no_wrap=True)
        table.add_column("Transport")
        table.add_column("状态")
        table.add_column("工具数", justify="right")
        table.add_column("详情")

        for s in statuses:
            if s["connected"]:
                status = "[green]✓ 已连接[/green]"
                detail = ", ".join(s["tools"][:5])
                if len(s["tools"]) > 5:
                    detail += f" ... (+{len(s['tools']) - 5})"
            else:
                status = "[red]✗ 失败[/red]"
                detail = s["error"][:50] if s["error"] else "—"
            table.add_row(s["name"], s["transport"], status, str(s["tool_count"]), detail)

        console.print(table)

    def _print_mcp_tools(self) -> None:
        statuses = self._mcp_manager.get_status()
        all_tools = []
        for s in statuses:
            if s["connected"]:
                for t in s["tools"]:
                    all_tools.append(f"{s['name']}__{t}")

        if not all_tools:
            self._sys_print("无可用 MCP 工具。")
            return

        table = Table(title=f"MCP 工具（共 {len(all_tools)} 个）", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("工具名", style="bold")
        for name in sorted(all_tools):
            table.add_row(name)
        console.print(table)

    # ------------------------------------------------------------------
    # Memory 操作
    # ------------------------------------------------------------------

    def _handle_memory_cmd(self, args: list[str]) -> None:
        if self._memory_manager is None:
            self._err_print("长期记忆系统未初始化（memory.enabled=false）。")
            return

        if not args:
            self._print_memory()
            return

        sub = args[0].lower()
        if sub == "clear":
            self._clear_memory()
        elif sub == "edit":
            self._edit_memory()
        elif sub == "stats":
            self._memory_stats()
        elif sub == "search":
            query = " ".join(args[1:]) if len(args) > 1 else ""
            if not query:
                self._err_print("用法：/memory search <关键词>")
            else:
                self._memory_search_cmd(query)
        elif sub == "extract":
            self._memory_extract()
        elif sub == "today":
            self._memory_daily()
        elif sub == "day":
            date = args[1] if len(args) > 1 else ""
            if not date:
                self._err_print("用法：/memory day <YYYY-MM-DD>")
            else:
                self._memory_daily(date)
        else:
            self._err_print(f"未知 memory 子命令：{sub}")

    def _print_memory(self) -> None:
        content = self._memory_manager.load()
        if not content.strip():
            self._sys_print("长期记忆为空。")
            return
        md = Markdown(content)
        console.print(Panel(
            md,
            title="[bold]长期记忆[/bold]",
            border_style="magenta",
            box=box.ROUNDED,
            padding=(0, 1),
        ))

    def _clear_memory(self) -> None:
        try:
            confirm = console.input("[bold red]确认清空长期记忆？(y/N): [/bold red]")
        except (KeyboardInterrupt, EOFError):
            console.print()
            self._sys_print("已取消。")
            return
        if confirm.strip().lower() == "y":
            self._memory_manager.save("")
            self._sys_print("长期记忆已清空。")
        else:
            self._sys_print("已取消。")

    def _edit_memory(self) -> None:
        import subprocess
        memory_path = self._memory_manager.path
        # 确保文件存在
        if not memory_path.exists():
            self._memory_manager.save("# 长期记忆\n")
        editor = os.environ.get("EDITOR", "notepad" if sys.platform == "win32" else "vim")
        try:
            subprocess.run([editor, str(memory_path)])
            self._sys_print("编辑完成。重新加载记忆...")
            # 记忆内容会在下次 system prompt 注入时自动更新
        except Exception as e:
            self._err_print(f"打开编辑器失败：{e}")

    def _memory_stats(self) -> None:
        """显示 observation 统计信息。"""
        if not self._memory_search:
            self._err_print("记忆检索系统未初始化。")
            return
        from rich.table import Table
        stats = self._memory_search.get_stats()
        table = Table(title="记忆系统统计", show_lines=True)
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green")
        table.add_row("总 observation 数", str(stats["total_observations"]))
        table.add_row("已晋升数", str(stats["promoted_count"]))
        table.add_row("FTS5 可用", "是" if stats["fts5_available"] else "否")
        table.add_row("向量库可用", "是" if stats["vectordb_available"] else "否")
        if stats["vectordb_available"]:
            table.add_row("向量库条数", str(stats["vectordb_count"]))
        for type_name, count in stats.get("by_type", {}).items():
            table.add_row(f"  类型: {type_name}", str(count))
        console.print(table)

    def _memory_search_cmd(self, query: str) -> None:
        """搜索历史记忆。"""
        if not self._memory_search:
            self._err_print("记忆检索系统未初始化。")
            return
        observations = self._memory_search.search(query)
        if not observations:
            self._sys_print("未找到相关记忆。")
            return
        for obs in observations:
            header = f"[bold cyan][{obs.type}][/bold cyan] {obs.title}"
            console.print(Panel(
                f"{obs.narrative}\n\n"
                f"[dim]概念：{', '.join(obs.concepts) if obs.concepts else '无'}[/dim]\n"
                f"[dim]来源：{obs.session_id} | 引用：{obs.relevance_count}[/dim]",
                title=header,
                border_style="blue",
                box=box.ROUNDED,
            ))

    def _memory_extract(self) -> None:
        """手动触发当前 session 的 observation 提取。"""
        if not self._extractor:
            self._err_print("提取器未初始化。")
            return
        self._sys_print("正在提取记忆...")
        observations = self._extractor.extract_from_session(self._session)
        if observations:
            self._sys_print(f"已提取 {len(observations)} 条记忆。")
            # 同步到向量库
            if (self._memory_search and self._memory_search.vector_store
                    and self._memory_search.vector_store.available):
                self._memory_search.vector_store.add_batch(observations)
        else:
            self._sys_print("未提取到有价值的记忆。")

    def _memory_daily(self, date: str | None = None) -> None:
        """显示每日记忆。"""
        if not self._observation_store:
            self._err_print("Observation 存储未初始化。")
            return
        if not date:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")
        from agent.observation import generate_daily_memory
        content = generate_daily_memory(date, self._observation_store)
        console.print(Panel(
            Markdown(content),
            title=f"每日记忆 · {date}",
            border_style="cyan",
            box=box.ROUNDED,
        ))

    def _on_session_end(self) -> None:
        """Session 结束时触发 observation 提取。"""
        if self._extractor and self._config.observation.enabled:
            try:
                observations = self._extractor.extract_from_session(self._session)
                if observations:
                    self._sys_print(f"已提取 {len(observations)} 条记忆。")
                    if (self._memory_search and self._memory_search.vector_store
                            and self._memory_search.vector_store.available):
                        self._memory_search.vector_store.add_batch(observations)
            except Exception as e:
                self._err_print(f"记忆提取失败：{e}")

    # ------------------------------------------------------------------
    # 其他命令
    # ------------------------------------------------------------------

    def _print_history(self) -> None:
        messages = self._session.messages
        user_msgs = [(i, m) for i, m in enumerate(messages) if m.get("role") == "user"]
        if not user_msgs:
            self._sys_print("当前对话历史为空。")
            return
        table = Table(title=f"当前对话历史（共 {len(user_msgs)} 轮）", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("轮次", style="cyan", no_wrap=True)
        table.add_column("内容预览")
        for turn, (_, m) in enumerate(user_msgs, 1):
            content = m.get("content", "")
            if isinstance(content, str):
                preview = content[:60].replace("\n", " ")
                table.add_row(str(turn), preview)
        console.print(table)

    def _clear_history(self) -> None:
        self._session.messages.clear()
        self._sys_print("已清空当前对话历史（Session 文件未删除）。")

    def _print_tools(self) -> None:
        enabled = self._config.enabled_tools
        table = Table(title="可用工具", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("状态", no_wrap=True)
        table.add_column("类型", no_wrap=True)
        table.add_column("名称", style="bold")
        table.add_column("描述")
        for name, td in TOOL_REGISTRY.items():
            is_mcp = "__" in name
            if is_mcp:
                status = "[green]MCP[/green]"
                tool_type = "[cyan]mcp[/cyan]"
            else:
                status = "[green]启用[/green]" if name in enabled else "[dim]禁用[/dim]"
                tool_type = "[dim]内置[/dim]"
            table.add_row(status, tool_type, name, td.description)
        console.print(table)

    def _print_config(self) -> None:
        cfg = self._config
        table = Table(title="当前配置", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("字段", style="cyan", no_wrap=True)
        table.add_column("值")
        table.add_row("模型", cfg.llm.model)
        table.add_row("API Base", cfg.llm.base_url)
        table.add_row("Provider", cfg.llm.provider)
        table.add_row("温度", str(cfg.llm.temperature))
        table.add_row("流式输出", str(cfg.llm.streaming))
        table.add_row("最大迭代", str(cfg.max_iterations))
        table.add_row("工作目录", str(cfg.resolved_work_dir()))
        table.add_row("Session 目录", str(cfg.resolved_session_dir()))
        table.add_row("配置文件", str(cfg.config_path))
        console.print(table)

    def _change_dir(self, path: str) -> None:
        from .tools import execute_tool
        result = execute_tool("change_dir", {"path": path}, self._loop.tool_ctx)
        self._sys_print(result)

    # ------------------------------------------------------------------
    # 打印工具方法
    # ------------------------------------------------------------------

    def _sys_print(self, msg: str) -> None:
        console.print(f"[info][系统][/info] {msg}")

    def _err_print(self, msg: str) -> None:
        console.print(f"[error][错误][/error] {msg}")

    def _print_banner(self) -> None:
        title = self._session.title or "(新对话)"
        work_dir = self._loop.tool_ctx.work_dir
        banner = Text()
        banner.append(f"{BOT_NAME}", style="bold cyan")
        banner.append(f" v{VERSION}\n", style="dim")
        banner.append(f"Session: {self._session.id}\n", style="dim")
        banner.append(f"工作目录: {work_dir}\n", style="dim")
        banner.append(f"模型: {self._config.llm.model}\n", style="dim")
        banner.append("输入 /help 查看可用命令，/chat 进入多行聊天框", style="dim")
        console.print(Panel(banner, border_style="cyan", box=box.ROUNDED, padding=(0, 1)))
        console.print()  # 空行缓冲，防止补全菜单遮挡 banner 底部边框
