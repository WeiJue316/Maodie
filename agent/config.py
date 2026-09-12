"""
配置加载模块。

加载顺序（后者覆盖前者）：
  1. 内置默认值
  2. config.yaml
  3. .env 文件
  4. 系统环境变量
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# project_class/ 目录（本文件的上一级）
PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class ModelPreset:
    """预设模型配置。"""
    name: str
    provider: str = ""
    base_url: str = ""
    api_key: str = ""


@dataclass
class LLMConfig:
    provider: str = "minimax"
    api_key: str = ""
    base_url: str = "https://api.minimax.chat/v1"
    model: str = "MiniMax-M2.7"
    temperature: float = 0.7
    timeout: int = 60
    max_retries: int = 3
    streaming: bool = True
    models: list[ModelPreset] = field(default_factory=list)


@dataclass
class SessionConfig:
    dir: str = ".sessions"
    max_history: int = 100
    auto_save: bool = True


@dataclass
class SkillsConfig:
    dir: str = "skills"
    max_skills_in_prompt: int = 50
    max_prompt_chars: int = 10000


@dataclass
class MemoryConfig:
    enabled: bool = True
    file: str = "MEMORY.md"
    auto_inject: bool = True
    trigger_words: list[str] = field(default_factory=lambda: [
        "记住", "记一下", "记着", "别忘了",
        "remember", "keep in mind", "don't forget",
    ])


@dataclass
class ObservationConfig:
    """Observation 结构化记忆存储配置。"""
    enabled: bool = True
    db_path: str = ".memory/memory.db"
    extract_model: str = ""                # 空则使用主 LLM 模型
    extract_temperature: float = 0.3
    max_observations_per_session: int = 10


@dataclass
class VectorDBConfig:
    """ChromaDB 向量检索配置。"""
    enabled: bool = True
    persist_dir: str = ".memory/chroma"
    embedding_model: str = "all-MiniLM-L6-v2"
    collection_name: str = "observations"


@dataclass
class MemorySearchConfig:
    """混合检索与晋升配置。"""
    enabled: bool = True
    auto_search: bool = True
    search_limit: int = 5
    promotion_threshold: int = 3
    auto_promote: bool = True


@dataclass
class AgentSpec:
    """单个 agent 的定义（用于多 agent 协作）。"""
    name: str = ""
    system_prompt: str = ""
    model: str | None = None
    tools: list[str] | None = None
    max_iterations: int | None = None
    result_summary_prompt: str | None = None


@dataclass
class OrchestratorConfig:
    """编排器配置。"""
    enabled: bool = False
    task_timeout: int = 300
    llm_timeout: int | None = None
    max_concurrent_tasks: int = 3
    max_result_chars: int = 12000
    task_retention_seconds: int = 3600


@dataclass
class MCPServerConfig:
    """MCP Server 配置。"""
    name: str = ""
    transport: str = "stdio"           # stdio | sse | streamable_http
    # stdio 参数
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    # HTTP 参数 (sse / streamable_http)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    # 通用参数
    timeout: int = 30
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    observation: ObservationConfig = field(default_factory=ObservationConfig)
    vectordb: VectorDBConfig = field(default_factory=VectorDBConfig)
    memory_search: MemorySearchConfig = field(default_factory=MemorySearchConfig)
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)
    agents: dict[str, AgentSpec] = field(default_factory=dict)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    max_iterations: int = 20
    work_dir: str = "."
    system_prompt: str = (
        "你是一个智能助手，可以使用工具帮助用户完成任务。"
        "工作目录为 {work_dir}。"
        "在使用工具时，请逐步思考并说明你的操作意图。"
    )
    enabled_tools: list[str] = field(default_factory=lambda: [
        "read_file",
        "write_file",
        "list_dir",
        "change_dir",
        "shell",
        "search_files",
        "select_skill",
        "install_skill",
    ])

    # 运行时属性（非配置，由 load_config 填充）
    config_path: Path = field(default_factory=lambda: PROJECT_ROOT / "config.yaml")
    project_root: Path = field(default_factory=lambda: PROJECT_ROOT)

    def resolved_work_dir(self) -> Path:
        """返回绝对工作目录路径。"""
        p = Path(self.work_dir)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()

    def resolved_session_dir(self) -> Path:
        """返回绝对 session 目录路径。"""
        p = Path(self.session.dir)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()

    def resolved_skills_dir(self) -> Path:
        """返回绝对 skills 目录路径。"""
        p = Path(self.skills.dir)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()

    def resolved_memory_path(self) -> Path:
        """返回 MEMORY.md 的绝对路径。"""
        p = Path(self.memory.file)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()

    def resolved_db_path(self) -> Path:
        """返回 Observation SQLite 数据库的绝对路径。"""
        p = Path(self.observation.db_path)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()

    def resolved_vectordb_dir(self) -> Path:
        """返回 ChromaDB 持久化目录的绝对路径。"""
        p = Path(self.vectordb.persist_dir)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()

    def formatted_system_prompt(self) -> str:
        return self.system_prompt.format(work_dir=str(self.resolved_work_dir()))


# ---------------------------------------------------------------------------
# 加载逻辑
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个 dict，override 覆盖 base。"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _apply_env_overrides(cfg: AgentConfig) -> None:
    """将环境变量覆盖到配置对象上。"""
    overrides: dict[str, tuple[Any, str]] = {
        "AGENT_API_KEY":     (cfg.llm, "api_key"),
        "AGENT_BASE_URL":    (cfg.llm, "base_url"),
        "AGENT_MODEL":       (cfg.llm, "model"),
        "AGENT_WORK_DIR":    (cfg, "work_dir"),
        "AGENT_SKILLS_DIR":  (cfg.skills, "dir"),
    }
    for env_key, (obj, attr) in overrides.items():
        val = os.environ.get(env_key)
        if val is not None:
            setattr(obj, attr, val)


def _interpolate_env(value: str) -> str:
    """将 ${VAR_NAME} 替换为环境变量值。未定义的变量保持原样。"""
    def replacer(m: re.Match) -> str:
        var = m.group(1)
        return os.environ.get(var, m.group(0))
    return re.sub(r'\$\{(\w+)\}', replacer, value)


def _interpolate_env_dict(d: dict[str, str]) -> dict[str, str]:
    """递归展开 dict 中所有 value 的 ${VAR}。"""
    return {k: _interpolate_env(v) for k, v in d.items()}


def _validate_mcp_servers(servers: list[MCPServerConfig]) -> None:
    """校验 MCP Server 配置，不合法时抛出 ValueError。"""
    names: set[str] = set()
    for i, s in enumerate(servers):
        prefix = f"mcp_servers[{i}]"
        if not s.name:
            raise ValueError(f"{prefix}: name 不能为空")
        if s.name in names:
            raise ValueError(f"{prefix}: name '{s.name}' 重复")
        names.add(s.name)

        if s.transport not in ("stdio", "sse", "streamable_http"):
            raise ValueError(f"{prefix} ({s.name}): transport 必须是 stdio/sse/streamable_http，当前：{s.transport}")

        if s.transport == "stdio" and not s.command:
            raise ValueError(f"{prefix} ({s.name}): stdio 类型必须指定 command")

        if s.transport in ("sse", "streamable_http") and not s.url:
            raise ValueError(f"{prefix} ({s.name}): {s.transport} 类型必须指定 url")

        if s.timeout <= 0:
            raise ValueError(f"{prefix} ({s.name}): timeout 必须 > 0，当前：{s.timeout}")

        # 校验正则合法性
        for pattern_list, field_name in [(s.include, "include"), (s.exclude, "exclude")]:
            for p in pattern_list:
                try:
                    re.compile(p)
                except re.error as e:
                    raise ValueError(f"{prefix} ({s.name}): {field_name} 正则 '{p}' 不合法：{e}")


def load_config(config_path: Path | None = None) -> AgentConfig:
    """
    加载并返回 AgentConfig。

    Args:
        config_path: config.yaml 的路径，默认为 project_class/config.yaml
    """
    if config_path is None:
        config_path = PROJECT_ROOT / "config.yaml"

    # 1. 加载 .env（不覆盖已有环境变量）
    dotenv_path = PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path, override=False)

    # 2. 读取 yaml
    yaml_data = _read_yaml(config_path)

    # 3. 构建配置对象
    cfg = AgentConfig()
    cfg.config_path = config_path
    cfg.project_root = PROJECT_ROOT

    llm_data: dict = yaml_data.get("llm", {})
    for key, val in llm_data.items():
        if key == "models":
            continue  # 下面单独处理
        if hasattr(cfg.llm, key):
            setattr(cfg.llm, key, val)

    # 解析 models 预设列表
    raw_models = llm_data.get("models", [])
    if isinstance(raw_models, list):
        cfg.llm.models = [
            ModelPreset(
                name=m.get("name", ""),
                provider=m.get("provider", ""),
                base_url=m.get("base_url", ""),
                api_key=_interpolate_env(m.get("api_key", "")),
            )
            for m in raw_models
            if isinstance(m, dict) and m.get("name")
        ]

    session_data: dict = yaml_data.get("session", {})
    for key, val in session_data.items():
        if hasattr(cfg.session, key):
            setattr(cfg.session, key, val)

    agent_data: dict = yaml_data.get("agent", {})
    for key, val in agent_data.items():
        if key == "work_dir":
            cfg.work_dir = val
        elif key == "max_iterations":
            cfg.max_iterations = int(val)
        elif key == "system_prompt":
            cfg.system_prompt = val

    tools_data: dict = yaml_data.get("tools", {})
    if "enabled" in tools_data and isinstance(tools_data["enabled"], list):
        cfg.enabled_tools = tools_data["enabled"]

    skills_data: dict = yaml_data.get("skills", {})
    if "dir" in skills_data:
        cfg.skills.dir = str(skills_data["dir"])

    memory_data: dict = yaml_data.get("memory", {})
    for key, val in memory_data.items():
        if hasattr(cfg.memory, key):
            setattr(cfg.memory, key, val)

    observation_data: dict = yaml_data.get("observation", {})
    for key, val in observation_data.items():
        if hasattr(cfg.observation, key):
            setattr(cfg.observation, key, val)

    vectordb_data: dict = yaml_data.get("vectordb", {})
    for key, val in vectordb_data.items():
        if hasattr(cfg.vectordb, key):
            setattr(cfg.vectordb, key, val)

    memory_search_data: dict = yaml_data.get("memory_search", {})
    for key, val in memory_search_data.items():
        if hasattr(cfg.memory_search, key):
            setattr(cfg.memory_search, key, val)

    # 解析 mcp_servers 列表
    raw_mcp = yaml_data.get("mcp_servers", [])
    if isinstance(raw_mcp, list):
        for item in raw_mcp:
            if not isinstance(item, dict):
                continue
            mcp_cfg = MCPServerConfig()
            for key, val in item.items():
                if hasattr(mcp_cfg, key):
                    # url / env / headers 等字符串字段均支持 ${ENV_VAR} 插值，
                    # 便于把含令牌的 MCP 地址放进 .env，避免提交到公开仓库
                    setattr(mcp_cfg, key, _interpolate_env(val) if isinstance(val, str) else val)
            # 环境变量插值（env 和 headers 字段）
            mcp_cfg.env = _interpolate_env_dict(mcp_cfg.env)
            mcp_cfg.headers = _interpolate_env_dict(mcp_cfg.headers)
            cfg.mcp_servers.append(mcp_cfg)
        _validate_mcp_servers(cfg.mcp_servers)

    # 解析 agents（多 agent 协作）
    raw_agents: dict = yaml_data.get("agents", {})
    if isinstance(raw_agents, dict):
        for name, agent_def in raw_agents.items():
            if not isinstance(agent_def, dict):
                continue
            cfg.agents[name] = AgentSpec(
                name=name,
                system_prompt=agent_def.get("system_prompt", ""),
                model=agent_def.get("model"),
                tools=agent_def.get("tools"),
                max_iterations=agent_def.get("max_iterations"),
                result_summary_prompt=agent_def.get("result_summary_prompt"),
            )

    # 解析 orchestrator
    orch_data: dict = yaml_data.get("orchestrator", {})
    if isinstance(orch_data, dict):
        for key, val in orch_data.items():
            if hasattr(cfg.orchestrator, key):
                setattr(cfg.orchestrator, key, val)

    # 4. 环境变量覆盖
    _apply_env_overrides(cfg)

    return cfg
