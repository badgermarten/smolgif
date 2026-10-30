# PyInstaller spec for the single-file Windows build, trimmed for size.
# Build from the repo root: python -m PyInstaller packaging/smolgif-windows.spec
import os

root = os.path.dirname(SPECPATH)

# Modules smolgif never uses on Windows. Downloads go through Windows' curl.exe, so no OpenSSL (ssl, _hashlib).
EXCLUDES = [
    "ssl", "_ssl", "_hashlib", "hashlib", "urllib.request", "http", "email",
    "unicodedata", "decimal", "_decimal", "xml", "pyexpat", "lzma", "_lzma", "bz2", "_bz2",
    "asyncio", "multiprocessing", "sqlite3", "unittest", "pydoc", "doctest", "pdb", "ctypes.macholib",
]

# Tk only needs a couple of Tcl encodings, and never Tcl's time-zone database
KEEP_TCL_ENCODINGS = {"ascii.enc", "cp1252.enc", "iso8859-1.enc", "utf-8.enc"}


def keep_data(dest):
    parts = dest.replace("\\", "/").split("/")
    if parts[0] == "_tcl_data" and len(parts) > 1:
        if parts[1] == "tzdata":
            return False
        if parts[1] == "encoding" and parts[-1] not in KEEP_TCL_ENCODINGS:
            return False
    return True


a = Analysis(
    [os.path.join(root, "smolgif.py")],
    pathex=[root],
    datas=[
        (os.path.join(root, "gifsicle", "gifsicle.exe"), "gifsicle"),
        (os.path.join(root, "gifsicle", "doc", "COPYING"), "gifsicle"),
    ],
    excludes=EXCLUDES,
)
a.datas = [entry for entry in a.datas if keep_data(entry[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="smolgif",
    console=False,
    upx=False,  # UPX-packed executables trip antivirus false positives
)
