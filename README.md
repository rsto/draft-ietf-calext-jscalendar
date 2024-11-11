# draft-ietf-calext-jscalendar

This repository contains the draft version of the [draft-ietf-calext-jscalendar-icalendar](https://datatracker.ietf.org/doc/draft-ietf-calext-jscalendar-icalendar/) IETF internet standard.

## rfctest

The rfctest directory contains a tool to extract and run tests from the XML document.

### Requirements

rfctest has been written for Python version 3.12. According to pylint, it should also work with version 3.8. It has no dependencies other than the Python standard library.

### Running

Run the rfctest module using its default configuration as:

    $ python -m rfctest

This expects the following environment variables:

- `RFCTEST_BACKEND_URL` (mandatory): a HTTP URL of the backend that converts JSCalendar and iCalendar.  Alternatively, use the `--url` argument.
- `RFCTEST_BACKEND_AUTH` (optional): user name and password for HTTP Basic authentication, in the form `<username>:<password>`.  Alternatively use the `--auth` argument.

It reads tests from the file `draft-ietf-calext-jscalendar-icalendar.xml` and writes its test report to `report.html`.  Use the `--help` argument to learn how to run with different configurations.

### Backend

The HTTP backend must accept POST requests at the given URL.

For iCalendar to JSCalendar conversion, the request will contain the `Content-Type` header with value `text/calendar;charset=utf-8` and the iCalendar data in the body.

For JSCalendar to iCalendar conversion, the request will contain the `Content-Type` header with value `application/jscalendar+json;type=group` and the JSCalendar data in the body.
