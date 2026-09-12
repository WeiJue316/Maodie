"""
test_config.py — 配置加载测试

覆盖 agent/config.py 的全部核心逻辑：
- 默认值
- yaml 覆盖默认值
- 环境变量优先级
- 路径解析
- system_prompt 占位符
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

import agent.config as config_module
from agent.config import AgentConfig, load_config


# ---------------------------------------------------------------------------
# 辅助：写 config yaml 到临时文件
# ---------------------------------------------------------------------------

def write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 测试：默认值
# ---------------------------------------------------------------------------

class TestDefaultValues:
    def test_default_llm_provider(self, tmp_path, monkeypatch):
        """无 config.yaml 时 llm.provider 为 minimax。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.llm.provider == "minimax"

    def test_default_llm_base_url(self, tmp_path, monkeypatch):
        """无 config.yaml 时 llm.base_url 指向 MiniMax。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert "minimax" in cfg.llm.base_url

    def test_default_api_key_is_empty(self, tmp_path, monkeypatch):
        """未配置 api_key 时默认为空字符串，不报错。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        # 确保环境变量中没有 AGENT_API_KEY
        monkeypatch.delenv("AGENT_API_KEY", raising=False)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.llm.api_key == ""

    def test_default_max_iterations(self, tmp_path, monkeypatch):
        """默认最大迭代次数为 20。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.max_iterations == 20

    def test_default_work_dir(self, tmp_path, monkeypatch):
        """默认 work_dir 为 '.'。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.work_dir == "."

    def test_default_enabled_tools(self, tmp_path, monkeypatch):
        """默认启用 8 个内置工具。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert set(cfg.enabled_tools) == {
            "read_file", "write_file", "list_dir",
            "change_dir", "shell", "search_files",
            "select_skill", "install_skill",
        }


# ---------------------------------------------------------------------------
# 测试：yaml 覆盖
# ---------------------------------------------------------------------------

class TestLoadFromYaml:
    def test_yaml_overrides_model(self, tmp_path, monkeypatch):
        """config.yaml 中的 llm.model 覆盖默认值。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.delenv("AGENT_MODEL", raising=False)
        cfg_path = write_yaml(tmp_path / "config.yaml", {"llm": {"model": "gpt-4o"}})
        cfg = load_config(cfg_path)
        assert cfg.llm.model == "gpt-4o"

    def test_yaml_overrides_temperature(self, tmp_path, monkeypatch):
        """config.yaml 中的 llm.temperature 被正确读取。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {"llm": {"temperature": 0.0}})
        cfg = load_config(cfg_path)
        assert cfg.llm.temperature == 0.0

    def test_yaml_overrides_max_iterations(self, tmp_path, monkeypatch):
        """config.yaml 中的 agent.max_iterations 被正确读取。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {"agent": {"max_iterations": 10}})
        cfg = load_config(cfg_path)
        assert cfg.max_iterations == 10

    def test_yaml_overrides_work_dir(self, tmp_path, monkeypatch):
        """config.yaml 中的 agent.work_dir 被正确读取。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.delenv("AGENT_WORK_DIR", raising=False)
        cfg_path = write_yaml(tmp_path / "config.yaml", {"agent": {"work_dir": "src"}})
        cfg = load_config(cfg_path)
        assert cfg.work_dir == "src"

    def test_yaml_overrides_session_dir(self, tmp_path, monkeypatch):
        """config.yaml 中的 session.dir 被正确读取。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {"session": {"dir": "my_sessions"}})
        cfg = load_config(cfg_path)
        assert cfg.session.dir == "my_sessions"

    def test_yaml_overrides_enabled_tools(self, tmp_path, monkeypatch):
        """config.yaml 中的 tools.enabled 列表被正确读取。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {
            "tools": {"enabled": ["read_file", "write_file"]}
        })
        cfg = load_config(cfg_path)
        assert cfg.enabled_tools == ["read_file", "write_file"]

    def test_partial_yaml_uses_defaults_for_rest(self, tmp_path, monkeypatch):
        """yaml 只写部分字段，其余字段仍使用默认值。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.delenv("AGENT_MODEL", raising=False)
        cfg_path = write_yaml(tmp_path / "config.yaml", {"llm": {"temperature": 0.5}})
        cfg = load_config(cfg_path)
        assert cfg.llm.temperature == 0.5
        assert cfg.llm.model == "MiniMax-M2.7"   # 其他字段保持默认
        assert cfg.max_iterations == 20


