# Copyright (C) 1998-2007 by the Free Software Foundation, Inc.
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

"""Determine whether this message should be held for approval.

This modules tests only for hold situations, such as messages that are too
large, messages that have potential administrivia, etc.  Definitive approvals
or denials are handled by a different module.

If no determination can be made (i.e. none of the hold criteria matches), then
we do nothing.  If the message must be held for approval, then the hold
database is updated and any administrator notification messages are sent.
Finally an exception is raised to let the pipeline machinery know that further
message handling should stop.
"""

from __future__ import with_statement

import email
import logging
import email.utils

from email.mime.message import MIMEMessage
from email.mime.text import MIMEText
from types import ClassType
from zope.interface import implements

from Mailman import Errors
from Mailman import Message
from Mailman import Utils
from Mailman import i18n
from Mailman.app.bounces import has_matching_bounce_header
from Mailman.app.moderator import hold_message
from Mailman.app.replybot import autorespond_to_sender
from Mailman.configuration import config
from Mailman.interfaces import IPendable

log = logging.getLogger('mailman.vette')

# Play footsie with _ so that the following are marked as translated, but
# aren't actually translated until we need the text later on.
def _(s):
    return s

__i18n_templates__ = True



class ForbiddenPoster(Errors.HoldMessage):
    reason = _('Sender is explicitly forbidden')
    rejection = _('You are forbidden from posting messages to this list.')

class ModeratedPost(Errors.HoldMessage):
    reason = _('Post to moderated list')
    rejection = _('Your message was deemed inappropriate by the moderator.')

class NonMemberPost(Errors.HoldMessage):
    reason = _('Post by non-member to a members-only list')
    rejection = _('Non-members are not allowed to post messages to this list.')

class NotExplicitlyAllowed(Errors.HoldMessage):
    reason = _('Posting to a restricted list by sender requires approval')
    rejection = _('This list is restricted; your message was not approved.')

class TooManyRecipients(Errors.HoldMessage):
    reason = _('Too many recipients to the message')
    rejection = _('Please trim the recipient list; it is too long.')

class ImplicitDestination(Errors.HoldMessage):
    reason = _('Message has implicit destination')
    rejection = _('''Blind carbon copies or other implicit destinations are
not allowed.  Try reposting your message by explicitly including the list
address in the To: or Cc: fields.''')

class Administrivia(Errors.HoldMessage):
    reason = _('Message may contain administrivia')

    def rejection_notice(self, mlist):
        listurl = mlist.script_url('listinfo')
        request = mlist.request_address
        return _("""Please do *not* post administrative requests to the mailing
list.  If you wish to subscribe, visit $listurl or send a message with the
word `help' in it to the request address, $request, for further
instructions.""")

class SuspiciousHeaders(Errors.HoldMessage):
    reason = _('Message has a suspicious header')
    rejection = _('Your message had a suspicious header.')

class MessageTooBig(Errors.HoldMessage):
    def __init__(self, msgsize, limit):
        Errors.HoldMessage.__init__(self)
        self.__msgsize = msgsize
        self.__limit = limit

    def reason_notice(self):
        size = self.__msgsize
        limit = self.__limit
        return _('''Message body is too big: $size bytes with a limit of
$limit KB''')

    def rejection_notice(self, mlist):
        kb = self.__limit
        return _('''Your message was too big; please trim it to less than
$kb KB in size.''')

class ModeratedNewsgroup(ModeratedPost):
    reason = _('Posting to a moderated newsgroup')



# And reset the translator
_ = i18n._



def ackp(msg):
    ack = msg.get('x-ack', '').lower()
    precedence = msg.get('precedence', '').lower()
    if ack <> 'yes' and precedence in ('bulk', 'junk', 'list'):
        return 0
    return 1



class HeldMessagePendable(dict):
    implements(IPendable)
    PEND_KEY = 'held message'



def process(mlist, msg, msgdata):
    if msgdata.get('approved'):
        return
    # Get the sender of the message
    listname = mlist.list_name
    adminaddr = listname + '-admin'
    sender = msg.get_sender()
    # Special case an ugly sendmail feature: If there exists an alias of the
    # form "owner-foo: bar" and sendmail receives mail for address "foo",
    # sendmail will change the envelope sender of the message to "bar" before
    # delivering.  This feature does not appear to be configurable.  *Boggle*.
    if not sender or sender[:len(listname)+6] == adminaddr:
        sender = msg.get_sender(use_envelope=0)
    #
    # Suspicious headers?
    if mlist.bounce_matching_headers:
        triggered = has_matching_bounce_header(mlist, msg)
        if triggered:
            # TBD: Darn - can't include the matching line for the admin
            # message because the info would also go to the sender
            hold_for_approval(mlist, msg, msgdata, SuspiciousHeaders)
            # no return



