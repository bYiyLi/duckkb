"""公平读写锁实现。"""

import threading
from contextlib import contextmanager
from typing import Generator


class FairReadWriteLock:
    """公平读写锁（避免写饥饿）。

    当有写请求在等待时，新的读请求必须排队。
    保证写操作最终能够执行，避免写饥饿问题。

    Attributes:
        _lock: 内部互斥锁。
        _read_ready: 读条件变量。
        _reader_count: 当前活跃的读线程数。
        _writer_waiting: 等待中的写线程数。
        _writer_active: 是否有写线程正在执行。
    """

    def __init__(self) -> None:
        """初始化公平读写锁。"""
        self._lock = threading.Lock()
        self._read_ready = threading.Condition(self._lock)
        self._reader_count = 0
        self._writer_waiting = 0
        self._writer_active = False

    @contextmanager
    def read_lock(self) -> Generator[None, None, None]:
        """获取读锁。

        如果有写请求在等待或写操作正在执行，新的读请求必须排队。
        """
        with self._lock:
            while self._writer_active or self._writer_waiting > 0:
                self._read_ready.wait()
            self._reader_count += 1
        try:
            yield
        finally:
            with self._lock:
                self._reader_count -= 1
                if self._reader_count == 0:
                    self._read_ready.notify_all()

    @contextmanager
    def write_lock(self) -> Generator[None, None, None]:
        """获取写锁（独占）。

        写操作需要等待所有读操作完成。
        """
        with self._lock:
            self._writer_waiting += 1
            while self._reader_count > 0 or self._writer_active:
                self._read_ready.wait()
            self._writer_waiting -= 1
            self._writer_active = True
        try:
            yield
        finally:
            with self._lock:
                self._writer_active = False
                self._read_ready.notify_all()
