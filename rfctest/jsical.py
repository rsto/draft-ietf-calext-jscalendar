from __future__ import annotations

import collections
import copy
import itertools
import json
import re
import uuid


from collections import UserList
from dataclasses import dataclass, field
from operator import itemgetter


class ParseError(ValueError):
    pass


@dataclass
class Parameter:
    name: str
    value: str

    def __str__(self):
        return f"{self.name}={self.value}"

    def normalize(self):
        self.name = self.name.upper()

    @staticmethod
    def _key(param):
        return (param.name, param.value)


@dataclass
class Property:
    name: str
    value: str
    params: list[Parameter] = field(default_factory=list)

    def __str__(self):
        params = "".join(f";{p}" for p in self.params)
        return f"{self.name}{params}:{self.value}"

    @staticmethod
    def _key(prop):
        return (prop.name, prop.value, [Parameter._key(param) for param in prop.params])

    def normalize(self):
        self.name = self.name.upper()
        for param in self.params:
            param.normalize()
        self.params.sort(key=Parameter._key)

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
class Component:
    name: str
    props: list[Property] = field(default_factory=list)
    comps: list[Component] = field(default_factory=list)
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

    @staticmethod
    def _key(comp):
        uids = list(filter(lambda prop: prop.name == "UID", comp.props))
        return (comp.name, uids[0].name if uids else "")

    def normalize(self):
        self.name = self.name.upper()
        for prop in self.props:
            prop.normalize()
        self.props.sort(key=Property._key)
        for comp in self.comps:
            comp.normalize()
        self.comps.sort(key=Component._key)

    def with_default_props(self) -> Component:
        vobj = copy.deepcopy(self)
        if vobj.name == "VCALENDAR" and not vobj.comps:
            vobj.comps.append(Component("VEVENT"))
        comps = [vobj]
        while comps:
            comp = comps.pop()
            comps.extend(comp.comps)
            have_props = set(prop.name.upper() for prop in comp.props)

            def add_default(prop):
                if not prop.name in have_props:
                    comp.props.append(prop)

            if comp.name == "VCALENDAR":
                add_default(Property("PRODID", "-//FOO//bar//EN"))
                add_default(Property("VERSION", "2.0"))
            elif comp.name == "VEVENT" or comp.name == "VTODO":
                add_default(Property("DTSTAMP", "20060102T030405Z"))
                add_default(Property("UID", f"{uuid.uuid4()}"))
                if comp.name == "VEVENT":
                    add_default(Property("DTSTART", "20060102T030405Z"))
                if "ATTENDEE" in have_props:
                    add_default(
                        Property("ORGANIZER", f"mailto:{uuid.uuid4()}@example.com")
                    )
                elif "ORGANIZER" in have_props:
                    add_default(
                        Property("ATTENDEE", f"mailto:{uuid.uuid4()}@example.com")
                    )
            elif comp.name == "DAYLIGHT" or comp.name == "STANDARD":
                add_default(Property("TZOFFSETFROM", "-0400"))
                add_default(Property("TZOFFSETTO", "-0300"))
                add_default(Property("DTSTART", "20010503T000000"))
            elif comp.name == "PARTICIPANT":
                add_default(Property("UID", f"{uuid.uuid4()}"))
            elif comp.name == "VTIMEZONE":
                add_default(Property("TZID", f"{uuid.uuid4()}"))

        return vobj

    def to_vcalendar(self) -> Component:
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
            parent = Component(parent_name, allow_any=True)
            parent.comps.append(vobj)
            vobj = parent
        if vobj.name != "VCALENDAR":
            vobj = Component("VCALENDAR", comps=[vobj])
        return vobj

    @classmethod
    def parse(cls, s: str, strict=False) -> Component:
        # Unfold and split lines
        lines = re.split(r"\r?\n", re.sub(r"\r?\n([ ]|\t)", "", s))
        # Parse example
        stack = [Component(None)]
        comp = stack[0]
        for line in map(str.strip, lines):
            if not line:
                continue
            if line == "...":
                if strict:
                    raise ParseError(f"Line '...' not allowed in strict mode")
                comp.allow_any = True
                continue
            prop = Property.parse(line)
            if prop.name == "BEGIN":
                comp.comps.append(Component(prop.value))
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
        elif strict and not comp.name:
            raise ParseError(f"No iCalendar object found")
        else:
            if not comp.comps:
                comp.allow_any = True
            comp.name = "VEVENT"
        return comp


