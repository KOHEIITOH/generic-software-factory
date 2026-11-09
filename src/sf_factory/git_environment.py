"""Git reads/materialization never inherit host repository redirection or global helpers."""
import os


def git_environment() -> dict[str, str]:
    return {**{k: v for k, v in os.environ.items() if not k.startswith('GIT_')},
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_SYSTEM': '/dev/null',
            'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_LAZY_FETCH': '1',
            'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_ALLOW_PROTOCOL': '',
            'GIT_TERMINAL_PROMPT': '0'}
