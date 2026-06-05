"""Project summarizer — tìm & trích xuất tóm tắt hệ thống cho CONTEXT.md."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Tên file markdown ưu tiên tìm kiếm (theo thứ tự)
_CANDIDATE_FILES = [
    "README.md",
    "SUMMARY.md",
    "ARCHITECTURE.md",
    "OVERVIEW.md",
    "readme.md",
    "Readme.md",
]

# Section headings nên bỏ qua khi trích xuất summary
_SKIP_SECTIONS = re.compile(
    r"^#+\s*("
    r"install|cài đặt|setup|getting started|prerequisites|requirements|yêu cầu"
    r"|license|giấy phép|contributing|đóng góp"
    r"|changelog|change log|release|phiên bản"
    r"|development|phát triển|testing|test|kiểm tra"
    r"|ci/cd|deploy|triển khai"
    r"|badges?"
    r"|table of contents|mục lục"
    r"|acknowledgments?|credits?"
    r")",
    re.IGNORECASE,
)


def find_summary_file(project_root: Path) -> Path | None:
    """Tìm file markdown phù hợp nhất trong project root.

    Returns:
        Path tới file tìm thấy, hoặc None nếu không có.
    """
    for name in _CANDIDATE_FILES:
        candidate = project_root / name
        if candidate.is_file():
            return candidate
    return None


def extract_summary_from_file(md_path: Path, *, max_chars: int = 3000) -> str:
    """Đọc file markdown và trích xuất phần mô tả hệ thống.

    Giữ lại:
      - Phần mở đầu (trước heading đầu tiên, hoặc dưới heading level-1)
      - Các section liên quan đến architecture / overview / cấu trúc

    Bỏ qua:
      - Installation, License, Contributing, Badges, Development, ...

    Args:
        md_path: Đường dẫn tới file .md
        max_chars: Giới hạn ký tự đầu ra

    Returns:
        Nội dung đã lọc, cắt ngắn nếu vượt max_chars.
    """
    try:
        content = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    lines = content.splitlines()
    kept_lines: list[str] = []
    skip_current_section = False

    for line in lines:
        # Kiểm tra nếu là heading
        if line.startswith("#"):
            stripped = line.strip()
            if _SKIP_SECTIONS.match(stripped):
                skip_current_section = True
                continue
            else:
                skip_current_section = False

        if not skip_current_section:
            # Bỏ badge images ở đầu file
            if line.strip().startswith("[![") or line.strip().startswith("![badge"):
                continue
            kept_lines.append(line)

    result = "\n".join(kept_lines).strip()

    # Cắt ngắn nếu quá dài
    if len(result) > max_chars:
        result = result[:max_chars].rsplit("\n", 1)[0] + "\n\n_(truncated)_"

    return result


def generate_summary_with_ai(
    files: dict,
    symbols: dict,
    *,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> str:
    """Dùng DeepSeek API để tạo tóm tắt hệ thống từ graph data.

    Args:
        files: dict[str, FileNode] từ GraphBuilder
        symbols: dict[str, Symbol] từ GraphBuilder
        api_key: DeepSeek API key
        model: Tên model DeepSeek
        base_url: Base URL của DeepSeek API

    Returns:
        Đoạn tóm tắt markdown (5-15 câu).
    """
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set — bỏ qua AI summary")
        return ""

    try:
        from openai import OpenAI
    except ImportError:
        logger.error(
            "openai package not installed. "
            "Install with: pip install project-graph-mapper[summary]"
        )
        return ""

    # Chuẩn bị context cho AI
    file_list = sorted(files.keys())
    lang_count: dict[str, int] = {}
    for fnode in files.values():
        lang = fnode.language or "unknown"
        lang_count[lang] = lang_count.get(lang, 0) + 1

    # Top symbols by kind
    kind_count: dict[str, int] = {}
    for sym in symbols.values():
        k = sym.kind.value
        kind_count[k] = kind_count.get(k, 0) + 1

    # Lấy top 20 symbols có nhiều used_by nhất
    top_symbols = sorted(
        symbols.values(),
        key=lambda s: len(s.used_by),
        reverse=True,
    )[:20]

    NL = chr(10)

    files_section = NL.join(f"- {f}" for f in file_list[:50])
    if len(file_list) > 50:
        files_section += f"{NL}..."

    langs_section = NL.join(
        f"- {lang}: {count} files"
        for lang, count in sorted(lang_count.items(), key=lambda x: -x[1])
    )

    kinds_section = NL.join(
        f"- {kind}: {count}"
        for kind, count in sorted(kind_count.items(), key=lambda x: -x[1])
    )

    top_section = NL.join(
        f"- {s.name} ({s.kind.value}) tại "
        f"{s.loc.file}:{s.loc.line} — {len(s.used_by)} callers"
        for s in top_symbols
        if s.used_by
    )

    prompt = f"""\
Bạn là chuyên gia phân tích phần mềm. Dựa vào thông tin cấu trúc dự án bên dưới,
hãy viết một đoạn tóm tắt tổng quan (summary) bằng tiếng Việt cho dự án này.

Yêu cầu:
- Viết 5-15 câu, dạng markdown
- Giải thích mục đích/chức năng chính của hệ thống
- Mô tả kiến trúc tổng quan (các layer, module chính)
- Đề cập công nghệ/ngôn ngữ sử dụng
- Không liệt kê chi tiết từng file, chỉ tóm tắt ý chính
- Trả về markdown text thuần, không có code block bao ngoài

## Thông tin dự án

**Files ({len(file_list)} files):**
{files_section}

**Ngôn ngữ:**
{langs_section}

**Symbols ({len(symbols)} total):**
{kinds_section}

**Top symbols (nhiều nơi gọi nhất):**
{top_section}
"""

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("DeepSeek API error: %s", e)
        return ""
