"""CLI 思考过程显示控制测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.cli import CLI
from agent.config import LLMConfig, ModelPreset
from agent.loop import ToolCallEvent, ToolResultEvent


@pytest.fixture
def cli(tmp_path):
    """创建一个 CLI 实例用于测试。"""
    from agent.config import AgentConfig, SessionConfig
    from agent.session import Session, SessionManager

    config = AgentConfig()
    config.llm = LLMConfig(api_key="test-key")
    config.session = SessionConfig(dir=str(tmp_path / ".sessions"))
    config.config_path = tmp_path / "config.yaml"
    config.project_root = tmp_path

    session_mgr = SessionManager(config.resolved_session_dir())
    session = session_mgr.new_session()

    cli_instance = CLI(config, session, session_mgr)
    return cli_instance


class TestThinkToggle:
    """测试 /think 命令切换功能。"""

    def test_default_show_thinking_is_true(self, cli):
        """默认应该显示思考过程。"""
        assert cli._show_thinking is True

    def test_think_command_toggles_to_false(self, cli):
        """执行 /think 后应该隐藏思考过程。"""
        cli._handle_slash("/think")
        assert cli._show_thinking is False

    def test_think_command_toggles_back_to_true(self, cli):
        """再次执行 /think 后应该显示思考过程。"""
        cli._handle_slash("/think")
        cli._handle_slash("/think")
        assert cli._show_thinking is True


class TestPromptIndicator:
    """测试提示符状态指示。"""

    def test_prompt_shows_indicator_when_thinking_enabled(self, cli):
        """思考过程开启时，提示符应该包含 🔍。"""
        cli._show_thinking = True
        with patch("agent.cli._read_line") as mock_read:
            mock_read.return_value = "/exit"
            try:
                cli.run()
            except (StopIteration, SystemExit):
                pass
            # 检查提示符参数
            call_args = mock_read.call_args[0][0]
            assert "🔍" in call_args

    def test_prompt_shows_normal_when_thinking_disabled(self, cli):
        """思考过程关闭时，提示符应该正常。"""
        cli._show_thinking = False
        with patch("agent.cli._read_line") as mock_read:
            mock_read.return_value = "/exit"
            try:
                cli.run()
            except (StopIteration, SystemExit):
                pass
            # 检查提示符参数
            call_args = mock_read.call_args[0][0]
            assert "🔍" not in call_args


class TestToolCallDisplay:
    """测试工具调用时的显示行为。"""

    def test_on_tool_call_shows_when_thinking_enabled(self, cli):
        """思考过程开启时，工具调用应该显示。"""
        cli._show_thinking = True
        event = ToolCallEvent(
            name="read_file",
            arguments={"path": "test.py"},
            call_id="call_123",
        )

        with patch("agent.cli.console") as mock_console:
            cli._on_tool_call(event)
            mock_console.print.assert_called_once()

    def test_on_tool_call_hidden_when_thinking_disabled(self, cli):
        """思考过程关闭时，工具调用不应该显示。"""
        cli._show_thinking = False
        event = ToolCallEvent(
            name="read_file",
            arguments={"path": "test.py"},
            call_id="call_123",
        )

        with patch("agent.cli.console") as mock_console:
            cli._on_tool_call(event)
            mock_console.print.assert_not_called()

    def test_on_tool_result_shows_when_thinking_enabled(self, cli):
        """思考过程开启时，工具结果应该显示。"""
        cli._show_thinking = True
        event = ToolResultEvent(
            name="read_file",
            call_id="call_123",
            result="file content here",
        )

        with patch("agent.cli.console") as mock_console:
            cli._on_tool_result(event)
            mock_console.print.assert_called_once()

    def test_on_tool_result_hidden_when_thinking_disabled(self, cli):
        """思考过程关闭时，工具结果不应该显示。"""
        cli._show_thinking = False
        event = ToolResultEvent(
            name="read_file",
            call_id="call_123",
            result="file content here",
        )

        with patch("agent.cli.console") as mock_console:
            cli._on_tool_result(event)
            mock_console.print.assert_not_called()


class TestToolCallTruncation:
    """测试工具调用信息截断。"""

    def test_long_args_truncated(self, cli):
        """长参数应该被截断到 120 字符。"""
        cli._show_thinking = True
        long_args = {"content": "x" * 200}
        event = ToolCallEvent(
            name="write_file",
            arguments=long_args,
            call_id="call_123",
        )

        with patch("agent.cli.console") as mock_console:
            cli._on_tool_call(event)
            call_args = mock_console.print.call_args[0][0]
            assert "..." in call_args

    def test_long_result_truncated(self, cli):
        """长结果应该被截断到 200 字符。"""
        cli._show_thinking = True
        long_result = "x" * 300
        event = ToolResultEvent(
            name="read_file",
            call_id="call_123",
            result=long_result,
        )

        with patch("agent.cli.console") as mock_console:
            cli._on_tool_result(event)
            call_args = mock_console.print.call_args[0][0]
            assert "..." in call_args


# ---------------------------------------------------------------------------
# /model 命令
# ---------------------------------------------------------------------------

class TestModelSwitch:
    """测试 /model 命令的模型切换功能。"""

    @pytest.fixture
    def cli_with_models(self, tmp_path):
        """带预设模型列表的 CLI 实例。"""
        from agent.config import AgentConfig, SessionConfig
        from agent.session import SessionManager

        config = AgentConfig()
        config.llm = LLMConfig(
            api_key="test-key",
            model="model-a",
            provider="pa",
            base_url="https://a.com/v1",
            models=[
                ModelPreset(name="model-a", provider="pa", base_url="https://a.com/v1"),
                ModelPreset(name="model-b", provider="pb", base_url="https://b.com/v1"),
            ],
        )
        config.session = SessionConfig(dir=str(tmp_path / ".sessions"))
        config.config_path = tmp_path / "config.yaml"
        config.project_root = tmp_path

        session_mgr = SessionManager(config.resolved_session_dir())
        session = session_mgr.new_session()

        return CLI(config, session, session_mgr)

    def test_show_model_list(self, cli_with_models):
        """/model 无参数时显示模型列表。"""
        with patch("agent.cli.console") as mock_console:
            cli_with_models._handle_model_cmd(None)
            # 应该打印 Table + 帮助信息
            assert mock_console.print.call_count >= 1

    def test_switch_by_index(self, cli_with_models):
        """/model 2 按编号切换到第二个模型。"""
        with patch("agent.cli.console"):
            cli_with_models._handle_model_cmd("2")
        assert cli_with_models._config.llm.model == "model-b"
        assert cli_with_models._config.llm.provider == "pb"
        assert cli_with_models._config.llm.base_url == "https://b.com/v1"

    def test_switch_by_name(self, cli_with_models):
        """/model model-b 按名称切换。"""
        with patch("agent.cli.console"):
            cli_with_models._handle_model_cmd("model-b")
        assert cli_with_models._config.llm.model == "model-b"
        assert cli_with_models._config.llm.provider == "pb"

    def test_switch_custom_model(self, cli_with_models):
        """/model custom-model 自定义模型名只改 model，不动 provider。"""
        with patch("agent.cli.console"):
            cli_with_models._handle_model_cmd("custom-model")
        assert cli_with_models._config.llm.model == "custom-model"
        assert cli_with_models._config.llm.provider == "pa"  # 不变
        assert cli_with_models._config.llm.base_url == "https://a.com/v1"  # 不变

    def test_switch_invalid_index(self, cli_with_models):
        """/model 99 编号超出范围时返回错误。"""
        with patch("agent.cli.console") as mock_console:
            cli_with_models._handle_model_cmd("99")
        # 应该调用 _err_print，即 console.print 包含 [错误]
        call_args = str(mock_console.print.call_args)
        assert "错误" in call_args or "超出" in call_args

    def test_no_presets_allows_custom(self, cli):
        """无预设模型时，/model xxx 仍可直接设置自定义模型。"""
        with patch("agent.cli.console"):
            cli._handle_model_cmd("my-custom")
        assert cli._config.llm.model == "my-custom"

    def test_switch_persists_to_config_yaml(self, cli_with_models):
        """/model 切换后应将选择写回 config.yaml。"""
        import yaml
        cfg_path = cli_with_models._config.config_path
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump({"llm": {"model": "model-a", "provider": "pa", "base_url": "https://a.com/v1"}}, f)

        with patch("agent.cli.console"):
            cli_with_models._handle_model_cmd("2")

        with open(cfg_path, encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        assert saved["llm"]["model"] == "model-b"
        assert saved["llm"]["provider"] == "pb"
        assert saved["llm"]["base_url"] == "https://b.com/v1"

    def test_switch_persists_to_env(self, cli_with_models):
        """/model 切换后应同步更新 .env 中的 AGENT_MODEL 等变量。"""
        import yaml
        cfg_path = cli_with_models._config.config_path
        env_path = cli_with_models._config.project_root / ".env"
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump({"llm": {"model": "model-a"}}, f)
        env_path.write_text(
            "AGENT_API_KEY=old-key\nAGENT_MODEL=model-a\nAGENT_BASE_URL=https://a.com/v1\n",
            encoding="utf-8",
        )

        with patch("agent.cli.console"):
            cli_with_models._handle_model_cmd("2")

        env_content = env_path.read_text(encoding="utf-8")
        assert "AGENT_MODEL=model-b" in env_content
        assert "AGENT_BASE_URL=https://b.com/v1" in env_content
        assert "AGENT_API_KEY=test-key" in env_content
