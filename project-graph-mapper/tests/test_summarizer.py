"""Tests for output/summarizer.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

from project_graph_mapper.output.summarizer import (
    extract_summary_from_file,
    find_summary_file,
)


class TestFindSummaryFile:
    def test_finds_readme(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("# My Project\n\nDescription here.")
        result = find_summary_file(tmp_path)
        assert result is not None
        assert result.name == "README.md"

    def test_finds_summary_md(self, tmp_path: Path):
        (tmp_path / "SUMMARY.md").write_text("# Summary\n\nOverview.")
        result = find_summary_file(tmp_path)
        assert result is not None
        assert result.name == "SUMMARY.md"

    def test_prefers_readme_over_summary(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("# Readme")
        (tmp_path / "SUMMARY.md").write_text("# Summary")
        result = find_summary_file(tmp_path)
        assert result is not None
        assert result.name == "README.md"

    def test_returns_none_when_no_md(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print('hello')")
        result = find_summary_file(tmp_path)
        assert result is None


class TestExtractSummaryFromFile:
    def test_extracts_description(self, tmp_path: Path):
        md = tmp_path / "README.md"
        md.write_text(textwrap.dedent("""\
            # My Project

            > A cool tool for dependency analysis.

            This tool scans source code and builds graphs.

            ## Installation

            ```bash
            pip install my-project
            ```

            ## Architecture

            The system has 3 layers: parser, graph, output.

            ## License

            MIT
        """))

        result = extract_summary_from_file(md)
        # Should keep description and architecture
        assert "A cool tool for dependency analysis" in result
        assert "3 layers" in result
        # Should skip installation and license
        assert "pip install" not in result
        assert "MIT" not in result

    def test_skips_badges(self, tmp_path: Path):
        md = tmp_path / "README.md"
        md.write_text(textwrap.dedent("""\
            [![Build](https://img.shields.io/badge/build-passing-green)]()
            [![Coverage](https://img.shields.io/badge/coverage-90%25-blue)]()

            # My Project

            Description text here.
        """))

        result = extract_summary_from_file(md)
        assert "img.shields.io" not in result
        assert "Description text here" in result

    def test_truncates_long_content(self, tmp_path: Path):
        md = tmp_path / "README.md"
        # Write a very long file
        content = "# Big Project\n\n" + ("This is a long line of text. " * 500)
        md.write_text(content)

        result = extract_summary_from_file(md, max_chars=200)
        assert len(result) <= 250  # some tolerance for truncation suffix
        assert "_(truncated)_" in result

    def test_handles_missing_file(self, tmp_path: Path):
        result = extract_summary_from_file(tmp_path / "nonexistent.md")
        assert result == ""

    def test_skips_vietnamese_install_section(self, tmp_path: Path):
        md = tmp_path / "README.md"
        md.write_text(textwrap.dedent("""\
            # Dự án của tôi

            Đây là công cụ phân tích.

            ## Cài đặt

            ```bash
            uv sync
            ```

            ## Cấu trúc dự án

            Hệ thống có 3 module chính.
        """), encoding="utf-8")

        result = extract_summary_from_file(md)
        assert "Đây là công cụ phân tích" in result
        assert "3 module chính" in result
        assert "uv sync" not in result
