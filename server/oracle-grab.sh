#!/usr/bin/env bash
# Keeps asking Oracle for the free ARM server (1 OCPU / 6 GB, Ubuntu 24.04) until it gets one.
# Run every 5 minutes by launchd (installed by oracle-grab-setup.sh). Uses .oci/config (git-ignored).
# When the server exists it saves the IP to .oci/server-ip.txt, shows a notification and switches itself off.
set -uo pipefail
cd "$(dirname "$0")/.."
export OCI_CLI_CONFIG_FILE="$PWD/.oci/config" OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
PLIST="$HOME/Library/LaunchAgents/com.olly.oracle-grab.plist"
IPFILE=.oci/server-ip.txt
NAME=shorts-server
log() { echo "$(date '+%F %T') $*"; }
finish() {
  echo "$1" > "$IPFILE"
  log "SERVER READY: $1"
  osascript -e "display notification \"IP $1 - tell Claude\" with title \"Oracle server is ready\"" 2>/dev/null
  launchctl unload "$PLIST" 2>/dev/null; exit 0
}
[ -s "$IPFILE" ] && { launchctl unload "$PLIST" 2>/dev/null; exit 0; }

T=$(sed -n 's/^tenancy=//p' .oci/config)
oq() { oci "$@" --raw-output 2>/dev/null; }

# already made (e.g. by an earlier run)?
ID=$(oq compute instance list --compartment-id "$T" --display-name "$NAME" \
      --query "data[?\"lifecycle-state\"=='RUNNING' || \"lifecycle-state\"=='PROVISIONING' || \"lifecycle-state\"=='STARTING'].id | [0]")
if [ -n "$ID" ] && [ "$ID" != "null" ]; then
  IP=$(oq compute instance list-vnics --instance-id "$ID" --query 'data[0]."public-ip"')
  [ -n "$IP" ] && [ "$IP" != "null" ] && finish "$IP"
  log "instance exists, waiting for its IP"; exit 0
fi

# network (made once): VCN + internet gateway + route + public subnet
V=$(oq network vcn list --compartment-id "$T" --display-name shorts-vcn --query 'data[0].id')
if [ -z "$V" ] || [ "$V" = "null" ]; then
  V=$(oq network vcn create --compartment-id "$T" --cidr-blocks '["10.0.0.0/16"]' --display-name shorts-vcn \
        --dns-label shortsvcn --wait-for-state AVAILABLE --query 'data.id') || { log "VCN create failed"; exit 1; }
  log "made VCN"
fi
IGW=$(oq network internet-gateway list --compartment-id "$T" --vcn-id "$V" --query 'data[0].id')
if [ -z "$IGW" ] || [ "$IGW" = "null" ]; then
  IGW=$(oq network internet-gateway create --compartment-id "$T" --vcn-id "$V" --is-enabled true \
          --display-name shorts-igw --wait-for-state AVAILABLE --query 'data.id')
  RT=$(oq network vcn get --vcn-id "$V" --query 'data."default-route-table-id"')
  oci network route-table update --rt-id "$RT" --force \
    --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null 2>&1
  log "made internet gateway + route"
fi
SUB=$(oq network subnet list --compartment-id "$T" --vcn-id "$V" --query 'data[0].id')
if [ -z "$SUB" ] || [ "$SUB" = "null" ]; then
  SUB=$(oq network subnet create --compartment-id "$T" --vcn-id "$V" --cidr-block 10.0.0.0/24 \
          --display-name shorts-subnet --dns-label shorts --wait-for-state AVAILABLE --query 'data.id')
  log "made subnet"
fi

IMG=$(oq compute image list --compartment-id "$T" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
        --shape VM.Standard.A1.Flex --sort-by TIMECREATED --sort-order DESC --query 'data[0].id')
[ -n "$IMG" ] && [ "$IMG" != "null" ] || { log "no Ubuntu image found"; exit 1; }

for AD in $(oq iam availability-domain list --compartment-id "$T" --query 'data[].name' | tr -d '[]",'); do
  out=$(oci compute instance launch --compartment-id "$T" --availability-domain "$AD" \
          --shape VM.Standard.A1.Flex --shape-config '{"ocpus":1,"memoryInGBs":6}' \
          --image-id "$IMG" --subnet-id "$SUB" --assign-public-ip true --display-name "$NAME" \
          --ssh-authorized-keys-file shorts-server.key.pub \
          --wait-for-state RUNNING --max-wait-seconds 900 --query 'data.id' --raw-output 2>&1)
  if [[ "$out" == ocid1.instance* ]]; then
    IP=$(oq compute instance list-vnics --instance-id "$out" --query 'data[0]."public-ip"')
    finish "$IP"
  fi
  log "$AD: $(echo "$out" | grep -o '"message": "[^"]*"' | head -1 || echo "$out" | tail -1)"
done
exit 0
