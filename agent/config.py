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


# 运行时 LLMConfig 中「当前生效」的字段，用于拷贝后覆盖 active 预置的 key/base_url
_LLM_MERGE_FIELDS = (
    "provider",
    "model",
    "base_url",
    "api_key",
    "temperature",
    "timeout",
    "max_retries",
    "streaming",
)


def active_llm_config(cfg: "AgentConfig") -> LLMConfig:
    """按当前选中的 model 解析出真正生效的 LLMConfig。

    配置里 model 可能是全局的 MiniMax，也可能切到 `llm.models` 中的某个预置
    （带独立 base_url / api_key）。此函数把该预置的 base_url / api_key 合并进
    拷贝，使「切换模型/Provider 后请求用对应预置的端点与密钥」成立。
    未命中的情况回落到全局值；api_key 一律只在服务端解析，永不回传前端。
    """
    merged = LLMConfig()
    for f in _LLM_MERGE_FIELDS:
        setattr(merged, f, getattr(cfg.llm, f))

    active = next((m for m in cfg.llm.models if m.name == cfg.llm.model), None)
    if active:
        if active.base_url:
            merged.base_url = active.base_url
        if active.api_key:
            merged.api_key = active.api_key
        if active.provider:
            merged.provider = active.provider
    return merged


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


RUNTIME_CONFIG_NAME = ".runtime_config.yaml"

# Web 可编辑的顶层配置段 → 字段映射，用于运行时覆盖文件的读写
_RUNTIME_SECTIONS: dict[str, tuple[str, ...]] = {
    "llm": ("provider", "model", "base_url", "temperature", "timeout", "streaming"),
    "agent": ("max_iterations", "work_dir", "system_prompt"),
    "session": ("dir", "max_history", "auto_save"),
    "memory": ("enabled",),
    "observation": ("enabled", "db_path"),
    "vectordb": ("enabled",),
    "memory_search": ("enabled", "search_limit", "promotion_threshold"),
}


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _apply_runtime_overlay(cfg: AgentConfig, data: dict[str, Any]) -> None:
    """把 Web 保存的运行时配置叠加到已构建的对象上（优先级最高）。"""
    llm = data.get("llm") or {}
    for k in _RUNTIME_SECTIONS["llm"]:
        if k in llm:
            setattr(cfg.llm, k, llm[k])
    if llm.get("api_key"):
        cfg.llm.api_key = llm["api_key"]
    if isinstance(llm.get("models"), list):
        cfg.llm.models = [
            ModelPreset(
                name=m.get("name", ""),
                provider=m.get("provider", ""),
                base_url=m.get("base_url", ""),
                api_key=m.get("api_key", ""),
            )
            for m in llm["models"]
            if isinstance(m, dict) and m.get("name")
        ]

    for sec, keys in _RUNTIME_SECTIONS.items():
        if sec == "llm":
            continue
        obj = data.get(sec) or {}
        # "agent" 段的 max_iterations/work_dir/system_prompt 是 AgentConfig 顶层字段
        src = cfg if sec == "agent" else getattr(cfg, sec)
        for k in keys:
            if k in obj:
                setattr(src, k, obj[k])


def save_config(cfg: AgentConfig, *, include_global_key: bool = False) -> Path:
    """把用户可在 Web 编辑的运行时配置持久化到独立的 `.runtime_config.yaml`。

    不改动私有 `config.yaml`（其中的 mcp URL 令牌与 api key 占位保持原样），
    api key 只写本地个人的、已被 gitignore 的覆盖文件。
    """
    llm: dict[str, Any] = {
        k: getattr(cfg.llm, k)
        for k in _RUNTIME_SECTIONS["llm"]
    }
    if include_global_key and cfg.llm.api_key:
        llm["api_key"] = cfg.llm.api_key
    llm["models"] = [
        {"name": m.name, "provider": m.provider, "base_url": m.base_url}
        | ({"api_key": m.api_key} if m.api_key else {})
        for m in cfg.llm.models
    ]

    out: dict[str, Any] = {"llm": llm}
    for sec, keys in _RUNTIME_SECTIONS.items():
        if sec == "llm":
            continue
        src = cfg if sec == "agent" else getattr(cfg, sec)
        out[sec] = {k: getattr(src, k) for k in keys}

    path = cfg.config_path.parent / RUNTIME_CONFIG_NAME
    _write_yaml(path, out)
    return path


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

    # 5. 运行时覆盖（Web 保存的配置）—— 优先级最高，重启后仍生效
    runtime_path = config_path.parent / RUNTIME_CONFIG_NAME
    if runtime_path.exists():
        _apply_runtime_overlay(cfg, _read_yaml(runtime_path))

    return cfg
