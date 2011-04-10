# Copyright (C) 2007-2011 by the Free Software Foundation, Inc.
#
# This file is part of GNU Mailman.
#
# GNU Mailman is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# GNU Mailman is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# GNU Mailman.  If not, see <http://www.gnu.org/licenses/>.

"""Harness for testing Mailman's documentation.

Note that doctest extraction does not currently work for zip file
distributions.  doctest discovery currently requires file system traversal.
"""

from __future__ import absolute_import, unicode_literals

__metaclass__ = type
__all__ = [
    'test_suite',
    ]


import os
import sys
import json
import doctest
import unittest

from base64 import b64encode
from email import message_from_string
from httplib2 import Http
from urllib import urlencode
from urllib2 import HTTPError

import mailman

from mailman.app.lifecycle import create_list
from mailman.config import config
from mailman.email.message import Message
from mailman.testing.layers import SMTPLayer


DOT = '.'



class chdir:
    """A context manager for temporary directory changing."""
    def __init__(self, directory):
        self._curdir = None
        self._directory = directory

    def __enter__(self):
        self._curdir = os.getcwd()
        os.chdir(self._directory)

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(self._curdir)
        # Don't suppress exceptions.
        return False



def specialized_message_from_string(unicode_text):
    """Parse text into a message object.

    This is specialized in the sense that an instance of Mailman's own Message
    object is returned, and this message object has an attribute
    `original_size` which is the pre-calculated size in bytes of the message's
    text representation.

    Also, the text must be ASCII-only unicode.
    """
    # This mimic what Switchboard.dequeue() does when parsing a message from
    # text into a Message instance.
    text = unicode_text.encode('ascii')
    original_size = len(text)
    message = message_from_string(text, Message)
    message.original_size = original_size
    return message


def stop():
    """Call into pdb.set_trace()"""
    # Do the import here so that you get the wacky special hacked pdb instead
    # of Python's normal pdb.
    import pdb
    pdb.set_trace()


def dump_msgdata(msgdata, *additional_skips):
    """Dump in a more readable way a message metadata dictionary."""
    if len(msgdata) == 0:
        print '*Empty*'
        return
    skips = set(additional_skips)
    # Some stuff we always want to skip, because their values will always be
    # variable data.
    skips.add('received_time')
    longest = max(len(key) for key in msgdata if key not in skips)
    for key in sorted(msgdata):
        if key in skips:
            continue
        print '{0:{2}}: {1}'.format(key, msgdata[key], longest)


def dump_list(list_of_things, key=str):
    """Print items in a string to get rid of stupid u'' prefixes."""
    # List of things may be a generator.
    list_of_things = list(list_of_things)
    if len(list_of_things) == 0:
        print '*Empty*'
    if key is not None:
        list_of_things = sorted(list_of_things, key=key)
    for item in list_of_things:
        print item


def call_http(url, data=None, method=None, username=None, password=None):
    """'Call' a URL with a given HTTP method and return the resulting object.

    The object will have been JSON decoded.

    :param url: The url to open, read, and print.
    :type url: string
    :param data: Data to use to POST to a URL.
    :type data: dict
    :param method: Alternative HTTP method to use.
    :type method: str
    :param username: The HTTP Basic Auth user name.  None means use the value
        from the configuration.
    :type username: str
    :param password: The HTTP Basic Auth password.  None means use the value
        from the configuration.
    :type username: str
    """
    headers = {}
    if data is not None:
        data = urlencode(data, doseq=True)
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if method is None:
        if data is None:
            method = 'GET'
        else:
            method = 'POST'
    method = method.upper()
    basic_auth = '{0}:{1}'.format(
        (config.webservice.admin_user if username is None else username),
        (config.webservice.admin_pass if password is None else password))
    headers['Authorization'] = 'Basic ' + b64encode(basic_auth)
    response, content = Http().request(url, method, data, headers)
    # If we did not get a 2xx status code, make this look like a urllib2
    # exception, for backward compatibility with existing doctests.
    if response.status // 100 != 2:
        raise HTTPError(url, response.status, content, response, None)
    if len(content) == 0:
        for header in sorted(response):
            print '{0}: {1}'.format(header, response[header])
        return None
    # XXX Workaround http://bugs.python.org/issue10038
    content = unicode(content)
    return json.loads(content)


