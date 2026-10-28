#!/usr/bin/env bash
# Open HTTP and HTTPS in the host firewall (blueprint §13.13 step 3).
# Oracle's Ubuntu images ship iptables rules that only allow SSH; the VCN security list
# must ALSO allow TCP 80 and 443 (done in the OCI console). Idempotent.
set -euo pipefail

for port in 80 443; do
  if ! sudo iptables -C INPUT -m state --state NEW -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
    echo "opened tcp/$port"
  fi
done
# HTTP/3 (optional)
if ! sudo iptables -C INPUT -m state --state NEW -p udp --dport 443 -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 6 -m state --state NEW -p udp --dport 443 -j ACCEPT
fi
sudo netfilter-persistent save
