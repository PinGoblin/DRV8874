"""MkDocs hooks.

The Raspberry Pi package and the MicroPython file are both called `pingoblin_motor`.
To document both, copy the MicroPython file to `.docs_build/pingoblin_motor_mp.py`
before the build; mkdocs.yml adds `.docs_build` to mkdocstrings' search paths.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _copy_mp_module():
    dst = os.path.join(ROOT, ".docs_build")
    os.makedirs(dst, exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, "micropython", "pingoblin_motor.py"),
                    os.path.join(dst, "pingoblin_motor_mp.py"))


# Copy when MkDocs loads this file (while it reads mkdocs.yml). mkdocstrings checks its
# search paths before any on_config hook runs, so .docs_build must exist by then.
_copy_mp_module()


def on_pre_build(config, **kwargs):
    """Refresh the copy before each build, so `mkdocs serve` picks up edits."""
    _copy_mp_module()
