"""Keep API calls on the host and run model-produced Python in isolated workers."""
import ast
import json
import os
import subprocess
from uuid import uuid4
import re
from types import SimpleNamespace
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.parse import urlsplit


def load_controller(source, api, execute_code):
    names = {"extract_python_code", "apply_calc"}
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != names:
        raise ValueError("Original controller functions missing")
    namespace = {
        "re": re, "openai": api, "capture_exec_output_and_errors": execute_code,
        "print": lambda *args: None,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "upstream/controller", "exec"), namespace)
    return namespace["apply_calc"]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
        headers = {"Content-Type": "application/json"}
        handlers = [NoRedirect()]
        if self.key is None:
            if self.base_url != "http://127.0.0.1:11434/v1":
                raise ValueError("Keyless requests are restricted to the local model server")
            payload["max_tokens"] = 192
            handlers.append(ProxyHandler({}))
        else:
            headers["Authorization"] = "Bearer " + self.key
        request = Request(self.base_url + "/chat/completions",
                          data=json.dumps(payload).encode(), headers=headers)
        with build_opener(*handlers).open(request, timeout=120 if self.key is None else 90) as response:
            body = json.load(response)
        text = body["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError("Expected text completion")
        self.records.append({
            "request": payload, "content": text, "model": body.get("model"), "usage": body.get("usage"),
        })
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def validate_image(image):
    if not re.fullmatch(r"[a-z0-9][a-zA-Z0-9/_.:-]*@sha256:[0-9a-f]{64}", image):
        raise ValueError("Expected a digest-pinned Docker image")


def docker_executor(source, image):
    """Run each model code block in a fresh, credential-free Docker worker."""
    validate_image(image)
    function = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "capture_exec_output_and_errors"
    )
    worker = (
        "import contextlib, io, sys, traceback\n"
        + ast.get_source_segment(source, function)
        + "\nsys.stdout.write(capture_exec_output_and_errors(sys.stdin.read())[:65536])"
    )
    docker_env = {name: os.environ[name] for name in ("PATH", "HOME", "XDG_RUNTIME_DIR") if name in os.environ}

    def execute(code):
        name = f"medcalc-code-{uuid4().hex}"
        command = [
            "docker", "run", "--rm", "--interactive", "--name", name,
            "--network=none", "--read-only", "--tmpfs=/tmp:size=16m",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
            "--cpus=1", "--memory=1g", "--pids-limit=32", "--log-driver=none",
            "--workdir=/tmp", image, "bash", "-c",
            'python -I -c "$1" 2>&1 | head -c 65536; code=${PIPESTATUS[0]}; '
            'test "$code" -eq 0 || test "$code" -eq 141',
            "medcalc-code", worker,
        ]
        try:
            result = subprocess.run(
                command, input=code, encoding="utf-8", errors="replace", capture_output=True,
                timeout=30, env=docker_env,
            )
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["docker", "rm", "-f", name], capture_output=True, check=False,
                timeout=15, env=docker_env,
            )
            return "Python execution timed out."
        if result.returncode:
            raise RuntimeError(f"Docker code worker failed: {result.stderr}")
        return result.stdout

    return execute


def run_controller(source, request, model, api, image):
    execute = docker_executor(source, image)
    answer, messages = load_controller(source, api, execute)(
        request["question"], request["patient_note"], model
    )
    return {
        "model": model,
        "messages": messages,
        "calls": api.records,
        "answer": "N/A" if answer is None else str(answer),
    }
