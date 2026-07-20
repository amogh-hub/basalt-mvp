from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from basalt_proof.command_center_server import create_command_center_server
from basalt_proof.workspace_service import BuildWorkspaceService, WorkspaceError


def make_repo(root: Path) -> Path:
    repo = root / 'repo'; repo.mkdir()
    (repo / 'app.py').write_text('def add(a, b):\n    return a + b\n', encoding='utf-8')
    (repo / 'tests').mkdir(); (repo / 'tests' / 'test_app.py').write_text('import unittest\n', encoding='utf-8')
    (repo / 'basalt.yaml').write_text('project:\n  name: phase7-demo\n  type: python\ncommands:\n  lint: python -m compileall app.py\n  test: python -m unittest discover -s tests -v\n', encoding='utf-8')
    return repo


class WorkspaceServiceTests(unittest.TestCase):
    def test_snapshot_declares_governed_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            data = BuildWorkspaceService(make_repo(Path(td))).snapshot()
            self.assertEqual(data['phase'], 7)
            self.assertTrue(data['capabilities']['editor'])
            self.assertFalse(data['capabilities']['arbitrary_shell'])

    def test_snapshot_declares_rc3_professional_capabilities(self):
        with tempfile.TemporaryDirectory() as td:
            data = BuildWorkspaceService(make_repo(Path(td))).snapshot()
            capabilities = data['capabilities']
            self.assertTrue(capabilities['multi_file_tabs'])
            self.assertTrue(capabilities['diff_before_save'])
            self.assertTrue(capabilities['diagnostics'])
            self.assertTrue(capabilities['git_visibility'])
            self.assertTrue(capabilities['resizable_layout'])

    def test_diff_preview_reports_changes_and_stale_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            service = BuildWorkspaceService(make_repo(Path(td)))
            opened = service.read_file('app.py')
            preview = service.diff_file('app.py', opened['content'] + '\nVALUE = 3\n', opened['sha256'])
            self.assertTrue(preview['changed'])
            self.assertFalse(preview['conflict'])
            self.assertEqual(preview['additions'], 2)
            (service.repo / 'app.py').write_text('external = True\n', encoding='utf-8')
            conflict = service.diff_file('app.py', 'proposed = True\n', opened['sha256'])
            self.assertTrue(conflict['conflict'])
            self.assertIn('proposed = True', conflict['unified_diff'])

    def test_diagnostics_detect_syntax_errors_and_clean_json(self):
        with tempfile.TemporaryDirectory() as td:
            service = BuildWorkspaceService(make_repo(Path(td)))
            broken = service.diagnostics('app.py', 'def broken(:\n    pass\n')
            self.assertEqual(broken['status'], 'ERROR')
            self.assertEqual(broken['errors'], 1)
            service.create_file('config.json', '{}\n')
            clean = service.diagnostics('config.json', '{"enabled": true}\n')
            self.assertEqual(clean['status'], 'CLEAN')

    def test_git_status_reports_branch_and_changes(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
            subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
            subprocess.run(['git', '-c', 'user.name=Basalt', '-c', 'user.email=basalt@example.com', 'commit', '-qm', 'initial'], cwd=repo, check=True)
            clean = BuildWorkspaceService(repo).git_status()
            self.assertTrue(clean['available'])
            self.assertFalse(clean['dirty'])
            (repo / 'app.py').write_text('changed = True\n', encoding='utf-8')
            dirty = BuildWorkspaceService(repo).git_status()
            self.assertTrue(dirty['dirty'])
            self.assertEqual(dirty['items'][0]['path'], 'app.py')

    def test_tree_excludes_protected_directories(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td)); (repo / '.git').mkdir(); (repo / '.git' / 'config').write_text('x')
            tree = BuildWorkspaceService(repo).tree(depth=3)
            names = json.dumps(tree)
            self.assertNotIn('.git', names)
            self.assertIn('app.py', names)

    def test_tree_excludes_generated_egg_info(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            generated = repo / 'demo.egg-info'; generated.mkdir(); (generated / 'PKG-INFO').write_text('generated')
            tree = BuildWorkspaceService(repo).tree(depth=3)
            self.assertNotIn('demo.egg-info', json.dumps(tree))

    def test_rc3_workspace_assets_declare_professional_interactions(self):
        root = Path(__file__).parents[1] / 'basalt_proof' / 'webui'
        html = (root / 'workspace.html').read_text(encoding='utf-8')
        js = (root / 'workspace.js').read_text(encoding='utf-8')
        self.assertIn('id="file-tabs"', html)
        self.assertIn('id="diff-dialog"', html)
        self.assertIn('id="command-palette"', html)
        self.assertIn('data-panel="proof"', html)
        self.assertIn('function renderTabs()', js)
        self.assertIn('async function reviewDiff()', js)
        self.assertIn('function installResizer', js)
        self.assertIn('function openPalette()', js)

    def test_rc3_css_contains_resizable_contained_workspace(self):
        css = (Path(__file__).parents[1] / 'basalt_proof' / 'webui' / 'workspace.css').read_text(encoding='utf-8')
        self.assertIn('--left-width:', css)
        self.assertIn('--right-width:', css)
        self.assertIn('grid-template-columns: var(--left-width) 4px minmax(420px, 1fr) 4px var(--right-width)', css)
        self.assertIn('.resizer', css)
        self.assertIn('.file-tabs', css)
        self.assertIn('.diff-output', css)

    def test_workspace_css_contains_terminal_inside_viewport(self):
        css = (Path(__file__).parents[1] / 'basalt_proof' / 'webui' / 'workspace.css').read_text(encoding='utf-8')
        self.assertIn('grid-template-rows: 52px minmax(0, 1fr) 28px', css)
        self.assertIn('grid-template-rows: auto auto auto minmax(0, 1fr)', css)
        self.assertIn('overflow: hidden', css)
        self.assertIn('#terminal', css)

    def test_read_and_optimistic_save(self):
        with tempfile.TemporaryDirectory() as td:
            service = BuildWorkspaceService(make_repo(Path(td)))
            opened = service.read_file('app.py')
            saved = service.save_file('app.py', opened['content'] + '\nVALUE = 1\n', opened['sha256'], 'Tester')
            self.assertIn('VALUE = 1', saved['content'])
            with self.assertRaises(WorkspaceError):
                service.save_file('app.py', 'stale', opened['sha256'])

    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            service = BuildWorkspaceService(make_repo(Path(td)))
            with self.assertRaises(WorkspaceError):
                service.read_file('../secret.txt')

    def test_protected_workspace_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td)); (repo / '.basalt').mkdir(); (repo / '.basalt' / 'x.txt').write_text('x')
            with self.assertRaises(WorkspaceError):
                BuildWorkspaceService(repo).read_file('.basalt/x.txt')

    def test_create_file_and_search(self):
        with tempfile.TemporaryDirectory() as td:
            service = BuildWorkspaceService(make_repo(Path(td)))
            service.create_file('pkg/new.py', 'SPECIAL_TOKEN = 7\n', 'Tester')
            result = service.search('SPECIAL_TOKEN')
            self.assertEqual(result['count'], 1)
            self.assertEqual(result['items'][0]['path'], 'pkg/new.py')

    def test_only_named_configured_commands_are_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            service = BuildWorkspaceService(make_repo(Path(td)))
            result = service.run_command('lint')
            self.assertEqual(result['status'], 'PASS')
            with self.assertRaises(WorkspaceError):
                service.run_command('rm -rf /')

    def test_events_are_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            service = BuildWorkspaceService(make_repo(Path(td)))
            opened = service.read_file('app.py')
            service.save_file('app.py', opened['content'], opened['sha256'], 'Tester')
            service.run_command('lint')
            self.assertEqual([e['event'] for e in service.events()], ['FILE_SAVED', 'COMMAND_RUN'])


