from __future__ import annotations

import argparse
import collections
import os
import sys
import xml.etree.ElementTree as XMLTree

from operator import attrgetter

from rfctest.rfctest import Test, TestState, TestOutcome, Backend
from rfctest.report import HTMLReporter


def find_tests(rfcfile_name: str, names: set[str] = None, verbose=False):
    tests = []
    for figure in XMLTree.parse(rfcfile_name).getroot().findall(".//figure"):
        anchor = figure.get("anchor")
        if not anchor:
            continue
        if names and anchor not in names:
            continue

        icalcode = figure.find("./sourcecode[@type='icalendar']")
        icaltext = icalcode.text.strip() if icalcode is not None else ""
        if not icaltext:
            if verbose or names:
                print(f"{anchor}: no icalendar sourcecode, ignoring", file=sys.stderr)
            continue

        jcalcode = figure.find("./sourcecode[@type='jscalendar']")
        jcaltext = jcalcode.text.strip() if jcalcode is not None else ""
        if not jcaltext:
            if verbose or names:
                print(f"{anchor}: no jscalendar sourcecode, ignoring", file=sys.stderr)
            continue

        tests.append(Test(anchor, icaltext, jcaltext))

    tests.sort(key=attrgetter("name"))
    return tests


def run_tests(tests: list[Test], backend: Backend):
    counter = collections.Counter()
    for test in tests:
        test.run(backend)
        counter[test.outcome()] += 1
        print(f"[{test.outcome()}]\t{test.name}", file=sys.stderr)
    print(f"Ran {counter.total()} test(s): ", end="", file=sys.stderr)
    print(", ".join(f"{counter[o]} {o}" for o in TestOutcome), end="", file=sys.stderr)
    print("", file=sys.stderr)


def report_tests(tests: list[Test], report):
    report.begin()
    report.summary(tests)
    for test in tests:
        report.begin_test(test)
        for state in TestState:
            report.report_state(test, state)
            if test.state == state:
                break
        report.end_test(test)
    report.end()


ENV_BACKEND_URL = "RFCTEST_BACKEND_URL"
ENV_BACKEND_AUTH = "RFCTEST_BACKEND_AUTH"
RFC_FILE = "draft-ietf-calext-jscalendar-icalendar.xml"
REPORT_FILE = "report.html"


def main():
    prog = "python -m rfctest"

    parser = argparse.ArgumentParser(
        prog=prog,
        description="Process draft-icalendar-jscalendar tests",
    )
    parser.add_argument(
        "-f",
        "--file",
        default=RFC_FILE,
        help=f"load tests from this file (default: {RFC_FILE})",
    )
    parser.add_argument(
        "-o",
        "--report",
        default=REPORT_FILE,
        help=f"write report to this file (default: {REPORT_FILE})",
    )
    parser.add_argument(
        "--url",
        help=f"use HTTP backend at this URL (default: {ENV_BACKEND_URL} environment variable)",
    )
    parser.add_argument(
        "--auth",
        help=f"use HTTP Basic authentication. AUTH must be username:password. (default: {ENV_BACKEND_AUTH} environment variable)",
    )
    parser.add_argument("test", nargs="*", help="process this test")
    args = parser.parse_args()

    if not args.url:
        args.url = os.getenv(ENV_BACKEND_URL)
    if not args.auth:
        args.auth = os.getenv(ENV_BACKEND_AUTH)

    want_tests = set(args.test) if args.test else None
    try:
        backend = Backend(args.url, args.auth)
        tests = find_tests(args.file, names=want_tests)
        run_tests(tests, backend)
        with open(args.report, "w", encoding="utf-8") as file:
            report = HTMLReporter(file)
            report_tests(tests, report)
    except OSError as e:
        print(f"{e}", file=sys.stderr)
        raise SystemExit from e

    sys.exit(1 if any(t.error for t in tests) else 0)


if __name__ == "__main__":
    main()
