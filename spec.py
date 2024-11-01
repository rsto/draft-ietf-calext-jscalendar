import yaml
import os
import pprint

from collections import defaultdict

from jinja2 import Environment, FileSystemLoader


def load(fname="spec.yaml"):
    with open(fname, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    spec = load()
    env = Environment(loader=FileSystemLoader("xmlsrc"))
    template = env.get_template("inconvertible.xml")
    print(template.render({"spec": spec }))


if __name__ == "__main__":
    main()