# ---------------------------------------------------------------------------
# 测试：环境变量优先级
# ---------------------------------------------------------------------------

class TestEnvVarOverrides:
    def test_env_overrides_api_key(self, tmp_path, monkeypatch):
        """AGENT_API_KEY 环境变量覆盖 yaml 中的 api_key。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("AGENT_API_KEY", "env-key-xyz")
        cfg_path = write_yaml(tmp_path / "config.yaml", {"llm": {"api_key": "yaml-key"}})
        cfg = load_config(cfg_path)
        assert cfg.llm.api_key == "env-key-xyz"

    def test_env_overrides_model(self, tmp_path, monkeypatch):
        """AGENT_MODEL 环境变量优先级高于 yaml。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("AGENT_MODEL", "env-model")
        cfg_path = write_yaml(tmp_path / "config.yaml", {"llm": {"model": "yaml-model"}})
        cfg = load_config(cfg_path)
        assert cfg.llm.model == "env-model"

    def test_env_overrides_base_url(self, tmp_path, monkeypatch):
        """AGENT_BASE_URL 环境变量覆盖 yaml 中的 base_url。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("AGENT_BASE_URL", "https://env.api.com/v1")
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.llm.base_url == "https://env.api.com/v1"

    def test_env_overrides_work_dir(self, tmp_path, monkeypatch):
        """AGENT_WORK_DIR 环境变量覆盖 yaml 中的 work_dir。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("AGENT_WORK_DIR", "/env/work")
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.work_dir == "/env/work"

    def test_env_without_yaml(self, tmp_path, monkeypatch):
        """无 yaml 时，环境变量也能生效。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("AGENT_API_KEY", "standalone-key")
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.llm.api_key == "standalone-key"


# ---------------------------------------------------------------------------
# 测试：路径解析
# ---------------------------------------------------------------------------

class TestPathResolution:
    def test_resolved_work_dir_relative(self, tmp_path, monkeypatch):
        """相对 work_dir 解析后是 project_root 下的绝对路径。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.delenv("AGENT_WORK_DIR", raising=False)
        cfg_path = write_yaml(tmp_path / "config.yaml", {"agent": {"work_dir": "src"}})
        cfg = load_config(cfg_path)
        cfg.project_root = tmp_path
        assert cfg.resolved_work_dir() == (tmp_path / "src").resolve()

    def test_resolved_work_dir_absolute(self, tmp_path, monkeypatch):
        """绝对路径的 work_dir 原样返回。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        abs_path = str(tmp_path / "abs_work")
        monkeypatch.setenv("AGENT_WORK_DIR", abs_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        cfg.project_root = tmp_path
        assert cfg.resolved_work_dir() == Path(abs_path)

    def test_resolved_session_dir(self, tmp_path, monkeypatch):
        """session.dir 相对路径解析为 project_root 下的绝对路径。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {"session": {"dir": "my_sess"}})
        cfg = load_config(cfg_path)
        cfg.project_root = tmp_path
        assert cfg.resolved_session_dir() == (tmp_path / "my_sess").resolve()


# ---------------------------------------------------------------------------
# 测试：system_prompt 格式化
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_formatted_system_prompt_contains_work_dir(self, tmp_path, monkeypatch):
        """{work_dir} 占位符被替换为实际工作目录。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.delenv("AGENT_WORK_DIR", raising=False)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        cfg.project_root = tmp_path
        prompt = cfg.formatted_system_prompt()
        assert "{work_dir}" not in prompt
        assert str(cfg.resolved_work_dir()) in prompt

    def test_custom_system_prompt_from_yaml(self, tmp_path, monkeypatch):
        """yaml 中自定义的 system_prompt 被加载。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        custom = "自定义提示词，工作目录：{work_dir}"
        cfg_path = write_yaml(tmp_path / "config.yaml", {"agent": {"system_prompt": custom}})
        cfg = load_config(cfg_path)
        cfg.project_root = tmp_path
        assert "自定义提示词" in cfg.formatted_system_prompt()


# ---------------------------------------------------------------------------
# 测试：模型预设列表
# ---------------------------------------------------------------------------

