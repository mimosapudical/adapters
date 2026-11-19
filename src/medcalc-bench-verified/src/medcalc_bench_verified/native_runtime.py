"""Execute the pinned original chat/code controller inside a disposable container.

No API calls happen at import. The CLI refuses host execution. The original
controller's code execution must never be invoked on the orchestration host.
"""
import argparse
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import re
import traceback
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def load_controller(source, api):
    names = {"capture_exec_output_and_errors", "extract_python_code", "apply_calc"}
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != names:
        raise ValueError("Original controller functions missing")
    namespace = {"contextlib": contextlib, "io": io, "re": re,
                 "traceback": traceback, "openai": api}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "upstream/controller", "exec"), namespace)
    return namespace["apply_calc"]


class ChatAPI:
    def __init__(self, model, base_url, key):
        u = urlsplit(base_url)
        if u.scheme != "https" or not u.netloc or u.username or u.password or u.query or u.fragment:
            raise ValueError("API base must be an HTTPS URL without credentials or query")
        self.model, self.base_url, self.key = model, base_url.rstrip("/"), key
        self.records = []
        self.ChatCompletion = self

    def create(self, model, messages):
        if model != self.model:
            raise ValueError("Unexpected model substitution")
        # Snapshot before the original controller mutates its message list.
        payload = {"model": model, "messages": json.loads(json.dumps(messages))}
        request = Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode(),
                          headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        with urlopen(request, timeout=90) as response:
            body = json.load(response)
        text = body["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError("Expected text completion")
        self.records.append({"request": payload, "response": body})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("MEDCALC_SANDBOX") != "1" or not Path("/.dockerenv").exists():
        raise RuntimeError("This code-executing controller must run inside Docker")
    model = os.environ["MODEL_NAME"]
    api = ChatAPI(model, os.environ["OPENAI_BASE_URL"], os.environ["OPENAI_API_KEY"])
    task = json.loads(args.request.read_text())
    controller = load_controller(args.source.read_text(), api)
    answer, messages = None, []
    try:
        answer, messages = controller(task["question"], task["patient_note"], model)
    finally:
        args.trace.parent.mkdir(parents=True, exist_ok=True)
        args.trace.write_text(json.dumps({"model": model, "messages": messages, "calls": api.records, "answer": answer}, indent=2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # The upstream controller returns None at its turn limit; represent an
    # ordinary failed answer without treating API or container errors as zero.
    args.output.write_text("N/A" if answer is None else str(answer))


if __name__ == "__main__":
    main()
