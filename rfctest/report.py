from __future__ import annotations

import html
import json

from rfctest.rfctest import Test, TestState
from rfctest.jsical import JPath


class JSONHighlighter:
    def __init__(self, file):
        self.file = file
        self.reset()

    def reset(self):
        self.indent = 0
        self.scope = []
        self.path = JPath([])
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

    def print(self, data, highlight: dict[str, list[JPath]] = None):
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
            # JSONEncoder returns a single token for the first item in
            # an array, e.g.
            #    >>> [tok for tok in json.JSONEncoder().iterencode([1])]
            #    ['[1', ']']
            # so we'll need to split that token into two to produce '['.
            if tok[0] == "[" and len(tok):
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

    def begin(self):
        print("<!doctype html>", file=self.file)
        print("<html>", file=self.file)
        print("<head>", file=self.file)
        print('<meta charset="utf-8">', file=self.file)
        print("<title>RFCtest</title>", file=self.file)
        print(
            """<style>
  .success { background: lightgreen; }
  .invalid { background: orange; }
  .error {background: red;}
  .sourcecode { white-space: pre; font-family: monospace; }
  .highlight { color: darkred; font-weight: bolder; }
  pre, .sourcecode { background-color: #efefef; width: max-content; padding: 1em; border: 1px solid #aaaaaa; }
</style>""",
            file=self.file,
        )
        print("</head>", file=self.file)
        print("<body>", file=self.file)
        print("<h1>iCalendar to JSCalendar</h1>", file=self.file)

    def end(self):
        print("</body>", file=self.file)
        print("</html>", file=self.file)
        print("\n", file=self.file)

    def summary(self, tests: list[Test]):
        print("<h2>Summary</h2>", file=self.file)
        print("<table>", file=self.file)
        print("<tr><th>Test name</th><th>Outcome</th></tr>", file=self.file)
        for test in tests:
            outcome = test.outcome()
            href = f"#{test.name}-{test.state}"
            print("<tr>", file=self.file)
            print(f"<td>{test.name}</td>", file=self.file)
            print(
                f'<td><a href="{href}"><span class="{outcome}">{outcome}</span></a></td></tr>',
                file=self.file,
            )
        print("</table>", file=self.file)

    def begin_test(self, test: Test):
        print("<hr>", file=self.file)
        print(f"<h2 id=>Test {test.name}</h2>", file=self.file)

    def end_test(self, test: Test):
        pass

    def report_diff(
        self,
        description: str,
        jvals: tuple[dict, dict],
        highlight: tuple[list[JPath], list[JPath]],
        captions: tuple[str, str],
    ):
        print(f"<p>{description}</p>", file=self.file)
        print(
            '<div style="display: flex; gap: 1em;" class="box">',
            file=self.file,
        )
        for i in range(2):
            print("<div>", file=self.file)
            print(
                f'<h4 style="text-align: center;">{captions[i]}</h4>',
                file=self.file,
            )
            print('<p class="sourcecode">', file=self.file)
            self.jhighlighter.print(jvals[i], highlight={"highlight": highlight[i]})
            print("</p>", file=self.file)
            print("</div>", file=self.file)
        print("</div>", file=self.file)

    def report_state(self, test: Test, state: TestState):
        print(f"<h3 id={test.name}-{state}>{state.value}</h3>", file=self.file)

        if test.error and test.state == state:
            print(
                f"<p>Failed with error</p><pre>{test.error}</pre>",
                file=self.file,
            )
            return

        match state:
            case TestState.READY:
                print(
                    f"<h4>iCalendar</h4><pre>{test.icaltext}</pre>",
                    file=self.file,
                )
                print(
                    f"<h4>JSCalendar</h4><pre>{test.jcaltext}</pre>",
                    file=self.file,
                )
            case TestState.PARSE_ICAL:
                print(f"<pre>{test.vcal}</pre>", file=self.file)
            case TestState.PARSE_JCAL:
                print(f"<pre>{test.jgroup}</pre>", file=self.file)
            case TestState.EXPAND_ICAL:
                print(f"<pre>{test.ical}</pre>", file=self.file)
            case TestState.GET_RESPONSE:
                print(f"<pre>{test.resp.decode()}</pre>", file=self.file)
            case TestState.PARSE_RESPONSE:
                s = json.dumps(test.jresp, indent=2)
                print(f"<pre>{s}</pre>", file=self.file)
            case TestState.DIFF:
                if test.jdiff.empty():
                    print("<p>All properties match.</p>", file=self.file)
                if test.jdiff.a_only:
                    self.report_diff(
                        "The following properties are expected but missing:",
                        (test.jgroup.to_json(), test.jresp),
                        (test.jdiff.a_only, []),
                        ("Expected", "Response"),
                    )
                if test.jdiff.unequal:
                    self.report_diff(
                        "The following property values do not match:",
                        (test.jgroup.to_json(), test.jresp),
                        (
                            [unq[0] for unq in test.jdiff.unequal],
                            [unq[1] for unq in test.jdiff.unequal],
                        ),
                        ("Expected", "Response"),
                    )
                if test.jdiff.b_only:
                    self.report_diff(
                        "The following properties are unexpected:",
                        (test.jgroup.to_json(), test.jresp),
                        ([], test.jdiff.b_only),
                        ("Expected", "Response"),
                    )
