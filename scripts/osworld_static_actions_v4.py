"""Parse saved action source without importing, evaluating or executing it.

Only top-level direct calls are classified. Imports/literal declarations can be
recognized as metadata; unsupported statements remain ordered boundaries.
Names describe saved source, never proof that a function actually ran.
"""
from __future__ import annotations

import ast
from collections import Counter

CALL_CATEGORY = {
    **{f"pyautogui.{name}": "click" for name in
       ("click", "doubleClick", "tripleClick", "rightClick", "middleClick")},
    **{f"pyautogui.{name}": "pointer" for name in
       ("moveTo", "moveRel", "dragTo", "dragRel", "mouseDown", "mouseUp")},
    **{f"pyautogui.{name}": "text_or_key" for name in
       ("press", "keyDown", "keyUp", "hotkey", "typewrite", "write")},
    "pyautogui.scroll": "scroll", "pyautogui.hscroll": "scroll",
    "pyautogui.sleep": "wait", "time.sleep": "wait",
    "pyautogui.screenshot": "screenshot",
    "pyperclip.copy": "clipboard", "pyperclip.paste": "clipboard",
}
MODULES = {"pyautogui", "time", "pyperclip"}


def literal_only(node):
    """Recognize syntax only; no constant values or encoded text are evaluated."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(literal_only(x) for x in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and literal_only(k) and literal_only(v)
                   for k, v in zip(node.keys, node.values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int, float)
    return False


def dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return base + "." + node.attr if base else None
    return None


def invalidate_bindings(node, aliases):
    # Rebinding an alias (including an attribute on the module) prevents later
    # calls from being resolved through a now-ambiguous binding.
    for child in ast.walk(node):
        if isinstance(child, (ast.Name, ast.Attribute)) and isinstance(child.ctx, (ast.Store, ast.Del)):
            name = dotted_name(child)
            if name:
                aliases.pop(name.split(".")[0], None)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            aliases.pop(child.name, None)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            aliases.pop(child.name, None)
        elif isinstance(child, ast.Import):
            for item in child.names:
                aliases.pop(item.asname or item.name.split(".")[0], None)
        elif isinstance(child, ast.ImportFrom):
            if any(item.name == "*" for item in child.names):
                aliases.clear()
            else:
                for item in child.names:
                    aliases.pop(item.asname or item.name, None)


def static_calls(source):
    result = {"status": "unknown", "source_call_syntax_count": 0,
              "calls": [], "tokens": [], "boundaries": [],
              "metadata_statements": {}, "reason_counts": {}}
    if not isinstance(source, str):
        result.update(reason_counts={"command_not_string": 1}, tokens=[None])
        return result
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        result.update(reason_counts={"syntax_error": 1}, tokens=[None],
                      parse_error=type(exc).__name__)
        return result
    result["source_call_syntax_count"] = sum(isinstance(n, ast.Call) for n in ast.walk(tree))
    # The original dataset's standalone pyautogui calls assume this name. Other
    # modules and aliases require an explicit import inside this saved command.
    aliases = {"pyautogui": "pyautogui"}
    metadata, reasons = Counter(), Counter()

    def boundary(statement, reason):
        reasons[reason] += 1
        result["tokens"].append(None)
        result["boundaries"].append({"line_in_command": statement.lineno,
                                     "column_in_command": statement.col_offset,
                                     "statement_type": type(statement).__name__, "reason": reason})

    for statement in tree.body:
        if isinstance(statement, ast.Import):
            valid = True
            for item in statement.names:
                bound = item.asname or item.name.split(".")[0]
                aliases.pop(bound, None)
                if item.name in MODULES:
                    aliases[bound] = item.name
                else:
                    valid = False
            if valid:
                metadata["known_import"] += 1
            else:
                boundary(statement, "unsupported_import")
            continue
        if isinstance(statement, ast.ImportFrom):
            valid = statement.level == 0 and statement.module in MODULES
            if any(item.name == "*" for item in statement.names):
                aliases.clear()
                valid = False
            else:
                for item in statement.names:
                    bound = item.asname or item.name
                    aliases.pop(bound, None)
                    canonical = f"{statement.module}.{item.name}"
                    if valid and canonical in CALL_CATEGORY:
                        aliases[bound] = canonical
                    else:
                        valid = False
            if valid:
                metadata["known_from_import"] += 1
            else:
                boundary(statement, "unsupported_from_import")
            continue
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            rebinds_alias = any(isinstance(t, ast.Name) and t.id in aliases for t in targets)
            annotation_safe = (not isinstance(statement, ast.AnnAssign)
                               or isinstance(statement.annotation, ast.Constant)
                               or (isinstance(statement.annotation, ast.Name)
                                   and statement.annotation.id in {"int", "float", "str", "bool", "list", "tuple", "dict", "set"}))
            invalidate_bindings(statement, aliases)
            if (not rebinds_alias and annotation_safe
                    and all(isinstance(t, ast.Name) for t in targets) and literal_only(statement.value)):
                metadata["literal_assignment"] += 1
            else:
                boundary(statement, "unsupported_assignment")
            continue
        if isinstance(statement, ast.Pass):
            metadata["pass"] += 1
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            metadata["constant_expression"] += 1
            continue
        if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)):
            invalidate_bindings(statement, aliases)
            boundary(statement, "unsupported_" + type(statement).__name__)
            continue
        call = statement.value
        # Nested/computed argument code is never interpreted or expanded.
        if any(isinstance(n, (ast.Call, ast.Lambda, ast.ListComp, ast.SetComp,
                              ast.DictComp, ast.GeneratorExp, ast.NamedExpr,
                              ast.Await, ast.Yield, ast.YieldFrom))
               for child in [*call.args, *(k.value for k in call.keywords)]
               for n in ast.walk(child)):
            invalidate_bindings(call, aliases)
            boundary(statement, "nested_or_dynamic_argument")
            continue
        name = dotted_name(call.func)
        parts = name.split(".") if name else []
        canonical = aliases.get(parts[0]) if parts else None
        if canonical and len(parts) > 1:
            canonical += "." + ".".join(parts[1:])
        if canonical not in CALL_CATEGORY:
            invalidate_bindings(call, aliases)
            if name in {"exec", "eval", "__import__", "setattr", "delattr", "globals", "locals"}:
                aliases.clear()
            boundary(statement, "unknown_or_unbound_call")
            continue
        item = {"call_index": len(result["calls"]) + 1,
                "line_in_command": call.lineno, "column_in_command": call.col_offset,
                "saved_name": name, "canonical_name": canonical,
                "category": CALL_CATEGORY[canonical]}
        result["calls"].append(item)
        result["tokens"].append(item["category"])
    result["metadata_statements"] = dict(metadata)
    result["reason_counts"] = dict(reasons)
    if result["calls"]:
        result["status"] = "partial" if result["boundaries"] else "known"
    else:
        result["status"] = "unknown" if result["boundaries"] else "metadata_only"
    return result


class Sequence:
    """Streaming source-order transitions; None never creates a bridge."""
    def __init__(self):
        self.previous = None
        self.length = 0
        self.transitions = Counter()
        self.segments = Counter()
        self.segment_actions = Counter()
        self.lengths = Counter()

    def end_segment(self):
        if self.previous is not None:
            self.segments[self.previous] += 1
            self.segment_actions[self.previous] += self.length
            self.lengths[f"{self.previous}:{self.length}"] += 1
        self.previous, self.length = None, 0

    def add(self, token):
        if token is None:
            self.end_segment()
            return
        if self.previous is not None:
            self.transitions[f"{self.previous}->{token}"] += 1
        if token != self.previous:
            self.end_segment()
            self.previous = token
        self.length += 1

    def finish(self):
        self.end_segment()
        return {"transition_counts": dict(sorted(self.transitions.items())),
                "segment_counts": dict(sorted(self.segments.items())),
                "segment_action_counts": dict(sorted(self.segment_actions.items())),
                "segment_length_counts": dict(sorted(self.lengths.items()))}
