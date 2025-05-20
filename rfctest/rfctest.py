from __future__ import annotations

import abc
import argparse
import base64
import collections
import copy
import enum
import html
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as XMLTree

from operator import attrgetter

from .jsical import JsonDiff, JObject, JsonPath, Component, ComponentDiff, ParseError


class BackendError(Exception):
    pass


class Backend:
    def __init__(self, url: str, user_pwd: str = None):
        self.url = url
        self.auth = base64.b64encode(user_pwd.encode()).decode() if user_pwd else None

    def http_post(self, data, headers: dict = None):
        if self.url is None:
            raise BackendError("No backend URL defined")
        headers = {} if headers is None else headers
        if self.auth:
            headers = {"Authorization": f"Basic {self.auth}"} | headers
        req = urllib.request.Request(self.url, headers=headers, data=data)
        try:
            with urllib.request.urlopen(req) as res:
                return res.read()
        except urllib.error.URLError as e:
            raise BackendError(e)

    def convert_to_jgroup(self, ical: bytes) -> bytes:
        res = self.http_post(
            ical,
            headers={
                "Content-Type": "text/calendar;charset=utf-8",
                "Accept": "application/jscalendar+json;type=group",
            },
        )
        return bytes(res)

    def convert_to_ical(self, jscal: dict) -> bytes:
        res = self.http_post(
            json.dumps(jscal).encode(),
            headers={
                "Content-Type": "application/jscalendar+json;type=group",
                "Accept": "text/calendar;charset=utf-8",
            },
        )
        return bytes(res)


class Test:
    class Result(abc.ABC):
        response: bytes = None
        """Undecoded backend response"""
        error: Exception = None
        """Any unexpected error"""

        def outcome(self) -> str:
            if self.error:
                return "error"
            elif self.response is None:
                return "none"
            elif not self.is_valid():
                return "invalid"
            else:
                return "success"

    class Ical2JscalResult(Result):
        json_response: dict = None
        """Normalized JSON response"""
        json_diff: JsonDiff = None
        """Diffed JSON response"""

        def is_valid(self) -> bool:
            return self.json_diff and self.json_diff.empty()

    class Jscal2IcalResult(Result):
        ical_response: Component = None
        """Normalized iCalendar response"""
        ical_diff: ComponentDiff = None
        """Diffed iCalendar response"""

        def is_valid(self) -> bool:
            return self.ical_diff and self.ical_diff.empty()

    name: str
    """Test name"""
    icaltext: str
    """Verbatim iCalendar example"""
    jscaltext: str
    """Verbatim JSCalendar example"""
    vobject: Component
    """Parsed iCalendar example"""
    jgroup: JObject
    """Parsed JSCalendar example"""
    expanded_ical: str
    """Expanded iCalendar example"""
    expanded_jscal: dict
    """Expanded JSCalendar example"""
    i2jresult: Ical2JscalResult
    """Result of iCalendar to JSCalendar conversion"""
    j2iresult: Ical2JscalResult
    """Result of iCalendar to JSCalendar conversion"""

    def __init__(self, name: str, icaltext: str, jcaltext: str):
        self.name = name
        self.icaltext = icaltext
        self.jscaltext = jcaltext
        self.vobject = Component.parse(self.icaltext).to_vcalendar()
        self.jgroup = JObject.parse(self.jscaltext).to_group().normalized()
        self.expanded_ical = self.vobject.with_default_props().to_ical()
        self.expanded_jscal = self.jgroup.with_default_props().to_json()
        self.i2jresult = None
        self.j2iresult = None

    def run(self, backend: Backend):
        try:
            self.i2jresult = Test.Ical2JscalResult()
            self.i2jresult.response = backend.convert_to_jgroup(
                self.expanded_ical.encode()
            )
            self.i2jresult.json_response = JsonDiff.normalize_json(
                json.loads(self.i2jresult.response)
            )
            self.i2jresult.json_diff = self.jgroup.diff_json(
                self.i2jresult.json_response
            )
        except Exception as e:
            self.i2jresult.error = e

        try:
            self.j2iresult = Test.Jscal2IcalResult()
            self.j2iresult.response = backend.convert_to_ical(self.expanded_jscal)
            ical_response = Component.parse(
                self.j2iresult.response.decode(), strict=True
            )
            ical_response.normalize()
            self.j2iresult.ical_response = ical_response
            vobject = copy.deepcopy(self.vobject)
            vobject.normalize()
            self.j2iresult.ical_diff = ComponentDiff(
                vobject, self.j2iresult.ical_response
            )
        except Exception as e:
            self.j2iresult.error = e


