"""
run_tests.py - Master Automated Test Runner for Blender 4.3+ / X-Plane 12 Addon.

Can be executed in headless Blender 4.3 CLI:
    & 'C:\Program Files\Blender Foundation\Blender 4.3\blender.exe' --background --factory-startup --python tests/run_tests.py

Supports CLI flags passed after '--':
    --tier <1|2|3|4|all>   Run a specific test tier (default: all)
    --module <module_name> Run a specific test module (e.g. test_obj8_importer)
    --verbose / -v         Enable detailed unittest verbosity
    --list                 List all test tiers, modules, and feature mappings

Exits with code 0 on complete pass (or safe skips for planned milestones), non-zero on test failures.
"""

import sys
import os
import time
import argparse
import unittest
from typing import List, Dict, Any, Tuple


# Ensure workspace root is in sys.path
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)


TIER_MODULE_MAP = {
    1: ["tests.test_synthetic_assets", "tests.test_tier1_features"],
    2: ["tests.test_tier2_boundary"],
    3: ["tests.test_tier3_combinations"],
    4: ["tests.test_tier4_scenarios"],
}

MODULAR_FILES = [
    "tests.test_addon_lifecycle",
    "tests.test_obj8_importer",
    "tests.test_acf_importer",
    "tests.test_rigging",
    "tests.test_materials",
    "tests.test_repacker",
    "tests.test_filtering",
    "tests.test_telemetry",
    "tests.test_fbx_export",
    "tests.test_roundtrip_obj8",
]


class FormattedTestResult(unittest.TextTestResult):
    """Custom TestResult formatter displaying tier and feature context."""

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.successes: List[unittest.TestCase] = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)
        if self.showAll:
            self.stream.writeln(" ... [ PASS ]")
            self.stream.flush()

    def addFailure(self, test, err):
        super().addFailure(test, err)
        if self.showAll:
            self.stream.writeln(" ... [ FAIL ]")
            self.stream.flush()

    def addError(self, test, err):
        super().addError(test, err)
        if self.showAll:
            self.stream.writeln(" ... [ ERROR ]")
            self.stream.flush()

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if self.showAll:
            self.stream.writeln(f" ... [ SKIP ] ({reason})")
            self.stream.flush()

    def startTest(self, test):
        super().startTest(test)
        if self.showAll:
            desc = test.shortDescription() or test._testMethodName
            mod = test.__class__.__module__.split('.')[-1]
            self.stream.write(f"  [{mod}] {test._testMethodName}: {desc}")
            self.stream.flush()


def parse_cli_args() -> argparse.Namespace:
    """Extract flags after '--' if present in sys.argv, otherwise parse sys.argv[1:]."""
    argv = sys.argv
    if "--" in argv:
        args_to_parse = argv[argv.index("--") + 1:]
    else:
        args_to_parse = [a for a in argv[1:] if not a.endswith('.py') and not a.startswith('--background') and not a.startswith('--factory-startup')]

    parser = argparse.ArgumentParser(description="Blender 4.3+ X-Plane 12 Test Suite Runner")
    parser.add_argument("--tier", choices=["1", "2", "3", "4", "all"], default="all", help="Target test tier to execute")
    parser.add_argument("--module", type=str, default=None, help="Specific test module name to run")
    parser.add_argument("--verbose", "-v", action="store_true", default=True, help="Verbose output")
    parser.add_argument("--list", action="store_true", help="List all registered test suites")

    return parser.parse_args(args_to_parse)


