from __future__ import annotations

import copy
import itertools
import json
import re
import uuid

from collections import UserList
from dataclasses import dataclass, field


class ParseError(ValueError):
    pass


@dataclass
class Parameter:
    name: str
    value: str

    def __str__(self):
        return f"{self.name}={self.value}"


@dataclass
class Property:
    name: str
    value: str
    params: list[Parameter] = field(default_factory=list)

    def __str__(self):
        params = "".join(f";{p}" for p in self.params)
        return f"{self.name}{params}:{self.value}"

    @classmethod
    def parse(cls, line: str) -> Property:
        # Parse name
        s = line
        m = re.match("([A-Za-z0-9-]+)[:;]", s)
        if not m:
            raise ParseError(f"iCalendar: invalid property name: {s}")
        name = s[0 : m.end() - 1].upper()
        s = s[m.end() - 1 :]

        # Parse parameters
        params = []
        while s[0] == ";":
            m = re.match(r';([A-Za-z0-9-]+)=((".*?(?<!\\)")|[^";:]*)', s)
            if not m:
                raise ParseError(f"iCalendar: invalid parameter: {s}")
            params.append(Parameter(m.group(1).upper(), m.group(2)))
            s = s[m.end() :]

        # Parse value
        if s[0] != ":":
            raise ParseError(f"iCalendar: missing property value: {line}")
        value = s[1:]
        return Property(name, value, params=params)


@dataclass
class VObject:
    name: str
    props: list[Property] = field(default_factory=list)
    comps: list[VObject] = field(default_factory=list)
    allow_any: bool = False

    def format(self, include_any=True) -> str:
        linegen = [
            [f"BEGIN:{self.name}"],
            map(str, self.props),
            (comp.format(include_any) for comp in self.comps),
            [f"END:{self.name}"],
        ]
        if include_any and self.allow_any:
            linegen.insert(-1, ["..."])
        return "\r\n".join(itertools.chain(*linegen))

    def to_ical(self) -> str:
        return self.format(include_any=False)

    def __str__(self):
        return self.format(include_any=True)

    def with_default_props(self) -> VObject:
        vobj = copy.deepcopy(self)
        comps = [vobj]
        while comps:
            comp = comps.pop()
            comps.extend(comp.comps)
            have_props = set(prop.name.upper() for prop in comp.props)

            def add_default(prop):
                if not prop.name in have_props:
                    comp.props.append(prop)

            match comp.name:
                case "VCALENDAR":
                    add_default(Property("PRODID", "-//FOO//bar//EN"))
                    add_default(Property("VERSION", "2.0"))
                case "VEVENT":
                    add_default(Property("DTSTAMP", "20060102T030405Z"))
                    add_default(Property("UID", f"{uuid.uuid4()}"))
                    add_default(Property("DTSTART", "20060102T030405Z"))
        return vobj

    def to_vcalendar(self) -> VObject:
        vobj = copy.deepcopy(self)
        default_parent = {
            "AVAILABLE": "VAVAILABILITY",
            "DAYLIGHT": "VTIMEZONE",
            "PARTICIPANT": "VEVENT",
            "STANDARD": "VTIMEZONE",
            "VALARM": "VEVENT",
            "VAVAILABILITY": "VCALENDAR",
            "VCALENDAR": None,
            "VEVENT": "VCALENDAR",
            "VFREEBUSY": "VCALENDAR",
            "VJOURNAL": "VCALENDAR",
            "VLOCATION": "VEVENT",
            "VRESOURCE": "VEVENT",
            "VTIMEZONE": "VCALENDAR",
            "VTODO": "VCALENDAR",
        }
        while parent_name := default_parent.get(vobj.name):
            parent = VObject(parent_name, allow_any=True)
            parent.comps.append(vobj)
            vobj = parent
        if vobj.name != "VCALENDAR":
            vobj = VObject("VCALENDAR", comps=[vobj])
        return vobj

    @classmethod
    def parse(cls, s: str, default_name="VEVENT") -> VObject:
        # Unfold and split lines
        lines = re.split(r"\r?\n", re.sub(r"\r?\n([ ]{2}|\t)", "", s.strip()))
        # Parse example
        stack = [VObject(None)]
        comp = stack[0]
        for line in map(str.strip, lines):
            if line == "...":
                comp.allow_any = True
                continue
            prop = Property.parse(line)
            if prop.name == "BEGIN":
                comp.comps.append(VObject(prop.value))
                stack.append(comp)
                comp = comp.comps[-1]
            elif prop.name == "END":
                if prop.value != comp.name:
                    raise ParseError(
                        f"Unexpected END:{prop.value}, expected END:{comp.name}"
                    )
                comp = stack.pop()
            else:
                comp.props.append(prop)
        comp = stack[0]
        if len(comp.comps) == 1 and not comp.props:
            comp = comp.comps[0]
        else:
            if not comp.comps:
                comp.allow_any = True
            comp.name = default_name
        return comp


