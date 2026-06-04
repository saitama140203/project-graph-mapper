from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from .base import BaseParser
from ..graph.models import CallSite, FileNode, Location, Symbol, SymbolKind

logger = logging.getLogger(__name__)

# ── Prompt template ──────────────────────────────────────────────────────────

_PROMPT = """\
You are a code analyzer. Analyze the following {ext} file and return JSON only (no markdown, no explanation):
{{
  "imports": ["list of imported modules/files"],
  "symbols": [
    {{
      "name": "symbol name",
      "kind": "function|class|method|struct|interface|enum",
      "line": line_number,
      "signature": "first line of declaration"
    }}
  ],
  "calls": [
    {{"callee": "function name being called", "line": line_number, "context": "the line of code"}}
  ]
}}

File ({ext}):
---
{source_code}
"""

_KIND_MAP: dict[str, SymbolKind] = {
    "function":  SymbolKind.FUNCTION,
    "class":     SymbolKind.CLASS,
    "method":    SymbolKind.METHOD,
    "struct":    SymbolKind.STRUCT,
    "interface": SymbolKind.INTERFACE,
    "enum":      SymbolKind.ENUM,
    "trait":     SymbolKind.TRAIT,
    "constant":  SymbolKind.CONSTANT,
}


class AiParser(BaseParser):
    """Parser dùng Anthropic API cho các file chưa có tree-sitter grammar.

    Hoạt động:
      1. Đọc source code
      2. Kiểm tra cache (theo file hash) — nếu hit thì dùng cache
      3. Gửi lên Claude Sonnet, yêu cầu trả về JSON
      4. Parse JSON → FileNode + list[Symbol]
      5. Lưu cache
    """

    def __init__(
        self,
        *,
        ai_extensions: list[str],
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        cache_dir: Path | None = None,
    ) -> None:
        self._extensions = ai_extensions
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._cache_dir = cache_dir
        self._cache: dict[str, dict] = {}
        self._client = None  # lazy init

        if self._cache_dir:
            self._load_cache()

    def extensions(self) -> list[str]:
        return list(self._extensions)

    def engine_name(self) -> str:
        return "AI"

    def language_name(self) -> str:
        return "ai"

    def parse_file(self, filepath: Path, root: Path) -> tuple[FileNode, list[Symbol]]:
        rel = str(filepath.relative_to(root)).replace("\\", "/")
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        file_hash = hashlib.md5(source.encode()).hexdigest()

        # Check cache
        cache_key = f"{rel}:{file_hash}"
        cached = self._cache.get(cache_key)
        if cached:
            return self._build_result(cached, rel, file_hash)

        # Call API
        result = self._call_api(filepath.suffix, source)
        if result:
            self._cache[cache_key] = result
            self._save_cache()

        return self._build_result(result, rel, file_hash)

    def resolve_calls(
        self,
        filepath: Path,
        root: Path,
        all_symbols: dict[str, Symbol],
    ) -> None:
        """Resolve calls dùng data từ AI response (đã cache)."""
        rel = str(filepath.relative_to(root)).replace("\\", "/")
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        file_hash = hashlib.md5(source.encode()).hexdigest()

        cache_key = f"{rel}:{file_hash}"
        cached = self._cache.get(cache_key)
        if not cached:
            return

        calls = cached.get("calls", [])
        for call_info in calls:
            callee = call_info.get("callee", "")
            line_num = call_info.get("line", 0)
            ctx = call_info.get("context", "")

            if not callee:
                continue

            for sym_id, sym in all_symbols.items():
                if sym.name == callee and not sym_id.startswith(f"{rel}::"):
                    already = any(cs.file == rel and cs.line == line_num for cs in sym.used_by)
                    if not already:
                        sym.used_by.append(CallSite(file=rel, line=line_num, context=ctx))

    # ── API call ─────────────────────────────────────────────────────────────

    def _call_api(self, ext: str, source: str) -> dict:
        """Gọi Anthropic API để parse file."""
        if not self._api_key:
            logger.warning("ANTHROPIC_API_KEY not set — skipping AI parse")
            return {"imports": [], "symbols": [], "calls": []}

        try:
            import anthropic
        except ImportError:
            logger.error(
                "anthropic package not installed. "
                "Install with: pip install project-graph-mapper[ai]"
            )
            return {"imports": [], "symbols": [], "calls": []}

        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key)

        # Truncate very large files to avoid excessive token usage
        max_chars = 50_000
        if len(source) > max_chars:
            source = source[:max_chars] + "\n... (truncated)"

        prompt = _PROMPT.format(ext=ext, source_code=source)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()
            # Xử lý trường hợp response có markdown code block
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]

            return json.loads(content)

        except json.JSONDecodeError:
            logger.warning("AI returned invalid JSON")
            return {"imports": [], "symbols": [], "calls": []}
        except Exception as e:
            logger.warning("AI API error: %s", e)
            return {"imports": [], "symbols": [], "calls": []}

    # ── Build result from parsed JSON ────────────────────────────────────────

    def _build_result(
        self,
        data: dict | None,
        rel_path: str,
        file_hash: str,
    ) -> tuple[FileNode, list[Symbol]]:
        if not data:
            return FileNode(path=rel_path, language="ai", last_hash=file_hash), []

        file_node = FileNode(
            path=rel_path,
            imports=data.get("imports", []),
            last_hash=file_hash,
            language="ai",
        )

        symbols: list[Symbol] = []
        for sym_data in data.get("symbols", []):
            name = sym_data.get("name", "")
            if not name:
                continue

            kind_str = sym_data.get("kind", "function")
            kind = _KIND_MAP.get(kind_str, SymbolKind.FUNCTION)
            line = sym_data.get("line", 1)
            sig = sym_data.get("signature", "")

            sym = Symbol(
                id=f"{rel_path}::{name}",
                name=name,
                kind=kind,
                loc=Location(file=rel_path, line=line),
                signature=sig,
            )
            symbols.append(sym)
            file_node.symbols.append(sym.id)

        return file_node, symbols

    # ── Cache management ─────────────────────────────────────────────────────

    def _load_cache(self) -> None:
        if not self._cache_dir:
            return
        cache_file = self._cache_dir / "ai_cache.json"
        if cache_file.exists():
            try:
                self._cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save_cache(self) -> None:
        if not self._cache_dir:
            return
        cache_file = self._cache_dir / "ai_cache.json"
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(self._cache, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("Failed to save AI cache: %s", e)
