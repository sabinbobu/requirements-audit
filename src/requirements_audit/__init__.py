"""Requirements Audit — multi-agent contradiction detection over requirement documents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("requirements-audit")
except PackageNotFoundError:  # package not installed (e.g. running from source tree)
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
