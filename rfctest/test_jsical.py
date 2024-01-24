import unittest

from rfctest.jsical import Property, VObject, JObject, JDiff, JPath


class TestVObject(unittest.TestCase):
    def test_parse_prop(self):
        self.assertEqual(
            VObject.parse("UID:1"),
            VObject("VEVENT", props=[Property("UID", "1")], allow_any=True),
        )

    def test_parse_begin(self):
        self.assertEqual(
            VObject.parse("BEGIN:VEVENT\n" + "UID:1\n" + "..."),
            VObject("VEVENT", props=[Property("UID", "1")], allow_any=True),
        )
        self.assertEqual(
            VObject.parse("BEGIN:VEVENT\n" + "UID:1"),
            VObject("VEVENT", props=[Property("UID", "1")], allow_any=False),
        )
        self.assertEqual(
            VObject.parse("BEGIN:VEVENT\n" + "UID:1\n" + "END:VEVENT\n"),
            VObject("VEVENT", props=[Property("UID", "1")], allow_any=False),
        )

    def test_parse_subcomps(self):
        self.assertEqual(
            VObject.parse(
                "BEGIN:VCALENDAR\n"
                + "BEGIN:VEVENT\n"
                + "UID:1\n"
                + "...\n"
                + "END:VEVENT\n"
                + "BEGIN:VEVENT\n"
                + "UID:2\n"
                + "...\n"
                + "END:VEVENT\n"
            ),
            VObject(
                "VCALENDAR",
                comps=[
                    VObject("VEVENT", props=[Property("UID", "1")], allow_any=True),
                    VObject("VEVENT", props=[Property("UID", "2")], allow_any=True),
                ],
            ),
        )

    def test_parse_folded(self):
        self.assertEqual(
            VObject.parse("UI\n  D:1\n"),
            VObject("VEVENT", props=[Property("UID", "1")], allow_any=True),
        )
        self.assertEqual(
            VObject.parse("SUMMARY:hello\n   world\n"),
            VObject(
                "VEVENT", props=[Property("SUMMARY", "hello world")], allow_any=True
            ),
        )
        self.assertEqual(
            VObject.parse("SUMMARY:hello\n\t world\n"),
            VObject(
                "VEVENT", props=[Property("SUMMARY", "hello world")], allow_any=True
            ),
        )


class TestJObject(unittest.TestCase):
    def test_parse_prop(self):
        self.assertEqual(
            JObject.parse(
                """
                "uid": "1"
                """
            ),
            JObject({"@type": "Event", "uid": "1", "...": ""}),
        )

    def test_parse_twoprop(self):
        self.assertEqual(
            JObject.parse(
                """
                "uid": "1",
                "title": "test"
                """
            ),
            JObject({"@type": "Event", "uid": "1", "title": "test", "...": ""}),
        )

    def test_parse_type(self):
        self.assertEqual(
            JObject.parse(
                """
                "@type": "Task",
                "uid": "1"
                """
            ),
            JObject({"@type": "Task", "uid": "1", "...": ""}),
        )

    def test_parse_obj(self):
        self.assertEqual(
            JObject.parse(
                """
                {
                  "uid": "1"
                }
                """
            ),
            JObject({"@type": "Event", "uid": "1"}),
        )

    def test_parse_obj_type(self):
        self.assertEqual(
            JObject.parse(
                """
                {
                  "@type": "Task",
                  "uid": "1"
                }
                """
            ),
            JObject({"@type": "Task", "uid": "1"}),
        )

    def test_parse_obj_dots(self):
        self.assertEqual(
            JObject.parse(
                """
                {
                  "uid": "1",
                  "...": ""
                }
                """
            ),
            JObject({"@type": "Event", "uid": "1", "...": ""}),
        )

    def test_to_group(self):
        data = {"@type": "Event", "uid": "1"}
        self.assertEqual(
            JObject(data).to_group(), JObject({"@type": "Group", "entries": [data]})
        )


