# Linux runtime TLS investigation and verification — 2026-10-19

## Root cause and evidence

Work starts from the requested `integration/working-main` commit
`4bf084093cc1575832db5f1c778018478641001b`, not `main`. That branch still declares
0.1.0 and has only an AArch64 Linux builder. The user identified the failing
published release as 0.1.1.1, built from
`87450ca381d2b74a0bcb429812333324ef16072f`, with newer shared Linux build tooling.
The implementation is based on the requested integration source; it does not
import unrelated changes from the release source.

Both official 0.1.1.1 Linux archives were downloaded over verified HTTPS and
matched the release's official SHA256SUMS:

| Artifact | SHA256 |
| --- | --- |
| linux-x64 | `ce56b4d61ba4de9ad9b5fdf73f11c69db78ffeef41694b0697e49fe3e8b2e7fc` |
| linux-aarch64 | `af4e611a418b382b22b447155572fe26217a08b8cd04632ee8aef47c72fee056` |

The x64 artifact's actual libcrypto reports OpenSSL 3.0.13 and compiled roots
`/usr/lib/ssl/cert.pem` and `/usr/lib/ssl/certs`. Neither exists on this Arch
host. No SSL_CERT_FILE/SSL_CERT_DIR overrides were set. OpenSSL's default trust
load returns success (1) while loading **zero** trust objects. Loading the OS
bundle `/etc/ssl/cert.pem` into the same store loads **121** objects.

An additional isolated C embedding probe loaded the release's actual
`libpython3.12.so.1.0`, `_ssl` extension, libssl and libcrypto, with Python 3.12
standard-library files supplied separately. It reports Python 3.12.15, OpenSSL
3.0.13 and `cafile=None, capath=None`. Its default context has zero CA objects;
the patched resolver selects `linux-system-file` and loads 121 CA objects with
`check_hostname=True` and `verify_mode=2` (`CERT_REQUIRED`). This is a probe of
the released libraries, not a claim of full frozen GUI execution.

The AArch64 artifact's library strings independently confirm OpenSSL 3.0.13 and
the same compiled roots. It was not loaded/executed on this x86_64 host.
System Python 3.14.8 instead uses OpenSSL 3.6.5 with readable `/etc/ssl` defaults.
This establishes the distribution-specific compiled trust-path mismatch. It does
not depend on assuming that PyInstaller always omits roots or that the server
has an invalid chain. The separate curl check received HTTP 200 with successful
certificate verification from the official checksum endpoint.

The integration/released Linux builders do not explicitly provide CA resources
or install an SSL trust runtime hook. Both release architectures bundle OpenSSL;
system Python uses the host libraries. The new x64 build's recorded runtime hooks
are `pyi_rth_inspect.py` and `pyi_rth__tkinter.py`; no SSL monkeypatch is added.
Host library search differences were isolated by explicitly loading the release
libraries, rather than assuming system OpenSSL represented frozen execution.

Reproduce the release-library root-store observation in a fresh process:

```sh
python build/inspect_linux_openssl.py \
  --library '/path/to/release/_internal/libcrypto.so.3' \
  --system-ca /etc/ssl/cert.pem
```

Only inspect trusted libraries matching the host architecture. This probe makes
no network connection. See [troubleshooting](../runtime-tls-troubleshooting.md)
for ordinary/frozen Python diagnostics and the opt-in checksum smoke.

## Implementation and security

Linux HTTPS runtime requests retain urllib headers, timeout values, proxy
handling and redirect behavior. A verified context is supplied per request.
Explicit CA settings are validated and retain OpenSSL's normal behavior for
unset locations; no fallback roots are added in this case. Otherwise usable
compiled defaults win, then known OS-managed bundle/directory locations, then
certifi's packaged Mozilla roots. A handshake failure is never retried with
different roots. There is no HTTP fallback, unverified context, disabled hostname
checking, `verify=False`, or global SSL monkeypatch. Windows uses the original
urllib context selection.

NW.js still selects version 0.117.0 by default, downloads official SHASUMS256.txt,
matches the ARM64 archive name, verifies the entire SHA256, checks extraction
paths/links, expected directory and AArch64 ELF architecture. Cache validation
also requires nonempty `icudtl.dat` and `resources.pak`, rejecting executable-only
incomplete downloads. The host converter's x64/AArch64 build target is independent
of the game runtime target. User runtime overrides retain their existing behavior.

