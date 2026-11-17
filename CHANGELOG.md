# Changelog

## 0.2.5 — first public repository version

- Serialize update shutdown with the hardware/browser scan-start barrier; refuse updates while a scan runs or waits.
- Create runtime lock files as the service user and refuse unsafe legacy upgrades instead of terminating active paper feed.
- Reject malformed CSRF headers and invalid profile identifiers as client errors.
- Report validated device-option failures with the affected setting, without forwarding unstructured native debug output.
- Add security/contribution documentation, sanitized setup examples and a pinned, read-only CI checkout.

## 0.2.4

- Read native SANE option values by index. Hardware sensors named `scan` no longer collide with Python method names and break JSON serialization.

## 0.2.3

- Use the actually accepted paper dimensions for the scan area after backend rounding.

## 0.2.2

- Allow native fixed-point millimetre quantization while preserving geometry bounds and other option checks.

## 0.2.1

- Add explicit Automatic mode: duplex capture followed by configurable blank-page filtering, with full original preservation when pages are removed.

## 0.2.0

- Add authenticated LAN web UI, browser scan start, persistent profiles, simplex capture and dynamic native options.

## 0.1.x

- Initial interactive installer, USB/SANE button workflow, PDF pipeline and durable Paperless-ngx queue.
