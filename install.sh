#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
if [[ ${1:-} == --help ]]; then
    cat <<'HELP'
Usage: sudo ./install.sh [--prepare-image|--update]
Interactive installation on Raspberry Pi OS Lite arm64 (Bookworm/Trixie).
--update keeps existing config/network/SSH and configures only the new web UI.
--prepare-image installs packages and files without secrets or service activation.
Requires existing Internet access; use Pi Imager for first network/user/SSH setup.
HELP
    exit 0
fi
mode=${1:-interactive}
[[ $# -le 1 && ( $mode == interactive || $mode == --prepare-image || $mode == --update ) ]] || { echo 'Unknown option. See --help.' >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo 'Run with sudo on the target Pi.' >&2; exit 1; }
[[ -f /etc/rpi-issue ]] || { echo 'Raspberry Pi OS is required.' >&2; exit 1; }
[[ $(dpkg --print-architecture) == arm64 ]] || { echo '64-bit Raspberry Pi OS (arm64) required.' >&2; exit 1; }
# shellcheck disable=SC1091
source /etc/os-release
[[ ${VERSION_CODENAME:-} == bookworm || ${VERSION_CODENAME:-} == trixie ]] || { echo 'Only Bookworm/Trixie supported.' >&2; exit 1; }
if [[ $mode != --prepare-image ]]; then
    [[ -t 0 ]] || { echo 'Interactive terminal required; do not pipe curl into sudo bash.' >&2; exit 1; }
    [[ -e /proc/device-tree/model ]] || { echo 'Cannot identify target Raspberry Pi.' >&2; exit 1; }
    model=$(tr -d '\0' </proc/device-tree/model)
    [[ $model == *'Raspberry Pi 3 Model B Plus'* || $model == *'Raspberry Pi 4 Model B'* ]] || { echo 'Target must be a Pi 3B+ or Pi 4B.' >&2; exit 1; }
fi
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
trap 'printf "Installation failed at line %s. Existing configuration and documents are retained; see README.\n" "$LINENO" >&2' ERR
apt-get update
apt-get install -y --no-install-recommends sane-utils libsane1 python3 python3-pil python3-img2pdf python3-sane python3-flask python3-waitress curl ca-certificates \
    usbutils network-manager openssh-server avahi-daemon raspi-config
if ! getent group ix500 >/dev/null; then groupadd --system ix500; fi
if ! id ix500 >/dev/null 2>&1; then useradd --system --gid ix500 --home-dir /var/lib/ix500-paperless --no-create-home --shell /usr/sbin/nologin ix500; fi
[[ $(getent passwd ix500 | cut -d: -f7) == /usr/sbin/nologin ]] || { echo 'Existing ix500 account is not a dedicated system account.' >&2; exit 1; }
install -d -o ix500 -g ix500 -m 0700 /var/lib/ix500-paperless
if [[ $mode != --prepare-image ]]; then
    if [[ $mode == --update && ! -f /etc/ix500-paperless/config.json ]]; then
        echo 'No existing appliance configuration. Use install.sh instead.' >&2
        exit 1
    fi
    python3 "$project_dir/src/maintenance.py"
fi
install -d -m 0755 /opt/ix500-paperless
install -m 0644 "$project_dir"/src/*.py /opt/ix500-paperless/
install -d -m 0755 /opt/ix500-paperless/templates /opt/ix500-paperless/static
install -m 0644 "$project_dir"/src/templates/* /opt/ix500-paperless/templates/
install -m 0644 "$project_dir"/src/static/* /opt/ix500-paperless/static/
install -m 0755 "$project_dir/uninstall.sh" /opt/ix500-paperless/uninstall.sh
install -d -o root -g ix500 -m 0750 /etc/ix500-paperless
install -d -o ix500 -g ix500 -m 0700 /var/lib/ix500-paperless
install -m 0644 "$project_dir"/systemd/* /etc/systemd/system/
install -m 0644 "$project_dir/udev/99-ix500-paperless.rules" /etc/udev/rules.d/
# Enable only fujitsu in a separate drop-in; leave system SANE configuration intact.
install -d -m 0755 /etc/sane.d/dll.d
printf 'fujitsu\n' >/etc/sane.d/dll.d/ix500-paperless
chmod 0644 /etc/sane.d/dll.d/ix500-paperless
if [[ $mode == --prepare-image ]]; then
    echo 'Image files prepared. At first boot configure with:'
    echo 'sudo python3 /opt/ix500-paperless/setup_wizard.py'
    exit 0
fi
systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --attr-match=idVendor=04c5 --attr-match=idProduct=132b
udevadm settle
systemctl enable --now avahi-daemon
if [[ $mode != --update ]]; then
    python3 /opt/ix500-paperless/setup_wizard.py
fi
if ! python3 /opt/ix500-paperless/setup_web.py; then
    systemctl enable --now ix500-scan.service ix500-upload.timer
    echo 'Web setup did not finish. Scanner/upload restarted. Run setup_web.py again to finish.' >&2
    exit 1
fi
systemctl enable --now ix500-scan.service ix500-upload.timer ix500-web.service