class JSONHighlighter:
    def __init__(self, file):
        self.file = file
        self.reset()

    def reset(self):
        self.indent = 0
        self.scope = []
        self.path = JsonPath([])
        self.toks = []
        self.highlight = {}

    def _flush(self, pre="", end=""):
        if not self.toks:
            return
        print(
            pre,
            " " * self.indent,
            "".join(html.escape(t) for t in self.toks),
            sep="",
            end=end,
            file=self.file,
        )
        self.toks.clear()

    def _enter_scope(self, tok):
        assert tok in ("{", "[")
        self.scope.append(tok)
        if tok == "[":
            self._enter_path("0")

    def _leave_scope(self):
        self._leave_path()
        self.scope.pop()

    def _enter_path(self, name):
        self.path.append(name)
        if css_class := self.highlight.get(self.path.encode()):
            print(f'<span class="{css_class}">', end="", file=self.file)

    def _leave_path(self, have_next=False):
        if self.path.encode() in self.highlight:
            print("</span>", end="", file=self.file)
        v = self.path.pop()
        if have_next and self.scope[-1] == "[":
            self._enter_path(str(int(v) + 1))

    def print(self, data, highlight: dict[str, list[JsonPath]] = None):
        self.reset()
        if not isinstance(data, dict) and not isinstance(data, list):
            print(json.dumps(data), file=self.file)
            return

        if highlight is not None:
            self.highlight.update(
                (jpath.encode(), css_class)
                for css_class, jpaths in highlight.items()
                for jpath in jpaths
            )

        tok_stack = []
        for tok in json.JSONEncoder(sort_keys=True, separators=(",", ": ")).iterencode(
            data
        ):
            # Split start of array and ',' from the actual array element.
            if tok[0] in "[," and len(tok) > 1:
                tok_stack.append(tok[1:])
                tok_stack.append(tok[0])
            else:
                tok_stack.append(tok)
            while len(tok_stack):
                tok = tok_stack.pop()
                match tok:
                    case "{" | "[":
                        self.toks.append(tok)
                        self._flush(end="\n")
                        self.indent += 2
                        self._enter_scope(tok)
                    case "}" | "]":
                        self._flush()
                        self.indent -= 2
                        self.toks.append(tok)
                        self._flush(pre="\n")
                        self._leave_scope()
                    case ",":
                        self.toks.append(tok)
                        self._flush(end="\n")
                        self._leave_path(have_next=True)
                    case ": ":
                        self.toks.append(tok)
                        self._enter_path(json.loads(self.toks[-2]))
                    case _:
                        self.toks.append(tok)
        self._flush(pre="\n", end="\n")  # flush any garbage


