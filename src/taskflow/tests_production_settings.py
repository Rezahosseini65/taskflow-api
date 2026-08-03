"""
Regression tests for the production settings module (audit finding C-3).

C-3 was that `taskflow.settings.production` was a three-line stub -- `DEBUG=False`
on top of base.py -- and could not actually boot. It inherited a committed
SECRET_KEY, an empty ALLOWED_HOSTS, sqlite, and (via base.py's MIDDLEWARE and the
unconditional imports in urls.py) hard references to debug_toolbar and
drf_spectacular, neither of which is installed outside development.

These tests boot the settings module in a subprocess rather than importing it
here. Django settings are process-global and read the environment at import time,
so reloading them in-process would leak state into the rest of the suite. A
subprocess is also the honest question: *would a deploy start?*
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

SRC_DIR = Path(settings.BASE_DIR)
REPO_ROOT = SRC_DIR.parent
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CI_CONFIG = REPO_ROOT / ".gitlab-ci.yml"

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


# A complete, valid production environment. These are throwaway values chosen to
# satisfy the settings module -- nothing here connects anywhere. The secret must
# clear Django's security.W009 heuristic (>= 50 chars, no 'django-insecure-'
# prefix) so that `check --deploy` assertions are not testing the placeholder.
PROD_ENV = {
    "DJANGO_SETTINGS_MODULE": "taskflow.settings.production",
    "DJANGO_SECRET_KEY": "test-only-placeholder-secret-key-0123456789abcdefghijklmnop",
    "DJANGO_ALLOWED_HOSTS": "example.com, api.example.com",
    "DATABASE_URL": "postgres://user:pass@localhost:5432/db",
    "DJANGO_CORS_ALLOWED_ORIGINS": "https://app.example.com",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.com",
}


def run_in_subprocess(code, env_overrides, clean=True):
    """Run `code` in a fresh interpreter with a controlled environment.

    `clean=True` starts from a minimal environment so that the developer's own
    exported variables -- and anything base.py's read_env() pulled in from a local
    .env -- cannot mask a missing setting. Returns (returncode, stdout, stderr).
    """
    if clean:
        env = {
            k: v
            for k, v in os.environ.items()
            if k in ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR")
        }
    else:
        env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # base.py reads src/taskflow/.env when present. On a developer machine that
    # file supplies DATABASE_URL, which would mask a missing-variable test and
    # make the "fails loudly" assertions pass for the wrong reason. Point the
    # settings at a path that does not exist so the environment is genuinely bare;
    # individual tests still override this if they want the real file.
    env["DJANGO_ENV_FILE"] = str(SRC_DIR / "taskflow" / ".env.does-not-exist")
    env.update(env_overrides)

    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(SRC_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


BOOT_AND_DUMP = """
import json
import django
django.setup()
from django.conf import settings as s

# Force the URLConf to import. Before C-3 this raised ImportError under
# production, because urls.py imported drf_spectacular and debug_toolbar
# unconditionally while both are installed only in development.
from django.urls import get_resolver
patterns = get_resolver().url_patterns

