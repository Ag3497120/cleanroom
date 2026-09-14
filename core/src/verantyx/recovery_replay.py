"""Replay only explicit finite predicates, using the existing engine and no DB/AI."""
import argparse
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import stat

from .domain.codec import canonical, decode, digest
from .domain.verification import MAX_INPUT, evidence_result, validate_spec
from .adapters.observations import _open_under, normalize_path, read_document
from .errors import LedgerError


def load_bundle(path, expected_id=None):
    bundle = decode(read_document(path, 4 * 1024 * 1024), 4 * 1024 * 1024)
    if (type(bundle) is not dict or set(bundle) != {"bundle_id", "payload"}
            or type(bundle["payload"]) is not dict
            or bundle["payload"].get("format") != "verantyx.recovery-bundle.v1"
            or digest(bundle["payload"]) != bundle["bundle_id"]
            or (expected_id is not None and expected_id != bundle["bundle_id"])):
        raise LedgerError("RECOVERY_BUNDLE_CHANGED")
    return bundle


def replay(bundle, asset_id, root, target=None):
    # Callers cannot bypass the same content binding used by the CLI loader.
    if digest(bundle["payload"]) != bundle["bundle_id"]:
        raise LedgerError("RECOVERY_BUNDLE_CHANGED")
    methods = [item for item in bundle["payload"]["methods"] if item["id"] == asset_id]
    if len(methods) != 1:
        raise LedgerError("ASSET_NOT_FOUND")
    item = methods[0]
    if item["family"] != "VERIFICATION" or not item.get("portable_execution"):
        raise LedgerError("ASSET_NOT_REUSABLE")
    spec = deepcopy(item["spec"])
    if digest(spec) != item["contract_hash"]:
        raise LedgerError("RECOVERY_CONTRACT_CHANGED")
    validate_spec(spec)
    if spec["method"] not in ("TEST", "NEGATIVE_CONTROL"):
        raise LedgerError("ASSET_NOT_REUSABLE")
    relative = normalize_path(target if target is not None else spec["target_path"])
    root = Path(root).expanduser().resolve(strict=True)
    fd = _open_under(root, relative)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise LedgerError("DOCUMENT_INVALID")
        raw = handle.read(MAX_INPUT + 1)
        after = os.fstat(handle.fileno())
    if len(raw) > MAX_INPUT:
        raise LedgerError("DOCUMENT_LIMIT")
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise LedgerError("SOURCE_CHANGED")
    # Explicit new binding. Expectations, negative controls and historical receipt
    # stay unchanged. This read-only result is not appended as canonical evidence.
    spec["target_path"] = relative
    outcome = evidence_result({"spec": spec}, raw)
    return {
        "format": "verantyx.portable-replay.v1", "bundle_id": bundle["bundle_id"],
        "asset_id": asset_id, "source_contract_hash": item["contract_hash"],
        "original_target": item["spec"]["target_path"], "target": relative,
        "target_sha256": hashlib.sha256(raw).hexdigest(),
        "result": outcome, "model_calls": 0, "project_database_used": False,
        "writes": False, "authority": "EXPLICIT_READ_ONLY_CHECK_NOT_POLICY_TRANSFER",
        "human_mastery": "NOT_ASSESSED",
    }


def main(argv=None, *, bundle_path=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=bundle_path)
    parser.add_argument("--expect-bundle")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--asset")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--target")
    args = parser.parse_args(argv)
    if args.bundle is None:
        parser.error("--bundle is required")
    if args.list and (args.asset or args.root or args.target):
        parser.error("--list cannot execute a check")
    if not args.list and (not args.asset or args.root is None):
        parser.error("--asset and --root are required")
    try:
        bundle = load_bundle(args.bundle, args.expect_bundle)
        if args.list:
            result = {"bundle_id": bundle["bundle_id"], "model_calls": 0,
                      "methods": [{key: item.get(key) for key in
                                   ("id", "name", "target", "portable_execution", "remaining")}
                                  for item in bundle["payload"]["methods"]]}
            print(canonical(result))
            return 0
        result = replay(bundle, args.asset, args.root, args.target)
        print(canonical(result))
        closure = result["result"]["closure"]
        return 0 if closure == "BOUNDED" else 1 if closure == "REFUTED" else 2
    except (LedgerError, OSError, KeyError, TypeError, ValueError) as error:
        print(canonical({"status": "UNKNOWN", "reason": getattr(error, "code", "INPUT_UNAVAILABLE"),
                         "model_calls": 0, "writes": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
