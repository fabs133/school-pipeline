# Scanner v3: File Inspection & Project-Aware Classification

## Context

The scanner currently handles `.docx`, `.txt`, `.pdf`, `.png`. The SD-KLG folder
reveals a completely different teaching style: structured project directories with
source code, databases, diagrams, archives, and multi-level task progressions.

New file types discovered:
- `.java` — source code (EventDispatcher.java, SchreckEvent.java)
- `.drawio` — diagram files (XML-based, contains UML/flowcharts)
- `.db` / `.sqlite` — SQLite databases shipped with SQL exercises
- `.zip` — project archives (AutorennenFX.zip, BingoFX_NN.zip, Sortieren_NN.zip)
- `.pdf` — already "supported" but only as opaque binary; needs text extraction

Current scanner location: `schulpipeline/scanner.py` (~540 lines)
Tests: `tests/test_scanner.py` (25 tests)

---

## Plan

### Step 1: File Reader Registry

**What**: Replace the hardcoded if/elif chain in `classify_file()` with a
pluggable reader registry. Each reader returns a standardized `ContentResult` dict.

**Why**: Adding 5+ new readers to the existing if/elif is unmaintainable.
The registry pattern pays for itself immediately here.

**Contract**:
```python
# New dataclass for reader output — same shape as current dicts but explicit
@dataclass
class ContentResult:
    full_text: str = ""
    text_preview: str = ""           # first 500 chars
    paragraph_count: int = 0
    table_count: int = 0
    empty_table_cells: int = 0
    image_count: int = 0
    language: str = ""               # "java", "sql", "xml", "german", ""
    structure: dict = field(default_factory=dict)  # type-specific metadata
    error: str | None = None

# Registry: maps content_type → reader function
READERS: dict[str, Callable[[Path], ContentResult]] = {
    "docx": read_docx,
    "txt":  read_txt,
    "java": read_java,
    "xml":  read_drawio,
    "db":   read_sqlite,
    "zip":  read_zip,
    "pdf":  read_pdf,
}
```

**File**: `schulpipeline/scanner.py` — refactor `_read_docx`/`_read_txt` into
registry, add `ContentResult` dataclass.

**Tests**: Existing tests must still pass (reader output shape unchanged).

**Acceptance**: `python -m pytest tests/test_scanner.py` — all green.

---

### Step 2: Java/Source Code Reader

**What**: Read `.java` files, extract class names, method signatures, imports.

**Why**: Determines if a file is a task template (`_NN` pattern = student fills in),
a solution/example, or a library file.

**Implementation**:
```python
def read_java(path: Path) -> ContentResult:
    """Read a Java source file. Extract structural metadata."""
    text = path.read_text(encoding="utf-8", errors="replace")
    
    structure = {
        "classes": [],      # regex: class/interface/enum declarations
        "methods": [],      # regex: method signatures (public/private/protected ... {)
        "imports": [],      # import lines
        "has_main": False,  # contains public static void main
        "loc": 0,           # non-blank lines
        "is_template": False,  # contains TODO/FIXME/NN/YOUR_CODE_HERE patterns
    }
    # ... regex extraction ...
    
    return ContentResult(
        full_text=text, text_preview=text[:500],
        paragraph_count=text.count("\n"),
        language="java", structure=structure,
    )
```

**Extend `content_type` mapping**:
```python
type_map additions: {".java": "java", ".py": "java", ".cs": "java", ".js": "java"}
# All source code goes through the same reader with minor language adaptation
```

**Classification signals**:
- `_NN` in filename → task template (student fills in blanks)
- `Lösung` in filename → solution
- `has_main` + no `_NN` → example/reference code
- Contains `TODO`/`FIXME`/`// YOUR CODE HERE` → task template

**Tests**:
- Java file with class + main method → detected
- `_NN` template file → classified as task
- Solution file → classified as info/solution

---

### Step 3: Drawio/XML Reader

**What**: Parse `.drawio` files (XML) to extract diagram metadata.

**Why**: Diagrams often show architecture (UML, flowcharts, ERDs). Knowing what's
in them helps bundle them with the right task.

