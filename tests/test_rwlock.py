"""FairReadWriteLock 单元测试。

验证公平读写锁的核心功能：
1. 多读并发
2. 写操作独占
3. 写饥饿避免（公平性）
4. 读等待写完成后继续
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from duckkb.utils.rwlock import FairReadWriteLock


class TestFairReadWriteLockBasic:
    """基础功能测试。"""

    def test_read_lock_basic(self) -> None:
        """测试读锁基本功能。"""
        lock = FairReadWriteLock()
        counter = [0]

        with lock.read_lock():
            counter[0] += 1

        assert counter[0] == 1

    def test_write_lock_basic(self) -> None:
        """测试写锁基本功能。"""
        lock = FairReadWriteLock()
        counter = [0]

        with lock.write_lock():
            counter[0] += 1

        assert counter[0] == 1

    def test_multiple_read_locks_can_be_acquired(self) -> None:
        """测试多个读锁可以同时获取。"""
        lock = FairReadWriteLock()
        active_readers = [0]
        max_readers = [0]
        lock_count = 3

        def read_task() -> None:
            with lock.read_lock():
                active_readers[0] += 1
                max_readers[0] = max(max_readers[0], active_readers[0])
                time.sleep(0.05)
                active_readers[0] -= 1

        threads = [threading.Thread(target=read_task) for _ in range(lock_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_readers[0] == lock_count, "多个读锁应该可以同时获取"


class TestFairReadWriteLockWriteExclusion:
    """写操作独占测试。"""

    def test_write_lock_blocks_other_writers(self) -> None:
        """测试写锁阻塞其他写操作。"""
        lock = FairReadWriteLock()
        write_order: list[int] = []
        active_writer = [False]
        conflict_detected = [False]

        def write_task(writer_id: int) -> None:
            with lock.write_lock():
                if active_writer[0]:
                    conflict_detected[0] = True
                active_writer[0] = True
                write_order.append(writer_id)
                time.sleep(0.05)
                active_writer[0] = False

        threads = [threading.Thread(target=write_task, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not conflict_detected[0], "写操作应该互斥"
        assert len(write_order) == 3

    def test_write_lock_blocks_readers(self) -> None:
        """测试写锁阻塞读操作。"""
        lock = FairReadWriteLock()
        read_started_during_write = [False]
        write_started = threading.Event()
        read_completed = threading.Event()

        def write_task() -> None:
            with lock.write_lock():
                write_started.set()
                time.sleep(0.1)

        def read_task() -> None:
            write_started.wait()
            read_started_during_write[0] = True
            with lock.read_lock():
                read_completed.set()

        write_thread = threading.Thread(target=write_task)
        read_thread = threading.Thread(target=read_task)

        write_thread.start()
        read_thread.start()

        time.sleep(0.05)
        assert not read_completed.is_set(), "读操作应该等待写操作完成"

        write_thread.join()
        read_thread.join()

        assert read_completed.is_set(), "读操作应该在写操作完成后继续"


class TestFairReadWriteLockFairness:
    """公平性测试（写饥饿避免）。"""

    def test_writer_blocks_new_readers(self) -> None:
        """测试写请求阻塞新的读请求。"""
        lock = FairReadWriteLock()
        events = {
            "reader1_started": threading.Event(),
            "writer_queued": threading.Event(),
            "reader2_started": threading.Event(),
            "writer_completed": threading.Event(),
        }

        def reader1_task() -> None:
            with lock.read_lock():
                events["reader1_started"].set()
                events["writer_queued"].wait()
                time.sleep(0.05)

        def writer_task() -> None:
            events["writer_queued"].set()
            with lock.write_lock():
                events["writer_completed"].set()

        def reader2_task() -> None:
            events["writer_queued"].wait()
            with lock.read_lock():
                events["reader2_started"].set()

        t1 = threading.Thread(target=reader1_task)
        t2 = threading.Thread(target=writer_task)
        t3 = threading.Thread(target=reader2_task)

        t1.start()
        events["reader1_started"].wait()

        t2.start()
        events["writer_queued"].wait()
        time.sleep(0.02)

        t3.start()
        time.sleep(0.02)

        assert not events["reader2_started"].is_set(), "reader2 应该等待 writer 完成"

        t1.join()
        t2.join()
        t3.join()

        assert events["writer_completed"].is_set(), "writer 应该完成"
        assert events["reader2_started"].is_set(), "reader2 应该在 writer 完成后执行"

    def test_no_writer_starvation(self) -> None:
        """测试写饥饿避免。

        场景：持续不断的读请求不应该导致写请求永远无法执行。
        """
        lock = FairReadWriteLock()
        writer_completed = threading.Event()
        reader_count = [0]
        stop_readers = threading.Event()

        def continuous_reader() -> None:
            while not stop_readers.is_set():
                with lock.read_lock():
                    reader_count[0] += 1
                    time.sleep(0.01)

        def writer_task() -> None:
            time.sleep(0.05)
            with lock.write_lock():
                writer_completed.set()

        reader_threads = [threading.Thread(target=continuous_reader) for _ in range(3)]
        for t in reader_threads:
            t.start()

        writer_thread = threading.Thread(target=writer_task)
        writer_thread.start()

        writer_thread.join(timeout=2.0)

        stop_readers.set()
        for t in reader_threads:
            t.join(timeout=1.0)

        assert writer_completed.is_set(), "写操作应该能够完成（无写饥饿）"
        assert reader_count[0] > 0, "读操作应该有执行"

    def test_writer_order_is_fair(self) -> None:
        """测试写请求按公平顺序执行。"""
        lock = FairReadWriteLock()
        execution_order: list[str] = []
        barrier = threading.Barrier(3)

        def reader_task(name: str) -> None:
            barrier.wait()
            with lock.read_lock():
                execution_order.append(f"{name}_start")
                time.sleep(0.02)
                execution_order.append(f"{name}_end")

        def writer_task(name: str) -> None:
            barrier.wait()
            with lock.write_lock():
                execution_order.append(f"{name}_start")
                time.sleep(0.02)
                execution_order.append(f"{name}_end")

        threads = [
            threading.Thread(target=reader_task, args=("r1",)),
            threading.Thread(target=writer_task, args=("w1",)),
            threading.Thread(target=reader_task, args=("r2",)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert "w1_start" in execution_order, "写操作应该执行"


class TestFairReadWriteLockConcurrency:
    """并发场景测试。"""

    def test_high_concurrency_reads(self) -> None:
        """测试高并发读场景。"""
        lock = FairReadWriteLock()
        counter = [0]
        iterations = 100
        thread_count = 10

        def read_task() -> None:
            for _ in range(iterations):
                with lock.read_lock():
                    _ = counter[0]
                    time.sleep(0.001)

        threads = [threading.Thread(target=read_task) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_mixed_read_write_operations(self) -> None:
        """测试混合读写场景。"""
        lock = FairReadWriteLock()
        data = [0]
        errors: list[Exception] = []

        def read_task() -> None:
            try:
                for _ in range(10):
                    with lock.read_lock():
                        _ = data[0]
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        def write_task() -> None:
            try:
                for i in range(5):
                    with lock.write_lock():
                        data[0] = i
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        threads = [
            *[threading.Thread(target=read_task) for _ in range(5)],
            *[threading.Thread(target=write_task) for _ in range(2)],
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"并发操作出错: {errors}"

    def test_thread_pool_executor_compatibility(self) -> None:
        """测试与 ThreadPoolExecutor 兼容性。"""
        lock = FairReadWriteLock()
        results: list[int] = []
        data = [0]

        def write_task(value: int) -> None:
            with lock.write_lock():
                data[0] = value
                time.sleep(0.01)

        def read_task() -> int:
            with lock.read_lock():
                return data[0]

        with ThreadPoolExecutor(max_workers=4) as executor:
            write_futures = [executor.submit(write_task, i) for i in range(3)]
            for f in write_futures:
                f.result()

            read_futures = [executor.submit(read_task) for _ in range(5)]
            for f in read_futures:
                results.append(f.result())

        assert len(results) == 5
        assert all(r == 2 for r in results), "所有读操作应该读到最后的写入值"


class TestFairReadWriteLockEdgeCases:
    """边界条件测试。"""

    def test_nested_read_lock_not_supported(self) -> None:
        """测试嵌套读锁（当前实现不支持，应避免死锁）。"""
        lock = FairReadWriteLock()
        outer_acquired = threading.Event()
        inner_blocked = threading.Event()

        def nested_read() -> None:
            with lock.read_lock():
                outer_acquired.set()
                time.sleep(0.05)

        t = threading.Thread(target=nested_read)
        t.start()
        outer_acquired.wait()

        with lock.read_lock():
            inner_blocked.set()

        t.join()

        assert inner_blocked.is_set(), "外层读锁不应阻塞内层读锁（同一锁对象）"

    def test_lock_state_consistency_after_exception(self) -> None:
        """测试异常后锁状态一致性。"""
        lock = FairReadWriteLock()

        try:
            with lock.write_lock():
                raise ValueError("Test exception")
        except ValueError:
            pass

        with lock.read_lock():
            pass

        with lock.write_lock():
            pass

    def test_rapid_acquire_release(self) -> None:
        """测试快速获取释放锁。"""
        lock = FairReadWriteLock()
        iterations = 1000

        def rapid_read() -> None:
            for _ in range(iterations):
                with lock.read_lock():
                    pass

        def rapid_write() -> None:
            for _ in range(iterations // 10):
                with lock.write_lock():
                    pass

        threads = [
            threading.Thread(target=rapid_read),
            threading.Thread(target=rapid_read),
            threading.Thread(target=rapid_write),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()


class TestDBMixinIntegration:
    """DBMixin 与 FairReadWriteLock 集成测试。

    使用 engine fixture 测试实际的并发行为。
    """

    def test_execute_read_allows_concurrency(self, engine) -> None:
        """测试 execute_read 允许并发执行。"""
        engine.execute_write("CREATE TABLE test_rw (id INTEGER, value VARCHAR)")
        engine.execute_write("INSERT INTO test_rw VALUES (1, 'test')")

        active_readers = [0]
        max_readers = [0]
        lock = threading.Lock()

        def read_task() -> None:
            with lock:
                active_readers[0] += 1
                max_readers[0] = max(max_readers[0], active_readers[0])
            result = engine.execute_read("SELECT * FROM test_rw")
            with lock:
                active_readers[0] -= 1
            assert len(result) == 1

        threads = [threading.Thread(target=read_task) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_readers[0] > 1, "多个读操作应该可以并发执行"

    def test_execute_write_is_exclusive(self, engine) -> None:
        """测试 execute_write 独占执行。"""
        engine.execute_write("CREATE TABLE test_ex (id INTEGER)")
        engine.execute_write("INSERT INTO test_ex VALUES (1)")

        write_order: list[int] = []

        def write_task(value: int) -> None:
            engine.execute_write(f"INSERT INTO test_ex VALUES ({value})")
            write_order.append(value)

        threads = [threading.Thread(target=write_task, args=(i,)) for i in range(2, 7)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        result = engine.execute_read("SELECT COUNT(*) FROM test_ex")
        assert result[0][0] == 6, "所有写操作应该都成功执行"
        assert len(write_order) == 5, "所有写操作应该都完成"

    def test_write_transaction_rollback_on_error(self, engine) -> None:
        """测试写事务在错误时回滚。"""
        engine.execute_write("CREATE TABLE test_txn (id INTEGER, value VARCHAR)")
        engine.execute_write("INSERT INTO test_txn VALUES (1, 'initial')")

        try:
            with engine.write_transaction() as conn:
                conn.execute("INSERT INTO test_txn VALUES (2, 'in_transaction')")
                raise ValueError("Simulated error")
        except ValueError:
            pass

        result = engine.execute_read("SELECT COUNT(*) FROM test_txn")
        assert result[0][0] == 1, "事务应该回滚，数据不应改变"

    @pytest.mark.asyncio
    async def test_async_concurrent_operations(self, async_engine) -> None:
        """测试异步环境下的并发操作。"""
        import asyncio

        await asyncio.to_thread(async_engine.execute_write, "CREATE TABLE test_async (id INTEGER)")
        await asyncio.to_thread(async_engine.execute_write, "INSERT INTO test_async VALUES (1)")

        async def read_task() -> int:
            result = await asyncio.to_thread(
                async_engine.execute_read, "SELECT COUNT(*) FROM test_async"
            )
            return result[0][0]

        async def write_task(value: int) -> None:
            await asyncio.to_thread(
                async_engine.execute_write, f"INSERT INTO test_async VALUES ({value})"
            )

        write_coros = [write_task(i) for i in range(2, 7)]
        read_coros = [read_task() for _ in range(10)]

        await asyncio.gather(*write_coros)
        results = await asyncio.gather(*read_coros)

        assert all(r == 6 for r in results), "所有读操作应该读到最终数据"
