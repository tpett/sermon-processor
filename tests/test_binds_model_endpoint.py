import ast
import json
import os
import re
from pathlib import Path

from sermon.binds_model_endpoint import BindsModelEndpoint
from sermon.config import ReadsConfiguration
from sermon.pipeline import classify
from test_config import ENVIRONMENT

HARDCODED_HOST = re.compile(r"https?://|localhost|mac-m1", re.I)
BINDER = Path(__file__).resolve().parents[1] / "src" / "sermon" / "binds_model_endpoint.py"


class AnswersLikeAHost:
    def __init__(self, replies):
        self.replies = list(replies)
        self.urls = []
        self.requests = []

    def __call__(self, request, timeout=None):
        self.urls.append(request.full_url)
        self.requests.append(request)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *failure):
        return False

    def read(self):
        return json.dumps({"response": self.replies[0]}).encode()


def test_a_substituted_model_endpoint_is_the_host_the_pipeline_posts_to(monkeypatch):
    substitute = "http://127.0.0.1:1"
    configuration = ReadsConfiguration(
        environment=ENVIRONMENT | {"SERMON_MODEL_ENDPOINT": substitute}
    )()
    host = AnswersLikeAHost(['{"ok": 1}'])
    monkeypatch.setattr(classify.urllib.request, "urlopen", host)
    try:
        BindsModelEndpoint(configuration)()
        assert classify.ENDPOINT == substitute
        assert classify.ollama("a-model", "ask") == '{"ok": 1}'
        assert host.urls == ["http://127.0.0.1:1/api/generate"]
        headers = {
            key.lower(): value for key, value in host.requests[0].header_items()
        }
        assert "authorization" not in headers
        assert {
            key for key in headers if any(part in key for part in ("auth", "token", "key"))
        } == set()
        assert "SERMON_MODEL_ENDPOINT" not in os.environ
    finally:
        classify.ENDPOINT = None


def test_nothing_in_the_process_start_bind_hardcodes_a_host():
    tree = ast.parse(BINDER.read_text(encoding="utf-8"))
    offenders = [
        f"{BINDER.name}:{node.lineno}:{node.value}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and HARDCODED_HOST.search(node.value)
    ]
    assert offenders == []
