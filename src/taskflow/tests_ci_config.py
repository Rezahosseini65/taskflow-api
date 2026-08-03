"""
Regression tests for the CI quality gates (audit finding M-3).

M-3 was that the project declared `flake8`, `black`, `pytest`, and coverage tooling
and CI ran none of it -- so a config that could not boot (C-3) and a model default
that made every signup a staff user (C-2) both sailed through a green pipeline.

These tests assert the gates exist and are wired to fail. They deliberately check
*structure*, not lint cleanliness: whether the code currently passes flake8 is a
separate question from whether CI would notice if it stopped.
"""

import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None


# settings.BASE_DIR is the `src/` directory; the repo root is its parent.
REPO_ROOT = Path(settings.BASE_DIR).parent
CI_CONFIG = REPO_ROOT / ".gitlab-ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"
FLAKE8_CONFIG = REPO_ROOT / ".flake8"

# The Docker dev stack mounts only `src/`, so the repo-root config files are not
# visible from inside the container unless they are copied in. They are present in
# CI, which checks out the whole repo, and locally when the suite is run from the
# host. Skipping is the honest outcome there; CIConfigLocationTests below still
# runs unconditionally, so a broken REPO_ROOT fails instead of silently skipping.
REPO_ROOT_AVAILABLE = CI_CONFIG.is_file()

requires_repo_root = unittest.skipUnless(
    REPO_ROOT_AVAILABLE,
    f"repo root not mounted (looked for {CI_CONFIG})",
)


class CIConfigLocationTests(SimpleTestCase):
    """Guards the path arithmetic the rest of this module depends on."""

    def test_base_dir_is_the_src_directory(self):
        # If BASE_DIR ever stops pointing at `src/`, REPO_ROOT silently becomes
        # wrong and every test below would skip rather than fail.
        self.assertEqual(Path(settings.BASE_DIR).name, "src")
        self.assertTrue(
            (Path(settings.BASE_DIR) / "manage.py").is_file(),
            "expected manage.py in BASE_DIR; the repo layout has changed",
        )


@requires_repo_root
class CIQualityGateTests(SimpleTestCase):
    """The pipeline must run the tools the project declares."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if yaml is None:  # pragma: no cover
            raise unittest.SkipTest("PyYAML not installed")
        cls.ci = yaml.safe_load(CI_CONFIG.read_text())
        cls.jobs = {
            name: body
            for name, body in cls.ci.items()
            if isinstance(body, dict) and "script" in body
        }

    def _all_script_lines(self):
        lines = []
        for body in self.jobs.values():
            lines.extend(body.get("script", []))
            lines.extend(body.get("before_script", []))
        return lines

    def _job_running(self, needle):
        """Return (job_name, job_body) for the first job whose script runs `needle`."""
        for name, body in self.jobs.items():
            for line in body.get("script", []):
                if needle in line:
                    return name, body
        return None, None

    def test_flake8_runs(self):
        name, _ = self._job_running("flake8")
        self.assertIsNotNone(name, "no CI job runs flake8 (M-3)")

    def test_black_check_runs(self):
        name, _ = self._job_running("black")
        self.assertIsNotNone(name, "no CI job runs black (M-3)")
        line = next(
            ln
            for body in self.jobs.values()
            for ln in body.get("script", [])
            if "black" in ln
        )
        self.assertIn(
            "--check",
            line,
            "black must run with --check in CI; without it black rewrites files "
            "and the job passes no matter what",
        )

    def test_critical_lint_gate_is_blocking(self):
        """The syntax-error/undefined-name tier must not be advisory."""
        name, body = self._job_running("--select=E9")
        self.assertIsNotNone(
            name,
            "no CI job runs the critical flake8 tier (E9/F63/F7/F82)",
        )
        self.assertFalse(
            body.get("allow_failure", False),
            f"job {name!r} runs the critical lint tier but is allow_failure -- "
            "undefined names and syntax errors would not block a merge",
        )

    def test_coverage_is_measured_and_gated(self):
        name, body = self._job_running("coverage run")
        self.assertIsNotNone(name, "CI does not measure coverage (M-3)")
        script = body["script"]
        self.assertTrue(
            any("coverage report" in ln for ln in script),
            "coverage is recorded but never reported, so the fail_under floor in "
            "pyproject.toml is never enforced",
        )
        self.assertFalse(
            body.get("allow_failure", False),
            f"job {name!r} enforces the coverage floor but is allow_failure",
        )
        # `|| true` on the reporting step would silently defeat the floor.
        for line in script:
            if "coverage report" in line:
                self.assertNotIn(
                    "|| true",
                    line,
                    "coverage report is suffixed with `|| true`, which discards "
                    "the fail_under exit code",
                )

    def test_deploy_check_runs_with_a_failing_exit_code(self):
        """`check --deploy` exits 0 on warnings unless --fail-level is set."""
        name, body = self._job_running("check --deploy")
        self.assertIsNotNone(
            name,
            "CI does not run `manage.py check --deploy` -- the gate that would "
            "have caught C-3 (M-3)",
        )
        line = next(ln for ln in body["script"] if "check --deploy" in ln)
        self.assertIn(
            "--fail-level",
            line,
            "`check --deploy` reports warnings but still exits 0; without "
            "--fail-level the job passes with 26 outstanding issues",
        )

    def test_makemigrations_check_is_retained(self):
        """This gate already existed; M-3's fix must not drop it."""
        self.assertTrue(
            any(
                "makemigrations --check" in ln for ln in self._all_script_lines()
            ),
            "the pre-existing `makemigrations --check` gate was removed",
        )

    def test_test_suite_still_runs(self):
        self.assertTrue(
            any(
                "manage.py test" in ln for ln in self._all_script_lines()
            ),
            "CI no longer runs the test suite",
        )


@requires_repo_root
class CoverageFloorTests(SimpleTestCase):
    """The coverage floor must exist and be a real number, not zero."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if tomllib is None:  # pragma: no cover
            raise unittest.SkipTest("tomllib not available")
        cls.pyproject = tomllib.loads(PYPROJECT.read_text())

    def test_fail_under_is_configured(self):
        report = (
            self.pyproject.get("tool", {}).get("coverage", {}).get("report", {})
        )
        self.assertIn(
            "fail_under",
            report,
            "no coverage floor in [tool.coverage.report]; `coverage report` "
            "would always exit 0",
        )
        self.assertGreater(
            report["fail_under"],
            0,
            "a fail_under of 0 is not a gate",
        )

    def test_coverage_is_a_declared_dependency(self):
        dev = (
            self.pyproject["tool"]["poetry"]["group"]["dev"]["dependencies"]
        )
        self.assertIn(
            "coverage",
            dev,
            "CI runs coverage but it is not in the dev dependency group, so "
            "`poetry install` would not provide it",
        )

    def test_flake8_config_exists(self):
        self.assertTrue(
            FLAKE8_CONFIG.is_file(),
            "no .flake8 config; flake8 would fall back to its 79-column default "
            "and contradict black's 88",
        )