class WorkspaceServerTests(unittest.TestCase):
    def request(self, server, method, path, body=None, token=None):
        c = HTTPConnection('127.0.0.1', server.server_address[1], timeout=20)
        headers={'Accept':'application/json'}; payload=None
        if body is not None: payload=json.dumps(body); headers['Content-Type']='application/json'
        if token: headers['X-Basalt-Action-Token']=token
        c.request(method,path,payload,headers); r=c.getresponse(); raw=r.read(); ct=r.getheader('Content-Type',''); c.close()
        return r.status, json.loads(raw.decode()) if 'json' in ct else raw

    def test_workspace_assets_and_read_api(self):
        with tempfile.TemporaryDirectory() as td:
            repo=make_repo(Path(td)); server=create_command_center_server(repo,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                status, html=self.request(server,'GET','/workspace'); self.assertEqual(status,200); self.assertIn(b'Build Workspace',html)
                status, data=self.request(server,'GET','/api/v1/workspace'); self.assertEqual(status,200); self.assertEqual(data['phase'],7)
                status, data=self.request(server,'GET','/api/v1/workspace/file?path=app.py'); self.assertEqual(status,200); self.assertIn('def add',data['content'])
            finally: server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_workspace_diff_diagnostics_and_git_apis(self):
        with tempfile.TemporaryDirectory() as td:
            repo=make_repo(Path(td)); server=create_command_center_server(repo,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                _, opened=self.request(server,'GET','/api/v1/workspace/file?path=app.py')
                status, diff=self.request(server,'POST','/api/v1/workspace/diff',{'path':'app.py','content':opened['content']+'\nVALUE=1\n','expected_sha256':opened['sha256']})
                self.assertEqual(status,200); self.assertTrue(diff['changed'])
                status, diagnostics=self.request(server,'POST','/api/v1/workspace/diagnostics',{'path':'app.py','content':'def broken(:\n'})
                self.assertEqual(status,200); self.assertEqual(diagnostics['status'],'ERROR')
                status, git=self.request(server,'GET','/api/v1/workspace/git')
                self.assertEqual(status,200); self.assertIn('available',git)
            finally: server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_workspace_write_requires_action_token(self):
        with tempfile.TemporaryDirectory() as td:
            repo=make_repo(Path(td)); server=create_command_center_server(repo,port=0,allow_actions=True,action_token='phase7-token')
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                _, opened=self.request(server,'GET','/api/v1/workspace/file?path=app.py')
                status, _=self.request(server,'POST','/api/v1/workspace/file',{'path':'app.py','content':'x=1\n','expected_sha256':opened['sha256']})
                self.assertEqual(status,403)
                status, saved=self.request(server,'POST','/api/v1/workspace/file',{'path':'app.py','content':'x=1\n','expected_sha256':opened['sha256']},'phase7-token')
                self.assertEqual(status,200); self.assertEqual(saved['content'],'x=1\n')
            finally: server.shutdown(); server.server_close(); thread.join(timeout=2)
