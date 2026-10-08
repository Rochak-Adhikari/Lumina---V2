"""Bounded, name-only search. No content reads, symlinks or junction traversal."""
from collections import deque
from pathlib import Path
from threading import Event
import os
import re
import time
import unicodedata

IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "vendor"}
STOP = {"find", "my", "me", "the", "a", "an", "please", "for", "search", "locate", "show", "of", "and", "in"}


def words(text):
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())


class FileIndex:
    def __init__(self, config):
        self.config = config
        self.root = config.root.resolve()

    def allowed(self, path):
        try:
            path.relative_to(self.root)
            cursor = path
            while cursor != self.root:
                if cursor.is_symlink() or cursor.is_junction():
                    return False
                cursor = cursor.parent
            return path.resolve(strict=True).is_relative_to(self.root)
        except (OSError, ValueError):
            return False

    def scan(self, cancel=None):
        cancel = cancel or Event()
        queue, entries = deque([self.root]), []
        deadline = time.monotonic() + self.config.scan_seconds
        skipped = 0
        limited = False
        while queue:
            if cancel.is_set() or time.monotonic() > deadline:
                limited = True
                break
            directory = queue.popleft()
            if not self.allowed(directory):
                skipped += 1
                continue
            try:
                with os.scandir(directory) as children:
                    for child in children:
                        if cancel.is_set() or time.monotonic() > deadline or len(entries) >= self.config.scan_limit:
                            limited = True
                            break
                        p = Path(child.path)
                        if child.name.startswith(".") or child.name in IGNORED or not self.allowed(p):
                            continue
                        is_dir = child.is_dir(follow_symlinks=False)
                        if not is_dir and not child.is_file(follow_symlinks=False):
                            continue
                        entries.append(self.entity(p, "folder" if is_dir else "file"))
                        if is_dir:
                            queue.append(p)
            except OSError:
                skipped += 1
            if limited:
                break
        return entries, {"scanned": len(entries), "scan_incomplete": limited or skipped > 0,
                         "skipped_directories": skipped}

    def entity(self, path, kind):
        rel = path.relative_to(self.root)
        return {"id": rel.as_posix() if rel.parts else ".", "filename": path.name,
                "path": str(path), "parent_path": str(path.parent), "type": kind,
                "branch": rel.parts[0] if rel.parts else "root"}

    def graph(self, entries, matched=False):
        nodes, links = {}, []
        root = self.entity(self.root, "folder")
        root["role"] = "context"
        nodes["."] = root
        visible_hits = 0
        for item in entries:
            path = Path(item["path"])
            if not self.allowed(path):
                continue
            chain = []
            cursor = path.parent
            while cursor != self.root:
                chain.append(self.entity(cursor, "folder"))
                cursor = cursor.parent
            needed = {n["id"] for n in [item, *chain]} - nodes.keys()
            if len(nodes) + len(needed) > self.config.graph_limit:
                continue
            for parent in reversed(chain):
                nodes.setdefault(parent["id"], {**parent, "role": "context"})
            nodes[item["id"]] = {**item, "role": "match" if matched else "entity"}
            visible_hits += 1
        for key in nodes:
            if key != ".":
                parent = Path(key).parent.as_posix()
                links.append({"source": parent, "target": key})
        return {"nodes": list(nodes.values()), "links": links, "visible_matches": visible_hits if matched else 0,
                "context_count": sum(n["role"] == "context" for n in nodes.values()),
                "truncated": visible_hits < len(entries)}

    def search(self, query, cancel=None):
        terms = list(dict.fromkeys(t for t in words(query) if t not in STOP))
        if not terms:
            raise ValueError("Use at least one meaningful filename or folder name.")
        entries, coverage = self.scan(cancel)
        strong, partial = [], []
        normalized = " ".join(terms)
        for entity in entries:
            tokens = words(Path(entity["filename"]).stem if entity["type"] == "file" else entity["filename"])
            hits = sum(any(t == w or (len(t) > 3 and w.startswith(t)) for w in tokens) for t in terms)
            if not hits:
                continue
            exact = " ".join(tokens) == normalized
            all_terms = hits == len(terms)
            parents = []
            cursor = Path(entity["path"]).parent
            while cursor.is_relative_to(self.root):
                parents.append(str(cursor))
                if cursor == self.root:
                    break
                cursor = cursor.parent
            result = {**entity, "match_score": round((1 if exact else .85) if all_terms else .7 * hits / len(terms), 3),
                      "match_type": "exact" if exact else "strong" if all_terms else "partial",
                      "relevant_parent_folders": parents}
            (strong if all_terms else partial).append(result)
        results = sorted(strong or partial, key=lambda n: (-n["match_score"], n["path"].casefold()))
        returned = results[:100]
        return {"ok": True, "query": query, "terms": terms, "count": len(results),
                "returned_count": len(returned), "partial": bool(results and not strong),
                "results_truncated": len(results) > len(returned), "results": returned,
                "graph": self.graph(returned, matched=True), **coverage}

    def overview(self, cancel=None):
        entries, coverage = self.scan(cancel)
        return {**self.graph(entries), **coverage}

