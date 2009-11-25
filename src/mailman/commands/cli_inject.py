# Copyright (C) 2009 by the Free Software Foundation, Inc.
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

"""Module stuff."""

from __future__ import absolute_import, unicode_literals

__metaclass__ = type
__all__ = [
    'Inject',
    ]


import sys

from zope.component import getUtility
from zope.interface import implements

from mailman.config import config
from mailman.core.i18n import _
from mailman.inject import inject_text
from mailman.interfaces.command import ICLISubCommand
from mailman.interfaces.listmanager import IListManager



class Inject:
    """Inject a message from a file into a mailing list's queue."""

    implements(ICLISubCommand)

    name = 'inject'

    def add(self, parser, command_parser):
        """See `ICLISubCommand`."""
        self.parser = parser
        command_parser.add_argument(
            '-q', '--queue',
            type=unicode, help=_("""\
            The name of the queue to inject the message to.  QUEUE must be one
            of the directories inside the qfiles directory.  If omitted, the
            incoming queue is used."""))
        command_parser.add_argument(
            '-s', '--show',
            action='store_true', default=False,
            help=_('Show a list of all available queue names and exit.'))
        command_parser.add_argument(
            '-f', '--filename',
            type=unicode, help=_("""
            Name of file containing the message to inject.  If not given, or
            '-' (without the quotes) standard input is used."""))
        # Required positional argument.
        command_parser.add_argument(
            'listname', metavar='LISTNAME', nargs=1,
            help=_("""\
            The 'fully qualified list name', i.e. the posting address of the
            mailing list to inject the message into."""))

    def process(self, args):
        """See `ICLISubCommand`."""
        # Process --show first; if given, print output and exit, ignoring all
        # other command line switches.
        if args.show:
            print 'Available queues:'
            for switchboard in sorted(config.switchboards):
                print '   ', switchboard
            return
        # Could be None or sequence of length 0.
        if args.listname is None:
            self.parser.error(_('List name is required'))
            return
        assert len(args.listname) == 1, (
            'Unexpected positional arguments: %s' % args.listname)
        fqdn_listname = args.listname[0]
        mlist = getUtility(IListManager).get(fqdn_listname)
        if mlist is None:
            self.parser.error(_('No such list: $fqdn_listname'))
            return
        queue = ('in' if args.queue is None else args.queue)
        switchboard = config.switchboards.get(queue)
        if switchboard is None:
            self.parser.error(_('No such queue: $queue'))
            return
        if args.filename in (None, '-'):
            try:
                message_text = sys.stdin.read()
            except KeyboardInterrupt:
                print 'Interrupted'
                sys.exit(1)
        else:
            with open(args.filename) as fp:
                message_text = fp.read()
        inject_text(mlist, message_text, switchboard=queue)