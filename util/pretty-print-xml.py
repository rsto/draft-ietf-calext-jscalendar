from __future__ import annotations

import argparse
import json
import sys
from lxml import etree

RFC_FILE = "draft-ietf-calext-jscalendar-icalendar.xml"


def main():
    prog = "pretty-print-xml"

    parser = argparse.ArgumentParser(
        prog=prog,
        description="Pretty-print the XML RFC source",
    )
    parser.add_argument(
        "-f",
        "--file",
        default=RFC_FILE,
        help=f"load tests from this file (default: {RFC_FILE})",
    )
    args = parser.parse_args()

    # Parse XML file.
    parser = etree.XMLParser(strip_cdata=False)
    tree = etree.parse(args.file, parser=parser)

    # Pretty-print JSON examples.
    for figure in tree.getroot().findall(".//figure"):
        anchor = figure.get("anchor") or "<unknown>"

        for jcalcode in figure.findall("./sourcecode[@type='jscalendar']"):
            text = jcalcode.text.strip()
            has_root = text.startswith(("[", "{"))
            if not has_root:
                text = "{" + text + "}"
            try:
                text = json.dumps(json.loads(text), indent=2)
            except json.decoder.JSONDecodeError as e:
                print(f'invalid JSON in anchor "{anchor}"', file=sys.stderr)
                raise e
            if not has_root:
                text = "\n".join(line[2:] for line in text.splitlines()[1:-1])
            jcalcode.text = etree.CDATA("\n" + text + "\n")

    # Pretty-print XML tree.
    etree.indent(tree)
    print(
        """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE rfc [
<!ENTITY nbsp "&#160;">
<!ENTITY zwsp "&#8203;">
<!ENTITY nbhy "&#8209;">
<!ENTITY wj "&#8288;">
]>
<?xml-stylesheet type="text/xsl" href="rfc2629.xslt"?>
<?rfc toc="yes"?>
<?rfc tocompact="yes"?>
<?rfc tocdepth="4"?>
<?rfc compact="yes"?>
<?rfc subcompact="yes"?>
<?rfc sortrefs="yes"?>
<?rfc symrefs="yes"?>
<?rfc iprnotified="no"?>
""",
        end="",
    )
    etree.dump(tree.getroot())


if __name__ == "__main__":
    main()
