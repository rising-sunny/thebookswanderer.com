"""deploy/nginx-security-hardening.sh against a throwaway tree shaped like Ubuntu's:
sites-enabled/<site> is a SYMLINK to sites-available/<site>. nginx itself is replaced by a stub."""
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "nginx-security-hardening.sh"
SITE = '''server {
    server_name localhost;
    location / { return 200; }
    location ~* \\.(css|js)$ {
        add_header Cache-Control "public" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    }
    listen 8083;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
'''


class HardeningScriptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for d in ("sites-available", "sites-enabled", "snippets", "conf.d", "backup"):
            (self.root / d).mkdir()
        self.real = self.root / "sites-available" / "shop"
        self.real.write_text(SITE)
        self.link = self.root / "sites-enabled" / "shop"
        self.link.symlink_to(self.real)                      # absolute symlink, as on Ubuntu

    def run_script(self, *args, nginx_test_passes=True):
        stub = self.root / "nginx-test.sh"
        stub.write_text("#!/bin/bash\n" + ("exit 0\n" if nginx_test_passes else
                        f'n=$(cat "{self.root}/n" 2>/dev/null || echo 0); echo $((n+1)) > "{self.root}/n"; [ "$n" -ge 1 ]\n'))
        stub.chmod(0o755)
        env = dict(os.environ, TBW_NGINX_SITE=str(self.link),
                   TBW_NGINX_HEADERS=str(self.root / "snippets" / "h.conf"),
                   TBW_NGINX_RATE=str(self.root / "conf.d" / "r.conf"),
                   TBW_NGINX_TEST=str(stub), TBW_NGINX_RELOAD="true",
                   TBW_NGINX_BACKUP_ROOT=str(self.root / "backup"))
        return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)

    def digest(self):
        return hashlib.sha256(self.real.read_bytes()).hexdigest()

    def test_failed_nginx_test_restores_the_real_file_byte_for_byte(self):
        before = self.digest()
        r = self.run_script("--apply", nginx_test_passes=False)   # first check fails, check after restore passes
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(self.digest(), before)                   # not truncated, not patched
        self.assertTrue(self.real.stat().st_size > 0)
        self.assertTrue(self.link.is_symlink())
        self.assertFalse((self.root / "snippets" / "h.conf").exists())
        self.assertFalse((self.root / "conf.d" / "r.conf").exists())
        self.assertIn("checksum verified", r.stderr)
        backup = next((self.root / "backup").glob("nginx-backup-*")) / "site.conf"
        self.assertFalse(backup.is_symlink())                     # a real copy, not a link
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), before)

    def test_apply_patches_through_the_symlink_and_keeps_it_a_symlink(self):
        r = self.run_script("--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.link.is_symlink())
        text = self.real.read_text()
        self.assertEqual(text.count("tbw-security-headers"), 0)   # include path is the stub's h.conf
        self.assertEqual(text.count("h.conf;"), 2)                # server level + the static location
        self.assertIn("limit_req_status 429;", text)
        self.assertEqual(self.run_script("--apply").returncode, 0)   # idempotent
        self.assertEqual(self.real.read_text().count("h.conf;"), 2)

    def test_dry_run_changes_nothing_and_an_empty_site_file_is_refused(self):
        before = self.digest()
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.digest(), before)
        self.real.write_text("")
        r = self.run_script("--apply")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty", r.stderr)


if __name__ == "__main__":
    unittest.main()
