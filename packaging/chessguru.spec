# PyInstaller recipe for the packaged app. Build with:
#   uv run --group build pyinstaller packaging/chessguru.spec --noconfirm
# Put the Stockfish binary in packaging/stockfish/ first to bundle it.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "src" / "chessguru" / "app"), "chessguru/app"),  # Streamlit runs these files
    (str(ROOT / "dbt" / "dbt_project.yml"), "dbt"),
    (str(ROOT / "dbt" / "profiles.yml"), "dbt"),
    (str(ROOT / "dbt" / "models"), "dbt/models"),
    (str(ROOT / "dbt" / "macros"), "dbt/macros"),
    (str(ROOT / "dbt" / "tests"), "dbt/tests"),
    (str(ROOT / "LICENSE"), "."),  # ChessGuru's own licence (GPL-3.0)
]
stockfish = ROOT / "packaging" / "stockfish"
if stockfish.exists():
    datas.append((str(stockfish), "stockfish"))

binaries = []
hiddenimports = []
for package in ("streamlit", "plotly", "dbt", "dbt_common", "dbt_extractor", "duckdb",
                "agate", "mashumaro", "chessguru"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
for dist in ("streamlit", "dbt-core", "dbt-duckdb", "dbt-adapters", "dbt-common",
             "dbt-protos", "plotly", "duckdb"):
    datas += copy_metadata(dist)

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tkinter", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChessGuru",
    console=True,  # the window shows progress; closing it stops the app
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ChessGuru")
