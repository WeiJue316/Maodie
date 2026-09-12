"""
MCP 模块测试。

由于 mcp 包可能未安装，所有依赖 mcp SDK 的测试都 mock 掉 import。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 测试配置加载和校验（不依赖 mcp 包）
# ---------------------------------------------------------------------------


class TestMCPServerConfig:
    """测试 MCPServerConfig 数据类和配置加载。"""

    def test_default_values(self):
        from agent.config import MCPServerConfig
        cfg = MCPServerConfig()
        assert cfg.name == ""
        assert cfg.transport == "stdio"
        assert cfg.command == ""
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.url == ""
        assert cfg.headers == {}
        assert cfg.timeout == 30
        assert cfg.include == []
        assert cfg.exclude == []

    def test_agent_config_has_mcp_servers(self):
        from agent.config import AgentConfig
        cfg = AgentConfig()
        assert cfg.mcp_servers == []


class TestInterpolateEnv:
    """测试环境变量插值。"""

    def test_interpolate_existing_var(self):
        from agent.config import _interpolate_env
        with patch.dict("os.environ", {"MY_TOKEN": "abc123"}):
            result = _interpolate_env("Bearer ${MY_TOKEN}")
            assert result == "Bearer abc123"

    def test_interpolate_missing_var_keeps_original(self):
        from agent.config import _interpolate_env
        result = "Bearer ${NONEXISTENT_VAR_XYZ}"
        assert _interpolate_env(result) == result

    def test_interpolate_multiple_vars(self):
        from agent.config import _interpolate_env
        with patch.dict("os.environ", {"A": "1", "B": "2"}):
            result = _interpolate_env("${A}-${B}")
            assert result == "1-2"

    def test_interpolate_env_dict(self):
        from agent.config import _interpolate_env_dict
        with patch.dict("os.environ", {"TOKEN": "secret"}):
            result = _interpolate_env_dict({
                "Authorization": "Bearer ${TOKEN}",
                "X-Static": "plain",
            })
            assert result == {"Authorization": "Bearer secret", "X-Static": "plain"}


class TestValidateMCPServers:
    """测试 MCP Server 配置校验。"""

    def test_valid_stdio(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="test", transport="stdio", command="npx")]
        _validate_mcp_servers(servers)  # 不应抛异常

    def test_valid_sse(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="test", transport="sse", url="http://localhost:3001/sse")]
        _validate_mcp_servers(servers)

    def test_valid_streamable_http(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="test", transport="streamable_http", url="http://localhost:8000/mcp")]
        _validate_mcp_servers(servers)

    def test_empty_name_raises(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="", transport="stdio", command="npx")]
        with pytest.raises(ValueError, match="name 不能为空"):
            _validate_mcp_servers(servers)

    def test_duplicate_name_raises(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [
            MCPServerConfig(name="test", transport="stdio", command="npx"),
            MCPServerConfig(name="test", transport="stdio", command="python"),
        ]
        with pytest.raises(ValueError, match="name 'test' 重复"):
            _validate_mcp_servers(servers)

    def test_invalid_transport_raises(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="test", transport="http")]
        with pytest.raises(ValueError, match="transport 必须是"):
            _validate_mcp_servers(servers)

    def test_stdio_without_command_raises(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="test", transport="stdio")]
        with pytest.raises(ValueError, match="stdio 类型必须指定 command"):
            _validate_mcp_servers(servers)

    def test_sse_without_url_raises(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="test", transport="sse")]
        with pytest.raises(ValueError, match="sse 类型必须指定 url"):
            _validate_mcp_servers(servers)

    def test_negative_timeout_raises(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="test", transport="stdio", command="npx", timeout=-1)]
        with pytest.raises(ValueError, match="timeout 必须 > 0"):
            _validate_mcp_servers(servers)

    def test_invalid_regex_raises(self):
        from agent.config import MCPServerConfig, _validate_mcp_servers
        servers = [MCPServerConfig(name="test", transport="stdio", command="npx", include=["[invalid"])]
        with pytest.raises(ValueError, match="正则 .* 不合法"):
            _validate_mcp_servers(servers)


class TestLoadConfigMCP:
    """测试 load_config 中 mcp_servers 的解析。"""

    def test_load_empty_mcp_servers(self, tmp_path):
        from agent.config import load_config
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("mcp_servers: []\n", encoding="utf-8")
        # 需要设置 project_root
        with patch("agent.config.PROJECT_ROOT", tmp_path):
            cfg = load_config(cfg_file)
        assert cfg.mcp_servers == []

    def test_load_stdio_server(self, tmp_path):
        from agent.config import load_config
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "mcp_servers:\n"
            "  - name: filesystem\n"
            "    transport: stdio\n"
            "    command: npx\n"
            "    args:\n"
            '      - "-y"\n'
            '      - "@modelcontextprotocol/server-filesystem"\n'
            "    timeout: 10\n",
            encoding="utf-8",
        )
        with patch("agent.config.PROJECT_ROOT", tmp_path):
            cfg = load_config(cfg_file)
        assert len(cfg.mcp_servers) == 1
        s = cfg.mcp_servers[0]
        assert s.name == "filesystem"
        assert s.transport == "stdio"
        assert s.command == "npx"
        assert s.args == ["-y", "@modelcontextprotocol/server-filesystem"]
        assert s.timeout == 10

    def test_load_with_env_interpolation(self, tmp_path):
        from agent.config import load_config
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "mcp_servers:\n"
            "  - name: github\n"
            "    transport: stdio\n"
            "    command: npx\n"
            "    env:\n"
            "      GITHUB_TOKEN: ${GITHUB_TOKEN}\n",
            encoding="utf-8",
        )
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_abc123"}):
            with patch("agent.config.PROJECT_ROOT", tmp_path):
                cfg = load_config(cfg_file)
        assert cfg.mcp_servers[0].env["GITHUB_TOKEN"] == "ghp_abc123"


# ---------------------------------------------------------------------------
# 测试 ToolContext 新增 mcp_manager
# ---------------------------------------------------------------------------


class TestToolContextMCPManager:
    """测试 ToolContext 的 mcp_manager 字段。"""

    def test_default_mcp_manager_is_none(self):
        from agent.tools import ToolContext
        ctx = ToolContext(work_dir=Path("/tmp"))
        assert ctx.mcp_manager is None

    def test_mcp_manager_can_be_set(self):
        from agent.tools import ToolContext
        ctx = ToolContext(work_dir=Path("/tmp"))
        mock_manager = MagicMock()
        ctx.mcp_manager = mock_manager
        assert ctx.mcp_manager is mock_manager


# ---------------------------------------------------------------------------
# 测试 get_openai_schemas 包含 MCP 工具
# ---------------------------------------------------------------------------


class TestGetOpenaiSchemasMCP:
    """测试 get_openai_schemas 自动包含 MCP 工具。"""

    def test_mcp_tool_included_in_schemas(self, tmp_path):
        from agent.tools import TOOL_REGISTRY, ToolDef, get_openai_schemas

        # 注册一个模拟 MCP 工具
        mock_tool = ToolDef(
            name="github__create_issue",
            description="Create a GitHub issue",
            schema={"type": "object", "properties": {"title": {"type": "string"}}},
            func=lambda args, ctx: "ok",
        )
        TOOL_REGISTRY["github__create_issue"] = mock_tool
        try:
            schemas = get_openai_schemas(["read_file"])
            names = [s["function"]["name"] for s in schemas]
            assert "read_file" in names
            assert "github__create_issue" in names
        finally:
            del TOOL_REGISTRY["github__create_issue"]

    def test_mcp_tool_not_in_enabled_tools_still_included(self):
        from agent.tools import TOOL_REGISTRY, ToolDef, get_openai_schemas

        mock_tool = ToolDef(
            name="test__search",
            description="Search",
            schema={"type": "object", "properties": {}},
            func=lambda args, ctx: "ok",
        )
        TOOL_REGISTRY["test__search"] = mock_tool
        try:
            # enabled_tools 里没有 test__search，但应该自动包含
            schemas = get_openai_schemas(["read_file"])
            names = [s["function"]["name"] for s in schemas]
            assert "test__search" in names
        finally:
            del TOOL_REGISTRY["test__search"]


# ---------------------------------------------------------------------------
# 测试 schema 转换（mock mcp 包）
# ---------------------------------------------------------------------------


class _FakeTool:
    """模拟 MCP Tool 对象，用于不依赖 mcp 包的测试。"""
    def __init__(self, name: str, description: str = "", input_schema: dict | None = None):
        self.name = name
        self.description = description
        self.inputSchema = input_schema or {}


class TestSchemaConversion:
    """测试 MCP Tool → OpenAI schema 转换。"""

    def test_mcp_tool_to_openai(self):
        from agent.mcp.schema import mcp_tool_to_openai

        tool = _FakeTool(
            name="search",
            description="Search for items",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )

        result = mcp_tool_to_openai(tool, "myserver")
        assert result["type"] == "function"
        assert result["function"]["name"] == "myserver__search"
        assert result["function"]["description"] == "Search for items"
        assert result["function"]["parameters"]["properties"]["query"]["type"] == "string"

    def test_apply_tool_filter_include(self):
        from agent.mcp.schema import apply_tool_filter

        tools = [_FakeTool("create_issue"), _FakeTool("list_issues"), _FakeTool("search")]
        result = apply_tool_filter(tools, include=["create.*"], exclude=[])
        assert len(result) == 1
        assert result[0].name == "create_issue"

    def test_apply_tool_filter_exclude(self):
        from agent.mcp.schema import apply_tool_filter

        tools = [_FakeTool("create_issue"), _FakeTool("admin_delete"), _FakeTool("search")]
        result = apply_tool_filter(tools, include=[], exclude=["admin_.*"])
        assert len(result) == 2
        names = [t.name for t in result]
        assert "admin_delete" not in names

    def test_apply_tool_filter_include_over_exclude(self):
        from agent.mcp.schema import apply_tool_filter

        tools = [_FakeTool("admin_list"), _FakeTool("admin_delete"), _FakeTool("search")]
        result = apply_tool_filter(tools, include=["admin_.*"], exclude=[".*_delete"])
        assert len(result) == 1
        assert result[0].name == "admin_list"


# ---------------------------------------------------------------------------
# 测试 AsyncBridge（不依赖 mcp 包）
# ---------------------------------------------------------------------------


class TestAsyncBridge:
    """测试 AsyncBridge 同步桥接。"""

    def test_start_and_stop(self):
        from agent.mcp.bridge import AsyncBridge

        bridge = AsyncBridge()
        bridge.start()
        assert bridge._loop is not None
        assert bridge._thread is not None
        assert bridge._thread.is_alive()
        bridge.stop()
        assert bridge._loop is None

    def test_run_sync_returns_value(self):
        from agent.mcp.bridge import AsyncBridge

        async def coro():
            return 42

        bridge = AsyncBridge()
        bridge.start()
        try:
            result = bridge.run_sync(coro())
            assert result == 42
        finally:
            bridge.stop()

    def test_run_sync_propagates_exception(self):
        from agent.mcp.bridge import AsyncBridge

        async def coro():
            raise ValueError("test error")

        bridge = AsyncBridge()
        bridge.start()
        try:
            with pytest.raises(ValueError, match="test error"):
                bridge.run_sync(coro())
        finally:
            bridge.stop()

    def test_run_sync_timeout(self):
        from agent.mcp.bridge import AsyncBridge

        async def coro():
            await asyncio.sleep(10)

        bridge = AsyncBridge()
        bridge.start()
        try:
            with pytest.raises(asyncio.TimeoutError):
                bridge.run_sync(coro(), timeout=0.1)
        finally:
            bridge.stop()

    def test_run_sync_before_start_raises(self):
        from agent.mcp.bridge import AsyncBridge

        bridge = AsyncBridge()
        async def coro():
            return 1
        with pytest.raises(RuntimeError, match="未启动"):
            bridge.run_sync(coro())

    def test_double_start_is_noop(self):
        from agent.mcp.bridge import AsyncBridge

        bridge = AsyncBridge()
        bridge.start()
        loop1 = bridge._loop
        bridge.start()  # 不应创建新 loop
        assert bridge._loop is loop1
        bridge.stop()


# ---------------------------------------------------------------------------
# 测试 MCPManager（mock mcp 包）
# ---------------------------------------------------------------------------


_HAS_MCP = False
try:
    import mcp  # noqa: F401
    _HAS_MCP = True
except ImportError:
    pass


@pytest.mark.skipif(not _HAS_MCP, reason="mcp 包未安装")
class TestMCPManager:
    """测试 MCPManager 核心逻辑（需要 mcp 包）。"""

    def _make_config(self, name="test", transport="stdio", command="echo"):
        cfg = MagicMock()
        cfg.name = name
        cfg.transport = transport
        cfg.command = command
        cfg.args = []
        cfg.env = {}
        cfg.cwd = ""
        cfg.url = ""
        cfg.headers = {}
        cfg.timeout = 30
        cfg.include = []
        cfg.exclude = []
        return cfg

    def test_result_to_str_text_content(self):
        from agent.mcp.manager import MCPManager

        content = MagicMock()
        content.text = "hello world"
        content.type = "text"
        result = MagicMock()
        result.content = [content]
        result.isError = False

        assert MCPManager._result_to_str(result) == "hello world"

    def test_result_to_str_error(self):
        from agent.mcp.manager import MCPManager

        content = MagicMock()
        content.text = "not found"
        content.type = "text"
        result = MagicMock()
        result.content = [content]
        result.isError = True

        assert "错误" in MCPManager._result_to_str(result)
        assert "not found" in MCPManager._result_to_str(result)

    def test_get_status_empty(self):
        from agent.mcp.manager import MCPManager
        from agent.mcp.bridge import AsyncBridge

        bridge = AsyncBridge()
        manager = MCPManager([], bridge)
        assert manager.get_status() == []

    def test_get_all_tools_empty(self):
        from agent.mcp.manager import MCPManager
        from agent.mcp.bridge import AsyncBridge

        bridge = AsyncBridge()
        manager = MCPManager([], bridge)
        assert manager.get_all_tools() == {}
