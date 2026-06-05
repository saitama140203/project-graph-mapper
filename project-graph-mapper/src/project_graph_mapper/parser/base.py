from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..graph.models import FileNode, Symbol

# ── Abstract base ────────────────────────────────────────────────────────────


class BaseParser(ABC):
    """Interface mà mọi language parser phải implement."""

    @abstractmethod
    def extensions(self) -> list[str]:
        """Trả về danh sách extensions mà parser này hỗ trợ, ví dụ ['.py']."""
        ...

    @abstractmethod
    def parse_file(self, filepath: Path, root: Path) -> tuple[FileNode, list[Symbol]]:
        """Parse 1 file, trả về FileNode + danh sách Symbol definitions."""
        ...

    @abstractmethod
    def resolve_calls(
        self,
        filepath: Path,
        root: Path,
        all_symbols: dict[str, Symbol],
    ) -> None:
        """Scan call sites trong file, điền vào used_by của symbols tương ứng."""
        ...

    def engine_name(self) -> str:
        """Tên engine hiển thị, ví dụ 'tree-sitter' hoặc 'AI'."""
        return "tree-sitter"

    def language_name(self) -> str:
        """Tên ngôn ngữ dùng cho FileNode.language field."""
        return type(self).__name__.replace("Parser", "").lower()


# ── Global registry ──────────────────────────────────────────────────────────

_REGISTRY: dict[str, BaseParser] = {}


def register(parser: BaseParser) -> None:
    """Đăng ký parser cho các extensions của nó."""
    for ext in parser.extensions():
        _REGISTRY[ext] = parser


def get_parser(filepath: Path | str) -> BaseParser | None:
    """Trả về parser phù hợp cho file, hoặc None nếu không hỗ trợ."""
    ext = Path(filepath).suffix.lower()
    return _REGISTRY.get(ext)


def supported_extensions() -> list[str]:
    """Trả về tất cả extensions đã đăng ký."""
    return list(_REGISTRY.keys())


def registered_parsers() -> list[tuple[str, BaseParser]]:
    """Trả về danh sách (extension, parser) đã đăng ký, deduplicated by parser instance."""
    seen: set[int] = set()
    result: list[tuple[str, BaseParser]] = []
    for ext, parser in _REGISTRY.items():
        pid = id(parser)
        if pid not in seen:
            seen.add(pid)
            result.append((ext, parser))
    return result


def clear_registry() -> None:
    """Xóa toàn bộ registry — dùng cho testing."""
    _REGISTRY.clear()