@dataclass
class PropertyDiff:
    del_param_a: list[int]
    add_param_b: list[int]
    diff_params: list[tuple[int, int]]
    set_value_b: bool

    def __init__(self, a: Property, b: Property):
        self.set_value_b = a.value != b.value

        a_params = collections.defaultdict(list)
        for p in enumerate(a.params):
            a_params[p[1].name].append(p)
        a_params.pop("JSID", None)

        b_params = collections.defaultdict(list)
        for p in enumerate(b.params):
            b_params[p[1].name].append(p)
        b_params.pop("JSID", None)

        def _aonly(a, b):
            l = []
            for k in set(a.keys()) - set(b.keys()):
                l.extend([t[0] for t in a[k]])
            return l

        self.del_param_a = _aonly(a_params, b_params)
        self.add_param_b = _aonly(b_params, a_params)

        self.diff_params = []
        for name in set(a_params.keys()) & set(b_params.keys()):
            for (idx_a, param_a), (idx_b, param_b) in zip(
                a_params[name], b_params[name]
            ):
                if param_a.value != param_b.value:
                    self.diff_params.append((idx_a, idx_b))
            len_a = len(a_params[name])
            len_b = len(b_params[name])
            if len_a > len_b:
                self.del_param_a.extend(
                    idx for (idx, param) in a_params[name][len_a - len_b :]
                )
            elif len_b > len_a:
                self.add_param_b.extend(
                    idx for (idx, param) in b_params[name][len_b - len_a :]
                )

        self.del_param_a.sort()
        self.add_param_b.sort()
        self.diff_params.sort()

    def empty(self) -> bool:
        return (
            not self.del_param_a
            and not self.add_param_b
            and not self.diff_params
            and not self.set_value_b
        )


