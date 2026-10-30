# smolgif

A small desktop app for batch-compressing animated GIFs with [Gifsicle](https://www.lcdf.org/gifsicle/).
By default it uses the same settings as [ezgif.com's optimizer](https://ezgif.com/optimize): `-O3 --lossy=30 --gamma=1`.

Each GIF is saved next to the original as `name-Opt.gif`. Several files are processed at once, one per CPU core pair.

## Install

**Windows:** download [smolgif.exe](../../releases/latest/download/smolgif.exe) and double-click it. Nothing to install.
The first time, Windows SmartScreen may say it doesn't recognize the app: click **More info → Run anyway**.

**Mac:** download [smolgif-mac.dmg](../../releases/latest/download/smolgif-mac.dmg), open it, and drag
**smolgif** into Applications. The app is signed and notarized by Apple.

**From source:** with [Python 3](https://www.python.org/downloads/) installed, double-click `smolgif.pyw` on Windows
or run `python3 smolgif.py`.

## Settings

| Setting | Default | What it does |
|---|---|---|
| Lossy | 30 | Higher means smaller files with more noise (0 turns it off) |
| Optimize | 3 | Gifsicle's `-O` level; 2 is about twice as fast and usually almost as small |
| Max colors | blank | Reduce the palette to 2–256 colors |
| Gamma 1 lossy | on | Measures lossy error the way Gifsicle did before 1.96 and the way ezgif does; gives much smaller files |

## Gifsicle updates

Once a month the app checks for a newer Gifsicle and asks before installing it. You can also click
**Check for Gifsicle Updates** at any time. Updates are verified before they are used:

- **Windows** downloads the official build from [eternallybored.org](https://eternallybored.org/misc/gifsicle/)
  (the Windows port linked from lcdf.org) and only accepts it if it is validly signed by its maintainer.
- **Mac** downloads from this repo's `gifsicle-X.Y` releases and only accepts it if the checksum matches
  and it is signed with our Apple Team ID.

Updates are installed per user (`%LOCALAPPDATA%\smolgif` or `~/Library/Application Support/smolgif`),
so no new app release is needed.

## How the Mac builds work (maintainers)

Two GitHub Actions workflows do the Mac work:

- **Gifsicle for macOS** (`.github/workflows/gifsicle-mac.yml`) runs on the 1st of every month. If lcdf.org has a
  version that has not been built yet, it builds a universal binary, signs and notarizes it, and publishes a
  `gifsicle-X.Y` release with the source tarball attached. Mac users get it through the in-app update check.
- **Release** (`.github/workflows/release.yml`) builds `smolgif.exe` and the signed, notarized Mac app and DMG.
  Push a tag such as `v1.0.1` to publish both on the Releases page, or run it manually to get build artifacts.
  It needs at least one `gifsicle-X.Y` release to exist, so run *Gifsicle for macOS* once first.

Both need these repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `MACOS_CERTIFICATE` | Your *Developer ID Application* certificate exported from Keychain Access as .p12, base64-encoded (`base64 -i cert.p12 \| pbcopy`) |
| `MACOS_CERTIFICATE_PASSWORD` | The password you set when exporting the .p12 |
| `APPLE_ID` | The Apple ID email of your developer account |
| `APPLE_APP_PASSWORD` | An app-specific password from [account.apple.com](https://account.apple.com) → Sign-In and Security |
| `APPLE_TEAM_ID` | Your 10-character Team ID from [developer.apple.com/account](https://developer.apple.com/account) → Membership |

## Licenses

Gifsicle is © Eddie Kohler and distributed under the GNU GPL v2; see `gifsicle/doc/COPYING`.
Its source code is at <https://www.lcdf.org/gifsicle/>, and each `gifsicle-X.Y` release here includes the exact
source tarball it was built from. The Windows binaries are by Jernej Simončič (eternallybored.org).
