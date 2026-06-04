import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ..graph.models import FileNode, Symbol


class JsonWriter:

    def write(
        self,
        files:   dict[str, FileNode],
        symbols: dict[str, Symbol],
        output_path: Path,
    ) -> Path:
        data = {
            "generated": datetime.now().isoformat(),
            "stats": {
                "total_files":   len(files),
                "total_symbols": len(symbols),
            },
            "files":   {k: asdict(v) for k, v in files.items()},
            "symbols": {k: asdict(v) for k, v in symbols.items()},
        }
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return output_path
