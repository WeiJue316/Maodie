"""
程序入口。

用法：
  python main.py                           # 启动新会话（交互模式）
  python main.py --resume                  # 恢复最近会话
  python main.py --session <id>            # 恢复指定会话
  python main.py --message "你好"          # 单条消息模式（非交互）
  python main.py --config /path/config.yaml
  python main.py --web --port 8000         # 启动 Web 模式
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 项目要求 Python >= 3.10。在 3.7/3.8/3.9 上，老 OpenSSL + httpx 会在握手阶段
# 抛 [Errno 0] ConnectError，表现为 "[错误] Agent 出错：Connection error."
# 所以入口处直接拦截，给出明确引导。
_MIN_PY = (3, 10)
if sys.version_info < _MIN_PY:
    sys.stderr.write(
        f"[ERROR] Python {_MIN_PY[0]}.{_MIN_PY[1]}+ required, "
        f"current: {sys.version.split()[0]} ({sys.executable})\n"
        "  Fix: conda activate py100 && python main.py\n"
        "  Or:  double-click run.bat\n"
    )
    sys.exit(1)

# Windows 控制台默认 GBK，LLM 输出含 emoji 或生僻字时会 UnicodeEncodeError。
# 把标准流重配为 UTF-8，失败字符降级为 ? 而非崩溃。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Python ReAct Agent CLI",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        metavar="PATH",
        help="配置文件路径（默认：project_class/config.yaml）",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        metavar="SESSION_ID",
        help="恢复指定 Session ID 的对话历史",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="恢复最近一次 Session",
    )
    parser.add_argument(
        "--message", "-m",
        type=str,
        default=None,
        metavar="TEXT",
        help="直接发送单条消息并退出（非交互模式）",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="禁用流式输出（覆盖配置文件设置）",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动 Web 模式（FastAPI 服务器）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Web 模式监听端口（默认：8000）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Web 模式监听地址（默认：0.0.0.0）",
    )
    return parser.parse_args()


def resolve_session(args, session_mgr, config):
    """根据命令行参数决定使用哪个 Session。"""
    from agent.session import Session

    if args.session:
        try:
            session = session_mgr.load_session(args.session)
            print(f"[系统] 已恢复 Session：{args.session}")
            return session
        except FileNotFoundError:
            print(f"[错误] Session 不存在：{args.session}", file=sys.stderr)
            sys.exit(1)

    if args.resume:
        session = session_mgr.get_latest_session()
        if session:
            print(f"[系统] 已恢复最近 Session：{session.id}")
            return session
        else:
            print("[系统] 无历史 Session，创建新对话。")

    return session_mgr.new_session(work_dir=str(config.resolved_work_dir()))


def _make_mcp_tool_wrapper(server_name: str, tool_name: str, manager, bridge):
    """为 MCP 工具创建同步 wrapper 闭包，注册到 TOOL_REGISTRY。"""
    def wrapper(args: dict, ctx) -> str:
        # 检查 server 是否已连接
        state = manager.states.get(server_name)
        if state is None or not state.connected:
            return f"[错误] MCP Server '{server_name}' 尚未连接，请稍后重试"
        return bridge.run_sync(
            manager.call_tool(server_name, tool_name, args),
            timeout=60,
        )
    return wrapper


def _register_mcp_tools(mcp_manager, mcp_bridge, schemas_override=None):
    """将 MCP 工具注册到 TOOL_REGISTRY。返回注册数量。

    Args:
        schemas_override: 直接传入 {server_name: [schema, ...]}，跳过 get_all_tools()
    """
    from agent.tools import TOOL_REGISTRY, ToolDef

    all_tools = schemas_override or mcp_manager.get_all_tools()
    count = 0
    for server_name, schemas in all_tools.items():
        for schema in schemas:
            full_name = schema["function"]["name"]
            tool_name = full_name.split("__", 1)[1]
            wrapper = _make_mcp_tool_wrapper(
                server_name, tool_name, mcp_manager, mcp_bridge,
            )
            TOOL_REGISTRY[full_name] = ToolDef(
                name=full_name,
                description=schema["function"].get("description", ""),
                schema=schema["function"].get("parameters", {}),
                func=wrapper,
            )
            count += 1
    return count


def run_single_message(message: str, config, session, session_mgr, skill_manager=None, memory_manager=None, memory_search=None, mcp_manager=None, orchestrator=None) -> None:
    """非交互模式：发送单条消息后退出。"""
    from agent.llm import LLMClient
    from agent.loop import AgentLoop, ToolCallEvent, ToolResultEvent
    from agent.memory import check_trigger_words

    # 触发词检测
    if memory_manager and config.memory.enabled:
        if check_trigger_words(message, config.memory.trigger_words):
            message += "\n\n[系统提示] 用户希望记住某些信息，请使用 write_memory 工具将其保存到长期记忆。"

    llm = LLMClient(config.llm)
    loop = AgentLoop(config, session, llm, skill_manager, memory_manager, memory_search, mcp_manager)
    if orchestrator:
        loop.tool_ctx.orchestrator = orchestrator

    def on_tool_call(e: ToolCallEvent) -> None:
        import json
        args_str = json.dumps(e.arguments, ensure_ascii=False)
        print(f"[调用工具] {e.name}  {args_str}", file=sys.stderr)

    def on_tool_result(e: ToolResultEvent) -> None:
        result = e.result[:200] + "..." if len(e.result) > 200 else e.result
        print(f"[工具结果] {result}", file=sys.stderr)

    if config.llm.streaming:
        for label, token in loop.stream_run(message, on_tool_call=on_tool_call, on_tool_result=on_tool_result):
            sys.stdout.write(token)
            sys.stdout.flush()
        print()
    else:
        answer = loop.run(message, on_tool_call=on_tool_call, on_tool_result=on_tool_result)
        print(answer)

    if config.session.auto_save:
        session_mgr.save_session(session)


def main() -> None:
    args = parse_args()

    # 1. 加载配置
    from agent.config import load_config
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)

    # 命令行覆盖
    if args.no_stream:
        config.llm.streaming = False

    # 检查 API Key
    if not config.llm.api_key:
        print(
            "[错误] 未配置 API Key。\n"
            "  请在 config.yaml 中设置 llm.api_key，\n"
            "  或设置环境变量 AGENT_API_KEY。",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. 初始化 Session 管理器
    from agent.session import SessionManager
    session_mgr = SessionManager(config.resolved_session_dir())

    # 3. 解析 Session
    session = resolve_session(args, session_mgr, config)

    # 4. 初始化 SkillManager
    from agent.skills import SkillManager
    from agent.tools import TOOL_REGISTRY
    skill_manager = SkillManager(config.resolved_skills_dir())
    skill_manager.discover(available_tools=set(TOOL_REGISTRY.keys()))

    # 5. 初始化 MemoryManager（如果启用）
    memory_manager = None
    if config.memory.enabled:
        from agent.memory import MemoryManager
        memory_manager = MemoryManager(config.resolved_memory_path())
        # 将 write_memory 加入 enabled_tools
        if "write_memory" not in config.enabled_tools:
            config.enabled_tools.append("write_memory")

    # 6. 初始化 ObservationStore（如果启用）
    observation_store = None
    if config.observation.enabled:
        from agent.observation import ObservationStore
        observation_store = ObservationStore(config.resolved_db_path())

    # 7. 初始化 VectorStore（如果启用）
    vector_store = None
    if config.vectordb.enabled:
        from agent.vectordb import VectorStore
        vector_store = VectorStore(
            persist_dir=config.resolved_vectordb_dir(),
            collection_name=config.vectordb.collection_name,
            embedding_model_name=config.vectordb.embedding_model,
        )
        # 启动时同步：SQLite → ChromaDB
        if vector_store.available and observation_store:
            synced = vector_store.sync_from_store(observation_store)
            if synced > 0:
                print(f"[系统] 向量数据库同步了 {synced} 条记忆。", file=sys.stderr)

    # 8. 初始化 MemorySearch
    memory_search = None
    if config.memory_search.enabled and observation_store:
        from agent.memory_search import MemorySearch
        llm_for_search = None
        if config.memory_search.auto_promote:
            from agent.llm import LLMClient as _LLM
            llm_for_search = _LLM(config.llm)
        memory_search = MemorySearch(
            store=observation_store,
            vector_store=vector_store,
            memory_manager=memory_manager,
            llm_client=llm_for_search,
            config=config.memory_search,
        )

    # 9. 初始化 Extractor
    extractor = None
    if config.observation.enabled and observation_store:
        from agent.extractor import ObservationExtractor
        from agent.llm import LLMClient as _LLM
        extractor = ObservationExtractor(
            llm_client=_LLM(config.llm),
            store=observation_store,
            vector_store=vector_store,
            config=config.observation,
        )

    # 10. 初始化 Orchestrator（如果启用）
    orchestrator = None
    if config.orchestrator.enabled and config.agents:
        from agent.orchestrator import Orchestrator
        orchestrator = Orchestrator(
            config=config,
            session_manager=session_mgr,
            observation_store=observation_store,
            observation_extractor=extractor,
        )
        # 将多 agent 工具加入 enabled_tools
        for tool_name in ("spawn_agent", "check_agent_status"):
            if tool_name not in config.enabled_tools:
                config.enabled_tools.append(tool_name)
        print(f"[系统] 多 Agent 编排器已启用，{len(config.agents)} 个 agent 可用。", file=sys.stderr)

    # 11. 将 search_memory 加入 enabled_tools
    if config.observation.enabled:
        if "search_memory" not in config.enabled_tools:
            config.enabled_tools.append("search_memory")

    # 11. 初始化 MCP（可选，后台连接 + 缓存）
    mcp_manager = None
    if config.mcp_servers:
        MCP_AVAILABLE = False
        try:
            import mcp as _mcp_mod  # noqa: F401
            MCP_AVAILABLE = True
        except ImportError:
            pass

        if not MCP_AVAILABLE:
            print("[警告] 配置了 MCP Server 但未安装 mcp 包，请运行: pip install mcp", file=sys.stderr)
        else:
            import threading
            from agent.mcp.bridge import AsyncBridge
            from agent.mcp.manager import MCPManager

            mcp_bridge = AsyncBridge()
            mcp_bridge.start()
            mcp_manager = MCPManager(config.mcp_servers, mcp_bridge)

            # 1) 先从缓存加载 schema，立即注册工具（不阻塞）
            cache_dir = config.project_root / ".memory"
            cached = MCPManager.load_cache(cache_dir)
            if cached:
                # 用缓存的 schema 创建临时状态，让工具先可用
                from agent.mcp.manager import MCPServerState
                for server_name in cached:
                    cfg = next((c for c in config.mcp_servers if c.name == server_name), None)
                    if cfg:
                        mcp_manager.states[server_name] = MCPServerState(config=cfg)
                tool_count = _register_mcp_tools(mcp_manager, mcp_bridge, schemas_override=cached)
                print(f"[系统] MCP 缓存已加载，{tool_count} 个工具可用（后台连接中...）", file=sys.stderr)

            # 2) 后台线程连接真实 MCP Server
            def _bg_connect():
                try:
                    mcp_bridge.run_sync(mcp_manager.connect_all())
                    # 连接完成后更新缓存
                    mcp_manager.save_cache(cache_dir)
                    # 重新注册工具（用真实 schema 替换缓存的）
                    _register_mcp_tools(mcp_manager, mcp_bridge)
                    connected = sum(1 for s in mcp_manager.get_status() if s["connected"])
                    total = sum(s["tool_count"] for s in mcp_manager.get_status())
                    # 不直接 print，存入队列等 REPL 安全时机显示
                    mcp_manager.pending_messages.append(
                        f"MCP 后台连接完成：{connected} 个 server，{total} 个工具。"
                    )
                except Exception as e:
                    mcp_manager.pending_messages.append(f"MCP 后台连接异常：{e}")
                    logger.warning("MCP 后台连接异常：%s", e)

            bg_thread = threading.Thread(target=_bg_connect, daemon=True)
            bg_thread.start()
            # 不注册 atexit 清理 — MCP SDK 的连接关闭可能阻塞，导致进程退不出。
            # daemon 线程会在进程退出时由操作系统回收。

    # 12. Web 模式
    if args.web:
        from agent.web import create_app
        import uvicorn

        app = create_app(
            config=config,
            session_manager=session_mgr,
            memory_manager=memory_manager,
            observation_store=observation_store,
            memory_search=memory_search,
            skill_manager=skill_manager,
            mcp_manager=mcp_manager,
            orchestrator=orchestrator,
        )

        print(f"[系统] Web 服务器启动中...")
        print(f"[系统] 访问地址: http://localhost:{args.port}")
        print(f"[系统] API 文档: http://localhost:{args.port}/docs")

        uvicorn.run(app, host=args.host, port=args.port)
        return

    # 13. 单条消息模式
    if args.message:
        run_single_message(args.message, config, session, session_mgr, skill_manager, memory_manager, memory_search, mcp_manager, orchestrator)
        return

    # 14. 交互模式
    from agent.cli import CLI
    cli = CLI(
        config, session, session_mgr, skill_manager, memory_manager,
        memory_search, extractor, observation_store, mcp_manager,
        orchestrator,
    )
    cli.run()


if __name__ == "__main__":
    main()