def hold_for_approval(mlist, msg, msgdata, exc):
    # BAW: This should really be tied into the email confirmation system so
    # that the message can be approved or denied via email as well as the
    # web.
    if isinstance(exc, ClassType) or isinstance(exc, type):
        # Go ahead and instantiate it now.
        exc = exc()
    listname = mlist.list_name
    sender = msgdata.get('sender', msg.get_sender())
    usersubject = msg.get('subject')
    charset = Utils.GetCharSet(mlist.preferred_language)
    if usersubject:
        usersubject = Utils.oneline(usersubject, charset)
    else:
        usersubject = _('(no subject)')
    message_id = msg.get('message-id', 'n/a')
    owneraddr = mlist.owner_address
    adminaddr = mlist.bounces_address
    requestaddr = mlist.request_address
    # We need to send both the reason and the rejection notice through the
    # translator again, because of the games we play above
    reason = Utils.wrap(exc.reason_notice())
    msgdata['rejection_notice'] = Utils.wrap(exc.rejection_notice(mlist))
    id = hold_message(mlist, msg, msgdata, reason)
    # Now we need to craft and send a message to the list admin so they can
    # deal with the held message.
    d = {'listname'   : listname,
         'hostname'   : mlist.host_name,
         'reason'     : _(reason),
         'sender'     : sender,
         'subject'    : usersubject,
         'admindb_url': mlist.script_url('admindb'),
         }
    # We may want to send a notification to the original sender too
    fromusenet = msgdata.get('fromusenet')
    # Since we're sending two messages, which may potentially be in different
    # languages (the user's preferred and the list's preferred for the admin),
    # we need to play some i18n games here.  Since the current language
    # context ought to be set up for the user, let's craft his message first.
    #
    # This message should appear to come from <list>-admin so as to handle any
    # bounce processing that might be needed.
    pendable = HeldMessagePendable(type=HeldMessagePendable.PEND_KEY, id=id)
    token = config.db.pendings.add(pendable)
    # Get the language to send the response in.  If the sender is a member,
    # then send it in the member's language, otherwise send it in the mailing
    # list's preferred language.
    member = mlist.members.get_member(sender)
    lang = (member.preferred_language if member else mlist.preferred_language)
    if not fromusenet and ackp(msg) and mlist.respond_to_post_requests and \
           autorespond_to_sender(mlist, sender, lang):
        # Get a confirmation token
        d['confirmurl'] = '%s/%s' % (
            mlist.script_url('confirm'), token)
        lang = msgdata.get('lang', lang)
        subject = _('Your message to $listname awaits moderator approval')
        text = Utils.maketext('postheld.txt', d, lang=lang, mlist=mlist)
        nmsg = Message.UserNotification(sender, adminaddr, subject, text, lang)
        nmsg.send(mlist)
    # Now the message for the list owners.  Be sure to include the list
    # moderators in this message.  This one should appear to come from
    # <list>-owner since we really don't need to do bounce processing on it.
    if mlist.admin_immed_notify:
        # Now let's temporarily set the language context to that which the
        # admin is expecting.
        with i18n.using_language(mlist.preferred_language):
            lang = mlist.preferred_language
            charset = Utils.GetCharSet(lang)
            # We need to regenerate or re-translate a few values in d
            d['reason'] = _(reason)
            d['subject'] = usersubject
            # craft the admin notification message and deliver it
            subject = _('$listname post from $sender requires approval')
            nmsg = Message.UserNotification(owneraddr, owneraddr, subject,
                                            lang=lang)
            nmsg.set_type('multipart/mixed')
            text = MIMEText(
                Utils.maketext('postauth.txt', d, raw=1, mlist=mlist),
                _charset=charset)
            dmsg = MIMEText(Utils.wrap(_("""\
If you reply to this message, keeping the Subject: header intact, Mailman will
discard the held message.  Do this if the message is spam.  If you reply to
this message and include an Approved: header with the list password in it, the
message will be approved for posting to the list.  The Approved: header can
also appear in the first line of the body of the reply.""")),
                            _charset=Utils.GetCharSet(lang))
            dmsg['Subject'] = 'confirm ' + token
            dmsg['Sender'] = requestaddr
            dmsg['From'] = requestaddr
            dmsg['Date'] = email.utils.formatdate(localtime=True)
            dmsg['Message-ID'] = email.utils.make_msgid()
            nmsg.attach(text)
            nmsg.attach(MIMEMessage(msg))
            nmsg.attach(MIMEMessage(dmsg))
            nmsg.send(mlist, **{'tomoderators': 1})
    # Log the held message
    log.info('%s post from %s held, message-id=%s: %s',
             listname, sender, message_id, reason)
    # raise the specific MessageHeld exception to exit out of the message
    # delivery pipeline
    raise exc