@dataclass
class ComponentDiff:
    del_comp_a: list[int]
    del_prop_a: list[int]

    diff_comps: list[tuple[int, int, ComponentDiff]]
    diff_props: list[tuple[int, int]]

    add_comp_b: list[int]
    add_prop_b: list[int]

    def __init__(self, a: Component, b: Component):
        a = copy.deepcopy(a)
        a.normalize()

        b = copy.deepcopy(b)
        b.normalize()

        a_props = collections.defaultdict(list)
        for p in enumerate(a.props):
            a_props[p[1].name].append(p)
        a_props.pop("JSID", None)

        b_props = collections.defaultdict(list)
        for p in enumerate(b.props):
            b_props[p[1].name].append(p)
        b_props.pop("JSID", None)

        a_comps = collections.defaultdict(list)
        for p in enumerate(a.comps):
            a_comps[p[1].name].append(p)

        b_comps = collections.defaultdict(list)
        for p in enumerate(b.comps):
            b_comps[p[1].name].append(p)

        def _aonly(a, b):
            l = []
            for k in set(a.keys()) - set(b.keys()):
                l.extend([t[0] for t in a[k]])
            return l

        self.del_prop_a = _aonly(a_props, b_props)
        self.del_comp_a = _aonly(a_comps, b_comps)
        if not a.allow_any:
            self.add_prop_b = _aonly(b_props, a_props)
            self.add_comp_b = _aonly(b_comps, a_comps)
        else:
            self.add_prop_b = []
            self.add_comp_b = []

        self.diff_comps = []
        for name in set(a_comps.keys()) & set(b_comps.keys()):
            for (idx_a, comp_a), (idx_b, comp_b) in zip(a_comps[name], b_comps[name]):
                diff = ComponentDiff(comp_a, comp_b)
                if not diff.empty():
                    self.diff_comps.append((idx_a, idx_b, diff))
            len_a = len(a_comps[name])
            len_b = len(b_comps[name])
            if len_a > len_b:
                self.del_comp_a.extend(
                    idx for (idx, comp) in a_comps[name][len_a - len_b :]
                )
            elif len_b > len_a:
                self.add_comp_b.extend(
                    idx for (idx, comp) in b_comps[name][len_b - len_a :]
                )

        self.diff_props = []
        for name in set(a_props.keys()) & set(b_props.keys()):
            for (idx_a, prop_a), (idx_b, prop_b) in zip(a_props[name], b_props[name]):
                diff = PropertyDiff(prop_a, prop_b)
                if not diff.empty():
                    self.diff_props.append((idx_a, idx_b, diff))
            len_a = len(a_props[name])
            len_b = len(b_props[name])
            if len_a > len_b:
                self.del_prop_a.extend(
                    idx for (idx, prop) in a_props[name][len_a - len_b :]
                )
            elif len_b > len_a:
                self.add_prop_b.extend(
                    idx for (idx, prop) in b_props[name][len_b - len_a :]
                )

        self.del_prop_a.sort()
        self.del_comp_a.sort()
        self.add_prop_b.sort()
        self.add_comp_b.sort()
        self.diff_comps.sort(key=lambda v: (v[0], v[1]))
        self.diff_props.sort(key=lambda v: (v[0], v[1]))

    def empty(self) -> bool:
        return (
            not self.del_comp_a
            and not self.del_prop_a
            and not self.add_comp_b
            and not self.add_comp_b
            and not self.diff_comps
            and not self.diff_props
        )


class JsonPath(UserList):
    def __init__(self, data):
        super().__init__(data)

    @classmethod
    def decode(cls, s: str) -> JsonPath:
        return JsonPath(
            list(s.replace("~1", "/").replace("~0", "~") for s in s.split("/"))
        )

    def encode(self) -> str:
        return "/".join(s.replace("~", "~0").replace("/", "~1") for s in self.data)


