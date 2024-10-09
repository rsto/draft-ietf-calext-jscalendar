import yaml
import os
from collections import UserDict

from jinja2 import Environment, FileSystemLoader


def load(fname="spec.yaml"):
    with open(fname, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def convertible_comp_elems(comp):
    elems = []
    for name, prop in comp.get("properties").items():
        if prop and prop.get("convert"):
            elems.append(
                {
                    "kind": "Property",
                    "name": name,
                    "prop": prop.get("convert").get("property"),
                    "note": prop.get("convert").get("note", ""),
                }
            )
    if comp.get("components"):
        for name, subcomp in comp.get("components").items():
            if subcomp and subcomp.get("convert"):
                elems.append(
                    {
                        "kind": "Component",
                        "name": name,
                        "prop": subcomp.get("convert").get("property"),
                        "note": subcomp.get("convert").get("note", ""),
                    }
                )
    return elems


def inconvertible_props(comp):
    return [
        name
        for name, prop in comp.get("properties").items()
        if not prop or not prop.get("convert")
    ]


def main():
    spec = load()

    env = Environment(loader=FileSystemLoader("xmlsrc"))
    env.globals["inconvertible_props"] = inconvertible_props
    env.globals["convertible_comp_elems"] = convertible_comp_elems

    template = env.get_template("main.xml")
    print(template.render(spec))


if __name__ == "__main__":
    main()
