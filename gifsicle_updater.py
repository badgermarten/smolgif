"""Finds the gifsicle binary to use and keeps it up to date.

Windows: official signed builds from eternallybored.org (the Windows port linked from lcdf.org).
macOS: signed + notarized builds that .github/workflows/gifsicle-mac.yml publishes to this repo's Releases.
Updates install into a per-user folder, one subfolder per version, so a running job is never disturbed.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

GITHUB_REPO = "badgermarten/smolgif"
# Apple Developer Team ID that signs the macOS gifsicle builds; filled in by the DMG workflow
MAC_TEAM_ID = ""
WINDOWS_SIGNER = "Jernej Simončič"
CHECK_INTERVAL = 30 * 24 * 3600

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
EXE = "gifsicle.exe" if IS_WINDOWS else "gifsicle"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def app_dir():
    # PyInstaller bundles unpack to sys._MEIPASS; running from source uses the script folder
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif IS_MAC:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "smolgif")


def parse_version(text):
    match = re.search(r"(\d+)\.(\d+)", text or "")
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


def format_version(version):
    return f"{version[0]}.{version[1]}"


def binary_version(path):
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True,
                                timeout=15, creationflags=NO_WINDOW)
        return parse_version(result.stdout.splitlines()[0] if result.stdout else "")
    except (OSError, subprocess.SubprocessError):
        return (0, 0)


def find_gifsicle():
    """Returns (path, version) of the newest working gifsicle, or (None, (0, 0))."""
    candidates = [os.path.join(app_dir(), "gifsicle", EXE), os.path.join(app_dir(), "bin", EXE)]
    updates_dir = os.path.join(data_dir(), "gifsicle")
    if os.path.isdir(updates_dir):
        candidates += [os.path.join(updates_dir, name, EXE) for name in os.listdir(updates_dir)]

    best = (None, (0, 0))
    for path in candidates:
        if os.path.isfile(path):
            version = binary_version(path)
            if version > best[1]:
                best = (path, version)
    return best


def _state_path():
    return os.path.join(data_dir(), "state.json")


def check_due():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            last_check = json.load(f).get("last_check", 0)
    except (OSError, ValueError):
        last_check = 0
    return time.time() - last_check >= CHECK_INTERVAL


def mark_checked():
    os.makedirs(data_dir(), exist_ok=True)
    with open(_state_path(), "w", encoding="utf-8") as f:
        json.dump({"last_check": time.time()}, f)


def _download(url):
    if IS_WINDOWS:
        # Windows 10+ ships curl.exe (using the system's TLS), so the .exe doesn't need to bundle OpenSSL
        curl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
        result = subprocess.run([curl, "-fsSL", "--max-time", "60", "-A", "smolgif-updater", url],
                                capture_output=True, creationflags=NO_WINDOW)
        if result.returncode != 0:
            raise RuntimeError(f"Download failed: {result.stderr.decode('utf-8', 'replace').strip()}")
        return result.stdout

    import urllib.request
    request = urllib.request.Request(url, headers={"User-Agent": "smolgif-updater"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def latest_available():
    """Returns (version, download_url) of the newest build for this platform, or None."""
    if IS_WINDOWS:
        arch = {"ARM64": "winarm64", "X86": "win32"}.get(platform.machine().upper(), "win64")
        page = _download("https://eternallybored.org/misc/gifsicle/").decode("utf-8", "replace")
        versions = {parse_version(v) for v in re.findall(rf"gifsicle-(\d+\.\d+)-{arch}\.zip", page)}
        if not versions:
            return None
        version = max(versions)
        return version, f"https://eternallybored.org/misc/gifsicle/releases/gifsicle-{format_version(version)}-{arch}.zip"

    if IS_MAC:
        releases = json.loads(_download(f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=50"))
        best = None
        for release in releases:
            tag = release.get("tag_name", "")
            if not tag.startswith("gifsicle-") or release.get("draft") or release.get("prerelease"):
                continue
            asset = next((a for a in release.get("assets", []) if a["name"].endswith("-macos.zip")), None)
            if asset and (best is None or parse_version(tag) > best[0]):
                best = (parse_version(tag), asset["browser_download_url"])
        return best

    return None


def _verify_signature(exe):
    """Raises unless the binary is signed by the expected publisher."""
    if IS_WINDOWS:
        # Compare inside PowerShell so the non-ASCII signer name never crosses a console code page
        script = ("$s = Get-AuthenticodeSignature -LiteralPath $env:GIFSICLE_EXE; "
                  "if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -like \"CN=$env:GIFSICLE_SIGNER,*\") "
                  "{ 'OK' } else { \"FAIL $($s.Status)\" }")
        env = dict(os.environ, GIFSICLE_EXE=exe, GIFSICLE_SIGNER=WINDOWS_SIGNER)
        # PowerShell 7 entries in PSModulePath (inherited or from the registry) make Windows PowerShell
        # load PS7's incompatible Security module, so pin it to the built-in module folder
        env["PSModulePath"] = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                           "System32", "WindowsPowerShell", "v1.0", "Modules")
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, env=env, timeout=60, creationflags=NO_WINDOW)
        if result.stdout.strip() != "OK":
            raise RuntimeError(f"Signature check failed ({result.stdout.strip() or result.stderr.strip()})")
    elif IS_MAC:
        if not MAC_TEAM_ID:
            raise RuntimeError("This build has no signing Team ID configured, so updates can't be verified")
        subprocess.run(["codesign", "--verify", "--strict", exe], check=True, capture_output=True)
        details = subprocess.run(["codesign", "-dv", exe], capture_output=True, text=True).stderr
        if f"TeamIdentifier={MAC_TEAM_ID}" not in details:
            raise RuntimeError("Signature check failed (unexpected signer)")
    else:
        raise RuntimeError("Automatic updates are only supported on Windows and macOS")


def install(version, url):
    """Downloads, verifies and installs a gifsicle build; returns the new binary path. Raises on failure."""
    updates_dir = os.path.join(data_dir(), "gifsicle")
    os.makedirs(updates_dir, exist_ok=True)
    final_dir = os.path.join(updates_dir, format_version(version))

    with tempfile.TemporaryDirectory(dir=updates_dir) as tmp:
        archive = os.path.join(tmp, "download.zip")
        data = _download(url)
        if IS_MAC:
            import hashlib
            expected = _download(url + ".sha256").decode().split()[0].lower()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError("Download checksum mismatch")
        with open(archive, "wb") as f:
            f.write(data)

        extract_dir = os.path.join(tmp, "x")
        with zipfile.ZipFile(archive) as z:
            z.extractall(extract_dir)
        exe = next((os.path.join(root, EXE) for root, _, files in os.walk(extract_dir) if EXE in files), None)
        if not exe:
            raise RuntimeError(f"{EXE} not found in download")
        if not IS_WINDOWS:
            os.chmod(exe, 0o755)

        _verify_signature(exe)
        if binary_version(exe) != version:
            raise RuntimeError(f"Downloaded binary is not version {format_version(version)}")

        if os.path.isdir(final_dir):
            shutil.rmtree(final_dir)
        shutil.copytree(os.path.dirname(exe), final_dir)

    return os.path.join(final_dir, EXE)
