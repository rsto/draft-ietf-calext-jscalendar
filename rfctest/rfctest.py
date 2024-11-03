from __future__ import annotations

import base64
import enum
import json
import urllib.request

from dataclasses import dataclass

from rfctest.jsical import JDiff, JObject, VObject, ParseError


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
        resp = self.http_post(
            ical,
            headers={
                "Content-Type": "text/calendar;charset=utf-8",
                "Accept": "application/jscalendar+json;type=group",
            },
        )
        return bytes(resp)


class TestState(enum.Enum):
    READY = "Read examples"
    PARSE_ICAL = "Parse iCalendar example"
    PARSE_JCAL = "Parse and normalize JSCalendar example"
    EXPAND_ICAL = "Expand iCalendar example"
    GET_RESPONSE = "Get backend reponse"
    PARSE_RESPONSE = "Normalize response"
    DIFF = "Diff response"

    def __str__(self):
        return self.name.lower()


class TestOutcome(enum.StrEnum):
    SUCCESS = enum.auto()
    INVALID = enum.auto()
    ERROR = enum.auto()


@dataclass
class Test:
    name: str
    """Test name"""
    icaltext: str
    """Verbatim iCalendar example"""
    jcaltext: str
    """Verbatim JSCalendar example"""
    state: TestState = TestState.READY
    """Test state"""
    vcal: VObject = None
    """Parsed iCalendar example"""
    jgroup: JObject = None
    """Parsed JSCalendar example"""
    ical: str = None
    """Expanded iCalendar data"""
    resp: bytes = None
    """Backend response"""
    jresp: dict = None
    """Normalized JSON response"""
    jdiff: JDiff = None
    """JSON diff"""
    error: Exception = None
    """Any unexpected error"""

    def _advance_state(self, next_state: TestState, until_state: TestState) -> bool:
        if until_state is not None and self.state == until_state:
            return False
        self.state = next_state
        return True

    def run(self, backend: Backend, until_state=None):
        try:
            if not self._advance_state(TestState.PARSE_ICAL, until_state):
                return
            self.vcal = VObject.parse(self.icaltext).to_vcalendar()

            if not self._advance_state(TestState.PARSE_JCAL, until_state):
                return
            self.jgroup = JObject.parse(self.jcaltext).to_group().normalized()

            if not self._advance_state(TestState.EXPAND_ICAL, until_state):
                return
            self.ical = self.vcal.with_default_props().to_ical()

            if not self._advance_state(TestState.GET_RESPONSE, until_state):
                return
            self.resp = backend.convert_to_jgroup(self.ical.encode())

            if not self._advance_state(TestState.PARSE_RESPONSE, until_state):
                return
            self.jresp = JDiff.normalize_json(json.loads(self.resp))

            if not self._advance_state(TestState.DIFF, until_state):
                return
            self.jdiff = self.jgroup.diff_json(self.jresp)
        except Exception as e:
            self.error = e

    def outcome(self) -> TestOutcome:
        if self.error:
            return TestOutcome.ERROR
        if not self.jdiff.empty():
            return TestOutcome.INVALID
        return TestOutcome.SUCCESS

    def failed(self) -> bool:
        return self.outcome() != TestOutcome.SUCCESS
