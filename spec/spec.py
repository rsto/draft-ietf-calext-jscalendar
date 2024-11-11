import yaml
import os
import pprint

from collections import defaultdict

from jinja2 import Environment, FileSystemLoader


def load(fname="spec.yaml"):
    with open(fname, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def inconvprops(s):
    props = []
    for prop_name, prop in s["icalendar"]["properties"].items():
        prop["name"] = prop_name
        params = []
        for param_name, param in prop["parameters"].items():
            if not "convert" in param:
                param = s["icalendar"]["parameters"][param_name]
                param["name"] = param_name
                params.append(param)
        if len(params) > 0:
            prop["parameters"] = params
            props.append(prop)
    props.sort(key=lambda p: p["name"])
    return props


def main():
    spec = load()
    env = Environment(loader=FileSystemLoader("xmlsrc"))
    template = env.get_template("inconvertible.xml")
    #pprint.pp(inconvprops(spec))
    print(template.render({"spec": spec, "props": inconvprops(spec) }))


if __name__ == "__main__":
    main()
