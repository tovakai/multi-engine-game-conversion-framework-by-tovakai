# Runtime download TLS failures on Linux

## Confirmed mechanism

The official 0.1.1.1 x64 artifact bundles Python 3.12.15 and OpenSSL 3.0.13.
Its OpenSSL library's compiled trust paths are `/usr/lib/ssl/cert.pem` and
`/usr/lib/ssl/certs`. Both are absent on the Arch host used in this investigation.
The released AArch64 library contains the same compiled paths and version.
System Python 3.14.8 uses OpenSSL 3.6.5 with existing `/etc/ssl/cert.pem` and
`/etc/ssl/certs` paths. No certificate environment overrides were set.

Loading default trust with the actual released x64 Python/OpenSSL libraries
produced zero CA certificates. The per-request resolver loaded 121 OS CA
certificates from `/etc/ssl/cert.pem`, with `CERT_REQUIRED` and hostname checks
enabled. This confirms a distribution-specific compiled-path mismatch. It does
not imply that all PyInstaller applications have defective TLS or that the
NW.js CDN has a broken certificate chain. The reported HTTP 403 using system
Python occurs after successful TLS negotiation; it is a different failure.

## Trust selection

Linux runtime downloaders use `megcfbt.tls.open_url`. Each HTTPS request gets a
verified client context; urllib still handles headers, proxies and redirects.
No global SSL state is changed, and a failed handshake is never retried with
different trust roots.

1. Validate explicitly present `SSL_CERT_FILE` and `SSL_CERT_DIR`. Empty values,
   unreadable/invalid PEM CA files and directories without readable hashed CA
   material fail with a local configuration error. A directory must use OpenSSL
   `hash.N` certificate filenames; run `openssl rehash` after managing its roots.
   Linux colon-separated directory lists are supported and each directory must
   contain readable hashed CA material. Explicit settings retain standard
   OpenSSL behavior for the other, unset default location. No extra OS locations
   or Mozilla roots are added when an override is present.
2. Keep usable OpenSSL default trust, including lazily loaded hashed directories.
3. If defaults have no usable roots, try OS-managed bundles at `/etc/ssl/cert.pem`,
   `/etc/ssl/certs/ca-certificates.crt`, `/etc/pki/tls/certs/ca-bundle.crt`,
   `/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem`, `/etc/ssl/ca-bundle.pem`,
   then hashed `/etc/ssl/certs` and `/etc/pki/tls/certs` directories.
4. If system material is unavailable, load certifi's maintained Mozilla bundle.
   Missing or corrupt packaged bundle data is an error. Keep this dependency
   updated when rebuilding the application.

This ordering preserves enterprise roots installed in system trust. For a
managed proxy or private CA, ask the administrator to install the correct CA
into system trust or provide a valid explicit configuration. Do not disable
certificate or hostname validation. Windows runtime requests continue to use
urllib's normal Python/Windows trust behavior.

## Reproduce diagnostics

Run from the source checkout, or substitute the shipped executable for Python:

```sh
python -m megcfbt.tls_diagnostics
python -m megcfbt.tls_diagnostics --smoke
"/path/to/Multi-Engine Game Conversion Framework by tovakai" --tls-diagnostics
"/path/to/Multi-Engine Game Conversion Framework by tovakai" --tls-diagnostics --smoke
```

The default command is offline and does not initialize GUI widgets. Compare its
Python/OpenSSL versions, frozen state, compiled/resolved paths, readability,
selected trust source and root count between system and frozen execution.
The optional smoke uses the exact NW.js checksum downloader and existing custom
User-Agent against `https://dl.nwjs.io/v0.117.0/SHASUMS256.txt`; success reports
HTTP 200 and the matching ARM64 archive checksum. It never downloads the archive.
A nonzero exit means configuration or smoke failure. Reports contain only CA
configuration, override presence and constrained error details; they do not dump
environment variables, proxy addresses, credentials, certificate contents or raw
tracebacks. Review local paths before attaching a report to a public issue.

CI can run the same frozen smoke on both native Linux runners via the workflow's
`tls_network_smoke` dispatch input or the explicit PR label `tls-network-smoke`.
Neither opt-in downloads the full runtime archive.

## Distinguish failures

| Message | Meaning / next action |
| --- | --- |
| TLS certificate validation / server identity | Check system roots, managed proxy CA and explicit CA settings. |
| Invalid SSL_CERT_FILE / SSL_CERT_DIR | Repair the explicit local setting; it is never ignored. |
| HTTP 403 / 404 / 5xx | Server rejected an HTTP request after TLS; check URL/version, CDN policy or retry a server outage. |
| DNS name resolution / could not reach host | Check connectivity, DNS and proxy configuration. |
| Network timeout / interrupted transfer | Retry after restoring connectivity; partial NW.js archives are discarded. |
| No official checksum entry | The official verification metadata does not identify the selected archive. |
| SHA256 mismatch | Archive integrity failed; the runtime is refused. |
| Incomplete archive / wrong architecture | Runtime validation failed; the runtime is refused. |

NW.js uses official sources and unchanged headers/timeouts. Downloads remain
temporary until checksum, safe extraction, expected directory, AArch64 executable
and required resource validation succeed. A valid cache avoids all network and
CA resolution. An invalid cache remains until replacement is ready; failed
replacement restores it. User-provided runtime overrides remain offline and
undergo the existing architecture checks.

## Conversion ordering and follow-up

The GUI Convert action calls `megcfbt.router.build_source`: prepare/extract input,
authoritative multi-engine detection, route to the builder, select runtime or
override, cache validation, official checksum retrieval, archive download/full
SHA256, safe extraction/architecture/resource checks, staged package construction,
transactional output install, Frame metadata/artwork and optional output ZIP.
The RPGM CLI reaches `rpgmframe.builder.build_game` directly with the same runtime
manager. Runtime provisioning already precedes package copying and output install.
An earlier network failure therefore leaves source and existing output intact.

ZIP preparation currently precedes routing and detection, including GUI inspection.
Bounded metadata reads from the central directory are feasible for ordinary
MV/MZ layouts, but the authoritative detector also handles wrapper chains,
`package.nw`, ambiguous exports and other engine precedence. A separate sparse
ZIP detector could change routing accuracy. This patch leaves detection intact.
A follow-up should share the detector's evidence model, bound metadata reads,
retain extraction for deep/ambiguous layouts, and reuse the selected runtime
across inspection/conversion. Do not predownload runtimes for unidentified engines.

## Downloader inventory

The shared resolver covers NW.js, official Godot metadata/checksums/archives,
downloadable custom Godot/GodotSteam bundles, mkxp, Ren'Py metadata/SDKs and
legacy-profile downloads, and shared native/Mono bundles (GameMaker, LÖVE, AGS,
EasyRPG and Mono use the latter). Each keeps its existing artifact validation,
cache and extraction logic.

Artwork/SteamGridDB requests also use urllib defaults but are optional media
requests, outside this runtime correction. Standalone STS2 runtime-fetch and
remote-worker scripts have independent execution environments and retain their
own urllib calls. Local Steam debug HTTP calls use loopback and are unrelated.
External build tools have their own network/trust configuration. No claim is made
that every HTTPS mechanism in the repository uses the new resolver.
