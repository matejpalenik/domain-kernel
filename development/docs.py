"""Prepare the website's reference from implemented Python source."""

import ast
import os
import re
import tomllib
from pathlib import Path

from pydantic import BaseModel

type _PublicSymbol = (
    ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef | ast.TypeAlias | ast.AnnAssign
)


class FieldDocumentation(BaseModel):
    """An annotation or enum member shown in the reference."""

    name: str
    annotation: str
    default: str = ""


class SymbolDocumentation(BaseModel):
    """One exported symbol and its source-backed documentation."""

    name: str
    kind: str
    signature: str
    description: str
    source: str
    line: int
    fields: list[FieldDocumentation]
    members: list[FieldDocumentation]


class ReferenceDocumentation(BaseModel):
    """The implemented public SDK inventory."""

    symbols: list[SymbolDocumentation]


def reference(*, root: Path) -> ReferenceDocumentation:
    """Read public exports without executing source or planned interface examples."""
    package = root / "src/domain_kernel"
    entry = ast.parse((package / "__init__.py").read_text())
    exports = next(
        item.value
        for item in entry.body
        if isinstance(item, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in item.targets)
    )
    if not isinstance(exports, ast.List):
        raise TypeError("Public exports must be an explicit list")
    names = [item.value for item in exports.elts if isinstance(item, ast.Constant)]
    symbols: list[SymbolDocumentation] = []
    for name in names:
        if not isinstance(name, str):
            raise TypeError("Every public export must have a string name")
        source, node = _resolve(root=root, tree=entry, path=package / "__init__.py", name=name)
        fields, members, initializer = _details(root=root, path=source, node=node)
        if isinstance(node, ast.TypeAlias):
            signature = ast.unparse(node)
            kind = "type alias"
            description = f"Public type alias for {ast.unparse(node.value)}."
        elif isinstance(node, ast.AnnAssign):
            signature = ast.unparse(node)
            kind = "constant"
            description = "Public constant used in SDK calls."
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else ""
            signature = f"{prefix}{name}({ast.unparse(node.args)})"
            if node.returns is not None:
                signature += f" -> {ast.unparse(node.returns)}"
            kind = "function"
            description = ast.get_docstring(node) or ""
        else:
            generic_name = name
            if node.type_params:
                generic_name += f"[{', '.join(ast.unparse(item) for item in node.type_params)}]"
            signature = (
                f"{generic_name}({ast.unparse(initializer.args).removeprefix('self, ')})"
                if initializer is not None
                else f"class {generic_name}({', '.join(ast.unparse(base) for base in node.bases)})"
            )
            kind = "enum" if members else "class"
            description = ast.get_docstring(node) or ""
        symbols.append(
            SymbolDocumentation(
                name=name,
                kind=kind,
                signature=signature,
                description=description,
                source=source.relative_to(root).as_posix(),
                line=node.lineno,
                fields=list(fields.values()),
                members=members,
            )
        )
    return ReferenceDocumentation(symbols=sorted(symbols, key=lambda item: item.name))


def _resolve(*, root: Path, tree: ast.Module, path: Path, name: str) -> tuple[Path, _PublicSymbol]:
    guarded_imports = [
        imported
        for item in tree.body
        if isinstance(item, ast.If)
        and isinstance(item.test, ast.Name)
        and item.test.id == "TYPE_CHECKING"
        for imported in item.body
        if isinstance(imported, ast.ImportFrom)
    ]
    for item in (*tree.body, *guarded_imports):
        if isinstance(item, ast.TypeAlias) and item.name.id == name:
            return path, item
        if (
            isinstance(item, ast.AnnAssign)
            and isinstance(item.target, ast.Name)
            and item.target.id == name
        ):
            return path, item
        if (
            isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == name
        ):
            return path, item
        if isinstance(item, ast.ImportFrom) and item.module is not None:
            for alias in item.names:
                if (alias.asname or alias.name) == name and item.module.startswith("domain_kernel"):
                    target = root / "src" / (item.module.replace(".", "/") + ".py")
                    return _resolve(
                        root=root, tree=ast.parse(target.read_text()), path=target, name=alias.name
                    )
    message = f"Cannot locate public source for {name} in {path}"
    raise ValueError(message)


def _details(
    *, root: Path, path: Path, node: _PublicSymbol
) -> tuple[dict[str, FieldDocumentation], list[FieldDocumentation], ast.FunctionDef | None]:
    fields: dict[str, FieldDocumentation] = {}
    members: list[FieldDocumentation] = []
    initializer = None
    if not isinstance(node, ast.ClassDef):
        return fields, members, initializer
    tree = ast.parse(path.read_text())
    local_imports = {
        alias.asname or alias.name
        for item in tree.body
        if isinstance(item, ast.ImportFrom)
        and item.module is not None
        and item.module.startswith("domain_kernel")
        for alias in item.names
    }
    local_classes = {item.name for item in tree.body if isinstance(item, ast.ClassDef)}
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in local_imports | local_classes:
            parent_path, parent = _resolve(root=root, tree=tree, path=path, name=base.id)
            inherited, inherited_members, inherited_init = _details(
                root=root, path=parent_path, node=parent
            )
            fields.update(inherited)
            members.extend(inherited_members)
            initializer = inherited_init
    is_enum = any(isinstance(base, ast.Name) and base.id == "StrEnum" for base in node.bases)
    for item in node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            initializer = item
        if (
            isinstance(item, ast.AnnAssign)
            and isinstance(item.target, ast.Name)
            and not item.target.id.startswith("_")
        ):
            fields[item.target.id] = FieldDocumentation(
                name=item.target.id,
                annotation=ast.unparse(item.annotation),
                default=ast.unparse(item.value) if item.value is not None else "",
            )
        if is_enum and isinstance(item, ast.Assign):
            members.extend(
                FieldDocumentation(name=target.id, annotation=ast.unparse(item.value))
                for target in item.targets
                if isinstance(target, ast.Name) and not target.id.startswith("_")
            )
    return fields, members, initializer


class SiteDocumentation(BaseModel):
    """The SDK version and exact source revision used by the website."""

    revision: str
    version: str


class PackageMetadata(BaseModel):
    """Only the package metadata the website needs."""

    version: str


def prepare(*, root: Path) -> None:
    """Write the SDK reference and website build metadata."""
    generated = root / "apps/docs/src/generated"
    generated.mkdir(parents=True, exist_ok=True)
    _ = (generated / "reference.json").write_text(
        reference(root=root).model_dump_json(indent=2) + "\n"
    )
    revision = os.environ.get("DOCS_REVISION", "")
    if re.fullmatch(r"[a-f0-9]{40}", revision) is None:
        raise ValueError("DOCS_REVISION must be a complete Git commit SHA")
    metadata = PackageMetadata.model_validate(
        tomllib.loads((root / "pyproject.toml").read_text())["project"]
    )
    site = SiteDocumentation(revision=revision, version=metadata.version)
    _ = (generated / "site.json").write_text(site.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    prepare(root=Path(__file__).resolve().parents[1])
