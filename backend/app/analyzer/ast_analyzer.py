"""Python AST Analyzer for extracting semantic structural changes between revisions."""
from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.app.analyzer.models import ChangeType, CodeChange


@dataclass
class FunctionSignature:
    name: str
    args: list[str]
    defaults: dict[str, str]
    vararg: Optional[str] = None
    kwarg: Optional[str] = None
    return_annotation: Optional[str] = None
    docstring: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    line_number: int = 1
    api_endpoint: Optional[dict[str, str]] = None


@dataclass
class ClassStructure:
    name: str
    bases: list[str]
    methods: dict[str, FunctionSignature] = field(default_factory=dict)
    line_number: int = 1


def _node_to_str(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _extract_api_endpoint(decorator: ast.expr) -> Optional[dict[str, str]]:
    """Detects route decorators such as @app.get('/users'), @router.post('/login'), @app.route('/items', methods=['POST'])."""
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    method = None
    path = None

    if isinstance(func, ast.Attribute):
        attr_name = func.attr.lower()
        if attr_name in {"get", "post", "put", "delete", "patch", "options", "head"}:
            method = attr_name.upper()
            if decorator.args:
                path = _node_to_str(decorator.args[0])
        elif attr_name == "route":
            method = "GET"
            if decorator.args:
                path = _node_to_str(decorator.args[0])
            for kw in decorator.keywords:
                if kw.arg == "methods":
                    method = _node_to_str(kw.value) or "GET"

    if path:
        # Strip quotes
        path = path.strip("'\"")
        return {"method": method or "GET", "path": path}
    return None


class CodeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.constants: dict[str, tuple[str, int]] = {}
        self.functions: dict[str, FunctionSignature] = {}
        self.classes: dict[str, ClassStructure] = {}
        self.env_vars: dict[str, tuple[Optional[str], int]] = {}
        self.flags: dict[str, tuple[Optional[str], int]] = {}  # "--timeout" -> (default, line)
        self.current_class: Optional[str] = None
        self.current_function: Optional[str] = None

    def visit_Assign(self, node: ast.Assign) -> None:
        # Only top-level/module constant assignments (never local variables inside functions or classes)
        if not self.current_class and not self.current_function:
            val_str = _node_to_str(node.value) or ""
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.constants[target.id] = (val_str, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # Only top-level/module annotated assignments (never inside functions or classes)
        if not self.current_class and not self.current_function and isinstance(node.target, ast.Name) and node.value:
            val_str = _node_to_str(node.value) or ""
            self.constants[node.target.id] = (val_str, node.lineno)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node)

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args_list: list[str] = [a.arg for a in node.args.args]
        defaults_dict: dict[str, str] = {}

        # Default values align with the end of positional args
        diff_count = len(node.args.args) - len(node.args.defaults)
        for i, default_node in enumerate(node.args.defaults):
            param_name = node.args.args[diff_count + i].arg
            defaults_dict[param_name] = _node_to_str(default_node) or ""

        ret_annot = _node_to_str(node.returns)
        docstring = ast.get_docstring(node)
        decorators = [_node_to_str(d) or "" for d in node.decorator_list]

        api_endpoint = None
        for d in node.decorator_list:
            ep = _extract_api_endpoint(d)
            if ep:
                api_endpoint = ep
                break

        sig = FunctionSignature(
            name=node.name,
            args=args_list,
            defaults=defaults_dict,
            vararg=node.args.vararg.arg if node.args.vararg else None,
            kwarg=node.args.kwarg.arg if node.args.kwarg else None,
            return_annotation=ret_annot,
            docstring=docstring,
            decorators=decorators,
            line_number=node.lineno,
            api_endpoint=api_endpoint,
        )

        if self.current_class:
            if self.current_class in self.classes:
                self.classes[self.current_class].methods[node.name] = sig
        else:
            self.functions[node.name] = sig

        # Save class and function state for inner functions/scopes
        old_class = self.current_class
        old_func = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_class = old_class
        self.current_function = old_func

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [_node_to_str(b) or "" for b in node.bases]
        self.classes[node.name] = ClassStructure(
            name=node.name,
            bases=bases,
            line_number=node.lineno,
        )
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_Call(self, node: ast.Call) -> None:
        # Detect os.getenv("VAR", default) or os.environ.get("VAR")
        call_str = _node_to_str(node.func) or ""
        if call_str in {"os.getenv", "os.environ.get"} and node.args:
            var_name = _node_to_str(node.args[0])
            if var_name:
                var_name = var_name.strip("'\"")
                default_val = _node_to_str(node.args[1]) if len(node.args) > 1 else None
                self.env_vars[var_name] = (default_val, node.lineno)

        # Detect CLI flags: parser.add_argument("--x") and click.option("--x")
        if call_str.endswith((".add_argument", ".option")):
            flag = next(
                (
                    arg.value
                    for arg in node.args
                    if isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value.startswith("--")
                ),
                None,
            )
            if flag:
                default = next((_node_to_str(kw.value) for kw in node.keywords if kw.arg == "default"), None)
                self.flags[flag] = (default, node.lineno)
        self.generic_visit(node)


def parse_python_ast(source_code: str) -> Optional[CodeVisitor]:
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None
    visitor = CodeVisitor()
    visitor.visit(tree)
    return visitor


def compare_python_ast(
    file_path: str,
    old_source: str,
    new_source: str,
) -> list[CodeChange]:
    """Compares AST structures between old_source and new_source to detect all changes."""
    old_ast = parse_python_ast(old_source) if old_source else None
    new_ast = parse_python_ast(new_source) if new_source else None

    changes: list[CodeChange] = []

    # 1. Compare Constants
    old_consts = old_ast.constants if old_ast else {}
    new_consts = new_ast.constants if new_ast else {}

    for name in sorted(old_consts.keys() & new_consts.keys()):
        old_val, _ = old_consts[name]
        new_val, line = new_consts[name]
        if old_val != new_val:
            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=ChangeType.CONSTANT_CHANGED,
                    symbol_name=name,
                    old_value=old_val,
                    new_value=new_val,
                    line_number=line,
                    diff_hunk=f"- {name} = {old_val}\n+ {name} = {new_val}",
                    details={"scope": "constant"},
                )
            )

    # 2. Compare Functions
    old_funcs = old_ast.functions if old_ast else {}
    new_funcs = new_ast.functions if new_ast else {}

    # Removed functions vs Renamed functions heuristic
    removed_func_names = set(old_funcs.keys()) - set(new_funcs.keys())
    added_func_names = set(new_funcs.keys()) - set(old_funcs.keys())

    # Detect renames (similar signature or high similarity)
    renamed_pairs: dict[str, str] = {}
    for r_name in list(removed_func_names):
        r_sig = old_funcs[r_name]
        for a_name in list(added_func_names):
            a_sig = new_funcs[a_name]
            # If same args or high name similarity
            name_sim = difflib.SequenceMatcher(None, r_name, a_name).ratio()
            if r_sig.args == a_sig.args and (name_sim > 0.4 or len(r_sig.args) > 0):
                renamed_pairs[r_name] = a_name
                changes.append(
                    CodeChange(
                        file_path=file_path,
                        change_type=ChangeType.FUNCTION_RENAMED,
                        symbol_name=a_name,
                        old_value=r_name,
                        new_value=a_name,
                        line_number=a_sig.line_number,
                        diff_hunk=f"- def {r_name}(...)\n+ def {a_name}(...)",
                        details={"old_name": r_name, "new_name": a_name},
                    )
                )
                removed_func_names.remove(r_name)
                added_func_names.remove(a_name)
                break

    for r_name in removed_func_names:
        sig = old_funcs[r_name]
        changes.append(
            CodeChange(
                file_path=file_path,
                change_type=ChangeType.FUNCTION_REMOVED,
                symbol_name=r_name,
                old_value=r_name,
                new_value=None,
                line_number=sig.line_number,
                diff_hunk=f"- def {r_name}({', '.join(sig.args)})",
                details={"name": r_name},
            )
        )

    for a_name in added_func_names:
        sig = new_funcs[a_name]
        changes.append(
            CodeChange(
                file_path=file_path,
                change_type=ChangeType.FUNCTION_ADDED,
                symbol_name=a_name,
                old_value=None,
                new_value=a_name,
                line_number=sig.line_number,
                diff_hunk=f"+ def {a_name}({', '.join(sig.args)})",
                details={"name": a_name},
            )
        )

    # Functions present in both: check parameters, defaults, return annotations, API endpoints
    for name in sorted(old_funcs.keys() & new_funcs.keys()):
        old_sig = old_funcs[name]
        new_sig = new_funcs[name]

        # API endpoint decorator change
        if old_sig.api_endpoint or new_sig.api_endpoint:
            old_ep = old_sig.api_endpoint or {}
            new_ep = new_sig.api_endpoint or {}
            if old_ep != new_ep:
                changes.append(
                    CodeChange(
                        file_path=file_path,
                        change_type=ChangeType.API_ENDPOINT_CHANGED,
                        symbol_name=name,
                        old_value=f"{old_ep.get('method', '')} {old_ep.get('path', '')}".strip(),
                        new_value=f"{new_ep.get('method', '')} {new_ep.get('path', '')}".strip(),
                        line_number=new_sig.line_number,
                        diff_hunk=f"- {old_ep}\n+ {new_ep}",
                        details={"old_endpoint": old_ep, "new_endpoint": new_ep},
                    )
                )

        # Parameter additions / removals
        old_args_set = set(old_sig.args)
        new_args_set = set(new_sig.args)

        removed_args = [a for a in old_sig.args if a not in new_args_set]
        added_args = [a for a in new_sig.args if a not in old_args_set]

        if removed_args:
            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=ChangeType.PARAMETER_REMOVED,
                    symbol_name=name,
                    old_value=", ".join(removed_args),
                    new_value=None,
                    line_number=new_sig.line_number,
                    diff_hunk=f"def {name}(...): removed params: {', '.join(removed_args)}",
                    details={"function": name, "removed_args": removed_args},
                )
            )

        if added_args:
            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=ChangeType.PARAMETER_ADDED,
                    symbol_name=name,
                    old_value=None,
                    new_value=", ".join(added_args),
                    line_number=new_sig.line_number,
                    diff_hunk=f"def {name}(...): added params: {', '.join(added_args)}",
                    details={"function": name, "added_args": added_args},
                )
            )

        # Parameter defaults changed
        for arg in sorted(old_sig.defaults.keys() & new_sig.defaults.keys()):
            if old_sig.defaults[arg] != new_sig.defaults[arg]:
                changes.append(
                    CodeChange(
                        file_path=file_path,
                        change_type=ChangeType.PARAMETER_CHANGED,
                        symbol_name=f"{name}.{arg}",
                        old_value=old_sig.defaults[arg],
                        new_value=new_sig.defaults[arg],
                        line_number=new_sig.line_number,
                        diff_hunk=f"param {arg} default: {old_sig.defaults[arg]} -> {new_sig.defaults[arg]}",
                        details={"function": name, "param": arg},
                    )
                )

        # Return type change
        if old_sig.return_annotation != new_sig.return_annotation:
            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=ChangeType.RETURN_TYPE_CHANGED,
                    symbol_name=name,
                    old_value=old_sig.return_annotation or "None",
                    new_value=new_sig.return_annotation or "None",
                    line_number=new_sig.line_number,
                    diff_hunk=f"- -> {old_sig.return_annotation}\n+ -> {new_sig.return_annotation}",
                    details={"function": name},
                )
            )

    # 3. Environment Variables
    old_env = old_ast.env_vars if old_ast else {}
    new_env = new_ast.env_vars if new_ast else {}

    for var in sorted(old_env.keys() & new_env.keys()):
        old_def, _ = old_env[var]
        new_def, line = new_env[var]
        if old_def != new_def:
            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=ChangeType.ENV_VAR_CHANGED,
                    symbol_name=var,
                    old_value=old_def or "",
                    new_value=new_def or "",
                    line_number=line,
                    diff_hunk=f"env var {var}: default changed from {old_def} to {new_def}",
                    details={"env_var": var},
                )
            )

    # 4. CLI Flags
    old_flags = old_ast.flags if old_ast else {}
    new_flags = new_ast.flags if new_ast else {}
    # Keep source order, so several renames in one file pair up correctly.
    removed_flags = [f for f in old_flags if f not in new_flags]
    added_flags = [f for f in new_flags if f not in old_flags]

    # Equal numbers gone and added means renames. Otherwise we can't tell, so we call them removals.
    if new_ast and len(removed_flags) == len(added_flags):
        for old_flag, new_flag in zip(removed_flags, added_flags):
            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=ChangeType.FLAG_RENAMED,
                    symbol_name=old_flag,
                    old_value=old_flag,
                    new_value=new_flag,
                    line_number=new_flags[new_flag][1],
                    diff_hunk=f"- add_argument(\"{old_flag}\")\n+ add_argument(\"{new_flag}\")",
                )
            )
    else:
        for old_flag in removed_flags:
            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=ChangeType.FLAG_REMOVED,
                    symbol_name=old_flag,
                    old_value=old_flag,
                    line_number=old_flags[old_flag][1],
                    diff_hunk=f"- add_argument(\"{old_flag}\")",
                )
            )

    for flag in sorted(old_flags.keys() & new_flags.keys()):
        old_default, _ = old_flags[flag]
        new_default, line = new_flags[flag]
        if old_default != new_default:
            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=ChangeType.FLAG_DEFAULT_CHANGED,
                    symbol_name=flag,
                    old_value=old_default or "",
                    new_value=new_default or "",
                    line_number=line,
                    diff_hunk=f"{flag} default: {old_default} -> {new_default}",
                )
            )

    return changes

