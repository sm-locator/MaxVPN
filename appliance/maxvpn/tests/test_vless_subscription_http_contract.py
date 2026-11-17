"""Exercise the real appliance POST dispatch without starting services.

The handler function is compiled from server.py and invoked with a harmless
fake transport/controller, so this test can run in CI without OpenWrt,
sing-box, real subscription credentials, or modifications to /etc/maxvpn.

This guards the important deployment-parity fix: invalid subscription
requests must return HTTP 422 rather than the generic upstream HTTP 502.
"""

import ast
import copy
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import pytest


SERVER = Path(__file__).resolve().parents[1] / "server.py"
PREVIEW = "/api/appliance/v1/vless/subscription/preview"
IMPORT = "/api/appliance/v1/vless/subscription/import"


class FakeSubscriptionError(Exception):
    pass


class FakeSubscriptionControl:
    def __init__(self, error=False):
        self.error = error
        self.calls = []

    def preview_subscription(self, payload):
        self.calls.append(("preview", payload))
        if self.error:
            raise FakeSubscriptionError("Недопустимая ссылка подписки.")
        return {"compatible": 1, "digest": "a" * 64}

    def import_subscription(self, payload):
        self.calls.append(("import", payload))
        if self.error:
            raise FakeSubscriptionError("Изменилось содержимое подписки.")
        return {"imported": 1, "updated": 0}


class FakeHandler:
    def __init__(self, path, payload):
        self.path = path
        self.payload = payload

    def read_json(self):
        return self.payload

    def send_json(self, code, body):
        return code, body

    def send_error_json(self, code, message):
        return code, str(message)


def compile_post_handler(controller):
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SERVER))
    classes = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Handler"
    ]
    assert len(classes) == 1
    methods = [
        node for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "do_POST"
    ]
    assert len(methods) == 1

    # Compile the actual handler, without server.py's startup side effects.
    module = ast.Module(body=[copy.deepcopy(methods[0])], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "re": re,
        "sqlite3": sqlite3,
        "urlparse": urlparse,
        "VLESS_CONTROL": controller,
        "VlessControlError": FakeSubscriptionError,
    }
    exec(compile(module, str(SERVER), "exec"), namespace)
    return namespace["do_POST"]


@pytest.mark.parametrize("route", [PREVIEW, IMPORT])
def test_subscription_errors_return_422_not_502(route):
    controller = FakeSubscriptionControl(error=True)
    do_post = compile_post_handler(controller)
    handler = FakeHandler(route, {"url": "http://invalid.example/"})

    status, message = do_post(handler)

    assert status == 422
    assert "подписки" in message
    assert controller.calls == [
        ("preview" if route == PREVIEW else "import", handler.payload)
    ]


@pytest.mark.parametrize("route", [PREVIEW, IMPORT])
def test_subscription_routes_delegate_and_return_200(route):
    controller = FakeSubscriptionControl()
    do_post = compile_post_handler(controller)
    handler = FakeHandler(route, {"url": "https://example.test/sub"})

    status, body = do_post(handler)

    assert status == 200
    if route == PREVIEW:
        assert body["compatible"] == 1
    else:
        assert body["imported"] == 1
    assert controller.calls == [
        ("preview" if route == PREVIEW else "import", handler.payload)
    ]
