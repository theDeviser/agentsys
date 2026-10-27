import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys.pipeline import PipelineError, expand  # noqa: E402
from agentsys.store import Store  # noqa: E402

from tests.helpers import IsolatedEnv  # noqa: E402


class TestPipeline(unittest.TestCase):
    def test_builtin_expand_and_deps(self):
        with IsolatedEnv() as env:
            env.cli("init", actor="human:v")
            specs = expand("research-implement", env.root, title="Feature", paths=["app/*"])
            self.assertEqual(len(specs), 2)
            st = Store(env.store_path())
            from agentsys.pipeline import create
            ids = create(st, "human:v", specs)
            self.assertEqual(len(ids), 2)
            impl = st.get(ids[1])
            self.assertEqual(impl["deps"], [ids[0]])

    def test_implement_requires_paths(self):
        with IsolatedEnv() as env:
            with self.assertRaises(PipelineError):
                expand("research-implement", env.root, title="X", paths=[])

    def test_pipeline_cli(self):
        with IsolatedEnv() as env:
            env.cli("init", actor="human:v")
            out = env.cli("pipeline", "research-implement", "My feat", "--path", "app/*", actor="human:v")
            lines = [l.strip() for l in out.stdout.splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
