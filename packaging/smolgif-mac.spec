# PyInstaller spec for the universal (Apple Silicon + Intel) macOS app, trimmed for size.
# Build from the repo root: python -m PyInstaller packaging/smolgif-mac.spec
# Env: GIFSICLE_BIN_DIR (folder holding the signed gifsicle + COPYING), BUNDLE_ID, APP_VERSION
import os

root = os.path.dirname(SPECPATH)
gifsicle_dir = os.environ.get("GIFSICLE_BIN_DIR", os.path.join(root, "build", "bin"))

# Modules smolgif never uses. Downloads go through /usr/bin/curl, so no OpenSSL (ssl, _hashlib);
# hashlib still works for the update checksum via Python's built-in SHA-256.
EXCLUDES = [
    "ssl", "_ssl", "_hashlib", "urllib.request", "http", "email",
    "unicodedata", "decimal", "_decimal", "xml", "pyexpat", "lzma", "_lzma", "bz2", "_bz2",
    "asyncio", "multiprocessing", "sqlite3", "unittest", "pydoc", "doctest", "pdb", "curses", "readline",
]

# Tk only needs a couple of Tcl encodings, and never Tcl's time-zone database
KEEP_TCL_ENCODINGS = {"ascii.enc", "cp1252.enc", "iso8859-1.enc", "utf-8.enc", "macRoman.enc"}


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
    binaries=[(os.path.join(gifsicle_dir, "gifsicle"), "bin")],
    datas=[(os.path.join(gifsicle_dir, "COPYING"), "bin")],
    excludes=EXCLUDES,
)
a.datas = [entry for entry in a.datas if keep_data(entry[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="smolgif",
    console=False,
    target_arch="universal2",
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="smolgif", upx=False)

app = BUNDLE(
    coll,
    name="smolgif.app",
    bundle_identifier=os.environ.get("BUNDLE_ID"),
    version=os.environ.get("APP_VERSION", "0.0.0"),
    info_plist={"NSHighResolutionCapable": True},
)
