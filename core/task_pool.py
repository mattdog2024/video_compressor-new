"""有上限的批量任务调度器。"""
from collections import deque
from typing import Callable, Deque, Iterable, List, Set


class TaskPool:
    """管理等待和运行中的任务，硬性限制最多同时运行三个。"""

    MAX_PARALLEL_TASKS = 3

    def __init__(self, max_parallel_tasks: int = MAX_PARALLEL_TASKS):
        self.max_parallel_tasks = self._clamp_limit(max_parallel_tasks)
        self.pending: Deque[int] = deque()
        self.active: Set[int] = set()

    @classmethod
    def _clamp_limit(cls, value: int) -> int:
        try:
            return max(1, min(cls.MAX_PARALLEL_TASKS, int(value)))
        except (TypeError, ValueError):
            return cls.MAX_PARALLEL_TASKS

    def set_max_parallel_tasks(self, value: int) -> None:
        """更新并发上限，范围固定在 1 到 3。"""
        self.max_parallel_tasks = self._clamp_limit(value)

    def reset(self, task_ids: Iterable[int]) -> None:
        """装入一批新任务；调用方须确保上一批已经结束。"""
        self.pending = deque(task_ids)
        self.active.clear()

    def start_available(self, start_callback: Callable[[int], None]) -> List[int]:
        """启动所有空闲槽位可容纳的任务，返回本轮启动的任务 ID。"""
        started: List[int] = []
        while self.pending and len(self.active) < self.max_parallel_tasks:
            task_id = self.pending.popleft()
            self.active.add(task_id)
            started.append(task_id)
            start_callback(task_id)
        return started

    def finish(self, task_id: int) -> None:
        """标记一个运行任务已结束。"""
        self.active.discard(task_id)

    def cancel(self) -> List[int]:
        """清空等待队列并返回正在运行的任务 ID。"""
        active_ids = list(self.active)
        self.pending.clear()
        self.active.clear()
        return active_ids

    @property
    def is_idle(self) -> bool:
        return not self.pending and not self.active

    @property
    def has_work(self) -> bool:
        return bool(self.pending or self.active)
