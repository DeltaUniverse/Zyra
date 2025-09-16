"""Dynamically loads all submodules within this package.

This `__init__.py` file serves as a meta-loader for the package it resides in.
It automatically discovers and imports all `.py` files in the same directory,
making them available in the `submodules` list.

Additionally, it includes a mechanism to handle hot-reloading. When this
package is reloaded (e.g., during development), it will also automatically
reload all of its discovered submodules to ensure changes are applied without
a full application restart.
"""

import importlib
import pkgutil
from pathlib import Path

current_dir = str(Path(__file__).parent)
submodules = [
    importlib.import_module("." + info.name, __name__)
    for info in pkgutil.iter_modules([current_dir])
]

try:
    _reload_flag: bool

    # noinspection PyUnboundLocalVariable
    if _reload_flag:  # skipcq: PYL-E0601
        # Module has been reloaded, reload our submodules
        for module in submodules:
            importlib.reload(module)
except NameError:
    _reload_flag = True
