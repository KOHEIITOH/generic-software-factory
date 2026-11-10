"""Headless startup preserves local binding, operator URL, build and error behavior."""
import sys
from types import SimpleNamespace

import pytest

from sf_factory import web_launcher
from sf_factory.cli import build_parser, main


@pytest.mark.parametrize('arguments,rebuild,no_browser', [
    ([], False, False), (['--no-browser'], False, True),
    (['--rebuild'], True, False), (['--rebuild', '--no-browser'], True, True),
])
def test_cli_passes_optional_browser_flag_and_preserves_launcher_exit(monkeypatch, arguments,
                                                                    rebuild, no_browser):
    args = build_parser().parse_args(['web', *arguments])
    assert (args.rebuild, args.no_browser) == (rebuild, no_browser)
    calls = []
    monkeypatch.setattr(web_launcher, 'launch_web', lambda **kw: calls.append(kw) or 7)
    monkeypatch.setattr(sys, 'argv', ['sf', 'web', *arguments])
    assert main() == 7
    assert calls == [{'rebuild': rebuild, 'no_browser': no_browser}]


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    frontend = tmp_path / 'web'
    (frontend / 'dist').mkdir(parents=True)
    (frontend / 'dist/index.html').write_text('fixture')
    monkeypatch.setattr(web_launcher, '__file__', str(tmp_path / 'src/sf_factory/web_launcher.py'))
    monkeypatch.setattr('sf_factory.factory_selection.data_directory', lambda: tmp_path / 'state')
    monkeypatch.setattr('sf_factory.factory_selection.open_factory',
                        lambda root: SimpleNamespace(root=root))
    app = object()
    monkeypatch.setitem(sys.modules, 'sf_factory.web_api',
                        SimpleNamespace(create_app=lambda **kwargs: app))
    browsers, servers, builds = [], [], []
    monkeypatch.setattr(web_launcher.webbrowser, 'open', lambda url: browsers.append(url))
    monkeypatch.setattr('uvicorn.run', lambda *a, **kw: servers.append((a, kw)))
    monkeypatch.setattr(web_launcher.shutil, 'which', lambda name: '/fixture/npm')
    monkeypatch.setattr(web_launcher.subprocess, 'run',
        lambda command, **kw: builds.append((command, kw)) or SimpleNamespace(returncode=0))
    return SimpleNamespace(frontend=frontend, app=app, browsers=browsers, servers=servers,
                           builds=builds)


@pytest.mark.parametrize('no_browser', [False, True])
@pytest.mark.parametrize('rebuild', [False, True])
def test_optional_browser_keeps_server_and_operator_link(launcher, capsys, no_browser, rebuild):
    assert web_launcher.launch_web(rebuild=rebuild, no_browser=no_browser) == 0
    assert launcher.servers == [((launcher.app,), {
        'host': '127.0.0.1', 'port': 8000, 'proxy_headers': False})]
    output = capsys.readouterr().out
    url = output.split('Software Factory dashboard: ', 1)[1].strip()
    assert url.startswith('http://127.0.0.1:8000/#operator=')
    assert launcher.browsers == ([] if no_browser else [url])
    assert [command for command, _ in launcher.builds] == (
        [['npm', 'install', '--no-audit', '--no-fund'], ['npm', 'run', 'build']]
        if rebuild else [])
    assert all(kw == {'cwd': launcher.frontend, 'check': False} for _, kw in launcher.builds)


def test_headless_build_failure_does_not_start_server(launcher, monkeypatch):
    monkeypatch.setattr(web_launcher.subprocess, 'run',
                        lambda *a, **kw: SimpleNamespace(returncode=9))
    assert web_launcher.launch_web(rebuild=True, no_browser=True) == 9
    assert launcher.servers == launcher.browsers == []


def test_headless_storage_failure_does_not_start_server(launcher, monkeypatch, capsys):
    def unavailable(root):
        raise OSError('fixture unavailable')
    monkeypatch.setattr('sf_factory.factory_selection.open_factory', unavailable)
    assert web_launcher.launch_web(no_browser=True) == 2
    assert launcher.servers == launcher.browsers == []
    assert 'Could not open dashboard storage' in capsys.readouterr().err


def test_headless_server_failure_keeps_exit_code(launcher, monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise OSError('fixture unavailable')
    monkeypatch.setattr('uvicorn.run', unavailable)
    assert web_launcher.launch_web(no_browser=True) == 1
    assert launcher.browsers == []
    assert 'Could not start dashboard' in capsys.readouterr().err