Partial archives are written separately and discarded on transfer failure;
Content-Length truncation is rejected. Existing destination files survive failed
transfers. Runtime staging remains temporary through integrity validation;
replacement restores the previous cache if installation fails. Valid cache hits
perform no TLS configuration or network work. Existing transactional source/
output behavior remains intact.

### Modified files

| File | Purpose |
| --- | --- |
| `megcfbt/tls.py` | Isolated Linux trust resolution and sanitized network-error classification. |
| `megcfbt/tls_diagnostics.py` | Offline/frozen diagnostics and explicit checksum-only live smoke. |
| `app/main.py` | Dispatch diagnostics before GUI imports. |
| `rpgmframe/runtime.py` | NW.js context integration, partial cleanup, truncation/resource validation and cache rollback. |
| `rpgmframe/godot_runtime.py` | Use shared trust for official Godot metadata/checksums/archive downloads. |
| `rpgmframe/godot_runtime_download.py` | Use shared trust for downloadable custom Godot/GodotSteam runtimes. |
| `rpgmframe/mkxp_runtime.py` | Use shared trust for mkxp runtime downloads. |
| `renframe/runtime.py` | Use shared trust for Ren'Py metadata and SDK archives. |
| `renframe/profiles.py` | Use shared trust for legacy-profile SDK downloads. |
| `megcfbt/runtime_download.py` | Use shared trust for native/Mono runtime bundles. |
| `pyproject.toml` | Linux-only certifi dependency and 0.1.1.2 candidate version. |
| `megcfbt/__init__.py` | Matching application/backend version. |
| `build/build_linux.sh` | Shared native Linux builder; collect CA data and license metadata. |
| `build/build_linux_aarch64.sh` | Native ARM64 wrapper with enforced host architecture. |
| `build/build_linux_x64.sh` | Native x64 wrapper, leaving ARM64 output runtime selection intact. |
| `build/release_metadata.py` | Verify x64/ARM64 application ELF architecture; select current-version notes. |
| `build/inspect_linux_openssl.py` | Reproducible released-library trust-store inspection. |
| `build/verify_frozen_runtime_fixture.py` | Actual frozen GUI cached-MV conversion check using a clearly synthetic ARM64 runtime. |
| `.github/workflows/build-linux-arm64.yml` | Both native build runners, frozen GUI/TLS/resource checks, cached conversion, optional live smoke. |
| `tests/test_tls.py` | Trust selection, invalid configuration, real MemoryBIO chain/hostname rejection, error categories and credential exclusion. |
| `tests/test_nwjs_provisioning.py` | Synthetic archive/checksum provisioning, cache safety, interrupted transfers and conversion preservation. |
| `tests/fixtures/tls/ca.pem` | Synthetic CA for deterministic cryptographic tests. |
| `tests/fixtures/tls/server.pem` | Synthetic localhost server certificate. |
| `tests/fixtures/tls/server.key` | Deliberately public, test-only server key. |
| `tests/fixtures/tls/README.md` | Fixture provenance, scope and renewal instructions. |
| `tests/test_godot_runtime_download.py` | Accept the new explicit context in network mocks. |
| `tests/test_godotsteam_provisioning.py` | Assert sanitized network failure while preserving cache-recovery check. |
| `tests/test_release_packaging.py` | Dynamic version fixture plus both native Linux archive architecture checks. |
| `README.md` | Link user-facing TLS troubleshooting. |
| `THIRD_PARTY_NOTICES.md` | certifi/Mozilla MPL-2.0 notice. |
| `docs/release-process.md` | Shared Linux builder, certificate packaging and opt-in CI smoke instructions. |
| `docs/runtime-tls-troubleshooting.md` | Root cause, trust configuration, failure categories, call chain, downloader inventory and ZIP preflight follow-up. |
| `docs/releases/0.1.1.2.md` | Next patch candidate bookkeeping; explicitly note base/release divergence. |
| `docs/reviews/linux-runtime-tls-2026-10-19.md` | This evidence/validation report. |

## Commands and results

Commands run from the feature checkout unless stated otherwise. No unit test
contacts an external service. Versioned release archives are local build artifacts
only; no release, tag, merge or application publication was performed.

