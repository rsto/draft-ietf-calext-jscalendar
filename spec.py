import yaml
import os
import pprint

from collections import defaultdict

from jinja2 import Environment, FileSystemLoader


def jsnoconv(spec):
    allprops = defaultdict(set)
    for prop_name, prop in spec["jscalendar"]["properties"].items():
        if prop_name == "@type":
            continue
        for obj_name in prop["objects"]:
            allprops[obj_name].add(prop_name)

    convprops = defaultdict(set)
    for comp_name, comp in spec["icalendar"]["components"].items():
        if "convert" in comp:
            for prop_name, prop in comp["properties"].items():
                if "convert" in prop:
                    convprops[comp["convert"]["object"]].add(
                        prop["convert"]["property"]
                    )
                    for param_name, param in spec["icalendar"]["properties"][prop_name][
                        "parameters"
                    ].items():
                        if "convert" in param:
                            if "object" in param["convert"]:
                                convprops[param["convert"]["object"]].add(
                                    param["convert"]["property"]
                                )
                            else:
                                convprops[comp["convert"]["object"]].add(
                                    param["convert"]["property"]
                                )
            if "components" in comp:
                for subcomp_name, subcomp in comp["components"].items():
                    if "convert" in subcomp:
                        convprops[comp["convert"]["object"]].add(
                            subcomp["convert"]["property"]
                        )

    for obj_name, obj_props in allprops.items():
        if not obj_name in convprops:
            print(f"Uncovered object: {obj_name}")
        else:
            diff = obj_props - convprops[obj_name]
            print(f"{obj_name}: {diff}")


def load(fname="spec.yaml"):
    with open(fname, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    spec = load()
    env = Environment(loader=FileSystemLoader("xmlsrc"))

    # template = env.get_template("inconvertible.xml")
    # print(template.render({"spec": spec}))

    jsnoconv(spec)


if __name__ == "__main__":
    main()
