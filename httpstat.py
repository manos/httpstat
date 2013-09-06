#!/usr/bin/env python
"""
httpstat [options] url [delay [count]]

    The delay/count options work just like vmstat or iostat.

Example:
    Fetch google.com once and exit:
    httpstat http://google.com 1 1

    Continually fetch google.com pausing for 2 seconds in-between:
    httpstat http://google.com 2

    Fetch google.com 10 times, waiting 2 seconds each interval:
    httpstat http://google.com 2 10

Output:
    After following any redirects, will output the following, over the
    last 500 datapoints (in seconds):

domain  status last min max avg stddev net_time

domain:   the domain requested, and external resources if -a is used.
status:   HTTP response code
last:     the last datapoint (response time to fetch the whole document)
min:      the fastest time
max:      the slowest time
avg:      the average response time
stddev:   standard deviation
net_time: network connect time (a HEAD request)

NOTE: if you use -e, and a small delay, all the requests probably will not
finish within the allotted time. It will still delay the requested amount,
but the output will not come every [delay] seconds.

NOTE: the first request will always take longer (hint: DNS).

"""

# standard libraries
import sys
import time
import logging
from optparse import OptionParser
from urlparse import urlparse

# other libraries (pip installable)
import requests
import numpy


def fetch_url(url, timeout=5, method='GET', keepalive=False):
    """
    Returns a requests-lib response object, for the requested URL.
    Timeout (per-try) units are seconds.
    """

    # add User-Agent header, to identify ourselves, to not confuse analysis tools
    headers = {'User-Agent': 'httpstat monitor', }

    # configure requests to close the HTTP connection each time:
    if not keepalive:
        s = requests.session()
        s.keep_alive = keepalive

    error = None
    resp = None

    if 'HEAD' in method:
        resp = requests.head(url, timeout=timeout)
    elif 'GET' in method:
        resp = requests.get(url, timeout=timeout)
    else:
        raise Exception("unrecognized HTTP method")

    return resp


def parse_html(html, domain):
    """ FUTURE WORK
    Parses html and returns all URLs of external resources, i.e. those not
    matching the 'domain' argument. For example, any
    <script src=...> (or img tag) that's not in the same domain.
    Format:
    { 'domain': [link1, link2, ...] }
    """
    pass


def td_secs(obj):
    """
    Given a datatime.timedelta object, return seconds as a float, including
    milliseconds.
    """
    return obj.seconds + obj.microseconds / 1E6


def format_floats(array, precision=4):
    """
    Takes an array of floats, and returns an array of strings, formatted
    using the supplied precision.
    """
    format_string = "{0:.%sf}" % precision
    return [format_string.format(val) for val in array]


def main():
    parser = OptionParser(usage=__doc__)
    parser.add_option("-d", "--debug", default=None, action="store_true",
                      help="enable debug output")
    parser.add_option("-e", "--external", default=None, action="store_true",
                      help="also fetch externally loaded resources, and report"
                           " their times")
    parser.add_option("-k", "--keepalive", default=False, action="store_true",
                      help="enable HTTP keepalive")
    parser.add_option("-n", "--num-datapoints", default=500,
                      help="number of data points to keep in memory")
    (options, args) = parser.parse_args()

    if options.debug:
        log_level = logging.DEBUG
    else:
        log_level = None

    logging.basicConfig(stream=sys.stdout, level=log_level)
    logging.basicConfig(stream=sys.stderr,
                        level=(logging.ERROR, logging.CRITICAL))

    # bail if we weren't given arguments.
    if len(args) < 1:
        logging.critical("Must supply at least the url argument. See --help.")
        sys.exit(1)

    url = args[0]
    delay = 1
    count = None

    # emulate iostat/vmstat argument behavior:
    if len(args) == 1:
        count = 1
    elif len(args) == 2:
        delay = float(args[1])
    elif len(args) == 3:
        delay = float(args[1])
        count = int(args[2])

    # set up a dict to hold timing information, per-domain:
    domain = urlparse(url).netloc
    stats = {domain:
             {'head': [],
              'get': []
              }
             }

    iterations = 0
    template = "{0:15} {1:7} {2:7} {3:7} {4:7} {5:7} {6:7} {7:7}"
    print template.format("domain", "status", "last", "min", "max", "avg", "stddev", "net time")

    while count is None or iterations < count:
        if iterations >= 1:  # don't sleep the first time
            time.sleep(delay)

        try:
            # TODO: find a way to get the network time without sending a separate HEAD
            # request every time.. (use a different lib for fetching URLs?).
            head_resp = fetch_url(url, method='HEAD', keepalive=options.keepalive)
            get_resp = fetch_url(url, method='GET', keepalive=options.keepalive)

        # all exceptions in 'requests' are a subclass of RequestException
        except requests.exceptions.RequestException, err:
            logging.error(err)
            iterations += 1
            continue

        # only keep options.num_datapoints, to preserve memory (so people can
        # run it forever, if needed), by shifting the array left: losing the
        # oldest data point. Assume python does this in constant time.
        if len(stats[domain]['head']) >= options.num_datapoints:
            stats[domain]['head'] = stats[domain]['head'][1:] + [td_secs(head_resp.elapsed)]
            stats[domain]['get'] = stats[domain]['get'][1:] + [td_secs(get_resp.elapsed)]
        else:
            stats[domain]['head'].append(td_secs(head_resp.elapsed))
            stats[domain]['get'].append(td_secs(get_resp.elapsed))

        # domain status last min max avg stddev net_time
        page_array = stats[domain]['get']

        data = [domain, str(get_resp.status_code)] + format_floats([page_array[-1],
                                                         min(page_array), max(page_array),
                                                         numpy.mean(page_array),
                                                         numpy.std(page_array),
                                                         stats[domain]['head'][-1]
                                                         ])

        print template.format(*data)

        # are we analyzing externally loading content?
        if options.external:
            logging.error("sorry, --external resource monitoring is not yet implemented."
                          "(but it's a cool idea, right?)")
            sys.exit(1)
            # external_urls = parse_html(get_resp.body, domain)

        iterations += 1

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print
        sys.exit(0)
