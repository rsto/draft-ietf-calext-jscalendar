import yaml
import os
import pprint

from collections import defaultdict

from jinja2 import Environment, FileSystemLoader


def objprops(spec, objs):
    props = list()
    for prop_name, prop in spec["jscalendar"]["properties"].items():
        if prop_name == "@type":
            continue
        prop_objs = set(prop["objects"])
        if not objs <= prop_objs:
            continue
        prop["name"] = prop_name
        props.append(prop)
    return props


def load(fname="spec.yaml"):
    with open(fname, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    spec = load()
    env = Environment(loader=FileSystemLoader("xmlsrc"))
    template = env.get_template("js2ical.xml")
    sections = [
        {
            "title": "Event and Task",
            "anchor": "convert-jscalendar-event-and-task",
            "objects": ["Event", "Task"],
        },
        {
            "title": "Event",
            "anchor": "convert-jscalendar-event",
            "objects": ["Event"],
        },
        {
            "title": "Task",
            "anchor": "convert-jscalendar-task",
            "objects": ["Task"],
        },
        {
            "title": "Group",
            "anchor": "convert-jscalendar-group",
            "objects": ["Group"],
        },
        {
            "title": "Alert",
            "anchor": "convert-jscalendar-alert",
            "objects": ["Alert"],
        },
        {
            "title": "OffsetTrigger",
            "anchor": "convert-jscalendar-offset-trigger",
            "objects": ["OffsetTrigger"],
        },
        {
            "title": "AbsoluteTrigger",
            "anchor": "convert-jscalendar-absolute-trigger",
            "objects": ["AbsoluteTrigger"],
        },
        {
            "title": "Link",
            "anchor": "convert-jscalendar-link",
            "objects": ["Link"],
        },
        {
            "title": "Location",
            "anchor": "convert-jscalendar-location",
            "objects": ["Location"],
        },
        {
            "title": "Participant",
            "anchor": "convert-jscalendar-participant",
            "objects": ["Participant"],
        },
        {
            "title": "TimeZone",
            "anchor": "convert-jscalendar-timezone",
            "objects": ["TimeZone"],
        },
        {
            "title": "TimeZoneRule",
            "anchor": "convert-jscalendar-timezonerule",
            "objects": ["TimeZoneRule"],
        },
        {
            "title": "VirtualLocation",
            "anchor": "convert-jscalendar-virtuallocation",
            "objects": ["VirtualLocation"],
        },
    ]
    for section in sections:
        print(
            template.render(
                {
                    "spec": spec,
                    "title": section["title"],
                    "anchor": section["anchor"],
                    "objprops": objprops(spec, set(section["objects"])),
                }
            )
        )


if __name__ == "__main__":
    main()
