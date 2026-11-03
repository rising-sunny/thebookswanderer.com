#!/bin/bash
# One-time, read-only: print the installed MCP bridge and the Search Console report code so they
# can be extended in the repository without overwriting newer code. Long key-like literals and
# e-mail addresses are masked; credential files are never read. Changes nothing.
scrub() { sed -E 's/([A-Za-z0-9_+\/=-]{32,})/<redacted>/g; s/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/<email>/g'; }
for f in /opt/tbw-mcp/tbw_mcp.py /opt/tbw-seo-agent/report.py /etc/systemd/system/tbw-seo-agent.service; do
  echo "######## $f ($(wc -l < "$f" 2>/dev/null) lines)"
  scrub < "$f" 2>/dev/null
done
echo "######## /opt/tbw-mcp and /opt/tbw-seo-agent files"
ls -la /opt/tbw-mcp /opt/tbw-seo-agent 2>/dev/null | grep -v '^total'
/opt/tbw-seo-agent/.venv/bin/pip list 2>/dev/null | grep -Ei 'google|requests|httpx'
echo "######## end"
