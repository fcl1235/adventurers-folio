"""按「顶层类/函数」把一个模块拆成子包, 原模块变成重新导出的门面。

与 _p4_split_mixin.py 的区别: 那个按「类里的方法」拆 mixin, 这个按
「模块里的整类」拆独立对话框/步骤类。

用法: python backup/_p4_split_classes.py 计划.json

计划 JSON:
{
  "src": "dnd55e/dialogs.py",
  "pkg": "dnd55e/dialogs",            # 目标子包目录 (建成包, 原 .py 删除)
  "header": "公共 import 头 (含 @@DOC@@ 占位)",
  "facade_header": "门面文件头",
  "groups": [
     {"mod": "metamagic", "doc": "...", "names": ["MetamagicDialog"]},
     ...
  ]
}
"""
import ast
import io
import json
import os
import sys


def load(p):
    return io.open(p, encoding="utf-8").read()


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
    lines = load(src_path).split("\n")
    tree = ast.parse("\n".join(lines))

    spans = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            start = node.lineno
            if getattr(node, "decorator_list", None):
                start = min(d.lineno for d in node.decorator_list)
            spans[node.name] = (start, node.end_lineno)

    assigned, bad = {}, []
    for g in plan["groups"]:
        for name in g["names"]:
            if name not in spans:
                bad.append("%s (不存在)" % name)
            elif name in assigned:
                bad.append("%s (重复分配)" % name)
            else:
                assigned[name] = g["mod"]
    if bad:
        raise SystemExit("问题: %s" % ", ".join(bad))
    missing = [n for n in spans if n not in assigned]
    if missing:
        raise SystemExit("未分配的顶层名字: %s" % ", ".join(missing))

    header = plan["header"].rstrip() + "\n"
    pkg = plan["pkg"]
    written = []
    for g in plan["groups"]:
        blocks = []
        for name in g["names"]:
            s, e = spans[name]
            blocks.append("\n".join(lines[s - 1:e]).rstrip("\n"))
        text = header.replace("@@DOC@@", g.get("doc", ""))
        text += "\n\n" + "\n\n\n".join(blocks) + "\n"
        p = dump(os.path.join(pkg, g["mod"] + ".py"), text)
        written.append((p, len(blocks)))

    # 门面: 把名字重新导出
    fac = plan["facade_header"].rstrip() + "\n\n"
    for g in plan["groups"]:
        fac += "from .%s import %s  # noqa: F401,E402\n" % (
            g["mod"], ", ".join(g["names"]))
    pub = []
    for g in plan["groups"]:
        pub.extend(g["names"])
    fac += "\n__all__ = [\n"
    for n in pub:
        fac += '    "%s",\n' % n
    fac += "]\n"
    dump(os.path.join(pkg, "__init__.py"), fac)

    os.remove(src_path)
    for p, n in written:
        print("%-44s %2d 个类" % (p, n))
    print("%-44s 门面 (导出 %d 个类)" % (os.path.join(pkg, "__init__.py"),
                                        len(pub)))


if __name__ == "__main__":
    main()