class TestDiffJson(unittest.TestCase):
    def test_trivial(self):
        self.assertEqual(JObject({}).diff_json({}), JDiff([], [], []))
        self.assertEqual(
            JObject({"a": 1}).diff_json({}), JDiff([JPath.decode("a")], [], [])
        )
        self.assertEqual(
            JObject({}).diff_json({"a": 1}), JDiff([], [], [JPath.decode("a")])
        )
        self.assertEqual(JObject({"a": 1}).diff_json({"a": 1}), JDiff([], [], []))
        self.assertEqual(
            JObject({"a": 1}).diff_json({"a": 2}), JDiff([], [JPath.decode("a")], [])
        )
        self.assertEqual(
            JObject({"a": 1}).diff_json({"b": 1}),
            JDiff([JPath.decode("a")], [], [JPath.decode("b")]),
        )

    def test_array(self):
        self.assertEqual(JObject({"a": []}).diff_json({"a": []}), JDiff([], [], []))
        self.assertEqual(JObject({"a": [1]}).diff_json({"a": [1]}), JDiff([], [], []))
        self.assertEqual(
            JObject({"a": [1]}).diff_json({"a": []}),
            JDiff([JPath.decode("a/0")], [], []),
        )
        self.assertEqual(
            JObject({"a": [1]}).diff_json({"a": [2]}),
            JDiff([], [JPath.decode("a/0")], []),
        )
        self.assertEqual(
            JObject({"a": []}).diff_json({"a": [1]}),
            JDiff([], [], [JPath.decode("a/0")]),
        )

    def test_obj(self):
        self.assertEqual(
            JObject({"a": {"b": 1}}).diff_json({"a": {}}),
            JDiff([JPath.decode("a/b")], [], []),
        )
        self.assertEqual(
            JObject({"a": {"b": 1}}).diff_json({"a": {"b": 2}}),
            JDiff([], [JPath.decode("a/b")], []),
        )
        self.assertEqual(
            JObject({"a": {}}).diff_json({"a": {"b": 1}}),
            JDiff([], [], [JPath.decode("a/b")]),
        )
        self.assertEqual(
            JObject({"a": 1}).diff_json({"a": {"b": 1}}),
            JDiff([], [JPath.decode("a")], []),
        )
        self.assertEqual(
            JObject({"a": {"b": 1, "c": 1}}).diff_json({"a": {"b": 1}}),
            JDiff([JPath.decode("a/c")], [], []),
        )

    def test_propkeys(self):
        self.assertEqual(
            JObject({"links": {"a": {"href": "http://x"}}}).diff_json(
                {"links": {"a": {"href": "http://x"}}},
            ),
            JDiff([], [], []),
        )
        self.assertEqual(
            JObject({"links": {"a": {"href": "http://x"}}}).diff_json(
                {"links": {"b": {"href": "http://x"}}},
            ),
            JDiff([], [], []),
        )
        self.assertEqual(
            JObject({"links": {"a": {"href": "http://a"}}}).diff_json(
                {"links": {"a": {"href": "http://b"}}},
            ),
            JDiff([JPath.decode("links/a")], [], [JPath.decode("links/a")]),
        )
        self.assertEqual(
            JObject({"links": {"a": {}}}).diff_json(
                {"links": {"a": {"href": "http://b"}}}
            ),
            JDiff([JPath.decode("links/a")], [], [JPath.decode("links/a")]),
        )
        self.assertEqual(
            JObject({"links": {"a": {"href": "http://a"}}}).diff_json(
                {"links": {"a": 1}},
            ),
            JDiff([JPath.decode("links/a")], [], [JPath.decode("links/a")]),
        )

    def test_extra(self):
        self.assertEqual(
            JObject({"a": 1, "b": 2, "...": ""}).diff_json({"a": 3, "c": 4}),
            JDiff([JPath.decode("b")], [JPath.decode("a")], []),
        )


class TestNormalizeJson(unittest.TestCase):
    def test_normalize_json_basic(self):
        self.assertEqual(
            JDiff.normalize_json(
                {"@type": "Event", "sequence": 0},
            ),
            {"@type": "Event"},
        )

    def test_normalize_json_nested(self):
        self.assertEqual(
            JDiff.normalize_json(
                {
                    "@type": "Group",
                    "entries": [
                        {
                            "@type": "Event",
                            "virtualLocations": {
                                "1": {"@type": "VirtualLocation", "name": ""}
                            },
                        }
                    ],
                }
            ),
            {
                "@type": "Group",
                "entries": [
                    {
                        "@type": "Event",
                        "virtualLocations": {"1": {"@type": "VirtualLocation"}},
                    }
                ],
            },
        )

    def test_normalize_json_null(self):
        self.assertEqual(
            JDiff.normalize_json(
                {"@type": "Event", "recurrenceIdTimeZone": None},
            ),
            {"@type": "Event"},
        )

    def test_normalize_json_rrule(self):
        self.assertEqual(
            JDiff.normalize_json(
                {"@type": "RecurrenceRule", "byMonthDay": [5, 1, 28, 3]}
            ),
            {"@type": "RecurrenceRule", "byMonthDay": [1, 3, 5, 28]},
        )