| Command / check | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q --tb=short` (Python 3.12.15) | 426 passed; six existing-style tar extraction deprecation warnings. |
| `.venv/bin/python -m pytest -q --tb=short tests/test_tls.py tests/test_nwjs_provisioning.py` | Initial targeted run: 40 passed, before three additional trust tests were added. |
| `.venv/bin/python -m pytest -q --tb=short tests/test_tls.py tests/test_release_packaging.py` | 31 passed after inaccessible/missing material and Linux packaging tests were added. |
| `.venv-314/bin/python -m pytest -q --tb=short` (Python 3.14.8) | 425 passed, one pre-existing bytecode-detection failure. |
| `/home/tovakai/Projects/multi-engine-game-conversion-framework-by-tovakai/work/.venv/bin/python -m pytest -q --tb=short` from `/tmp/megcfbt-baseline` (before renaming the Python 3.14 venv) | Same bytecode-detection failure; 380 passed, one failed. No unrelated bytecode fix included. |
| `PIP_NO_INDEX=1 PIP_NO_BUILD_ISOLATION=0 bash build/build_linux_x64.sh` | Canonical native x64 build succeeds using installed Python 3.12 dependencies; local 0.1.1.2 archive generated. |
| `file 'dist/linux-x64/Multi-Engine Game Conversion Framework by tovakai/Multi-Engine Game Conversion Framework by tovakai'` | ELF64 x86-64 converter. |
| `'<frozen executable>' --tls-diagnostics` | Success: frozen=True, 121 OS CA objects, CERT_REQUIRED, hostname validation enabled, 117 valid bundled Mozilla CA objects. |
| `'<frozen executable>' --tls-diagnostics --smoke` | Attempted; fails with distinct DNS error because ordinary process network access is restricted. No claim of application HTTP 200. |
| `.venv/bin/python -m megcfbt.tls_diagnostics --smoke` | Same environmental DNS restriction; system/non-frozen trust resolution succeeds. |
| `'<frozen executable>' --verify-gui-startup --receipt /tmp/megcfbt-frozen-startup.json` | Attempted; Tk cannot connect to display `:0`. No successful GUI receipt. |
| `/tmp/megcfbt-xvfb/usr/bin/Xvfb :97 -screen 0 1024x768x24 -nolisten tcp -ac` | Attempted isolated display; sandbox refuses listening sockets. GUI conversion remains unavailable locally. |
| `bash build/build_linux_aarch64.sh` | Correctly refuses an x86_64 host; native AArch64 build/execution unavailable here. |
| `.venv/bin/python -m megcfbt.cli --version` | Reports 0.1.1.2. |
| `git diff --check` | Passes. |

The exact separate real-network control was:

```sh
curl -fL --connect-timeout 10 \
  -A 'RPGMFrame/0.0.1 (+https://github.com/AZumD/RPGMFrame)' \
  -H 'Accept: */*' -o /tmp/megcfbt-live-SHASUMS256.txt \
  --write-out 'HTTP %{http_code}; TLS verify result %{ssl_verify_result}\n' \
  https://dl.nwjs.io/v0.117.0/SHASUMS256.txt
```

Result: HTTP 200, TLS verify result 0. This is curl connectivity evidence,
**not** proof that the packaged urllib live smoke passed. No complete NW.js
archive was downloaded merely to repeat this connectivity test.

## Regression scope and remaining validation

The full suite exercises native/Mono, Ren'Py, legacy profiles, Godot/GodotSteam,
engine routing and CLI/builder behavior. New NW.js tests cover successful verified
install and cache reuse, invalid cache repair, previous-cache survival, install
rollback, wrong architecture, resource-incomplete and unsafe archives, missing/
invalid official checksum data, SHA256 mismatch, decode errors, interrupted/
short transfers, source preservation, output preservation, and offline overrides.
Real OpenSSL MemoryBIO tests prove successful trusted handshakes, untrusted-chain
rejection and hostname mismatch rejection without live sockets.

Native AArch64 hardware execution, actual graphical conversion and live packaged
urllib checksum/archive provisioning are not validated locally. Both native CI
runners now build the package, check frozen GUI startup, parse the actual bundled
CA data, and perform cached synthetic MV conversion. Those are planned CI checks,
not results claimed from this session. The optional live CI smoke must be run
explicitly. The synthetic cached ELF is not a playable runtime or gameplay test.
No full real NW.js archive, uncached physical-device conversion or gameplay
validation was performed; those remain acceptance work in a capable environment.

ZIP runtime preflight is documented as a separate follow-up to preserve existing
multi-engine precedence, deep/archive inspection and extraction safety. This patch
does not avoid the reported 3.7 GiB extraction before provisioning. Artwork and
standalone STS2 scripts retain their independently scoped download mechanisms.

The requested integration branch predates the failing release. Promotion must
account for that divergence and the already-published features/version line.
The candidate version bookkeeping does not authorize publication from this older
branch. The PR remains reviewable without merging, tagging or releasing it.