class JPath(UserList):
    def __init__(self, data):
        super().__init__(data)

    @classmethod
    def decode(cls, s: str) -> JPath:
        return JPath(
            list(s.replace("~1", "/").replace("~0", "~") for s in s.split("/"))
        )

    def encode(self) -> str:
        return "/".join(s.replace("~", "~0").replace("/", "~1") for s in self.data)


@dataclass
class JDiff:
    a_only: list[JPath]
    unequal: list[JPath]
    b_only: list[JPath]

    def empty(self) -> bool:
        return not self.a_only and not self.unequal and not self.b_only

    @classmethod
    def diff_json(cls, a: dict, b: dict) -> JDiff:
        ao, unq, bo = JDiff._jval(a, b, JPath([]), JPath([]))
        return JDiff(ao, unq, bo)

    @staticmethod
    def _jval(
        a, b, apath: JPath, bpath: JPath
    ) -> tuple[list[JPath], list[JPath], list[JPath]]:
        if type(a) != type(b):
            return [], [apath], []
        if isinstance(a, dict):
            return JDiff._dict(a, b, apath, bpath)
        if isinstance(a, list):
            return JDiff._array(a, b, apath, bpath)
        if a != b:
            return [], [apath], []
        return [], [], []

    @staticmethod
    def _array(
        a: list, b: list, apath: JPath, bpath: JPath
    ) -> tuple[list[JPath], list[JPath], list[JPath]]:
        n = min(len(a), len(b))
        a_only = [apath + [f"{i}"] for i in range(n, len(a))]
        b_only = [bpath + [f"{i}"] for i in range(n, len(b))]
        unequal = []
        for i in range(n):
            ao, unq, bo = JDiff._jval(a[i], b[i], apath + [f"{i}"], bpath + [f"{i}"])
            a_only.extend(ao)
            unequal.extend(unq)
            b_only.extend(bo)
        return a_only, unequal, b_only

    @staticmethod
    def _dict(
        a: dict, b: dict, apath: JPath, bpath: JPath
    ) -> tuple[list[JPath], list[JPath], list[JPath]]:
        extra = a.pop("...", None)
        akeys, both, bkeys = JDiff._split_keys(a, b, apath, bpath)
        a_only = [apath + [key] for key in akeys]
        b_only = [bpath + [key] for key in bkeys]
        if extra is not None:
            a["..."] = extra
            b_only.clear()

        unequal = []
        for akey, bkey in both:
            ao, unq, bo = JDiff._jval(a[akey], b[bkey], apath + [akey], bpath + [bkey])
            a_only.extend(ao)
            unequal.extend(unq)
            b_only.extend(bo)
        return a_only, unequal, b_only

    @staticmethod
    def _split_keys(
        a: dict, b: dict, apath: JPath, bpath: JPath
    ) -> tuple[list[str], list[(str, str)], list[str]]:
        """Split the keys of objects a and b into three lists.

        The first list contains keys only occurring in object a,
        the third list contains keys only occurring in object b.
        The middle list contains a tuple of keys for a and b which
        should be checked for equal values.

        Note that the keys in the middle list may differ for a and
        b for properties where the keys are of JSCalendar type Id."""
        prop_keys = {
            "alerts": lambda v: v.get("trigger", {}).get(
                "offset", v.get("trigger", {}).get("when")
            ),
            "links": lambda v: v.get("href"),
            "locations": lambda v: v.get("name"),
            "virtualLocations": lambda v: v.get("uri"),
            "participants": lambda v: v.get("scheduleId"),
        }
        pkey = prop_keys.get(apath[-1]) if len(apath) and len(bpath) else None
        if pkey and apath[-1] == bpath[-1]:
            apkeys = {
                pkey(v): k for k, v in a.items() if isinstance(v, dict) and pkey(v)
            }
            bpkeys = {
                pkey(v): k for k, v in b.items() if isinstance(v, dict) and pkey(v)
            }
            both = [(apkeys[p], bpkeys[p]) for p in set(apkeys) & set(bpkeys)]
            akeys = set(a) - set(k[0] for k in both)
            bkeys = set(b) - set(k[1] for k in both)
        else:
            akeys = list(set(a) - set(b))
            both = [(key, key) for key in set(a) & set(b)]
            bkeys = list(set(b) - set(a))
        return akeys, both, bkeys

    @staticmethod
    def _normalize(data):
        # Traverse lists
        if isinstance(data, list):
            for v in data:
                JDiff._normalize(v)
            return

        # Ignore basic types
        if not isinstance(data, dict):
            return

        typ = data.get("@type")
        # Special-case recurrence rules
        if typ == "RecurrenceRule":
            for k in (
                "byMonthDay",
                "byMonth",
                "byYearDay",
                "byWeekNo",
                "byHour",
                "byMinute",
                "bySecond",
                "bySetPosition",
            ):
                vals = data.get(k)
                if k == "byDay":
                    cmp = lambda x: (x.get("day"), x.get("nthOfPeriod", 0))
                else:
                    cmp = None
                try:
                    data[k] = sorted(vals, key=cmp)
                except (AttributeError, TypeError):
                    pass
        # Do not normalize localizations and recurrence overrides
        localizations = data.pop("localizations", None)
        recurrence_overrides = data.pop("recurrenceOverrides", None)
        # Remove default and optional null values
        common_default_values = {
            "alerts": None,  # null value
            "categories": None,  # null value
            "description": "",
            "descriptionContentType": "text/plain",
            "duration": "PT0S",
            "excluded": False,
            "freeBusyStatus": "busy",
            "keywords": None,  # null value
            "links": None,  # null value
            "locations": None,  # null value
            "participants": None,  # null value
            "priority": 0,
            "privacy": "public",
            "recurrenceIdTimeZone": None,
            "recurrenceOverrides": None,  # null value
            "recurrenceRules": None,  # null value
            "relatedTo": None,  # null value
            "sequence": 0,
            "showWithoutTime": False,
            "status": "confirmed",
            "timeZone": None,
            "timeZones": None,  # null value
            "title": "",
            "useDefaultAlerts": False,
            "virtualLocations": None,  # null value
        }
        default_values = {
            "Alert": {
                "action": "display",
            },
            "Event": common_default_values
            | {
                "duration": "PT0S",
                "status": "confirmed",
            },
            "OffsetTrigger": {
                "relativeTo": "start",
            },
            "Participant": {
                "expectReply": False,
                "participationStatus": "needs-action",
                "scheduleAgent": "server",
                "scheduleForceSend": False,
                "scheduleSequence": 0,
            },
            "RecurrenceRule": {
                "interval": 1,
                "rscale": "gregorian",
                "skip": "omit",
                "firstDayOfWeek": "mo",
            },
            "Relation": {
                "relation": {},
            },
            "Task": common_default_values,
            "VirtualLocation": {"name": ""},
        }
        for k, v in default_values.get(typ, {}).items():
            if k in data and data[k] == v:
                del data[k]

        # Normalize subobjects
        for v in data.values():
            JDiff._normalize(v)

        # Add back localizations and recurrenceOverrides
        if localizations is not None:
            data["localizations"] = localizations
        if recurrence_overrides is not None:
            data["recurrenceOverrides"] = recurrence_overrides

    @staticmethod
    def normalize_json(data: dict) -> dict:
        data = copy.deepcopy(data)
        JDiff._normalize(data)
        return data


