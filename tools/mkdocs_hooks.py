"""MkDocs hooks.

The Raspberry Pi package and the MicroPython file are both called `pingoblin_motor`.
To document both, copy the MicroPython file to `.docs_build/pingoblin_motor_mp.py`
before the build; mkdocs.yml adds `.docs_build` to mkdocstrings' search paths.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def on_config(config, **kwargs):
    """Copy the MicroPython module under its documentation alias."""
    dst = os.path.join(ROOT, ".docs_build")
    os.makedirs(dst, exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, "micropython", "pingoblin_motor.py"),
                    os.path.join(dst, "pingoblin_motor_mp.py"))
    return config
