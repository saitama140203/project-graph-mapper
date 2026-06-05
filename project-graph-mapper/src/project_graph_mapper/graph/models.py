from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SymbolKind(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    STRUCT = "struct"  # Go, Rust, C
    INTERFACE = "interface"  # Go, Java, TypeScript
    ENUM = "enum"  # Rust, Java, TypeScript
    TRAIT = "trait"  # Rust
    IMPL = "impl"  # Rust impl block
    CONSTANT = "constant"  # Go const, Rust const


@dataclass
class Location:
    file: str
    line: int
    col: int = 0


@dataclass
class CallSite:
    """Một chỗ trong code gọi đến symbol này."""

    file: str
    line: int
    context: str


@dataclass
class Symbol:
    """Đại diện cho một thực thể code được định nghĩa (function, class, method, struct, ...).

    Attributes:
        id: ID duy nhất của symbol (ví dụ: 'utils/auth.py::validate_token').
        name: Tên hiển thị của symbol.
        kind: Thể loại symbol (FUNCTION, CLASS, METHOD, STRUCT, INTERFACE, ...).
        loc: Vị trí khai báo trong dự án (file, dòng, cột).
        signature: Dòng khai báo chữ ký của hàm/lớp (nếu có).
        docstring: Chuỗi chú thích hoặc tài liệu của symbol (nếu có).
        uses: Danh sách các ID symbol khác mà symbol này gọi/sử dụng.
        used_by: Danh sách các vị trí (CallSite) gọi tới symbol này.
    """

    id: str
    name: str
    kind: SymbolKind
    loc: Location
    signature: str = ""
    docstring: str = ""

    uses: list[str] = field(default_factory=list)
    used_by: list[CallSite] = field(default_factory=list)


@dataclass
class FileNode:
    path: str
    imports: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    last_hash: str = ""
    language: str = ""
