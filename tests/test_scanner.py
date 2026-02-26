"""Tests for schulpipeline.scanner — reader registry, readers, classification, bundles."""

from __future__ import annotations

import sqlite3
import textwrap
import zipfile
from pathlib import Path
from unittest import mock

import pytest

from schulpipeline.scanner import (
    READERS,
    ContentResult,
    ScanResult,
    ScannedFile,
    TaskBundle,
    build_bundles,
    classify_file,
    detect_project_bundles,
    read_docx,
    read_drawio,
    read_java,
    read_pdf,
    read_sqlite,
    read_txt,
    read_zip,
    scan_directory,
    to_manifest,
    to_summary,
)


# ============================================================
# Helpers
# ============================================================

def _make_tree(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    """Create a file tree under tmp_path. Returns the root."""
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
    return tmp_path


# ============================================================
# ContentResult dataclass
# ============================================================

class TestContentResult:
    def test_defaults(self):
        cr = ContentResult()
        assert cr.full_text == ""
        assert cr.error is None
        assert cr.language == ""
        assert cr.structure == {}

    def test_with_values(self):
        cr = ContentResult(full_text="hello", language="java", error=None)
        assert cr.full_text == "hello"
        assert cr.language == "java"


# ============================================================
# Reader Registry
# ============================================================

class TestReaderRegistry:
    def test_all_expected_readers_registered(self):
        expected = {"docx", "txt", "java", "python", "csharp", "javascript",
                    "html", "css", "fxml", "drawio", "db", "zip", "pdf"}
        assert expected == set(READERS.keys())

    def test_readers_are_callable(self):
        for name, reader in READERS.items():
            assert callable(reader), f"Reader {name} is not callable"

    def test_source_code_types_share_reader(self):
        assert READERS["java"] is READERS["python"]
        assert READERS["java"] is READERS["csharp"]


# ============================================================
# read_txt
# ============================================================

class TestReadTxt:
    def test_basic(self, tmp_path):
        p = tmp_path / "hello.txt"
        p.write_text("Line 1\nLine 2\n\nLine 4\n", encoding="utf-8")
        cr = read_txt(p)
        assert cr.error is None
        assert cr.paragraph_count == 3  # blank line skipped
        assert "Line 1" in cr.full_text
        assert len(cr.text_preview) <= 500

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        cr = read_txt(p)
        assert cr.error is None
        assert cr.paragraph_count == 0

    def test_nonexistent_file(self, tmp_path):
        p = tmp_path / "nope.txt"
        cr = read_txt(p)
        assert cr.error is not None


# ============================================================
# read_java
# ============================================================

class TestReadJava:
    def test_java_class_with_main(self, tmp_path):
        p = tmp_path / "Main.java"
        p.write_text(textwrap.dedent("""\
            import java.util.Scanner;

            public class Main {
                public static void main(String[] args) {
                    System.out.println("Hello");
                }

                public void helper() {}
            }
        """), encoding="utf-8")
        cr = read_java(p)
        assert cr.error is None
        assert cr.language == "java"
        assert "Main" in cr.structure["classes"]
        assert cr.structure["has_main"] is True
        assert "java.util.Scanner" in cr.structure["imports"]
        assert cr.structure["loc"] > 0
        assert cr.structure["is_template"] is False

    def test_template_detection(self, tmp_path):
        p = tmp_path / "Task_NN.java"
        p.write_text("public class Task {\n    // TODO: implement\n}\n", encoding="utf-8")
        cr = read_java(p)
        assert cr.structure["is_template"] is True

    def test_python_file_uses_same_reader(self, tmp_path):
        p = tmp_path / "script.py"
        p.write_text("def main():\n    pass\n", encoding="utf-8")
        cr = read_java(p)  # same reader
        assert cr.error is None
        assert cr.language == "python"

    def test_nonexistent(self, tmp_path):
        cr = read_java(tmp_path / "nope.java")
        assert cr.error is not None


# ============================================================
# read_drawio
# ============================================================

class TestReadDrawio:
    def test_basic_diagram(self, tmp_path):
        p = tmp_path / "diagram.drawio"
        p.write_text(textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <mxfile name="Test">
              <diagram>
                <mxGraphModel>
                  <root>
                    <mxCell id="0"/>
                    <mxCell id="1" parent="0"/>
                    <mxCell id="2" value="Start" parent="1" vertex="1"/>
                    <mxCell id="3" value="End" parent="1" vertex="1"/>
                    <mxCell id="4" parent="1" source="2" target="3" edge="1"/>
                  </root>
                </mxGraphModel>
              </diagram>
            </mxfile>
        """), encoding="utf-8")
        cr = read_drawio(p)
        assert cr.error is None
        assert "Start" in cr.structure["labels"]
        assert "End" in cr.structure["labels"]
        assert cr.structure["has_edges"] is True
        assert cr.language == "xml"
        assert cr.paragraph_count == 2

    def test_empty_diagram(self, tmp_path):
        p = tmp_path / "empty.drawio"
        p.write_text('<?xml version="1.0"?><mxfile/>', encoding="utf-8")
        cr = read_drawio(p)
        assert cr.error is None
        assert cr.structure["labels"] == []

    def test_invalid_xml(self, tmp_path):
        p = tmp_path / "bad.drawio"
        p.write_text("not xml at all {{{", encoding="utf-8")
        cr = read_drawio(p)
        assert cr.error is not None


# ============================================================
# read_sqlite
# ============================================================

class TestReadSqlite:
    def test_two_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE employees (id INTEGER, name TEXT, salary REAL)")
        conn.execute("INSERT INTO employees VALUES (1, 'Alice', 50000)")
        conn.execute("INSERT INTO employees VALUES (2, 'Bob', 60000)")
        conn.execute("CREATE TABLE departments (id INTEGER, dept TEXT)")
        conn.execute("INSERT INTO departments VALUES (1, 'Engineering')")
        conn.commit()
        conn.close()

        cr = read_sqlite(db_path)
        assert cr.error is None
        assert cr.table_count == 2
        assert cr.language == "sql"
        tables = cr.structure["tables"]
        emp = next(t for t in tables if t["name"] == "employees")
        assert emp["row_count"] == 2
        assert len(emp["columns"]) == 3
        assert cr.structure["total_rows"] == 3

    def test_empty_database(self, tmp_path):
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.close()
        cr = read_sqlite(db_path)
        assert cr.error is None
        assert cr.table_count == 0

    def test_corrupted_file(self, tmp_path):
        db_path = tmp_path / "corrupt.db"
        db_path.write_bytes(b"this is not a database")
        cr = read_sqlite(db_path)
        assert cr.error is not None


# ============================================================
# read_zip
# ============================================================

class TestReadZip:
    def test_java_project(self, tmp_path):
        zp = tmp_path / "GameFX.zip"
        with zipfile.ZipFile(str(zp), "w") as zf:
            zf.writestr("src/Main.java", "public class Main {}")
            zf.writestr("src/View.fxml", "<AnchorPane/>")
            zf.writestr("style.css", "body {}")
        cr = read_zip(zp)
        assert cr.error is None
        assert cr.structure["project_type"] == "javafx"
        assert cr.structure["has_src"] is True
        assert cr.structure["total_files"] == 3

    def test_python_project(self, tmp_path):
        zp = tmp_path / "app.zip"
        with zipfile.ZipFile(str(zp), "w") as zf:
            zf.writestr("app.py", "print('hi')")
            zf.writestr("requirements.txt", "requests")
        cr = read_zip(zp)
        assert cr.structure["project_type"] == "python"

    def test_not_a_zip(self, tmp_path):
        p = tmp_path / "fake.zip"
        p.write_text("not a zip", encoding="utf-8")
        cr = read_zip(p)
        assert cr.error is not None
        assert "Not a valid ZIP" in cr.error


# ============================================================
# read_pdf
# ============================================================

class TestReadPdf:
    def test_no_library_graceful(self, tmp_path):
        """Without pdfplumber/fitz installed, returns graceful error."""
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"%PDF-1.4 fake content")
        with mock.patch.dict("sys.modules", {"pdfplumber": None, "fitz": None}):
            cr = read_pdf(p)
        assert cr.error == "no_pdf_library"
        assert "install pdfplumber" in cr.text_preview


# ============================================================
# classify_file
# ============================================================

class TestClassifyFile:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        # Make it truly 0 bytes
        p.write_bytes(b"")
        sf = classify_file(p, tmp_path)
        assert sf.role == "empty"
        assert sf.confidence == 1.0

    def test_docx_pdf_duplicate(self, tmp_path):
        p = tmp_path / "Aufgabe.docx.pdf"
        p.write_bytes(b"fake pdf")
        sf = classify_file(p, tmp_path)
        assert sf.role == "duplicate"
        assert sf.duplicate_of is not None

    def test_png_is_info(self, tmp_path):
        p = tmp_path / "diagram.png"
        p.write_bytes(b"\x89PNG fake")
        sf = classify_file(p, tmp_path)
        assert sf.role == "info"

    def test_png_in_img_folder_is_resource(self, tmp_path):
        p = tmp_path / "Subject" / "IMG" / "photo.png"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"\x89PNG fake")
        sf = classify_file(p, tmp_path)
        assert sf.role == "resource"

    def test_db_is_resource(self, tmp_path):
        db_path = tmp_path / "northwind.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()
        sf = classify_file(db_path, tmp_path)
        assert sf.role == "resource"
        assert sf.content_type == "db"

    def test_zip_nn_is_task(self, tmp_path):
        zp = tmp_path / "GameFX_NN.zip"
        with zipfile.ZipFile(str(zp), "w") as zf:
            zf.writestr("Main.java", "class Main {}")
        sf = classify_file(zp, tmp_path)
        assert sf.role == "task"
        assert sf.content_type == "zip"

    def test_zip_normal_is_resource(self, tmp_path):
        zp = tmp_path / "GameFX.zip"
        with zipfile.ZipFile(str(zp), "w") as zf:
            zf.writestr("Main.java", "class Main {}")
        sf = classify_file(zp, tmp_path)
        assert sf.role == "resource"

    def test_drawio_is_info(self, tmp_path):
        p = tmp_path / "uml.drawio"
        p.write_text('<?xml version="1.0"?><mxfile/>', encoding="utf-8")
        sf = classify_file(p, tmp_path)
        assert sf.role == "info"
        assert sf.content_type == "drawio"

    def test_java_template_is_task(self, tmp_path):
        p = tmp_path / "Task_NN.java"
        p.write_text("public class Task {\n    // TODO: implement\n}\n", encoding="utf-8")
        sf = classify_file(p, tmp_path)
        assert sf.role == "task"
        assert sf.content_type == "java"

    def test_java_with_main_is_info(self, tmp_path):
        p = tmp_path / "Example.java"
        p.write_text(textwrap.dedent("""\
            public class Example {
                public static void main(String[] args) {
                    System.out.println("demo");
                }
            }
        """), encoding="utf-8")
        sf = classify_file(p, tmp_path)
        assert sf.role == "info"

    def test_java_solution_is_info(self, tmp_path):
        p = tmp_path / "Lösung_Task1.java"
        p.write_text("public class Task1 { void solve() {} }", encoding="utf-8")
        sf = classify_file(p, tmp_path)
        assert sf.role == "info"

    def test_txt_with_task_keywords(self, tmp_path):
        p = tmp_path / "Aufgabe_01.txt"
        p.write_text(
            "Aufgabe 1\nBearbeiten Sie die folgenden Fragen.\n"
            "Beschreiben Sie den Vorgang.\n"
            "Erklären Sie das Konzept.\n"
            "Nennen Sie drei Beispiele.\n",
            encoding="utf-8",
        )
        sf = classify_file(p, tmp_path)
        assert sf.role == "task"
        assert sf.confidence >= 0.5

    def test_txt_with_info_keywords(self, tmp_path):
        p = tmp_path / "Info_Material.txt"
        p.write_text(
            "Informationsteil\nDefinition: Ein Prozess ist...\n"
            "Grundsätzlich unterscheidet man...\n"
            "Beispiele dafür sind...\n" * 5,
            encoding="utf-8",
        )
        sf = classify_file(p, tmp_path)
        assert sf.role == "info"

    def test_unknown_extension(self, tmp_path):
        p = tmp_path / "mystery.xyz"
        p.write_bytes(b"binary stuff")
        sf = classify_file(p, tmp_path)
        assert sf.content_type == "unknown"
        assert sf.role == "unknown"


# ============================================================
# Bundle Detection
# ============================================================

class TestBuildBundles:
    def test_task_with_info_pair(self):
        files = [
            ScannedFile(path="SUB/Aufgabe_Lesen.docx", filename="Aufgabe_Lesen.docx",
                        subject_folder="SUB", size_bytes=100, content_type="docx",
                        role="task", confidence=0.8),
            ScannedFile(path="SUB/Lesen_Info.docx", filename="Lesen_Info.docx",
                        subject_folder="SUB", size_bytes=100, content_type="docx",
                        role="info", confidence=0.7),
        ]
        bundles = build_bundles(files)
        assert len(bundles) >= 1
        task_bundle = next((b for b in bundles if b.task_files), None)
        assert task_bundle is not None

    def test_empty_and_duplicate_excluded(self):
        files = [
            ScannedFile(path="SUB/empty.txt", filename="empty.txt",
                        subject_folder="SUB", size_bytes=0, content_type="txt",
                        role="empty", confidence=1.0),
            ScannedFile(path="SUB/x.docx.pdf", filename="x.docx.pdf",
                        subject_folder="SUB", size_bytes=50, content_type="pdf",
                        role="duplicate", confidence=0.95),
        ]
        bundles = build_bundles(files)
        assert len(bundles) == 0


class TestDetectProjectBundles:
    def test_mixed_types_project(self, tmp_path):
        """Directory with java + docx = project bundle."""
        files = [
            ScannedFile(path="SD/GameFX/Main.java", filename="Main.java",
                        subject_folder="SD", size_bytes=500, content_type="java",
                        role="info", confidence=0.7),
            ScannedFile(path="SD/GameFX/README.docx", filename="README.docx",
                        subject_folder="SD", size_bytes=800, content_type="docx",
                        role="info", confidence=0.6),
            ScannedFile(path="SD/GameFX/diagram.drawio", filename="diagram.drawio",
                        subject_folder="SD", size_bytes=300, content_type="drawio",
                        role="info", confidence=0.8),
        ]
        bundles = detect_project_bundles(files, tmp_path)
        assert len(bundles) == 1
        assert bundles[0].task_type == "project"

    def test_level_progression(self, tmp_path):
        """LVL files detected as progressive task."""
        files = [
            ScannedFile(path="SD/TicTac/LVL1_Basic.java", filename="LVL1_Basic.java",
                        subject_folder="SD", size_bytes=400, content_type="java",
                        role="info", confidence=0.7),
            ScannedFile(path="SD/TicTac/LVL2_AI.java", filename="LVL2_AI.java",
                        subject_folder="SD", size_bytes=600, content_type="java",
                        role="info", confidence=0.7),
            ScannedFile(path="SD/TicTac/TicTac.docx", filename="TicTac.docx",
                        subject_folder="SD", size_bytes=500, content_type="docx",
                        role="task", confidence=0.8),
        ]
        bundles = detect_project_bundles(files, tmp_path)
        assert len(bundles) == 1

    def test_no_project_for_docs_only(self, tmp_path):
        """Directory with only docs should NOT trigger project detection."""
        files = [
            ScannedFile(path="SUB/docs/A.docx", filename="A.docx",
                        subject_folder="SUB", size_bytes=100, content_type="docx",
                        role="task", confidence=0.8),
            ScannedFile(path="SUB/docs/B.docx", filename="B.docx",
                        subject_folder="SUB", size_bytes=100, content_type="docx",
                        role="info", confidence=0.7),
        ]
        bundles = detect_project_bundles(files, tmp_path)
        assert len(bundles) == 0


# ============================================================
# Integration: scan_directory
# ============================================================

class TestScanDirectory:
    def test_synthetic_tree(self, tmp_path):
        """Integration test with a synthetic SD-KLG-style directory."""
        _make_tree(tmp_path, {
            # A project directory
            "SD-TEST/Block1/GameFX/GameMain.java": textwrap.dedent("""\
                public class GameMain {
                    public static void main(String[] args) {}
                }
            """),
            "SD-TEST/Block1/GameFX/GameFX.drawio": (
                '<?xml version="1.0"?><mxfile>'
                '<diagram><mxGraphModel><root>'
                '<mxCell id="0"/><mxCell id="1" parent="0"/>'
                '<mxCell id="2" value="Player" parent="1" vertex="1"/>'
                '</root></mxGraphModel></diagram></mxfile>'
            ),
            "SD-TEST/Block1/GameFX/Aufgabe_Game.txt": (
                "Aufgabe 1\nErstellen Sie ein Spiel.\n"
                "Beschreiben Sie die Klassen.\nBearbeiten Sie das Projekt.\n"
            ),
            # A plain task
            "SD-TEST/Block2/Übung_SQL.txt": (
                "Übung SQL\nSchreiben Sie eine SELECT-Abfrage.\n"
                "Erklären Sie das Ergebnis.\nNennen Sie die Spalten.\n"
            ),
            # An empty file
            "SD-TEST/Block2/empty.txt": "",
        })

        # Make empty.txt truly 0 bytes
        (tmp_path / "SD-TEST/Block2/empty.txt").write_bytes(b"")

        result = scan_directory(tmp_path / "SD-TEST")
        assert result.total_files == 5
        assert len(result.files) == 5

        roles = {f.role for f in result.files}
        assert "empty" in roles
        assert "task" in roles or "info" in roles

        # Bundles should exist
        assert len(result.bundles) >= 1

        # The project directory should be detected
        content_types = {f.content_type for f in result.files}
        assert "java" in content_types
        assert "drawio" in content_types

    def test_skips_hidden_and_temp(self, tmp_path):
        _make_tree(tmp_path, {
            "visible.txt": "content",
            ".hidden.txt": "secret",
            "_temp.txt": "temp",
            "~lock.txt": "lock",
            "__pycache__/cache.pyc": "bytes",
        })
        result = scan_directory(tmp_path)
        assert result.total_files == 1
        assert result.files[0].filename == "visible.txt"


# ============================================================
# Output
# ============================================================

class TestOutput:
    def test_to_summary(self):
        result = ScanResult(scan_root="/test", total_files=2, subject_folders=["SUB"])
        result.files = [
            ScannedFile(path="SUB/a.txt", filename="a.txt", subject_folder="SUB",
                        size_bytes=100, content_type="txt", role="task", confidence=0.8),
            ScannedFile(path="SUB/b.txt", filename="b.txt", subject_folder="SUB",
                        size_bytes=50, content_type="txt", role="info", confidence=0.6),
        ]
        result.bundles = [
            TaskBundle(bundle_id="sub_a", title="A Task", subject="SUB",
                       task_files=["SUB/a.txt"]),
        ]
        summary = to_summary(result)
        assert "Scan: /test" in summary
        assert "TASK" in summary
        assert "INFO" in summary
        assert "File types:" in summary

    def test_to_manifest(self):
        result = ScanResult(scan_root="/test", total_files=1, subject_folders=["SUB"])
        result.files = [
            ScannedFile(path="SUB/a.txt", filename="a.txt", subject_folder="SUB",
                        size_bytes=100, content_type="txt", role="task", confidence=0.8),
        ]
        result.bundles = []
        m = to_manifest(result)
        assert m["total_files"] == 1
        assert m["files"][0]["role"] == "task"
        assert m["summary"]["task"] == 1
