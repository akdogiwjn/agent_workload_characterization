"""Read the existing audit catalog without upgrading its snapshot claims."""

from dataclasses import dataclass
from pathlib import Path

import yaml


class CatalogError(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    """Safe YAML with duplicate mapping keys rejected, including merge keys."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(set(keys)) != len(keys):
            raise CatalogError("duplicate YAML key")
        return super().construct_mapping(node, deep=deep)


@dataclass(frozen=True)
class Source:
    source_id: str
    path: Path
    kind: str
    metadata: dict


class Catalog:
    def __init__(self, path: Path):
        self.path = Path(path).resolve(strict=True)
        try:
            data = yaml.load(self.path.read_text(encoding="utf-8"), Loader=UniqueLoader)
            if not isinstance(data, dict) or data.get("catalog_version") != "1.1":
                raise CatalogError("unsupported catalog version")
            roots = data["roots"]
            if not isinstance(roots, dict) or not isinstance(data["sources"], list):
                raise CatalogError("invalid catalog roots/sources")
            if any(not isinstance(value, str) or not Path(value).is_absolute() for value in roots.values()):
                raise CatalogError("all catalog roots must be absolute paths")
            self.roots = {name: Path(value).resolve() for name, value in roots.items()}
            self.sources: dict[str, Source] = {}
            for item in data["sources"]:
                identity = item["source_id"]
                locator = item["locator"]
                root = Path(roots[locator["root"]])
                relative = Path(locator["path"])
                if not isinstance(identity, str) or not identity.strip() or identity in self.sources:
                    raise CatalogError("missing or duplicate source ID")
                if not root.is_absolute() or relative.is_absolute() or ".." in relative.parts:
                    raise CatalogError("locator requires absolute root and contained relative path")
                resolved_root = root.resolve()
                resolved = (root / relative).resolve()
                if not resolved.is_relative_to(resolved_root):
                    raise CatalogError("locator symlink escapes declared root")
                if locator["kind"] not in ("file", "directory"):
                    raise CatalogError("unsupported locator kind")
                self.sources[identity] = Source(identity, resolved, locator["kind"], item)
        except (KeyError, TypeError, yaml.YAMLError) as error:
            raise CatalogError("malformed catalog") from error

    def source(self, source_id: str) -> Source:
        try:
            return self.sources[source_id]
        except KeyError as error:
            raise CatalogError("unknown source ID") from error

    def inspect(self, source_id: str) -> dict:
        """Only stat the locator; no recursive scan, parsing or source execution."""
        source = self.source(source_id)
        try:
            stat = source.path.stat()
            actual = "file" if source.path.is_file() else "directory" if source.path.is_dir() else "other"
            return {"source_id": source_id, "path": str(source.path), "declared_kind": source.kind,
                    "actual_kind": actual, "status": "exists" if actual == source.kind else "kind_mismatch",
                    "size_bytes": stat.st_size if actual == "file" else None,
                    "snapshot": source.metadata.get("snapshot")}
        except FileNotFoundError:
            return {"source_id": source_id, "status": "missing", "path": str(source.path)}
        except PermissionError:
            return {"source_id": source_id, "status": "unreadable", "path": str(source.path)}

    def protected_paths(self) -> tuple[Path, ...]:
        # Protect whole legacy roots, including files not individually inventoried.
        # The project root is not itself protected: it contains our new outputs.
        return (self.path, *(path for name, path in self.roots.items() if name != "project"),
                *(source.path for source in self.sources.values()))
