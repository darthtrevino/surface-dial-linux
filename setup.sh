#!/usr/bin/env bash
set -euo pipefail

project_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
user_bin_directory="${HOME}/.local/bin"
user_systemd_directory="${HOME}/.config/systemd/user"
udev_rule="/etc/udev/rules.d/70-surface-dial.rules"

usage() {
  cat <<'EOF'
Usage: ./setup.sh [install|uninstall]

Install or remove the Surface Dial volume controller for the current user.
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null; then
    printf 'Required command not found: %s\n' "$1" >&2
    exit 1
  fi
}

install_controller() {
  if ((EUID == 0)); then
    printf 'Run this script as your desktop user, not with sudo.\n' >&2
    exit 1
  fi

  require_command python3
  require_command wpctl
  require_command systemctl
  require_command udevadm
  require_command sudo

  install -Dm755 \
    "${project_directory}/src/surface_dial.py" \
    "${user_bin_directory}/surface-dial"
  install -Dm644 \
    "${project_directory}/systemd/surface-dial.service" \
    "${user_systemd_directory}/surface-dial.service"
  sudo install -Dm644 \
    "${project_directory}/udev/70-surface-dial.rules" \
    "${udev_rule}"

  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=input --action=change

  systemctl --user daemon-reload
  systemctl --user enable --now surface-dial.service

  cat <<'EOF'
Surface Dial support installed.

If the service reports a permission error, disconnect and reconnect the Dial.
View service logs with:
  journalctl --user -u surface-dial.service -f
EOF
}

uninstall_controller() {
  if ((EUID == 0)); then
    printf 'Run this script as your desktop user, not with sudo.\n' >&2
    exit 1
  fi

  require_command systemctl
  require_command udevadm
  require_command sudo

  systemctl --user disable --now surface-dial.service 2>/dev/null || true
  rm -f \
    "${user_systemd_directory}/surface-dial.service" \
    "${user_bin_directory}/surface-dial"
  sudo rm -f "${udev_rule}"

  sudo udevadm control --reload-rules
  systemctl --user daemon-reload
  systemctl --user reset-failed

  printf 'Surface Dial support removed.\n'
}

case "${1:-install}" in
  install)
    install_controller
    ;;
  uninstall)
    uninstall_controller
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