print("---JSON---")
print(json.dumps({
    "DEBUG": s.DEBUG,
    "ALLOWED_HOSTS": list(s.ALLOWED_HOSTS),
    "DB_ENGINE": s.DATABASES["default"]["ENGINE"],
    "SECRET_KEY": s.SECRET_KEY,
    "MIDDLEWARE": list(s.MIDDLEWARE),
    "INSTALLED_APPS": list(s.INSTALLED_APPS),
    "SESSION_COOKIE_SECURE": s.SESSION_COOKIE_SECURE,
    "CSRF_COOKIE_SECURE": s.CSRF_COOKIE_SECURE,
    "AUTH_COOKIE_SECURE": s.SIMPLE_JWT["AUTH_COOKIE_SECURE"],
    "SECURE_SSL_REDIRECT": s.SECURE_SSL_REDIRECT,
    "SECURE_HSTS_SECONDS": s.SECURE_HSTS_SECONDS,
    "SECURE_PROXY_SSL_HEADER": list(s.SECURE_PROXY_SSL_HEADER),
    "X_FRAME_OPTIONS": s.X_FRAME_OPTIONS,
    "SECURE_REFERRER_POLICY": s.SECURE_REFERRER_POLICY,
    "SECURE_CONTENT_TYPE_NOSNIFF": s.SECURE_CONTENT_TYPE_NOSNIFF,
    "CORS_ALLOWED_ORIGINS": list(getattr(s, "CORS_ALLOWED_ORIGINS", [])),
    "CORS_ALLOW_ALL_ORIGINS": getattr(s, "CORS_ALLOW_ALL_ORIGINS", False),
    "n_urlpatterns": len(patterns),
}))
"""


class ProductionSettingsBootTests(SimpleTestCase):
    """Production settings must import, and must be secure once they do."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        result = run_in_subprocess(BOOT_AND_DUMP, PROD_ENV)
        if result.returncode != 0:
            raise AssertionError(
                "production settings failed to boot (C-3):\n" + result.stderr
            )
        payload = result.stdout.split("---JSON---", 1)[1]
        cls.conf = json.loads(payload)

    def test_debug_is_off(self):
        self.assertFalse(self.conf["DEBUG"])

    def test_allowed_hosts_come_from_the_environment_and_are_stripped(self):
        # env.list splits on commas without stripping, so the second entry would
        # be " api.example.com" and could never match a real Host header.
        self.assertEqual(
            self.conf["ALLOWED_HOSTS"], ["example.com", "api.example.com"]
        )

    def test_secret_key_comes_from_the_environment(self):
        self.assertEqual(self.conf["SECRET_KEY"], PROD_ENV["DJANGO_SECRET_KEY"])
        self.assertNotIn(
            "django-insecure",
            self.conf["SECRET_KEY"],
            "production is using base.py's development fallback key",
        )

    def test_database_is_not_sqlite(self):
        self.assertEqual(
            self.conf["DB_ENGINE"], "django.db.backends.postgresql"
        )

    def test_debug_toolbar_is_absent(self):
        joined = " ".join(self.conf["MIDDLEWARE"] + self.conf["INSTALLED_APPS"])
        self.assertNotIn(
            "debug_toolbar",
            joined,
            "debug_toolbar reaches production; it was in base.py's MIDDLEWARE",
        )

    def test_urlconf_loads_without_development_only_packages(self):
        # setUpClass already imported the URLConf; a non-empty pattern list
        # confirms it resolved rather than silently producing nothing.
        self.assertGreater(self.conf["n_urlpatterns"], 0)

    def test_cookies_are_secure(self):
        self.assertTrue(self.conf["SESSION_COOKIE_SECURE"])
        self.assertTrue(self.conf["CSRF_COOKIE_SECURE"])
        self.assertTrue(
            self.conf["AUTH_COOKIE_SECURE"],
            "the JWT cookie is sent over plain HTTP; base.py leaves "
            "AUTH_COOKIE_SECURE False for local development and production "
            "must override it",
        )

    def test_https_is_enforced(self):
        self.assertTrue(self.conf["SECURE_SSL_REDIRECT"])
        self.assertGreater(self.conf["SECURE_HSTS_SECONDS"], 0)
        # nginx terminates TLS; without this Django sees proxied requests as
        # HTTP and SECURE_SSL_REDIRECT becomes a redirect loop.
        self.assertEqual(
            self.conf["SECURE_PROXY_SSL_HEADER"],
            ["HTTP_X_FORWARDED_PROTO", "https"],
        )

    def test_security_headers(self):
        self.assertEqual(self.conf["X_FRAME_OPTIONS"], "DENY")
        self.assertTrue(self.conf["SECURE_CONTENT_TYPE_NOSNIFF"])
        self.assertTrue(self.conf["SECURE_REFERRER_POLICY"])

    def test_cors_is_an_explicit_allowlist(self):
        self.assertFalse(
            self.conf["CORS_ALLOW_ALL_ORIGINS"],
            "CORS_ALLOW_ALL_ORIGINS with credentialed requests would attach "
            "the auth cookie to requests from any origin",
        )
        self.assertEqual(
            self.conf["CORS_ALLOWED_ORIGINS"], ["https://app.example.com"]
        )