**Implementation**:
```python
def read_drawio(path: Path) -> ContentResult:
    """Read a .drawio file (XML). Extract text labels and diagram type."""
    import xml.etree.ElementTree as ET
    
    tree = ET.parse(str(path))
    root = tree.getroot()
    
    # Extract all text content from mxCell value attributes
    labels = []
    for cell in root.iter("mxCell"):
        value = cell.get("value", "").strip()
        if value and not value.startswith("<"):  # skip HTML-formatted cells
            labels.append(value)
    
    structure = {
        "labels": labels,            # all text in diagram boxes
        "cell_count": len(list(root.iter("mxCell"))),
        "has_edges": any(c.get("edge") for c in root.iter("mxCell")),
        "diagram_name": root.get("name", path.stem),
    }
    
    full_text = "\n".join(labels)
    return ContentResult(
        full_text=full_text, text_preview=full_text[:500],
        paragraph_count=len(labels),
        language="xml", structure=structure,
    )
```

**Classification**: Always `info` (reference diagram). Bundle by filename stem
matching with task `.docx` files.

**Tests**:
- Valid drawio XML → labels extracted
- Empty/minimal drawio → no crash, empty labels

---

### Step 4: SQLite Database Reader

**What**: Inspect `.db` and `.sqlite` files — list tables, schemas, row counts.

**Why**: These are exercise databases. Knowing the schema tells us what SQL
exercises they belong to and whether they're empty templates or populated.

**Implementation**:
```python
def read_sqlite(path: Path) -> ContentResult:
    """Inspect a SQLite database. Extract schema and row counts."""
    import sqlite3
    
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)  # read-only!
    cursor = conn.cursor()
    
    tables = []
    for (name,) in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall():
        cols = cursor.execute(f"PRAGMA table_info('{name}')").fetchall()
        count = cursor.execute(f"SELECT COUNT(*) FROM '{name}'").fetchone()[0]
        tables.append({
            "name": name,
            "columns": [{"name": c[1], "type": c[2]} for c in cols],
            "row_count": count,
        })
    
    conn.close()
    
    # Build text representation for keyword matching
    text_parts = [f"Database: {path.name}"]
    for t in tables:
        cols_str = ", ".join(f"{c['name']} {c['type']}" for c in t["columns"])
        text_parts.append(f"Table {t['name']} ({t['row_count']} rows): {cols_str}")
    
    full_text = "\n".join(text_parts)
    return ContentResult(
        full_text=full_text, text_preview=full_text[:500],
        table_count=len(tables),
        paragraph_count=len(tables),
        language="sql",
        structure={"tables": tables, "total_rows": sum(t["row_count"] for t in tables)},
    )
```

**Classification**: Always `resource` (new role) — a database is neither task nor
info, it's a resource that accompanies a task.

**New role**: `resource` — files that support tasks but aren't tasks themselves
(databases, ZIP archives, images in IMG/ folders).

**Tests**:
- Create in-memory SQLite with 2 tables → schema extracted
- Empty database → no crash
- Corrupted file → graceful error

---

### Step 5: ZIP Archive Reader

**What**: List ZIP contents without extracting. Detect project type from contents.

**Why**: ZIP files are either project templates (`_NN.zip`) or reference
implementations. Contents reveal the project structure.

**Implementation**:
```python
def read_zip(path: Path) -> ContentResult:
    """List ZIP archive contents and detect project type."""
    import zipfile
    
    if not zipfile.is_zipfile(str(path)):
        return ContentResult(error=f"Not a valid ZIP: {path.name}")
    
    with zipfile.ZipFile(str(path), "r") as zf:
        entries = zf.namelist()
    
    extensions = [Path(e).suffix.lower() for e in entries if Path(e).suffix]
    
    # Detect project type
    project_type = "unknown"
    if any(e.endswith(".java") for e in entries):
        project_type = "java"
    elif any(e.endswith(".py") for e in entries):
        project_type = "python"
    elif any(e.endswith(".fxml") or e.endswith(".css") for e in entries):
        project_type = "javafx"
    
    structure = {
        "entries": entries[:50],  # cap for sanity
        "total_files": len(entries),
        "extensions": list(set(extensions)),
        "project_type": project_type,
        "has_src": any("src/" in e or "src\\" in e for e in entries),
    }
    
    full_text = f"Archive: {path.name}\n" + "\n".join(entries[:50])
    return ContentResult(
        full_text=full_text, text_preview=full_text[:500],
        paragraph_count=len(entries),
        language="", structure=structure,
    )
```

