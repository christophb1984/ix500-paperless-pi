# Verification scope

## Automated checks

The repository contains behavioral tests for scan/profile validation, native options and ranges, fixed-point geometry, the `scan` sensor/Python-method name collision, incomplete duplex stacks, simplex and automatic mode, PDF generation and retained originals.

Upload tests use actual curl against a local HTTP server to check multipart upload, authentication, task tracking, denied uploads, unreachable servers and ambiguous responses. A worker integration test uses the real daemon and native-query subprocess with a simulated scanner to check browser/button coordination and immutable profiles.

Web tests cover authentication, CSRF/Origin, malformed inputs, logout, attempt limits and credential-free state responses. Maintenance tests cover idle shutdown, the scan-start barrier, retained queued requests, and avoidance of root-created runtime locks.

Additional checks: Python compilation, JavaScript syntax, shell syntax, ShellCheck and an optional Chromium smoke test for desktop and mobile layouts. CI runs the Linux suite and systemd unit validation; inspect the repository Actions page for results for the specific commit being installed.

The first public version was prepared using Python 3.12 on macOS arm64 with isolated dependencies. A compatibility run also exercised img2pdf 0.4.4's API. This does not replace the actual Bookworm/Trixie package stack.

## Hardware evidence and limits

One deployment has confirmed the USB iX500, button workflow and Paperless upload. The web initialization bugs were diagnosed against real device output; the operator confirmed the subsequent correction. There is no complete compatibility matrix spanning both Pi models, both OS releases and all native device options.

The automated native backend is simulated. Exact descriptor availability, transport behavior, USB permissions, systemd isolation, image-build boot and physical paper/roller behavior still need the [hardware acceptance checks](ACCEPTANCE.md) on each target installation. Synthetic tests do not establish blank-filter accuracy for arbitrary real documents.

No real credentials, personal documents, runtime configuration or diagnostic conversation are included in the public repository.

## First public source check

The publication tree passed **61 tests**, Python/JavaScript/shell syntax checks and ShellCheck. The optional Chromium flow passed at desktop and phone sizes. A separate read-only review found the upgrade start/stop race; the guarded shutdown and its regression tests address it. File-hygiene checks found only the example JSON, no real credentials, user paths, private keys or personal documents. Actual GitHub Actions results are tied to the published commit and should be checked on the Actions page.
