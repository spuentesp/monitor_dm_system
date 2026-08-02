#!/usr/bin/env bash
# Open TCP 3000 and 8000 in firewalld's active zone so a phone/laptop on the
# same LAN can reach the dev stack. The runtime rules are then promoted to
# permanent so they survive a reboot.
#
# Run: sudo bash scripts/open-lan-ports.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This script needs root. Re-run with: sudo bash $0" >&2
    exit 1
fi

ZONE=$(firewall-cmd --get-default-zone)
echo "→ firewalld default zone: ${ZONE}"

echo "→ Opening TCP 3000 and 8000 in zone '${ZONE}'"
firewall-cmd --zone="${ZONE}" --add-port=3000/tcp
firewall-cmd --zone="${ZONE}" --add-port=8000/tcp

echo "→ Promoting runtime rules to permanent"
firewall-cmd --runtime-to-permanent

echo
echo "✓ Open ports in zone '${ZONE}':"
firewall-cmd --zone="${ZONE}" --list-ports
