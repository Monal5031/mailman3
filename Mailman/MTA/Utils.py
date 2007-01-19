# Copyright (C) 2001-2007 by the Free Software Foundation, Inc.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301,
# USA.

"""Utilities for list creation/deletion hooks."""

import os
import pwd

from Mailman.configuration import config



def getusername():
    username = os.environ.get('USER') or os.environ.get('LOGNAME')
    if not username:
        import pwd
        username = pwd.getpwuid(os.getuid())[0]
    if not username:
        username = '<unknown>'
    return username



def _makealiases_mailprog(mlist):
    wrapper = os.path.join(config.WRAPPER_DIR, 'mailman')
    # Most of the list alias extensions are quite regular.  I.e. if the
    # message is delivered to listname-foobar, it will be filtered to a
    # program called foobar.  There are two exceptions:
    #
    # 1) Messages to listname (no extension) go to the post script.
    # 2) Messages to listname-admin go to the bounces script.  This is for
    #    backwards compatibility and may eventually go away (we really have no
    #    need for the -admin address anymore).
    #
    # Seed this with the special cases.
    listname = mlist.internal_name()
    fqdn_listname = mlist.fqdn_listname
    aliases = [
        (listname, '"|%s post %s"' % (wrapper, fqdn_listname)),
        ]
    for ext in ('admin', 'bounces', 'confirm', 'join', 'leave', 'owner',
                'request', 'subscribe', 'unsubscribe'):
        aliases.append(('%s-%s' % (listname, ext),
                        '"|%s %s %s"' % (wrapper, ext, fqdn_listname)))
    return aliases



def _makealiases_maildir(mlist):
    maildir = config.MAILDIR_DIR
    listname = mlist.internal_name()
    fqdn_listname = mlist.fqdn_listname
    if not maildir.endswith('/'):
        maildir += '/'
    # Deliver everything using maildir style.  This way there's no mail
    # program, no forking and no wrapper necessary!
    #
    # Note, don't use this unless your MTA leaves the envelope recipient in
    # Delivered-To:, Envelope-To:, or Apparently-To:
    aliases = [(listname, maildir)]
    for ext in ('admin', 'bounces', 'confirm', 'join', 'leave', 'owner',
                'request', 'subscribe', 'unsubscribe'):
        aliases.append(('%s-%s' % (listname, ext), maildir))
    return aliases



# XXX This won't work if Mailman.MTA.Utils is imported before the
# configuration is loaded.
if config.USE_MAILDIR:
    makealiases = _makealiases_maildir
else:
    makealiases = _makealiases_mailprog