class HTMLReporter:
    def __init__(self, file):
        self.file = file
        self.jhighlighter = JSONHighlighter(file)

    def print(self, tests: list[Test]):
        self._print_preamble()
        self._print_summary(tests)
        for test in tests:
            print("<hr>", file=self.file)
            print(f"<h2 id={test.name}>Test {test.name}</h2>", file=self.file)
            self._print_test_details(test)
            self._print_i2jresult(test)
            self._print_j2iresult(test)
        self._print_footer()

    def _print_preamble(self):
        print(
            """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>RFCtest</title>
<style>
  .success { background: lightgreen; }
  .invalid { background: orange; }
  .error {background: red;}
  .sourcecode { white-space: pre; font-family: monospace; }
  .highlight { color: darkred; font-weight: bolder; }
  pre, .sourcecode { background-color: #efefef; width: max-content; padding: 1em; border: 1px solid #aaaaaa; }
</style>
</head>
<body>
<h1>jscalendar-icalendar</h1>
""",
            file=self.file,
        )

    def _print_footer(self):
        print(
            """
</body>
</html>""",
            file=self.file,
        )

    def _print_summary(self, tests: list[Test]):
        print(
            """
<h2>Summary</h2>
<table>
  <tr>
    <th>Test name</th>
    <th>iCalendar to JSCalendar</th>
    <th>JSCalendar to iCalendar</th>
  </tr>""",
            file=self.file,
        )
        for test in tests:
            print(
                f"""
<tr>
  <td>{test.name}</td>
  <td>
    <a href="#{test.name}-i2j">
      <span class="{test.i2jresult.outcome()}">
          {test.i2jresult.outcome()}
      </span>
    </a>
  </td>
 <td>
   <a href="#{test.name}-j2i">
     <span class="{test.j2iresult.outcome()}">
       {test.j2iresult.outcome()}
     </span>
   </a>
 </td>
</tr>""",
                file=self.file,
            )
        print("</table>", file=self.file)

    def _print_test_details(self, test: Test):
        print(
            f"""
<details>
  <summary>Test Input</summary>
  <h3>Original examples</h3>
  <h4>iCalendar</h4>
  <pre>{html.escape(test.icaltext)}</pre>
  <h4>JSCalendar</h4>
  <pre>{html.escape(test.jscaltext)}</pre>
  <h3>Parsed iCalendar example</h3>
  <pre>{html.escape(str(test.vobject))}</pre>
  <h3>Parsed JSCalendar example</h3>
  <pre>{html.escape(str(test.jgroup))}</pre>
  <h3>Expanded iCalendar example</h3>
  <pre>{html.escape(test.expanded_ical)}</pre>
</details>""",
            file=self.file,
        )

    def _print_i2jresult(self, test: Test):
        print(
            f"""
<h3 id={test.name}-i2j>iCalendar to JSCalendar</h3>
  <p>
    <span class="{test.i2jresult.outcome()}">
      {test.i2jresult.outcome()}
    </span>
  </p>""",
            file=self.file,
        )
        if test.i2jresult.error:
            print(f"<pre>{test.i2jresult.error}</pre>", file=self.file)
        if not test.i2jresult.json_diff.empty():
            a = test.jgroup.to_json()
            b = test.i2jresult.json_response
            jdiff = test.i2jresult.json_diff
            if jdiff.missing:
                self._print_json_diff(
                    "The following properties are expected but missing:",
                    (a, b),
                    (jdiff.missing, []),
                    ("Expected", "Response"),
                )
            if jdiff.notequal:
                self._print_json_diff(
                    "The following property values do not match:",
                    (a, b),
                    (
                        [neq[0] for neq in jdiff.notequal],
                        [neq[1] for neq in jdiff.notequal],
                    ),
                    ("Expected", "Response"),
                )
            if jdiff.unexpected:
                self._print_json_diff(
                    "The following properties are unexpected:",
                    (a, b),
                    ([], jdiff.unexpected),
                    ("Expected", "Response"),
                )

        print("<details><summary>Test Output</summary>", file=self.file)
        if test.i2jresult.response:
            print(f"<h3>Backend response</h3>", file=self.file)
            print(f"<pre>{html.escape(test.i2jresult.response.decode())}</pre>", file=self.file)
        if test.i2jresult.json_response:
            print(f"<h3>Normalized backend response</h3>", file=self.file)
            s = json.dumps(test.i2jresult.json_response, indent=2)
            print(f"<pre>{html.escape(s)}</pre>", file=self.file)
        print("</details>", file=self.file)

    def _print_json_diff(
        self,
        description: str,
        jvals: tuple[dict, dict],
        highlight: tuple[list[JsonPath], list[JsonPath]],
        captions: tuple[str, str],
    ):
        print(
            f'<p>{description}</p><div style="display: flex; gap: 1em;" class="box">',
            file=self.file,
        )
        for i in range(2):
            print(
                f'<div><h4 style="text-align: center;">{captions[i]}</h4><p class="sourcecode">',
                file=self.file,
            )
            self.jhighlighter.print(jvals[i], highlight={"highlight": highlight[i]})
            print("</p></div>", file=self.file)
        print("</div>", file=self.file)

    def _print_j2iresult(self, test: Test):
        print(f"<h3 id={test.name}-j2i>JSCalendar to iCalendar</h3>", file=self.file)
        print(
            f"""
<p>
  <span class="{test.j2iresult.outcome()}">
    {test.j2iresult.outcome()}
  </span>
</p>""",
            file=self.file,
        )
        if test.j2iresult.error:
            print(f"<pre>{test.j2iresult.error}</pre>", file=self.file)
        if test.j2iresult.ical_diff and not test.j2iresult.ical_diff.empty():
            print(f"<h3>Expected</h3>", file=self.file)
            print(f"<pre>{html.escape(str(test.vobject))}</pre>", file=self.file)
            print(f"<h3>Got</h3>", file=self.file)
            print(f"<pre>{html.escape(str(test.j2iresult.ical_response))}</pre>", file=self.file)


        print("<details>", file=self.file)
        print("<summary>Test Output</summary>", file=self.file)
        if test.j2iresult.response:
            print(f"<h3>Backend response</h3>", file=self.file)
            print(f"<pre>{html.escape(test.j2iresult.response.decode())}</pre>", file=self.file)
        if test.j2iresult.ical_response:
            print(f"<h3>Normalized backend response</h3>", file=self.file)
            print(f"<pre>{html.escape(str(test.j2iresult.ical_response))}</pre>", file=self.file)
        print("</details>", file=self.file)


def find_tests(rfcfile_name: str, names: set[str] = None, verbose=False):
    tests = []
    for figure in XMLTree.parse(rfcfile_name).getroot().findall(".//figure"):
        anchor = figure.get("anchor")
        if not anchor:
            continue
        if not anchor.startswith("test-") or names and anchor not in names:
            continue

        icalcode = figure.find("./sourcecode[@type='text/calendar']")
        icaltext = icalcode.text.strip() if icalcode is not None else ""
        if not icaltext:
            if verbose or names:
                print(f"{anchor}: no icalendar sourcecode, ignoring", file=sys.stderr)
            continue

        jcalcode = figure.find("./sourcecode[@type='json']")
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
        print(f"{test.name}", file=sys.stderr)


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
            HTMLReporter(file).print(tests)
    except OSError as e:
        print(f"{e}", file=sys.stderr)
        raise SystemExit from e