**Classification**:
- `_NN.zip` → task (template project for student)
- Other `.zip` → resource

**Tests**:
- Create temp ZIP with .java files → project_type detected
- Non-ZIP file with .zip extension → graceful error

---

### Step 6: PDF Text Extraction

**What**: Extract text from PDFs using `pdfplumber` or `PyMuPDF` (fitz).

**Why**: Currently PDFs are classified as `info` with 50% confidence — pure
guesswork. SD-KLG has real PDF tasks ("SQL - Personal - Aufgaben.pdf").

**Implementation**:
```python
def read_pdf(path: Path) -> ContentResult:
    """Extract text from a PDF file."""
    # Try pdfplumber first (better table extraction), fall back to PyMuPDF
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
            tables = []
            for p in pdf.pages:
                tables.extend(p.extract_tables() or [])
        full_text = "\n".join(pages)
        return ContentResult(
            full_text=full_text, text_preview=full_text[:500],
            paragraph_count=full_text.count("\n"),
            table_count=len(tables),
            language="", structure={"page_count": len(pages)},
        )
    except ImportError:
        pass
    
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        pages = [page.get_text() for page in doc]
        full_text = "\n".join(pages)
        doc.close()
        return ContentResult(
            full_text=full_text, text_preview=full_text[:500],
            paragraph_count=full_text.count("\n"),
            language="", structure={"page_count": len(pages)},
        )
    except ImportError:
        pass
    
    # No PDF library available — return minimal result
    return ContentResult(
        text_preview=f"[PDF: {path.name}, {path.stat().st_size} bytes — install pdfplumber for text extraction]",
        structure={"page_count": 0},
        error="no_pdf_library",
    )
```

**Dependency**: Optional. `pdfplumber` preferred, `PyMuPDF` fallback, graceful
degradation if neither installed. Add to `pyproject.toml` as optional:
```toml
[project.optional-dependencies]
pdf = ["pdfplumber>=0.9"]
```

**Tests**:
- Mock pdfplumber import → text extracted
- No PDF library → graceful fallback with error message

---

### Step 7: Project-Aware Bundle Detection

**What**: Detect multi-file project structures (Autorenner/, TicTacTo/, LightsFX/)
and bundle them as single logical units.

**Why**: Current bundler works per-file by filename similarity. SD-KLG has
directory-based projects where ALL files in a folder belong together.

**Implementation** — new function `detect_project_bundles()`:
```python
def detect_project_bundles(files: list[ScannedFile], scan_root: Path) -> list[TaskBundle]:
    """Detect directory-based project bundles.
    
    Heuristics:
    1. Directory contains mixed file types (.java + .docx + .drawio) → project
    2. Directory has LVL/Level progression in filenames → progressive task
    3. Directory contains _NN or Lösung files → task + solution pair
    4. IMG/ subdirectory → visual resources for parent
    """
    # Group files by their immediate parent directory
    by_dir: dict[str, list[ScannedFile]] = {}
    for f in files:
        parent = str(Path(f.path).parent)
        by_dir.setdefault(parent, []).append(f)
    
    project_bundles = []
    for dir_path, dir_files in by_dir.items():
        types = {f.content_type for f in dir_files}
        
        # Mixed types (code + docs + diagrams) = project
        is_project = len(types & {"java", "docx", "xml", "zip"}) >= 2
        
        # LVL progression detection
        has_levels = any(re.search(r"LVL\d|Level\d", f.filename, re.I) for f in dir_files)
        
        if is_project or has_levels:
            bundle = TaskBundle(
                bundle_id=_make_id(dir_path.split(os.sep)[-1], "project"),
                title=Path(dir_path).name,
                subject=_find_subject_folder(dir_path),
                task_type="project",
            )
            for f in dir_files:
                if f.role == "task" or "_NN" in f.filename:
                    bundle.task_files.append(f.path)
                elif f.role == "resource" or f.content_type in ("db", "zip", "png"):
                    bundle.duplicates.append(f.path)  # reuse as "resources"
                elif "Lösung" in f.filename or "Loesung" in f.filename:
                    bundle.answer_files.append(f.path)
                else:
                    bundle.info_files.append(f.path)
            project_bundles.append(bundle)
    
    return project_bundles
```

