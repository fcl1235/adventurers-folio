"""把一个 mixin 类按方法名拆成多个宿主类 (保持方法源码一字不改)。

用法:
    python backup/_p4_split_mixin.py 计划.json

计划 JSON 结构:
{
  "src": "dnd55e/ui_actions.py",
  "out_dir": "dnd55e/ui",
  "header": "模块头 import (多行)",      // 写给每个新文件
  "aggregator": {                        // 可选: 把原文件重写成汇总类
      "path": "dnd55e/ui_actions.py",
      "header": "...",
      "cls": "AppActions",
      "bases": ["DiceMixin", "StatsMixin"]
  },
  "mods": [
     {"mod": "dice", "cls": "DiceMixin", "doc": "...", "methods": [...]}
  ]
}
"""
import ast
import io
import json
import os
import sys


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def dump(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def main():
    plan = json.loads(load(sys.argv[1]))
    src_path = plan["src"]
    src = load(src_path)
    lines = src.split("\n")

    tree = ast.parse(src)
    cls = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            cls = node
            break
    if cls is None:
        raise SystemExit("%s 里没有类定义" % src_path)

    spans = {}
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            if node.decorator_list:
                start = min(d.lineno for d in node.decorator_list)
            spans[node.name] = (start, node.end_lineno)

    # 类体里的类级属性 (非方法) —— 自动搬到 aggregator, 因为 App 继承它,
    # 方法里的 cls.XXX 取到的仍是同一个类
    method_ids = set()
    for s, e in spans.values():
        method_ids.update(range(s, e + 1))
    class_attrs = []
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, (ast.Expr, ast.Pass)):
            continue
        seg = lines[node.lineno - 1:node.end_lineno]
        if any(i + 1 in method_ids for i in range(node.lineno - 1,
                                                  node.end_lineno)):
            continue
        class_attrs.append("\n".join(seg).rstrip("\n"))

    assigned = {}
    bad = []
    for spec in plan["mods"]:
        for name in spec["methods"]:
            if name not in spans:
                bad.append(name)
                continue
            if name in assigned:
                bad.append("%s (重复分配)" % name)
            assigned[name] = spec["mod"]
    if bad:
        raise SystemExit("问题方法: %s" % ", ".join(bad))
    unassigned = [n for n in spans if n not in assigned]
    if unassigned:
        raise SystemExit("未分配的方法: %s" % ", ".join(unassigned))

    header = plan["header"].rstrip() + "\n"
    written = []
    for spec in plan["mods"]:
        blocks = []
        for name in spec["methods"]:
            s, e = spans[name]
            blocks.append("\n".join(lines[s - 1:e]).rstrip("\n"))
        text = spec.get("header", header).rstrip() + "\n"
        if spec.get("doc"):
            text = text.replace("@@DOC@@", spec["doc"])
        else:
            text = text.replace("@@DOC@@", "")
        text += "\n\nclass %s(%s):\n" % (spec["cls"],
                                        ", ".join(spec.get("bases", [])))
        if spec.get("extra"):
            text += spec["extra"].rstrip("\n") + "\n\n"
        text += "\n\n".join(blocks) + "\n"
        p = dump(os.path.join(plan["out_dir"], spec["mod"] + ".py"), text)
        written.append((p, len(blocks)))

    agg = plan.get("aggregator")
    if agg:
        text = agg["header"].rstrip() + "\n\n\nclass %s(%s):\n" % (
            agg["cls"], ", ".join(agg["bases"]))
        text += '    """原来的方法已按模块拆到其它文件, 这里只做组合。"""\n'
        for a in class_attrs:
            text += "\n".join("    " + ln if ln.strip() else ln
                              for ln in a.split("\n")) + "\n\n"
        dump(agg["path"], text)

    for p, n in written:
        print("%-42s %2d 个方法" % (p, n))
    if agg:
        print("%-42s 汇总类 %s(%s)" % (agg["path"], agg["cls"],
                                       ", ".join(agg["bases"])))


if __name__ == "__main__":
    main()
