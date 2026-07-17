from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from basalt_proof.cli import main
from basalt_proof.context_compiler import (
    classify_task,
    compile_context_for_repo,
    compile_context_pack,
    ensure_fresh_graph,
)
from basalt_proof.knowledge_graph import (
    GraphStore,
    analyze_impact,
    build_project_graph,
    check_graph_freshness,
    query_graph,
    write_graph_artifacts,
)
from basalt_proof.proof import verify_repo


class Phase2FixtureMixin:
    def write_fixture(self, root: Path) -> None:
        app = root / "app"
        frontend = root / "frontend"
        tests = root / "tests"
        db = root / "db"
        for folder in (app, frontend, tests, db):
            folder.mkdir(parents=True, exist_ok=True)
        (app / "__init__.py").write_text("", encoding="utf-8")
        (app / "auth.py").write_text(
            "from dataclasses import dataclass\n\n"
            "class APIRouter:\n"
            "    def post(self, path):\n"
            "        def decorator(function):\n"
            "            return function\n"
            "        return decorator\n\n"
            "router = APIRouter()\n\n"
            "@dataclass\n"
            "class Session:\n"
            "    token: str\n\n"
            "def validate_password(password: str) -> bool:\n"
            "    return len(password) >= 8\n\n"
            "@router.post('/auth/login')\n"
            "def login_user(email: str, password: str) -> Session:\n"
            "    if not validate_password(password):\n"
            "        raise ValueError('weak password')\n"
            "    return Session(token=email)\n",
            encoding="utf-8",
        )
        (app / "service.py").write_text(
            "from app.auth import login_user\n\n"
            "def create_session(email: str, password: str):\n"
            "    return login_user(email, password)\n",
            encoding="utf-8",
        )
        (tests / "test_auth.py").write_text(
            "import unittest\n"
            "from app.auth import login_user, validate_password\n\n"
            "class AuthTests(unittest.TestCase):\n"
            "    def test_login(self):\n"
            "        self.assertTrue(validate_password('12345678'))\n"
            "        self.assertEqual(login_user('a@b.com', '12345678').token, 'a@b.com')\n",
            encoding="utf-8",
        )
        (frontend / "authClient.ts").write_text(
            "export async function login(email: string, password: string) {\n"
            "  return fetch('/auth/login', { method: 'POST' });\n"
            "}\n",
            encoding="utf-8",
        )
        (frontend / "LoginPage.tsx").write_text(
            "import { login } from './authClient';\n"
            "export const LoginPage = () => login('a@b.com', '12345678');\n",
            encoding="utf-8",
        )
        (db / "schema.sql").write_text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY);\n"
            "CREATE TABLE sessions (user_id INTEGER REFERENCES users(id));\n",
            encoding="utf-8",
        )
        (root / "basalt.features.json").write_text(
            json.dumps(
                {
                    "features": [
                        {
                            "id": "login",
                            "name": "Login",
                            "description": "User login and session creation",
                            "keywords": ["auth", "login", "session"],
                            "files": [
                                "app/auth.py",
                                "app/service.py",
                                "frontend/LoginPage.tsx",
                                "frontend/authClient.ts",
                            ],
                            "tests": ["tests/test_auth.py"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (root / "basalt.yaml").write_text(
            "project:\n  name: phase2-fixture\n  type: python\n"
            "commands:\n  lint: python -m compileall app tests\n"
            "  test: python -m unittest discover -s tests -v\n"
            "proof:\n  require_lint: true\n  require_tests: true\n"
            "  mutation_sample: false\n  scan_exclude: frontend,db\n"
            "policy:\n  block_secrets: true\n  block_destructive_migrations: true\n"
            "sandbox:\n  mode: temp\n",
            encoding="utf-8",
        )


class ProjectKnowledgeGraphTests(Phase2FixtureMixin, unittest.TestCase):
    def test_python_ast_symbols_routes_and_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            names = {(item.name, item.kind) for item in graph.symbols}
            self.assertIn(("Session", "class"), names)
            self.assertIn(("login_user", "function"), names)
            self.assertIn(("POST /auth/login", "api_route"), names)
            self.assertTrue(any(item.edge_type == "calls" for item in graph.edges))
            login = next(item for item in graph.symbols if item.name == "login_user")
            self.assertIn("Session", login.return_type)

    def test_javascript_component_and_relative_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            component = next(item for item in graph.symbols if item.name == "LoginPage")
            self.assertEqual(component.kind, "component")
            self.assertTrue(
                any(
                    edge.edge_type == "imports"
                    and edge.source_file == "frontend/LoginPage.tsx"
                    and edge.target_file == "frontend/authClient.ts"
                    for edge in graph.edges
                )
            )

    def test_sql_schema_nodes_and_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            self.assertEqual(set(graph.schemas), {"sessions", "users"})
            self.assertTrue(any(item.edge_type == "references_table" for item in graph.edges))

    def test_python_import_graph_is_resolved_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            self.assertTrue(
                any(
                    edge.edge_type == "imports"
                    and edge.source_file == "app/service.py"
                    and edge.target_file == "app/auth.py"
                    for edge in graph.edges
                )
            )

    def test_file_to_test_mapping_uses_import_truth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            mapping = next(
                item
                for item in graph.test_mappings
                if item.test_file == "tests/test_auth.py" and item.source_file == "app/auth.py"
            )
            self.assertEqual(mapping.confidence, 1.0)
            self.assertIn("imports", mapping.reason)

    def test_explicit_feature_to_file_map_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            feature = next(item for item in graph.features if item.id == "login")
            self.assertEqual(feature.source, "explicit")
            self.assertIn("app/auth.py", feature.files)
            self.assertIn("tests/test_auth.py", feature.tests)
            self.assertTrue(any(item.edge_type == "implemented_by" for item in graph.edges))

    def test_graph_store_contains_relational_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            store = repo / ".basalt" / "knowledge-graph.sqlite3"
            graph = build_project_graph(repo, store)
            loaded = GraphStore(store).load()
            self.assertEqual(loaded.state_hash, graph.state_hash)
            with sqlite3.connect(store) as connection:
                symbol_count = connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
                edge_count = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
                feature_count = connection.execute("SELECT COUNT(*) FROM features").fetchone()[0]
            self.assertGreater(symbol_count, 0)
            self.assertGreater(edge_count, 0)
            self.assertGreater(feature_count, 0)

    def test_rebuild_reports_unchanged_files_as_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            store = repo / ".basalt" / "knowledge-graph.sqlite3"
            first = build_project_graph(repo, store)
            second = build_project_graph(repo, store)
            self.assertEqual(first.state_hash, second.state_hash)
            self.assertEqual(len(second.reused_files), second.files_scanned)
            self.assertEqual(second.changed_files, [])

    def test_freshness_detects_changed_new_and_removed_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            store = repo / ".basalt" / "knowledge-graph.sqlite3"
            build_project_graph(repo, store)
            self.assertTrue(check_graph_freshness(repo, store).fresh)
            (repo / "app" / "auth.py").write_text("def changed():\n    return True\n", encoding="utf-8")
            (repo / "app" / "new_module.py").write_text("VALUE = 1\n", encoding="utf-8")
            (repo / "app" / "service.py").unlink()
            status = check_graph_freshness(repo, store)
            self.assertFalse(status.fresh)
            self.assertIn("app/auth.py", status.changed_files)
            self.assertIn("app/new_module.py", status.new_files)
            self.assertIn("app/service.py", status.removed_files)

    def test_query_searches_symbols_files_and_features(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            result = query_graph(graph, "login")
            self.assertTrue(any(item["name"] == "login_user" for item in result["symbols"]))
            self.assertTrue(any(item["id"] == "login" for item in result["features"]))

    def test_impact_analysis_follows_reverse_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            impact = analyze_impact(graph, "app/auth.py", depth=3)
            self.assertTrue(impact.found)
            self.assertIn("app/service.py", impact.impacted_files)
            self.assertIn("tests/test_auth.py", impact.impacted_tests)
            self.assertIn("login", impact.impacted_features)
            self.assertIn(impact.risk_level, {"MEDIUM", "HIGH"})

    def test_graph_artifacts_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            paths = write_graph_artifacts(graph, repo / ".basalt")
            self.assertEqual(len(paths), 3)
            self.assertTrue(all(path.exists() for path in paths))


class ContextCompilerTests(Phase2FixtureMixin, unittest.TestCase):
    def test_task_classifier(self) -> None:
        self.assertEqual(classify_task("Fix the login authentication bug"), "bug_fix")
        self.assertEqual(classify_task("Write mutation tests for auth"), "testing")
        self.assertEqual(classify_task("Review database migration"), "migration")

    def test_context_pack_selects_target_and_related_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            pack = compile_context_pack(
                repo,
                graph,
                task="Fix the login session validation bug",
                agent_role="BackendAgent",
                targets=["app/auth.py"],
                token_budget=3000,
            )
            selected = {item["path"] for item in pack.files}
            self.assertIn("app/auth.py", selected)
            self.assertIn("tests/test_auth.py", pack.tests)
            self.assertIn("Login", pack.features)
            self.assertLessEqual(pack.estimated_tokens, pack.token_budget)
            self.assertEqual(pack.project_state_hash, graph.state_hash)

    def test_testing_agent_prioritizes_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            pack = compile_context_pack(
                repo,
                graph,
                task="Strengthen proof for login behavior",
                agent_role="TestingAgent",
                token_budget=4000,
            )
            selected = {item["path"] for item in pack.files}
            self.assertIn("tests/test_auth.py", selected)

    def test_context_pack_obeys_small_token_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            graph = build_project_graph(repo)
            pack = compile_context_pack(
                repo,
                graph,
                task="Review all login files",
                agent_role="CodeReviewAgent",
                token_budget=500,
            )
            self.assertLessEqual(pack.estimated_tokens, 500)
            self.assertGreaterEqual(len(pack.files), 1)

    def test_no_refresh_rejects_stale_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            store = repo / ".basalt" / "knowledge-graph.sqlite3"
            build_project_graph(repo, store)
            (repo / "app" / "auth.py").write_text("def changed():\n    return True\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                ensure_fresh_graph(repo, store, refresh=False)

    def test_context_compiler_auto_refreshes_and_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            output = repo / ".basalt"
            pack, artifacts = compile_context_for_repo(
                repo,
                output,
                task="Audit login security",
                agent_role="SecurityAgent",
                targets=["login_user"],
                token_budget=2500,
            )
            self.assertTrue(pack.freshness["fresh"])
            self.assertEqual(len(artifacts), 4)
            self.assertTrue(all(path.exists() for path in artifacts))
            latest = json.loads((output / "context-pack.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["context_pack_id"], pack.context_pack_id)


class Phase2CliAndIntegrationTests(Phase2FixtureMixin, unittest.TestCase):
    def run_cli(self, args: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(args)
        return code, output.getvalue()

    def test_graph_cli_build_status_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            code, output = self.run_cli(["graph", "build", str(repo)])
            self.assertEqual(code, 0)
            self.assertIn("Project Knowledge Graph", output)
            code, output = self.run_cli(["graph", "status", str(repo)])
            self.assertEqual(code, 0)
            self.assertIn("fresh: True", output)
            code, output = self.run_cli(["graph", "query", str(repo), "login"])
            self.assertEqual(code, 0)
            self.assertIn("login_user", output)

    def test_impact_and_context_cli_write_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            code, output = self.run_cli(["impact", str(repo), "app/auth.py"])
            self.assertEqual(code, 0)
            self.assertIn("Change Impact Analysis", output)
            self.assertTrue((repo / ".basalt" / "impact-analysis.json").exists())
            code, output = self.run_cli(
                [
                    "context",
                    str(repo),
                    "--task",
                    "Fix login auth",
                    "--role",
                    "BackendAgent",
                    "--target",
                    "app/auth.py",
                    "--budget",
                    "2000",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("Context Compiler", output)
            self.assertTrue((repo / ".basalt" / "context-pack.json").exists())

    def test_verify_persists_phase2_graph_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_fixture(repo)
            report = verify_repo(repo, sandbox_override="temp", output_dir=repo / ".basalt")
            self.assertEqual(report.final_status.value, "VERIFIED")
            self.assertTrue((repo / ".basalt" / "knowledge-graph.sqlite3").exists())
            self.assertTrue((repo / ".basalt" / "project-graph.json").exists())
            self.assertGreater(len(report.knowledge_graph.test_mappings), 0)
            artifact_names = {item.name for item in report.artifacts}
            self.assertIn("Knowledge Graph SQLite", artifact_names)
            self.assertIn("Project Graph JSON", artifact_names)


if __name__ == "__main__":
    unittest.main()
