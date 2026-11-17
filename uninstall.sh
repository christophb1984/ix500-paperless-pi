#!/usr/bin/env bash
set -Eeuo pipefail
if [[ ${1:-} == --help ]]; then
    echo 'Usage: sudo ./uninstall.sh'
    echo 'Removes appliance code, units and USB/SANE rules. Retains all secrets, jobs, user and network/SSH settings.'
    exit 0
fi
[[ $# -eq 0 ]] || { echo 'Unknown option.' >&2; exit 2; }
[[ $EUID -eq 0 && -d /run/systemd/system ]] || { echo 'Run with sudo on the target Pi.' >&2; exit 1; }
systemctl disable --now ix500-upload.timer ix500-scan.service ix500-web.service 2>/dev/null || true
systemctl stop ix500-upload.service 2>/dev/null || true
rm -f /etc/systemd/system/ix500-scan.service /etc/systemd/system/ix500-upload.service /etc/systemd/system/ix500-upload.timer /etc/systemd/system/ix500-web.service
rm -f /etc/udev/rules.d/99-ix500-paperless.rules /etc/sane.d/dll.d/ix500-paperless
rm -f /opt/ix500-paperless/appliance.py /opt/ix500-paperless/setup_wizard.py /opt/ix500-paperless/uninstall.sh
rm -f /opt/ix500-paperless/control.py /opt/ix500-paperless/sane_options.py /opt/ix500-paperless/webapp.py /opt/ix500-paperless/setup_web.py /opt/ix500-paperless/maintenance.py
rm -f /opt/ix500-paperless/templates/index.html /opt/ix500-paperless/static/app.js /opt/ix500-paperless/static/style.css
rmdir /opt/ix500-paperless/templates /opt/ix500-paperless/static 2>/dev/null || true
rm -rf /opt/ix500-paperless/__pycache__
rmdir /opt/ix500-paperless 2>/dev/null || true
systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --attr-match=idVendor=04c5 --attr-match=idProduct=132b
printf '%s\n' 'Appliance removed. Retained: /etc/ix500-paperless, /var/lib/ix500-paperless, ix500 system account, packages, admin user, SSH and network settings.'
printf '%s\n' 'Review README before manually removing retained data or credentials.'
