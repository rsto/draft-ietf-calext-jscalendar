import yaml
import os
from collections import UserDict

from jinja2 import Environment, FileSystemLoader


def load(fname="spec.yaml"):
    with open(fname, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def prop_stats(spec):
    converted = set()
    covered = set()
    for comp in spec["icalendar"]["components"].values():
        for prop_name, prop in comp["properties"].items():
            covered.add(prop_name)
            if "convert" in prop:
                converted.add(prop_name)
    all = set(prop_name for prop_name in spec["icalendar"]["properties"])
    return { "all": all, "converted": converted, "covered": covered }


def main():
    spec = load()
    env = Environment(loader=FileSystemLoader("xmlsrc"))
    template = env.get_template("main.xml")
    print(template.render(spec))


if __name__ == "__main__":
    main()
