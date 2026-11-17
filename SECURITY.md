# Security model

This is a single-operator appliance for a **trusted LAN**. Do not forward its HTTP port to the Internet. Use a VPN or an appropriately configured HTTPS reverse proxy for remote access. HTTP exposes passwords and documents to network observers; an application password does not provide encryption.

## Existing protections

- Separate web password, PBKDF2-SHA256 hash, random session key, twelve-hour signed session cookie, HttpOnly/SameSite-Strict, CSRF and Origin checks.
- Login attempts limited per client IP. The in-memory counter resets on service restart; this is not Internet-facing abuse protection.
- Browser receives public scan profiles and status, never the Paperless token. JSON inputs are validated; native options are checked against actual device descriptors before scanning. No shell command endpoint.
- Runtime services use the unprivileged `ix500` account with systemd restrictions. The web/upload services have no USB access. Only the scanner service opens the device.
- Token-bearing configuration is `root:ix500` 0640; runtime job directories are 0700. Credentials are passed to curl through stdin, not process arguments. TLS verification remains enabled; redirects are not followed.
- PDFs are made durable before queue publication. Ambiguous uploads and partial scans are retained for review. No automatic deletion of imported documents.
- Upgrades hold the same start barrier used by the hardware/browser worker while checking idle state and stopping services.

## Trust boundaries and limitations

Root and the `ix500` service account can read appliance credentials and documents. The web, scanner and upload processes share that account; they are not isolated from each other after a full service-account compromise. Give the scanner a dedicated Paperless identity with the required document/task permissions, rather than an unnecessary administrator identity.

The system is not a multi-user document service. It does not expose document downloads, provide per-user authorization, replace a firewall, encrypt the SD card, guarantee exactly-once delivery, or protect against a malicious administrator. Automatic blank detection is a heuristic: preserve and inspect originals, especially for faint print or signatures. Keep OS packages updated and monitor free space.

Concurrent manual administrator scans/commands during an upgrade are unsupported. Upgrades from very old versions without the shared control channel require a deliberate manual service stop while idle.

## Reporting a security problem

Use GitHub's **Report a vulnerability** / private reporting feature if it is enabled for this repository. If unavailable, open a minimal issue requesting a private contact route **without exploit details or sensitive material**. No private email address is published here.

Never attach tokens, passwords, private SSH keys, live configuration, network profiles, SD-card images, or personal scanned documents to public issues. Provide a redacted minimal reproduction and relevant version information. If a token or document was accidentally published, revoke the token or remove access as appropriate; deleting it from the latest commit does not remove Git history.

## Supported version

The latest published early release is maintained on a best-effort basis. No security SLA is provided. Test upgrades and keep paper/original backups until processing has been confirmed.
