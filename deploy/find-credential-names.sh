#!/bin/bash
# Find where a credential is configured on the VPS, without ever printing a secret.
#   bash deploy/find-credential-names.sh bonanz
# Prints: files whose name matches; and, inside config files, only the matching variable or
# key names with set/empty. Values and whole lines are never printed.
set -u
PAT="${1:?pattern}"
ROOTS="/var/www /etc /root /opt /srv /home /usr/local/etc"

echo "-- files named like '$PAT'"
timeout 60 find $ROOTS -xdev \( -path '*/node_modules' -o -path '*/.venv' -o -path '*/site-packages' -o -path '*/.git' \) -prune \
  -o -iname "*$PAT*" -print 2>/dev/null | head -50

echo "-- names containing '$PAT' inside config files"
timeout 120 find $ROOTS -xdev \( -path '*/node_modules' -o -path '*/.venv' -o -path '*/site-packages' -o -path '*/.git' \
  -o -path '/var/www/*/assets' -o -path '/var/www/*/digital*' \) -prune -o -type f -size -1024k \
  \( -name '.env*' -o -name '*.env' -o -name '*.conf' -o -name '*.ini' -o -name '*.json' -o -name '*.service' \
     -o -name '*.yaml' -o -name '*.yml' -o -name '*.toml' -o -name '*.cfg' -o -name 'environment' \) -print 2>/dev/null |
while IFS= read -r f; do
  grep -Iqi -- "$PAT" "$f" 2>/dev/null || continue
  # NAME=value or "name": value; print the name and whether a value follows, nothing else
  awk -v pat="$PAT" -v file="$f" '
    BEGIN { IGNORECASE = 1 }
    {
      line = $0
      if (match(line, /^[ \t]*(export[ \t]+)?[A-Za-z_][A-Za-z0-9_.]*[ \t]*=/)) {
        name = substr(line, RSTART, RLENGTH - 1); sub(/^[ \t]*(export[ \t]+)?/, "", name); sub(/[ \t]+$/, "", name)
        val = substr(line, RSTART + RLENGTH); gsub(/^[ \t"'\'']+|[ \t"'\'']+$/, "", val)
        if (tolower(name) ~ tolower(pat)) printf "%s: %s = %s\n", file, name, (val == "" ? "empty" : "set")
      } else if (match(line, /"[^"]*"[ \t]*:/)) {
        name = substr(line, RSTART + 1); sub(/"[ \t]*:.*/, "", name)
        if (tolower(name) ~ tolower(pat)) printf "%s: key \"%s\"\n", file, name
      } else if (tolower(line) ~ tolower(pat)) {
        printf "%s: line %d mentions it (not shown)\n", file, NR
      }
    }' "$f" 2>/dev/null | head -20
done
echo "-- done"
