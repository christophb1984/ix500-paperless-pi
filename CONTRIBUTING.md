# Contributing

Small, reproducible fixes and hardware compatibility reports are welcome.

1. Describe the problem and expected result before proposing a broad change.
2. Reproduce bugs with a failing behavioral test, implement the smallest fix, and run the full test suite from the README.
3. Keep dependencies in the Raspberry Pi OS/Debian package ecosystem. Do not add a desktop requirement or another process competing for USB.
4. Preserve existing documents, credentials and queue state. Unknown scan outcomes must not become silent success or an unconditional POST retry.
5. Include only synthetic documents and deliberately fake test credentials. See SECURITY.md before sharing diagnostics.

Hardware reports should include Pi model, OS/SANE/Paperless versions, scan profile, tested page count and observed result. Redact device serials, account names and network details. There is no requirement to share real documents.

The optional browser test is `tests/browser_smoke.py` and requires Playwright/Chromium in an isolated development environment. The default suite uses fake scanner boundaries and needs no physical scanner. Native option descriptors, quantization and method-name collisions deserve regression coverage when changed.

Contributions are provided under the repository's MIT license. No contributor license agreement is required.
