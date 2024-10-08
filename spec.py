import yaml
import os
from collections import UserDict

from jinja2 import Environment, FileSystemLoader


def load(fname="spec.yaml"):
    with open(fname, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


env = Environment(loader=FileSystemLoader("xmlsrc"))
template = env.get_template("main.xml")
with open('draft-ietf-calext-jscalendar.xml', 'w') as f:
    print(template.render(), file=f)
