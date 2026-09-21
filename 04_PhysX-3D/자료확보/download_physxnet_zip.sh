#!/usr/bin/env bash
set -u

ROOT=/home/minsujo/Desktop/SH/PHYSx
DEST="$ROOT/data/physxnet-download"
LOGROOT="$ROOT/logs/physxnet-download-20260921"
URL='https://huggingface.co/datasets/Caoza/PhysX-3D/resolve/ca1f6d3f5cfb5c39dc183251a3a2999dcb42e093/PhysXNet.zip?download=true'
EXPECTED_BYTES=16306354206
EXPECTED_SHA256=a4970a3936e8a1fc823d17b64d23b167d73997a13686011bc46f7b98774a7e75

umask 077
mkdir -p "$DEST" "$LOGROOT"
RUN="$LOGROOT/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir "$RUN"
exec > >(tee -a "$RUN/stdout.log") 2> >(tee -a "$RUN/stderr.log" >&2)

printf '%s\n' "download_run=$RUN" "started_at=$(date -Is)" "url=$URL" \
  "expected_bytes=$EXPECTED_BYTES" "expected_sha256=$EXPECTED_SHA256"
printf '%s\n' "download_path=$DEST/PhysXNet.zip" "partial_path=$DEST/PhysXNet.zip.part"

available=$(df --output=avail -B1 "$ROOT" | tail -n 1 | tr -d '[:space:]')
if [ "${available:-0}" -lt "$EXPECTED_BYTES" ]; then
  printf '%s\n' "ERROR: insufficient free space: ${available:-unknown} bytes" >&2
  exit 2
fi

if [ -e "$DEST/PhysXNet.zip" ]; then
  actual_bytes=$(stat -c '%s' "$DEST/PhysXNet.zip")
  actual_sha=$(sha256sum "$DEST/PhysXNet.zip" | awk '{print $1}')
  if [ "$actual_bytes" = "$EXPECTED_BYTES" ] && [ "$actual_sha" = "$EXPECTED_SHA256" ]; then
    printf '%s\n' "status=already_verified" "bytes=$actual_bytes" "local_sha256=$actual_sha" "ended_at=$(date -Is)"
    exit 0
  fi
  printf '%s\n' "ERROR: existing final file does not match official metadata; preserving it and stopping" >&2
  printf '%s\n' "existing_bytes=$actual_bytes" "existing_local_sha256=$actual_sha" >&2
  exit 3
fi

curl --fail --location --retry 5 --retry-all-errors --connect-timeout 30 \
  --continue-at - --output "$DEST/PhysXNet.zip.part" "$URL"

actual_bytes=$(stat -c '%s' "$DEST/PhysXNet.zip.part")
actual_sha=$(sha256sum "$DEST/PhysXNet.zip.part" | awk '{print $1}')
printf '%s\n' "partial_bytes=$actual_bytes" "partial_local_sha256=$actual_sha"
if [ "$actual_bytes" != "$EXPECTED_BYTES" ] || [ "$actual_sha" != "$EXPECTED_SHA256" ]; then
  printf '%s\n' "ERROR: downloaded file failed official size/hash check; partial preserved" >&2
  exit 4
fi
mv --no-clobber "$DEST/PhysXNet.zip.part" "$DEST/PhysXNet.zip"
printf '%s\n' "status=verified" "bytes=$actual_bytes" "local_sha256=$actual_sha" "ended_at=$(date -Is)"
