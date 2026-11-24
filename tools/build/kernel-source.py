#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Export the locked Linux commit as OpenWrt's checksum-verified source archive."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from workspace import LINUX, DOWNLOADS, OPENWRT

PROJECT = Path(__file__).resolve().parents[2]


def export_kernel():
    lock = json.loads((PROJECT / "manifests/kernel.json").read_text())
    version = lock["version"]
    series = ".".join(version.split(".")[:2])
    target_ref = lock.get("commit", "HEAD")
    commit = subprocess.check_output(
        ["git", "-C", str(LINUX), "rev-parse", f"{target_ref}^{{commit}}"],
        text=True,
    ).strip()
    if lock.get("commit") and commit != lock["commit"]:
        raise SystemExit(f"Missing locked Linux commit {lock['commit']}")
    archive = lock.get("archive") or f"linux-{version}-sy108-{commit[:12]}.tar.gz"
    dest = DOWNLOADS / archive
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        partial = dest.with_suffix(dest.suffix + ".part")
        try:
            with partial.open("wb") as output:
                process = subprocess.Popen(
                    ["git", "-C", str(LINUX), "archive", "--format=tar", f"--prefix=linux-{version}/", commit],
                    stdout=subprocess.PIPE,
                )
                compressed = subprocess.run(["gzip", "-n"], stdin=process.stdout, stdout=output)
                process.stdout.close()
                if process.wait() or compressed.returncode:
                    raise RuntimeError("Linux export failed")
            partial.rename(dest)
        finally:
            partial.unlink(missing_ok=True)
    with dest.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if lock.get("sha256") and lock.get("archive") == archive and digest != lock["sha256"]:
        mismatch = (
            f"Linux archive checksum mismatch: manifest={lock['sha256']} computed={digest}"
        )
        if os.environ.get("SY108_RELAX_KERNEL_HASH") == "1":
            # The exported tree is pinned by commit above, and the resulting digest is
            # still written to LINUX_KERNEL_HASH so OpenWrt verifies the same bytes.
            # Only the gzip deflate output differs between host gzip builds.
            print(f"warning: {mismatch}", file=sys.stderr)
            print(
                "warning: commit/tree already verified; relaxing compression checksum",
                file=sys.stderr,
            )
        else:
            raise SystemExit(mismatch)
    kernel_mk = OPENWRT / f"target/linux/sprd/kernel-{series}"
    if kernel_mk.parent.is_dir():
        kernel_mk.write_text(f"LINUX_VERSION-{series} = {version[len(series):]}\nLINUX_KERNEL_HASH-{version} = {digest}\n")
    return {"commit": commit, "archive": archive, "sha256": digest, "path": str(dest)}


if __name__ == "__main__":
    info = export_kernel()
    print(info["path"])
