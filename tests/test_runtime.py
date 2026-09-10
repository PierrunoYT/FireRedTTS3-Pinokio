"""Exercise UI registration and GPU validation without downloading model weights."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


SOURCE = Path(__file__).resolve().parents[1] / "app" / "webui.py"


def load_function(name, namespace):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


class RuntimeTests(unittest.TestCase):
    def test_synthesis_events_share_one_serial_queue(self):
        buttons = []

        def button(*args, **kwargs):
            component = MagicMock()
            buttons.append(component)
            return component

        gr = MagicMock()
        gr.Button.side_effect = button
        handlers = {
            name: MagicMock() for name in (
                "run_clone", "run_voice_design", "run_semantic_edit",
                "run_acoustic_edit", "run_instruct_clone"
            )
        }
        build_ui = load_function("build_ui", {
            "gr": gr, "describe_runtime": lambda: "test GPU",
            "LANGUAGE_CHOICES": ["Auto-detect"], "AUTO_LANGUAGE": "Auto-detect",
            "advanced_block": lambda *args, **kwargs: [None] * 7,
            **handlers,
        })
        build_ui("models")
        registrations = [button.click.call_args for button in buttons]
        self.assertCountEqual([call.args[0] for call in registrations], handlers.values())
        groups = {call.kwargs.get("concurrency_id") for call in registrations}
        self.assertEqual(len(groups), 1)
        self.assertNotIn(None, groups)
        for call in registrations:
            self.assertEqual(call.kwargs["concurrency_limit"], 1)

    def check_gpu(self, native):
        cuda = MagicMock()
        cuda.is_available.return_value = True
        cuda.get_device_capability.return_value = (8, 0) if native else (7, 5)
        cuda.get_device_properties.return_value.total_memory = 24 * 1024 ** 3
        cuda.is_bf16_supported.side_effect = lambda including_emulation=True: native or including_emulation
        torch = MagicMock(cuda=cuda)
        check = load_function("check_runtime", {"torch": torch})
        module = SimpleNamespace(Qwen3_1_7B_ConfigDict={"attn_implementation": "sdpa"})
        with patch.dict("sys.modules", {"fireredtts3.llm.fireredtts3_base": module}):
            check()

    def test_rejects_emulated_bfloat16(self):
        with self.assertRaisesRegex(SystemExit, "no native bfloat16 support"):
            self.check_gpu(native=False)

    def test_accepts_native_bfloat16(self):
        self.check_gpu(native=True)


if __name__ == "__main__":
    unittest.main()