class TestModelPresets:
    def test_default_models_is_empty(self, tmp_path, monkeypatch):
        """未配置 models 时默认为空列表。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.llm.models == []

    def test_models_loaded_from_yaml(self, tmp_path, monkeypatch):
        """yaml 中的 models 列表被正确解析为 ModelPreset。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {
            "llm": {
                "models": [
                    {"name": "model-a", "provider": "pa", "base_url": "https://a.com/v1"},
                    {"name": "model-b", "provider": "pb", "base_url": "https://b.com/v1"},
                ]
            }
        })
        cfg = load_config(cfg_path)
        assert len(cfg.llm.models) == 2
        assert cfg.llm.models[0].name == "model-a"
        assert cfg.llm.models[0].provider == "pa"
        assert cfg.llm.models[1].name == "model-b"

    def test_models_with_optional_fields(self, tmp_path, monkeypatch):
        """models 条目的 provider 和 base_url 可以省略。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {
            "llm": {
                "models": [
                    {"name": "simple-model"},
                ]
            }
        })
        cfg = load_config(cfg_path)
        assert len(cfg.llm.models) == 1
        assert cfg.llm.models[0].name == "simple-model"
        assert cfg.llm.models[0].provider == ""
        assert cfg.llm.models[0].base_url == ""

    def test_models_without_name_skipped(self, tmp_path, monkeypatch):
        """没有 name 字段的 model 条目被跳过。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {
            "llm": {
                "models": [
                    {"name": "valid"},
                    {"provider": "no-name"},
                ]
            }
        })
        cfg = load_config(cfg_path)
        assert len(cfg.llm.models) == 1
        assert cfg.llm.models[0].name == "valid"


# ---------------------------------------------------------------------------
# 测试：多 agent 配置（agents + orchestrator）
# ---------------------------------------------------------------------------

class TestMultiAgentConfig:
    def test_default_agents_is_empty(self, tmp_path, monkeypatch):
        """未配置 agents 时默认为空 dict。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.agents == {}

    def test_default_orchestrator_disabled(self, tmp_path, monkeypatch):
        """未配置 orchestrator 时默认 enabled=False。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.orchestrator.enabled is False
        assert cfg.orchestrator.task_timeout == 300
        assert cfg.orchestrator.max_concurrent_tasks == 3
        assert cfg.orchestrator.max_result_chars == 12000
        assert cfg.orchestrator.task_retention_seconds == 3600

    def test_agents_loaded_from_yaml(self, tmp_path, monkeypatch):
        """yaml 中的 agents 被正确解析为 AgentSpec。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {
            "agents": {
                "architect": {
                    "system_prompt": "你是架构师",
                    "model": "gpt-4o",
                    "tools": ["read_file", "list_dir"],
                    "max_iterations": 15,
                },
                "coder": {
                    "system_prompt": "你是开发者",
                },
            }
        })
        cfg = load_config(cfg_path)
        assert len(cfg.agents) == 2
        assert "architect" in cfg.agents
        assert "coder" in cfg.agents
        assert cfg.agents["architect"].name == "architect"
        assert cfg.agents["architect"].system_prompt == "你是架构师"
        assert cfg.agents["architect"].model == "gpt-4o"
        assert cfg.agents["architect"].tools == ["read_file", "list_dir"]
        assert cfg.agents["architect"].max_iterations == 15
        # coder 只填了 system_prompt，其余为 None（继承默认）
        assert cfg.agents["coder"].system_prompt == "你是开发者"
        assert cfg.agents["coder"].model is None
        assert cfg.agents["coder"].tools is None
        assert cfg.agents["coder"].max_iterations is None

    def test_orchestrator_loaded_from_yaml(self, tmp_path, monkeypatch):
        """yaml 中的 orchestrator 配置被正确读取。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {
            "orchestrator": {
                "enabled": True,
                "task_timeout": 600,
                "max_concurrent_tasks": 5,
                "max_result_chars": 8000,
                "task_retention_seconds": 7200,
            }
        })
        cfg = load_config(cfg_path)
        assert cfg.orchestrator.enabled is True
        assert cfg.orchestrator.task_timeout == 600
        assert cfg.orchestrator.max_concurrent_tasks == 5
        assert cfg.orchestrator.max_result_chars == 8000
        assert cfg.orchestrator.task_retention_seconds == 7200

    def test_agent_spec_defaults(self, tmp_path, monkeypatch):
        """AgentSpec 未填字段保持 None，不覆盖主 config 默认值。"""
        monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
        cfg_path = write_yaml(tmp_path / "config.yaml", {
            "agents": {
                "minimal": {
                    "system_prompt": "最小 agent",
                }
            }
        })
        cfg = load_config(cfg_path)
        agent = cfg.agents["minimal"]
        assert agent.model is None
        assert agent.tools is None
        assert agent.max_iterations is None
        assert agent.result_summary_prompt is None