@dataclass
class JsonDiff:
    missing: list[JsonPath]
    notequal: list[tuple[JsonPath]]
    unexpected: list[JsonPath]

    def empty(self) -> bool:
        return not self.missing and not self.notequal and not self.unexpected

    @classmethod
    def diff_json(cls, a: dict, b: dict) -> JsonDiff:
        missing, notequal, unexpected = JsonDiff._diff_jval(
            a, b, JsonPath([]), JsonPath([])
        )
        return JsonDiff(missing, notequal, unexpected)

    @staticmethod
    def _diff_jval(
        a, b, apath: JsonPath, bpath: JsonPath
    ) -> tuple[list[JsonPath], list[JsonPath], list[JsonPath]]:
        if type(a) != type(b):
            return [], [(apath, bpath)], []
        if isinstance(a, dict):
            return JsonDiff._diff_dict(a, b, apath, bpath)
        if isinstance(a, list):
            return JsonDiff._diff_array(a, b, apath, bpath)
        if a != b:
            return [], [(apath, bpath)], []
        return [], [], []

    @staticmethod
    def _diff_array(
        a: list, b: list, apath: JsonPath, bpath: JsonPath
    ) -> tuple[list[JsonPath], list[JsonPath], list[JsonPath]]:
        n = min(len(a), len(b))
        missing = [apath + [f"{i}"] for i in range(n, len(a))]
        unexpected = [bpath + [f"{i}"] for i in range(n, len(b))]
        notequal = []
        for i in range(n):
            miss, neq, unex = JsonDiff._diff_jval(
                a[i], b[i], apath + [f"{i}"], bpath + [f"{i}"]
            )
            missing.extend(miss)
            notequal.extend(neq)
            unexpected.extend(unex)
        return missing, notequal, unexpected

    @staticmethod
    def _diff_dict(
        a: dict, b: dict, apath: JsonPath, bpath: JsonPath
    ) -> tuple[list[JsonPath], list[JsonPath], list[JsonPath]]:
        extra = a.pop("...", None)
        akeys, both, bkeys = JsonDiff._split_keys(a, b, apath, bpath)
        missing = [apath + [key] for key in akeys]
        unexpected = [bpath + [key] for key in bkeys]
        if extra is not None:
            a["..."] = extra
            unexpected.clear()

        notequal = []
        for akey, bkey in both:
            miss, neq, unex = JsonDiff._diff_jval(
                a[akey], b[bkey], apath + [akey], bpath + [bkey]
            )
            missing.extend(miss)
            notequal.extend(neq)
            unexpected.extend(unex)
        return missing, notequal, unexpected

    @staticmethod
    def _split_keys(
        a: dict, b: dict, apath: JsonPath, bpath: JsonPath
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
            "participants": lambda v: v.get("calendarAddress"),
        }
        pkey = prop_keys.get(apath[-1]) if len(apath) and len(bpath) else None
        if pkey and apath[-1] == bpath[-1]:
            if len(a) == 1 and len(b) == 1:
                return [], [(list(a)[0], list(b)[0])], []
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
                JsonDiff._normalize(v)
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
        elif typ == "ICalComponent":
            ical_props = data.get("properties")
            if ical_props:
                # Sort jCal properties by name, value, value type
                ical_props.sort(key=itemgetter(0, 3, 2))
            ical_comps = data.get("components")
            if ical_comps:
                # Sort jCal components by name
                ical_comps.sort(key=itemgetter(0))
        elif typ == "Group":
            entries = data.get("entries")
            if isinstance(entries, list):
                pass
                entries.sort(key=lambda e: (e.get("uid"), e.get("start")))

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
            "timeZone": None,  # null value
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
            JsonDiff._normalize(v)

        # Add back localizations and recurrenceOverrides
        if localizations is not None:
            data["localizations"] = localizations
        if recurrence_overrides is not None:
            data["recurrenceOverrides"] = recurrence_overrides

    @staticmethod
    def normalize_json(data: dict) -> dict:
        data = copy.deepcopy(data)
        JsonDiff._normalize(data)
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
            data = {"...": ""} | parent(data)
        return JObject(data)

    def to_json(self) -> dict:
        return copy.deepcopy(self.data)

    def diff_json(self, data: dict) -> JsonDiff:
        return JsonDiff.diff_json(self.data, data)

    def normalized(self) -> JObject:
        return JObject(JsonDiff.normalize_json(self.data))

    def with_default_props(self) -> JObject:
        def add_default_props(jval: dict):
            if isinstance(jval, list):
                for v in jval:
                    add_default_props(v)
            elif isinstance(jval, dict):
                if "@type" in jval and "..." in jval:
                    del jval["..."]
                    match jval.get("@type", None):
                        case "Event":
                            if not "uid" in jval:
                                jval["uid"] = f"{uuid.uuid4()}"
                            if not "updated" in jval:
                                jval["updated"] = "2006-01-02T03:04:05Z"
                            if not "start" in jval:
                                jval["start"] = "2006-01-02T03:04:05"
                        case "Group":
                            if not "entries" in jval:
                                jval["entries"] = [{"@type": "Event", "...": ""}]
                        case "Link":
                            if not "href" in jval:
                                jval["href"] = f"https://example.com/{uuid.uuid4()}"
                        case "Task":
                            if not "uid" in jval:
                                jval["uid"] = f"{uuid.uuid4()}"
                            if not "updated" in jval:
                                jval["updated"] = "2006-01-02T03:04:05Z"
                        # FIXME to be continued
                for v in jval.values():
                    add_default_props(v)

        data = copy.deepcopy(self.data)
        add_default_props(data)
        return JObject(data)

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