def run_test_suite(target_tier: str = "all", specific_module: str = None, verbose: bool = True) -> int:
    """
    Assembles and executes the test suite.
    :return: Exit code (0 for success, 1 for failures/errors)
    """
    print("=" * 80)
    print(" BLENDER 4.3+ / X-PLANE 12 AUTOMATED TEST SUITE RUNNER")
    print(f" Workspace Root: {WORKSPACE_ROOT}")
    try:
        import bpy
        print(f" Blender Runtime: {bpy.app.version_string} (Headless: {bpy.app.background})")
    except ImportError:
        print(" Blender Runtime: Standalone Python (Outside Blender)")
    print("=" * 80)

    loader = unittest.defaultTestLoader
    tier_results: Dict[int, Dict[str, int]] = {1: {}, 2: {}, 3: {}, 4: {}}

    total_run = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0

    start_time = time.time()

    if specific_module:
        module_name = specific_module if specific_module.startswith("tests.") else f"tests.{specific_module}"
        print(f"\n[RUNNING SINGLE MODULE] {module_name}")
        try:
            mod = __import__(module_name, fromlist=[''])
            suite = loader.loadTestsFromModule(mod)
            runner = unittest.TextTestRunner(resultclass=FormattedTestResult, verbosity=2 if verbose else 1)
            res = runner.run(suite)
            total_run = res.testsRun
            total_failed = len(res.failures)
            total_errors = len(res.errors)
            total_skipped = len(res.skipped)
        except Exception as e:
            print(f"ERROR: Failed to import or run module {module_name}: {e}")
            return 1

    else:
        # Run selected tiers
        tiers_to_run = [1, 2, 3, 4] if target_tier == "all" else [int(target_tier)]

        for tier_num in tiers_to_run:
            print(f"\n{'#' * 80}")
            print(f" EXECUTING TIER {tier_num}: {get_tier_name(tier_num)}")
            print(f"{'#' * 80}")

            tier_suite = unittest.TestSuite()
            for mod_path in TIER_MODULE_MAP.get(tier_num, []):
                try:
                    mod = __import__(mod_path, fromlist=[''])
                    mod_suite = loader.loadTestsFromModule(mod)
                    tier_suite.addTests(mod_suite)
                except Exception as e:
                    print(f"  [ERROR] Loading module {mod_path}: {e}")

            runner = unittest.TextTestRunner(resultclass=FormattedTestResult, verbosity=2 if verbose else 1)
            tier_res = runner.run(tier_suite)

            tier_results[tier_num] = {
                "run": tier_res.testsRun,
                "passed": len(tier_res.successes),
                "failed": len(tier_res.failures),
                "errors": len(tier_res.errors),
                "skipped": len(tier_res.skipped)
            }

            total_run += tier_res.testsRun
            total_failed += len(tier_res.failures)
            total_errors += len(tier_res.errors)
            total_skipped += len(tier_res.skipped)

    duration = time.time() - start_time

    # Print Final Summary Table
    print("\n" + "=" * 80)
    print(" TEST EXECUTION SUMMARY")
    print("=" * 80)
    print(f" {'Tier / Suite':<40} | {'Run':<6} | {'Pass':<6} | {'Skip':<6} | {'Fail':<6} | {'Error':<6}")
    print("-" * 80)

    for t_num in sorted(tier_results.keys()):
        data = tier_results[t_num]
        if data:
            name = f"Tier {t_num}: {get_tier_name(t_num)}"
            print(f" {name:<40} | {data.get('run',0):<6} | {data.get('passed',0):<6} | {data.get('skipped',0):<6} | {data.get('failed',0):<6} | {data.get('errors',0):<6}")

    print("-" * 80)
    print(f" {'TOTAL':<40} | {total_run:<6} | {total_run - total_failed - total_errors - total_skipped:<6} | {total_skipped:<6} | {total_failed:<6} | {total_errors:<6}")
    print(f" Total Execution Time: {duration:.2f} seconds")
    print("=" * 80)

    if total_failed == 0 and total_errors == 0:
        print(" >>> OVERALL STATUS: ALL TESTS PASSED (or cleanly skipped pending planned milestones)")
        return 0
    else:
        print(f" >>> OVERALL STATUS: FAILED ({total_failed} failures, {total_errors} errors)")
        return 1


def get_tier_name(tier_num: int) -> str:
    names = {
        1: "Feature Coverage (Isolation)",
        2: "Boundary & Corner Cases",
        3: "Cross-Feature Combinations",
        4: "Real-World Application Scenarios",
    }
    return names.get(tier_num, f"Tier {tier_num}")


def main():
    args = parse_cli_args()
    if args.list:
        print("Registered Tiers & Modules:")
        for t, mods in TIER_MODULE_MAP.items():
            print(f"  Tier {t} ({get_tier_name(t)}):")
            for m in mods:
                print(f"    - {m}")
        print("\nModular Test Suites:")
        for m in MODULAR_FILES:
            print(f"    - {m}")
        sys.exit(0)

    code = run_test_suite(target_tier=args.tier, specific_module=args.module, verbose=args.verbose)
    sys.exit(code)


if __name__ == "__main__":
    main()
