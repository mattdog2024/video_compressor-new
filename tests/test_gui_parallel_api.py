"""防止 GUI 把 TaskPool 的状态属性误当成方法调用。"""
import ast
import unittest
from pathlib import Path


class GuiParallelApiTests(unittest.TestCase):
    def test_task_pool_state_properties_are_not_called(self):
        app_path = Path(__file__).parents[1] / "gui" / "app.py"
        tree = ast.parse(app_path.read_text(encoding="utf-8"))
        invalid_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"has_work", "is_idle"}:
                    invalid_calls.append((node.func.attr, node.lineno))
        self.assertEqual(invalid_calls, [])


if __name__ == "__main__":
    unittest.main()
