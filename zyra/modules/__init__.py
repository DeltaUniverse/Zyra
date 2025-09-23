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
    if _reload_flag:
        for module in submodules:
            importlib.reload(module)
except NameError:
    _reload_flag = True
