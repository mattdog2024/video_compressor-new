"""最多三个任务并行调度的回归测试。"""
import unittest

from core.task_pool import TaskPool


class TaskPoolTests(unittest.TestCase):
    def test_starts_at_most_three_tasks(self):
        pool = TaskPool(3)
        pool.reset([1, 2, 3, 4, 5])
        started = []

        self.assertEqual(pool.start_available(started.append), [1, 2, 3])
        self.assertEqual(started, [1, 2, 3])
        self.assertEqual(pool.active, {1, 2, 3})
        self.assertEqual(list(pool.pending), [4, 5])

        pool.finish(2)
        self.assertEqual(pool.start_available(started.append), [4])
        self.assertEqual(pool.active, {1, 3, 4})
        self.assertEqual(list(pool.pending), [5])

    def test_limit_is_clamped_to_three(self):
        self.assertEqual(TaskPool(9).max_parallel_tasks, 3)
        self.assertEqual(TaskPool(0).max_parallel_tasks, 1)
        self.assertEqual(TaskPool("bad").max_parallel_tasks, 3)

    def test_cancel_clears_waiting_and_active_tasks(self):
        pool = TaskPool(3)
        pool.reset([1, 2, 3, 4])
        pool.start_available(lambda _: None)

        active = pool.cancel()
        self.assertEqual(set(active), {1, 2, 3})
        self.assertTrue(pool.is_idle)


if __name__ == "__main__":
    unittest.main()