@dataclass
class JObject:
    data: dict

    def __init__(self, data):
        self.data = data

    def __str__(self):
        return json.dumps(self.data, sort_keys=True, indent=2)

    def to_group(self) -> JObject:
        data = copy.deepcopy(self.data)
        default_parent = {
            "AbsoluteTrigger": lambda d: {"@type": "Alert", "trigger": d},
            "Alert": lambda d: {"@type": "Event", "alerts": {"1": d}},
            "Event": lambda d: {"@type": "Group", "entries": [d]},
            "Group": None,
            "Link": lambda d: {"@type": "Event", "links": {"1": d}},
            "Location": lambda d: {"@type": "Event", "locations": {"1": d}},
            "OffsetTrigger": lambda d: {"@type": "Alert", "trigger": d},
            "Participant": lambda d: {"@type": "Event", "participants": {"1": d}},
            "RecurrenceRule": lambda d: {"@type": "Event", "recurrenceRules": [d]},
            "Task": lambda d: {"@type": "Group", "entries": [d]},
            "TimeZone": lambda d: {"@type": "Event", "timeZones": {"/1": d}},
            "VirtualLocation": lambda d: {
                "@type": "Event",
                "virtualLocations": {"1": d},
            },
        }
        while parent := default_parent.get(data["@type"]):
            data = parent(data)
        return JObject(data)

    def to_json(self) -> dict:
        return copy.deepcopy(self.data)

    def diff_json(self, data: dict) -> JDiff:
        return JDiff.diff_json(self.data, data)

    @classmethod
    def parse(cls, s: str, default_type="Event") -> JObject:
        s = s.strip()
        if s[0] != "{":
            s = "{" + s + ',"...": ""' + "}"
        try:
            data = json.loads(s)
        except json.JSONDecodeError as e:
            raise ParseError(f"JSON: {e}") from e
        if not "@type" in data:
            data["@type"] = default_type
        return JObject(data)
