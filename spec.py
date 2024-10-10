import yaml
import os
from collections import defaultdict

from jinja2 import Environment, FileSystemLoader


def load(fname="spec.yaml"):
    with open(fname, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def prop_stats(spec):
    converted = set()
    covered = set()
    for comp_name, comp in spec["icalendar"]["components"].items():
        for prop_name, prop in comp["properties"].items():
            covered.add(prop_name)
            if "convert" in prop:
                converted.add(prop_name)
    all = set(prop_name for prop_name in spec["icalendar"]["properties"])
    return {"all": all, "converted": converted, "covered": covered}


def conv_props(spec):
    conv = defaultdict(lambda: defaultdict(lambda: { "comps": set(), "object": None }))
    for comp_name, comp in spec["icalendar"]["components"].items():
        for prop_name, prop in comp["properties"].items():
            if "convert" in prop:
                conv[prop_name][prop["convert"]["property"]]["comps"].add(comp_name)
                if "object" in prop["convert"]:
                    conv[prop_name][prop["convert"]["property"]]["object"] = prop["convert"]["object"]
            else:
                conv[prop_name]
    return conv


def main():
    spec = load()
    env = Environment(loader=FileSystemLoader("xmlsrc"))
    template = env.get_template("main.xml")
    print(template.render({"spec": spec, "conv_props": conv_props(spec)}))


if __name__ == "__main__":
    main()