class ProductionFailsLoudlyTests(SimpleTestCase):
    """A missing secret must stop the boot, not fall back to a default."""

    IMPORT_ONLY = "import django; django.setup()"

    def _boot_without(self, name):
        env = {k: v for k, v in PROD_ENV.items() if k != name}
        return run_in_subprocess(self.IMPORT_ONLY, env)

    def test_missing_secret_key_is_fatal(self):
        result = self._boot_without("DJANGO_SECRET_KEY")
        self.assertNotEqual(
            result.returncode,
            0,
            "production booted without DJANGO_SECRET_KEY -- it fell back to "
            "the committed development key",
        )
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_missing_allowed_hosts_is_fatal(self):
        result = self._boot_without("DJANGO_ALLOWED_HOSTS")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS", result.stderr)

    def test_missing_database_url_is_fatal(self):
        # base.py defaults to sqlite; production must not inherit that.
        result = self._boot_without("DATABASE_URL")
        self.assertNotEqual(
            result.returncode,
            0,
            "production booted without DATABASE_URL and would have used the "
            "sqlite fallback from base.py",
        )
        self.assertIn("DATABASE_URL", result.stderr)


class SettingsModuleDefaultTests(SimpleTestCase):
    """Importing the package must not pin DJANGO_SETTINGS_MODULE."""

    def test_importing_taskflow_does_not_select_development_settings(self):
        # taskflow/__init__.py imports celery.py, which used to call
        # os.environ.setdefault('DJANGO_SETTINGS_MODULE', <development>) at
        # import time. That ran before wsgi.py could apply its own default, so a
        # deploy that omitted the variable silently served with DEBUG=True.
        code = (
            "import os, taskflow; "
            "print('VALUE=' + repr(os.environ.get('DJANGO_SETTINGS_MODULE')))"
        )
        result = run_in_subprocess(code, {})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "VALUE=None",
            result.stdout,
            "importing taskflow set DJANGO_SETTINGS_MODULE as a side effect",
        )

    def test_wsgi_and_asgi_default_to_production(self):
        for module in ("wsgi", "asgi"):
            with self.subTest(module=module):
                source = (SRC_DIR / "taskflow" / f"{module}.py").read_text()
                self.assertIn(
                    "taskflow.settings.production",
                    source,
                    f"{module}.py does not default to production settings; the "
                    "old default named the settings package, whose __init__.py "
                    "is empty",
                )


class EnvExampleTests(SimpleTestCase):
    """Every name the settings read should be documented."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not ENV_EXAMPLE.is_file():
            raise unittest.SkipTest(f"repo root not mounted ({ENV_EXAMPLE})")
        cls.text = ENV_EXAMPLE.read_text()

    def test_documents_every_required_production_name(self):
        for name in (
            "DJANGO_SECRET_KEY",
            "DJANGO_ALLOWED_HOSTS",
            "DATABASE_URL",
            "DJANGO_SETTINGS_MODULE",
            "REDIS_URL",
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
        ):
            with self.subTest(name=name):
                self.assertIn(name, self.text)

    def test_ships_no_real_secret(self):
        for line in self.text.splitlines():
            if line.startswith("DJANGO_SECRET_KEY="):
                self.assertEqual(
                    line.strip(),
                    "DJANGO_SECRET_KEY=",
                    "the template must ship an empty secret, not a value",
                )


class DeployCheckGateTests(SimpleTestCase):
    """The CI gate must run against production and must block."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not CI_CONFIG.is_file():
            raise unittest.SkipTest(f"repo root not mounted ({CI_CONFIG})")
        if yaml is None:  # pragma: no cover
            raise unittest.SkipTest("PyYAML not installed")
        cls.ci = yaml.safe_load(CI_CONFIG.read_text())

    def test_deploy_check_targets_production_and_blocks(self):
        job = self.ci.get("deploy_check")
        self.assertIsNotNone(job, "the deploy_check job was removed")
        self.assertFalse(
            job.get("allow_failure", False),
            "deploy_check is advisory; C-3 is fixed, so it should block",
        )
        settings_module = job.get("variables", {}).get("DJANGO_SETTINGS_MODULE")
        self.assertEqual(
            settings_module,
            "taskflow.settings.production",
            "deploy_check still runs against development settings, so it "
            "cannot catch a production-only misconfiguration",
        )

    def test_ci_does_not_fabricate_a_dotenv_file(self):
        for name, body in self.ci.items():
            if not isinstance(body, dict):
                continue
            for line in body.get("before_script", []) + body.get("script", []):
                self.assertNotIn(
                    "DOTENV_CONTENT",
                    line,
                    f"job {name!r} writes a .env from a CI variable; the "
                    "settings read individual names from the environment",
                )
