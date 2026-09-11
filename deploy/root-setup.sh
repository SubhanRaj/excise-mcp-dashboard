#!/usr/bin/env bash
# One-time root setup to bring excise-mcp-dashboard up on Apache port 8084,
# matching the sibling apps. Idempotent -- safe to re-run.
#
#   sudo bash deploy/root-setup.sh
#
# Everything else (tunnel, DNS, systemd --user unit, .env) is already done.

set -euo pipefail

APP=/home/subhan/Sites/excise-mcp-dashboard
PORT=8084
VHOST=/etc/apache2/sites-available/excise-mcp-dashboard.conf
PORTS=/etc/apache2/ports.conf
OVERRIDE=/etc/systemd/system/apache2.service.d/override.conf

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

echo "1/5  vhost -> $VHOST"
install -m 0644 "$APP/deploy/apache-vhost.conf" "$VHOST"

echo "2/5  Listen 127.0.0.1:$PORT in $PORTS"
if ! grep -qE "^\s*Listen\s+127\.0\.0\.1:$PORT(\s|\$)" "$PORTS"; then
  printf 'Listen 127.0.0.1:%s\n' "$PORT" >> "$PORTS"
  echo "     added"
else
  echo "     already present"
fi

echo "3/5  ReadWritePaths in $OVERRIDE"
NEW_PATHS="$APP/web/storage $APP/web/bootstrap/cache $APP/web/storage/app/kb-uploads"
if grep -q "$APP/web/storage " "$OVERRIDE" || grep -q "$APP/web/storage\$" "$OVERRIDE"; then
  echo "     already present"
else
  cp -a "$OVERRIDE" "$OVERRIDE.bak.$(date +%Y%m%d%H%M%S)"
  # Append the app's paths to the end of the existing ReadWritePaths= line, in place.
  sed -i "s#^\(ReadWritePaths=.*\)#\1 $NEW_PATHS#" "$OVERRIDE"
  echo "     appended (backup written alongside)"
fi

echo "4/5  a2ensite + configtest"
a2ensite excise-mcp-dashboard >/dev/null
apachectl configtest

echo "5/5  reload + restart"
systemctl daemon-reload
systemctl restart apache2

echo
echo "Local check:"
curl -sS -o /dev/null -w "  http://127.0.0.1:$PORT/health -> %{http_code}\n" "http://127.0.0.1:$PORT/health" || true
echo "Public check (through the tunnel):"
curl -sS -o /dev/null -w "  https://visualizer.exciseup.in/health -> %{http_code}\n" --max-time 20 https://visualizer.exciseup.in/health || true
echo
echo "Both should be 200. / and /login stay unbuilt until Milestone 5."
