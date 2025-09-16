"""Provides a base class for type checking purposes.

This module uses a common pattern to define a base class `ZyraBase` that
resolves to `abc.ABC` at runtime but allows for forward-referencing the full
`Zyra` bot class during static type analysis. This avoids circular import
issues while providing accurate type hints throughout the codebase.
"""

from typing import TYPE_CHECKING, Any

ZyraBase: Any
if TYPE_CHECKING:
    from .bot import Zyra

    ZyraBase = Zyra

else:
    import abc

    ZyraBase = abc.ABC
