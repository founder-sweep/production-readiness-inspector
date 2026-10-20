"""Lexically scoped, literal-only FastAPI/Uvicorn AST evidence."""
from __future__ import annotations

import ast

from .model import Analysis

HEALTH = {"/health", "/healthz", "/ready", "/readyz"}


class Locals(ast.NodeVisitor):
    def __init__(self):
        self.names = set()

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.names.add(node.id)

    def visit_FunctionDef(self, node):
        self.names.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef


class PythonInspector(ast.NodeVisitor):
    def __init__(self, path: str, analysis: Analysis):
        self.path, self.analysis = path, analysis
        self.env = {}
        self.scope = "module"
        self.apps = {}
        self.created = {}
        self.decorators = set()

    def resolve(self, node):
        if isinstance(node, ast.Name):
            return self.env.get(node.id)
        if isinstance(node, ast.Attribute):
            parent = self.resolve(node.value)
            if isinstance(parent, str):
                return f"{parent}.{node.attr}"
        return None

    def visit_Import(self, node):
        for alias in node.names:
            self.env[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name == "*":
                self.analysis.note("python_star_import_not_resolved", self.path, node.lineno)
                self.analysis.coverage["python"] = "partial"
            else:
                self.env[alias.asname or alias.name] = f"{node.module}.{alias.name}" if not node.level else None

    def visit_Assign(self, node):
        self.visit(node.value)
        value = self.created.get(id(node.value)) or self.resolve(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.env[target.id] = value
            else:
                for child in ast.walk(target):
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                        self.env[child.id] = None

    def visit_AnnAssign(self, node):
        if node.value:
            self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self.env[node.target.id] = self.created.get(id(node.value)) or self.resolve(node.value)

    def visit_AugAssign(self, node):
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self.env[node.target.id] = None

    def visit_FunctionDef(self, node):
        for decorator in node.decorator_list:
            self.decorators.add(id(decorator))
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default:
                self.visit(default)
        self.env[node.name] = None
        outer, scope = self.env, self.scope
        self.env = outer.copy()
        self.scope = f"{scope}/{node.name}"
        local = Locals()
        for statement in node.body:
            local.visit(statement)
        names = local.names | {arg.arg for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]}
        names |= {arg.arg for arg in [node.args.vararg, node.args.kwarg] if arg}
        for name in names:
            self.env[name] = None
        for statement in node.body:
            self.visit(statement)
        self.env, self.scope = outer, scope

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        outer, scope = self.env, self.scope
        self.env = outer.copy()
        self.scope = f"{scope}/{node.name}"
        for statement in node.body:
            self.visit(statement)
        self.env, self.scope = outer, scope
        self.env[node.name] = None

    def visit_Lambda(self, node):
        # A lambda introduces lexical bindings that are outside this profile.
        self.analysis.note("lambda_body_not_resolved", self.path, node.lineno)

    def visit_Call(self, node):
        name = self.resolve(node.func)
        is_app = name == "fastapi.FastAPI"
        is_router = name == "fastapi.APIRouter"
        is_uvicorn = name == "uvicorn.run"
        if is_app or is_router:
            key = ("app" if is_app else "router", id(node))
            self.created[id(node)] = key
            self.apps[key] = {"node": node, "scope": self.scope, "health": False}
            if is_app:
                self.analysis.coverage["fastapi"] = "syntax_only"
                for rule in ("PR-FASTAPI-001", "PR-FASTAPI-002"):
                    self.analysis.rule_states[rule] = "evaluated"
        if is_app or is_uvicorn:
            self.analysis.rule_states["PR-PY-001"] = "evaluated"
            field = "debug" if is_app else "reload"
            for keyword in node.keywords:
                if keyword.arg == field:
                    if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        self.analysis.emit("PR-PY-001", self.path, keyword.value.lineno,
                                           f"Recognized {'FastAPI' if is_app else 'uvicorn.run'} call has literal {field}=True.",
                                           [self.scope, ast.dump(node, include_attributes=False), field])
                    elif not isinstance(keyword.value, ast.Constant):
                        self.analysis.note("dynamic_development_setting_not_evaluated", self.path, keyword.value.lineno)
                        self.analysis.coverage["python"] = "partial"
                elif keyword.arg is None:
                    self.analysis.note("expanded_call_keywords_not_evaluated", self.path, node.lineno)
                    self.analysis.coverage["python"] = "partial"
        if isinstance(node.func, ast.Attribute):
            owner = self.resolve(node.func.value)
            if isinstance(owner, tuple) and owner in self.apps:
                method = node.func.attr
                if method == "include_router":
                    self.analysis.note("included_router_not_resolved", self.path, node.lineno)
                    self.analysis.coverage["fastapi"] = "partial"
                registered = id(node) in self.decorators or method == "add_api_route" and (len(node.args) >= 2 or any(key.arg == "endpoint" for key in node.keywords))
                if method in {"get", "api_route", "add_api_route"} and registered:
                    keywords = {key.arg: key.value for key in node.keywords}
                    route = node.args[0] if node.args else keywords.get("path")
                    methods = keywords.get("methods")
                    gets = methods is None or isinstance(methods, (ast.List, ast.Tuple)) and any(isinstance(item, ast.Constant) and item.value == "GET" for item in methods.elts)
                    if isinstance(route, ast.Constant) and route.value in HEALTH and gets:
                        self.apps[owner]["health"] = True
                        status = keywords.get("status_code")
                        if isinstance(status, ast.Constant) and type(status.value) is int and status.value >= 400:
                            self.analysis.emit("PR-FASTAPI-002", self.path, status.lineno,
                                               "A conventional GET health route declares a literal status_code >= 400.",
                                               [self.scope, ast.dump(node, include_attributes=False)])
                    elif route is not None and not isinstance(route, ast.Constant):
                        self.analysis.note("dynamic_route_not_resolved", self.path, node.lineno)
                        self.analysis.coverage["fastapi"] = "partial"
        self.generic_visit(node)

    def finish(self):
        for key, app in self.apps.items():
            if key[0] == "app" and not app["health"]:
                self.analysis.emit("PR-FASTAPI-001", self.path, app["node"].lineno,
                                   "No directly declared conventional GET health route was found for this constructor in this module. Included routers, custom paths and runtime behavior are not resolved.",
                                   [app["scope"], ast.dump(app["node"], include_attributes=False)], inference=True)


def inspect_python(data: bytes, path: str, analysis: Analysis):
    # ast.parse(bytes) honors Python encoding cookies. It does not import code.
    tree = ast.parse(data, filename="<analysis-input>")
    if sum(1 for _ in ast.walk(tree)) > 100000:
        raise ValueError("python_node_limit")
    if analysis.coverage["python"] != "partial":
        analysis.coverage["python"] = "analyzed"
    visitor = PythonInspector(path, analysis)
    visitor.visit(tree)
    visitor.finish()
