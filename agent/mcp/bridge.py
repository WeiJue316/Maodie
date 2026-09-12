"""
同步桥接：在后台线程运行 asyncio event loop，提供同步调用接口。
"""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import Any


class AsyncBridge:
    """后台 event loop 线程，将 async 调用包装为同步。"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台 event loop 线程。"""
        if self._loop is not None:
            return

        # Windows 上 ProactorEventLoop 与 subprocess (stdio MCP) 不兼容，
        # 强制使用 SelectorEventLoop。
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止 event loop。daemon 线程会在进程退出时自动终止。"""
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
        # 不 join — event loop 可能卡在 I/O 上，强制等待会阻塞退出。
        # daemon 线程会在进程退出时被操作系统回收。
        self._loop = None
        self._thread = None

    def run_sync(self, coro: Any, timeout: float | None = None) -> Any:
        """将 async coroutine 提交到后台 loop，同步等待结果。

        Args:
            coro: asyncio coroutine 对象
            timeout: 超时秒数，None 表示不限

        Returns:
            coroutine 的返回值

        Raises:
            RuntimeError: event loop 未启动
            TimeoutError: 执行超时
            Exception: coroutine 内部抛出的异常
        """
        if self._loop is None:
            raise RuntimeError("AsyncBridge 未启动，调用 start() 先")

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def _run_loop(self) -> None:
        """后台线程入口：运行 event loop。"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