def dump_json(url, data=None, method=None, username=None, password=None):
    """Print the JSON dictionary read from a URL.

    :param url: The url to open, read, and print.
    :type url: string
    :param data: Data to use to POST to a URL.
    :type data: dict
    :param method: Alternative HTTP method to use.
    :type method: str
    :param username: The HTTP Basic Auth user name.  None means use the value
        from the configuration.
    :type username: str
    :param password: The HTTP Basic Auth password.  None means use the value
        from the configuration.
    :type username: str
    """
    results = call_http(url, data, method, username, password)
    if results is None:
        return
    for key in sorted(results):
        if key == 'entries':
            for i, entry in enumerate(results[key]):
                # entry is a dictionary.
                print 'entry %d:' % i
                for entry_key in sorted(entry):
                    print '    {0}: {1}'.format(entry_key, entry[entry_key])
        else:
            print '{0}: {1}'.format(key, results[key])



def setup(testobj):
    """Test setup."""
    # Make sure future statements in our doctests are the same as everywhere
    # else.
    testobj.globs['absolute_import'] = absolute_import
    testobj.globs['unicode_literals'] = unicode_literals
    # In general, I don't like adding convenience functions, since I think
    # doctests should do the imports themselves.  It makes for better
    # documentation that way.  However, a few are really useful, or help to
    # hide some icky test implementation details.
    testobj.globs['call_http'] = call_http
    testobj.globs['config'] = config
    testobj.globs['create_list'] = create_list
    testobj.globs['dump_json'] = dump_json
    testobj.globs['dump_msgdata'] = dump_msgdata
    testobj.globs['dump_list'] = dump_list
    testobj.globs['message_from_string'] = specialized_message_from_string
    testobj.globs['smtpd'] = SMTPLayer.smtpd
    testobj.globs['stop'] = stop
    testobj.globs['transaction'] = config.db



def test_suite():
    suite = unittest.TestSuite()
    topdir = os.path.dirname(mailman.__file__)
    packages = []
    for dirpath, dirnames, filenames in os.walk(topdir):
        if 'docs' in dirnames:
            docsdir = os.path.join(dirpath, 'docs')[len(topdir)+1:]
            packages.append(docsdir)
    # Under higher verbosity settings, report all doctest errors, not just the
    # first one.
    flags = (doctest.ELLIPSIS |
             doctest.NORMALIZE_WHITESPACE |
             doctest.REPORT_NDIFF)
    # Add all the doctests in all subpackages.
    doctest_files = {}
    with chdir(topdir):
        for docsdir in packages:
            # Look to see if the package defines a test layer, otherwise use
            # SMTPLayer.
            package_path = 'mailman.' + DOT.join(docsdir.split(os.sep))
            try:

                __import__(package_path)
            except ImportError:
                layer = SMTPLayer
            else:
                layer = getattr(sys.modules[package_path], 'layer', SMTPLayer)
            for filename in os.listdir(docsdir):
                base, extension = os.path.splitext(filename)
                if os.path.splitext(filename)[1] in ('.txt', '.rst'):
                    module_path = package_path + '.' + base
                    doctest_files[module_path] = (
                        os.path.join(docsdir, filename), layer)
    for module_path in sorted(doctest_files):
        path, layer = doctest_files[module_path]
        test = doctest.DocFileSuite(
            path,
            package='mailman',
            optionflags=flags,
            setUp=setup)
        test.layer = layer
        suite.addTest(test)
    return suite
