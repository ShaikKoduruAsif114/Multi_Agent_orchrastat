"""
evaluation/verify_manifest.py

Read-only verification of the FROZEN benchmark inputs against the immutable
SHA256 manifest (evaluation/benchmark_input_manifest_sha256_20260909.txt).

This is the integrity gate that must pass BEFORE and AFTER every experiment:
if any hidden test, task specification, fixture repository file, or benchmark
config changed, the experiment's numbers are not comparable to previous
experiments and the run must be flagged.

The manifest itself is NEVER modified here; verification is read-only.
Manifest format: workspace-relative-path|sha256 (lines starting with '#' are
comments; a UTF-8 BOM before the first comment is tolerated).

Usage:
    python evaluation/verify_manifest.py                       # verify, exit 0/1
    python evaluation/verify_manifest.py --json                # machine-readable
    python evaluation/verify_manifest.py --fail-on-extra False # ignore files added after freeze
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "evaluation" / "benchmark_input_manifest_sha256_20260909.txt"


def parse_manifest(manifest_path: Path = MANIFEST_PATH) -> dict:
    """Return {workspace-relative-posix-path: sha256hex} from the manifest."""
    data = manifest_path.read_bytes()
    # Manifest was written with a UTF-8 BOM; tolerate both.
    text = data.decode("utf-8-sig")
    entries: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            raise ValueError(f"malformed manifest line (expected path|sha256): {line!r}")
        path, _, digest = line.partition("|")
        path, digest = path.strip(), digest.strip().lower()
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise ValueError(f"malformed manifest digest for {path!r}")
        if path in entries:
            raise ValueError(f"duplicate manifest path: {path!r}")
        entries[path] = digest
    if not entries:
        raise ValueError("manifest contains no entries")
    return entries


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(manifest_path: Path = MANIFEST_PATH,
                    repo_root: Path = REPO_ROOT,
                    fail_on_extra: bool = True) -> dict:
    """Verify every manifest entry; optionally flag extra frozen-path files.

    Returns a machine-readable report dict. Never writes anything.
    """
    manifest = parse_manifest(manifest_path)
    matched: list[str] = []
    changed: list[dict] = []
    missing: list[str] = []
    for rel, expected in sorted(manifest.items()):
        p = repo_root / rel
        if not p.is_file():
            missing.append(rel)
            continue
        actual = sha256_file(p)
        if actual == expected:
            matched.append(rel)
        else:
            changed.append({"path": rel, "expected": expected, "actual": actual})

    # The manifest header declares its frozen scope: task specifications,
    # hidden tests, benchmark config, fixture repositories. Files inside those
    # scopes that are NOT in the manifest (e.g. added after the freeze) break
    # comparability and fail the gate; harness generator scripts that merely
    # live in the same directories are reported as informational only.
    frozen_scope_patterns = (
        "evaluation/benchmark/fixture_repos/",
        "evaluation/hidden_tests/",
        "evaluation/benchmark/task_*.json",
        "evaluation/configs/benchmark.yaml",
    )

    def _in_frozen_scope(rel: str) -> bool:
        import fnmatch
        return any(fnmatch.fnmatch(rel, pat) or rel.startswith(pat)
                   for pat in frozen_scope_patterns)

    extra: list[str] = []
    extra_info: list[str] = []
    if fail_on_extra:
        frozen_roots = sorted({p.split("/")[0] + "/" + p.split("/")[1]
                               for p in manifest if p.count("/") >= 1})
        for rel_dir in frozen_roots:
            base = repo_root / rel_dir
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts:
                    rel = p.relative_to(repo_root).as_posix()
                    if rel in manifest:
                        continue
                    (extra if _in_frozen_scope(rel) else extra_info).append(rel)

    ok = not missing and not changed and (not fail_on_extra or not extra)
    return {
        "ok": ok,
        "manifest": str(manifest_path.relative_to(repo_root)),
        "manifest_entries": len(manifest),
        "verified": len(matched),
        "changed": changed,
        "missing": missing,
        "extra": sorted(extra) if fail_on_extra else None,
        "extra_info_non_frozen_scope": sorted(extra_info) if fail_on_extra else None,
        "fail_on_extra": fail_on_extra,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify frozen benchmark inputs (read-only).")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON only")
    ap.add_argument("--fail-on-extra", default="true", choices=["true", "false"],
                    help="fail if files exist inside frozen dirs but not in the manifest")
    ap.add_argument("--manifest", default=None, help="override manifest path")
    args = ap.parse_args()

    manifest_path = Path(args.manifest) if args.manifest else MANIFEST_PATH
    report = verify_manifest(manifest_path, fail_on_extra=args.fail_on_extra == "true")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[MANIFEST] entries={report['manifest_entries']} verified={report['verified']} "
              f"changed={len(report['changed'])} missing={len(report['missing'])} "
              f"extra={len(report['extra'] or [])} ok={report['ok']}")
        for c in report["changed"][:10]:
            print(f"  CHANGED {c['path']}")
        for m in report["missing"][:10]:
            print(f"  MISSING {m}")
        for e in (report["extra"] or [])[:10]:
            print(f"  EXTRA   {e}")
        info = report.get("extra_info_non_frozen_scope") or []
        if info:
            print(f"  ({len(info)} non-frozen-scope files present, informational only)")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