**IMG/ handling**: Files in `IMG/` subdirectories get role `resource` and are
linked to the parent directory's bundle automatically.

**Tests**:
- Directory with .java + .docx + .drawio → detected as project
- LVL1/LVL2/LVL3 files → progressive task bundle
- IMG/ subdirectory → resources linked to parent

---

### Step 8: Extended content_type Map & Role

**What**: Update the type mapping and add the `resource` role.

```python
TYPE_MAP = {
    # Documents
    ".docx": "docx", ".pdf": "pdf", ".txt": "txt", ".pptx": "pptx", ".xlsx": "xlsx",
    # Source code
    ".java": "java", ".py": "python", ".cs": "csharp", ".js": "javascript",
    ".html": "html", ".css": "css", ".fxml": "fxml",
    # Data
    ".db": "db", ".sqlite": "db", ".sql": "sql", ".csv": "csv", ".json": "json",
    # Diagrams
    ".drawio": "xml",
    # Archives
    ".zip": "zip",
    # Images
    ".png": "png", ".jpg": "png", ".jpeg": "png", ".gif": "png",
}

# Updated role set
ROLES = {"task", "info", "answer", "onenote_export", "duplicate", "empty", "resource", "unknown"}
```

---

### Step 9: Tests

Each step above includes its own test requirements. Additionally:

**Integration test**: Run scanner on a synthetic SD-KLG-style directory tree:
```
test_project_tree/
  SD-TEST/
    Block 1/
      Projects/
        GameFX/
          GameMain.java
          GameView.java
          GameFX.drawio
          GameProject.docx
          GameFX_NN.zip
        Übungen/
          Aufgabe_Testen.pdf
          ÜbungSoft.docx
    Block 2/
      northwind.sqlite
      SQL - Personal - Aufgaben.pdf
```

Expected: 2 project bundles (GameFX, Übungen), SQL task bundled with database.

---

### Step 10: CLI Updates

Add `--verbose` flag that prints `ContentResult.structure` per file (useful for
debugging reader output).

Add file type statistics to summary:
```
File types: 12 docx, 8 png, 5 pdf, 4 java, 3 db, 2 drawio, 2 zip
```

---

## Decision Log

| # | Decision | Choice | Reason |
|---|----------|--------|--------|
| 1 | Reader registry vs if/elif | Registry (dict) | 5+ new types; if/elif doesn't scale |
| 2 | New `resource` role | Yes | DBs/ZIPs/images aren't task/info; need their own category |
| 3 | PDF library | Optional pdfplumber | Don't force heavy dep; graceful fallback |
| 4 | SQLite read mode | `?mode=ro` URI | Safety: never modify student databases |
| 5 | ZIP handling | List only, don't extract | Fast, safe, sufficient for classification |
| 6 | Project detection | Directory-based heuristic | SD-KLG organizes by folder, not filename |
| 7 | Source code reader | One reader, all languages | Structure extraction is similar across languages |
| 8 | drawio parsing | stdlib xml.etree | No extra dependency; drawio is simple XML |

## Execution Order

Steps 1→8 are code changes. Step 9 is tests. Step 10 is polish.

Dependencies: Step 1 (registry) must come first — all other readers plug into it.
Steps 2–6 are independent of each other and can be done in any order.
Step 7 depends on steps 2–6 (needs new content types to detect projects).

Estimated scope: ~400 lines new code, ~200 lines refactored, ~150 lines tests.