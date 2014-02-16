# -*- coding: utf-8 -*-

"""
Copyright (C) 2014 Axel Mendoza <aekroft at gmail.com>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# stdlib
import re

import random
import socket
import time
import datetime
import dateutil
import pytz

from logging import getLogger
from traceback import format_exc

import cgi

from imaplib import IMAP4
from imaplib import IMAP4_SSL
from poplib import POP3
from poplib import POP3_SSL

import smtplib

import email
from email.message import Message
from email.MIMEText import MIMEText
from email.MIMEBase import MIMEBase
from email.MIMEMultipart import MIMEMultipart
from email.Charset import Charset
from email.Header import Header
from email.header import decode_header
from email.Utils import formatdate, make_msgid, COMMASPACE
from email import Encoders

# Zato
from zato.common import ZatoException
from zato.server.service import Service

try:
    from html2text import html2text
except ImportError:
    html2text = None

name_with_email_pattern = re.compile(r'("[^<@>]+")\s*<([^ ,<@]+@[^> ,]+)>')
address_pattern = re.compile(r'([^ ,<@]+@[^> ,]+)')

MAIL_CONN_INFO_PREFIX = 'zato:mail:conn-info'
SMTP_PARAMS = {}

for name in('smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 'smtp_encryption', 'smtp_debug'):
    SMTP_PARAMS[name] = '{}:{}'.format(MAIL_CONN_INFO_PREFIX, name)

IMAP_PARAMS = {}

for name in('imap_host', 'imap_port', 'imap_user', 'imap_pass', 'imap_ssl'):
    IMAP_PARAMS[name] = '{}:{}'.format(MAIL_CONN_INFO_PREFIX, name)

POP3_PARAMS = {}

for name in('pop3_host', 'pop3_port', 'pop3_user', 'pop3_pass', 'pop3_ssl'):
    POP3_PARAMS[name] = '{}:{}'.format(MAIL_CONN_INFO_PREFIX, name)


def flatten(list):
    """Flatten a list of elements into a uniqu list
    Author: Christophe Simonis (christophe@tinyerp.com)

    Examples::
    >>> flatten(['a'])
    ['a']
    >>> flatten('b')
    ['b']
    >>> flatten( [] )
    []
    >>> flatten( [[], [[]]] )
    []
    >>> flatten( [[['a','b'], 'c'], 'd', ['e', [], 'f']] )
    ['a', 'b', 'c', 'd', 'e', 'f']
    >>> t = (1,2,(3,), [4, 5, [6, [7], (8, 9), ([10, 11, (12, 13)]), [14, [], (15,)], []]])
    >>> flatten(t)
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    """

    def isiterable(x):
        return hasattr(x, "__iter__")

    r = []
    for e in list:
        if isiterable(e):
            map(r.append, flatten(e))
        else:
            r.append(e)
    return r

def try_coerce_ascii(string_utf8):
    """Attempts to decode the given utf8-encoded string
       as ASCII after coercing it to UTF-8, then return
       the confirmed 7-bit ASCII string.

       If the process fails (because the string
       contains non-ASCII characters) returns ``None``.
    """
    try:
        string_utf8.decode('ascii')
    except UnicodeDecodeError:
        return
    return string_utf8

def encode_header(header_text):
    """Returns an appropriate representation of the given header value,
       suitable for direct assignment as a header value in an
       email.message.Message. RFC2822 assumes that headers contain
       only 7-bit characters, so we ensure it is the case, using
       RFC2047 encoding when needed.

       :param header_text: unicode or utf-8 encoded string with header value
       :rtype: string | email.header.Header
       :return: if ``header_text`` represents a plain ASCII string,
                return the same 7-bit string, otherwise returns an email.header.Header
                that will perform the appropriate RFC2047 encoding of
                non-ASCII values.
    """
    if not header_text: return ""
    # convert anything to utf-8, suitable for testing ASCIIness, as 7-bit chars are
    # encoded as ASCII in utf-8
    header_text_utf8 = unicode(header_text).encode('utf-8')
    header_text_ascii = try_coerce_ascii(header_text_utf8)
    # if this header contains non-ASCII characters,
    # we'll need to wrap it up in a message.header.Header
    # that will take care of RFC2047-encoding it as
    # 7-bit string.
    return header_text_ascii if header_text_ascii\
         else Header(header_text_utf8, 'utf-8')

def encode_header_param(param_text):
    """Returns an appropriate RFC2047 encoded representation of the given
       header parameter value, suitable for direct assignation as the
       param value (e.g. via Message.set_param() or Message.add_header())
       RFC2822 assumes that headers contain only 7-bit characters,
       so we ensure it is the case, using RFC2047 encoding when needed.

       :param param_text: unicode or utf-8 encoded string with header value
       :rtype: string
       :return: if ``param_text`` represents a plain ASCII string,
                return the same 7-bit string, otherwise returns an
                ASCII string containing the RFC2047 encoded text.
    """
    # For details see the encode_header() method that uses the same logic
    if not param_text: return ""
    param_text_utf8 = unicode(param_text).encode('utf-8')
    param_text_ascii = try_coerce_ascii(param_text_utf8)
    return param_text_ascii if param_text_ascii\
         else Charset('utf8').header_encode(param_text_utf8)
         
def extract_rfc2822_addresses(text):
    """Returns a list of valid RFC2822 addresses
       that can be found in ``source``, ignoring 
       malformed ones and non-ASCII ones.
    """
    if not text: return []
    candidates = address_pattern.findall(unicode(text).encode('utf-8'))
    return filter(try_coerce_ascii, candidates)

def encode_rfc2822_address_header(header_text):
    """If ``header_text`` contains non-ASCII characters,
       attempts to locate patterns of the form
       ``"Name" <address@domain>`` and replace the
       ``"Name"`` portion by the RFC2047-encoded
       version, preserving the address part untouched.
    """
    header_text_utf8 = unicode(header_text).encode('utf-8')
    header_text_ascii = try_coerce_ascii(header_text_utf8)
    if header_text_ascii:
        return header_text_ascii
    # non-ASCII characters are present, attempt to
    # replace all "Name" patterns with the RFC2047-
    # encoded version
    def replace(match_obj):
        name, email = match_obj.group(1), match_obj.group(2)
        name_encoded = str(Header(name, 'utf-8'))
        return "%s <%s>" % (name_encoded, email)
    header_text_utf8 = name_with_email_pattern.sub(replace,
                                                   header_text_utf8)
    # try again after encoding
    header_text_ascii = try_coerce_ascii(header_text_utf8)
    if header_text_ascii:
        return header_text_ascii
    # fallback to extracting pure addresses only, which could
    # still cause a failure downstream if the actual addresses
    # contain non-ASCII characters
    return COMMASPACE.join(extract_rfc2822_addresses(header_text_utf8))

def generate_tracking_message_id(res_id):
    """Returns a string that can be used in the Message-ID RFC822 header field

       Used to track the replies related to a given object thanks to the "In-Reply-To"
       or "References" fields that Mail User Agents will set.
    """
    try:
        rnd = random.SystemRandom().random()
    except NotImplementedError:
        rnd = random.random()
    rndstr = ("%.15f" % rnd)[2:]
    return "<%.15f.%s-zato-%s@%s>" % (time.time(), rndstr, res_id, socket.gethostname())

def plaintext2html(text, container_tag=False):
    """ Convert plaintext into html. Content of the text is escaped to manage
        html entities, using cgi.escape().
        - all \n,\r are replaced by <br />
        - enclose content into <p>
        - 2 or more consecutive <br /> are considered as paragraph breaks

        :param string container_tag: container of the html; by default the
            content is embedded into a <div>
    """
    text = cgi.escape(unicode(text))

    # 1. replace \n and \r
    text = text.replace('\n', '<br/>')
    text = text.replace('\r', '<br/>')

    # 2-3: form paragraphs
    idx = 0
    final = '<p>'
    br_tags = re.compile(r'(([<]\s*[bB][rR]\s*\/?[>]\s*){2,})')
    for item in re.finditer(br_tags, text):
        final += text[idx:item.start()] + '</p><p>'
        idx = item.end()
    final += text[idx:] + '</p>'

    # 4. container
    if container_tag:
        final = '<%s>%s</%s>' % (container_tag, final, container_tag)
    return unicode(final)

def append_content_to_html(html, content, plaintext=True, preserve=False, container_tag=False):
    """ Append extra content at the end of an HTML snippet, trying
        to locate the end of the HTML document (</body>, </html>, or
        EOF), and converting the provided content in html unless ``plaintext``
        is False.
        Content conversion can be done in two ways:
        - wrapping it into a pre (preserve=True)
        - use plaintext2html (preserve=False, using container_tag to wrap the
            whole content)
        A side-effect of this method is to coerce all HTML tags to
        lowercase in ``html``, and strip enclosing <html> or <body> tags in
        content if ``plaintext`` is False.

        :param str html: html tagsoup (doesn't have to be XHTML)
        :param str content: extra content to append
        :param bool plaintext: whether content is plaintext and should
            be wrapped in a <pre/> tag.
        :param bool preserve: if content is plaintext, wrap it into a <pre>
            instead of converting it into html
    """
    html = unicode(html)
    if plaintext and preserve:
        content = u'\n<pre>%s</pre>\n' % unicode(content)
    elif plaintext:
        content = '\n%s\n' % plaintext2html(content, container_tag)
    else:
        content = re.sub(r'(?i)(</?html.*>|</?body.*>|<!\W*DOCTYPE.*>)', '', content)
        content = u'\n%s\n' % unicode(content)
    # Force all tags to lowercase
    html = re.sub(r'(</?)\W*(\w+)([ >])',
        lambda m: '%s%s%s' % (m.group(1), m.group(2).lower(), m.group(3)), html)
    insert_location = html.find('</body>')
    if insert_location == -1:
        insert_location = html.find('</html>')
    if insert_location == -1:
        return '%s%s' % (html, content)
    return '%s%s%s' % (html[:insert_location], content, html[insert_location:])

def decode(text):
    """Returns unicode() string conversion of the the given encoded smtp header text"""
    if text:
        text = decode_header(text.replace('\r', ''))
        return ''.join([x[1] != None and unicode(x[0], x[1]) or unicode(x[0]) for x in text])
    
def message_extract_payload(message):
    """Extract body as HTML and attachments from the mail message"""
    attachments = []
    body = u''
    if not message.is_multipart() or 'text/' in message.get('content-type', ''):
        encoding = message.get_content_charset()
        body = message.get_payload(decode=True)
        if encoding:
            body = unicode(body, encoding, errors='replace')
        else:
            body = unicode(body, errors='replace')
        if message.get_content_type() == 'text/plain':
            # text/plain -> <pre/>
            body = append_content_to_html(u'', body, preserve=True)
    else:
        alternative = (message.get_content_type() == 'multipart/alternative')
        for part in message.walk():
            if part.get_content_maintype() == 'multipart':
                continue  # skip container
            filename = part.get_filename()  # None if normal part
            encoding = part.get_content_charset()  # None if attachment
            # 1) Explicit Attachments -> attachments
            if filename or part.get('content-disposition', '').strip().startswith('attachment'):
                attachments.append((filename or 'attachment', part.get_payload(decode=True)))
                continue
            # 2) text/plain -> <pre/>
            if part.get_content_type() == 'text/plain' and (not alternative or not body):
                body = append_content_to_html(body, unicode(part.get_payload(decode=True),
                                                                     encoding, errors='replace'), preserve=True)
            # 3) text/html -> raw
            elif part.get_content_type() == 'text/html':
                if encoding:
                    html = unicode(part.get_payload(decode=True), encoding, errors='replace')
                else:
                    html = unicode(part.get_payload(decode=True), errors='replace')
                if alternative:
                    body = html
                else:
                    body = append_content_to_html(body, html, plaintext=False)
            # 4) Anything else -> attachment
            else:
                attachments.append((filename or 'attachment', part.get_payload(decode=True)))
    return body, attachments

class FetchMailMixin(object):
    
    def message_parse(self, message):
        """Parses a string or email.message.Message representing an
           RFC-2822 email, and returns a generic dict holding the
           message details.

           :param message: the message to parse
           :type message: email.message.Message | string | unicode
           :rtype: dict
           :return: A dict with the following structure::
                    { 'message_id': msg_id,
                      'subject': subject,
                      'from': from,
                      'to': to,
                      'cc': cc,
                      'body': unified_body,
                      'attachments': [('file1', 'bytes'),
                                      ('file2', 'bytes')}
                    }
        """
        msg_dict = {
            'type': 'email',
        }
        if not isinstance(message, Message):
            if isinstance(message, unicode):
                # Warning: message_from_string doesn't always work correctly on unicode,
                # we must use utf-8 strings here :-(
                message = message.encode('utf-8')
            message = email.message_from_string(message)

        message_id = message['message-id']
        if not message_id:
            # Very unusual situation, be we should be fault-tolerant here
            message_id = "<%s@localhost>" % time.time()
            self.logger.debug('Parsing Message without message-id, generating a random one: %s'%(message_id))
        msg_dict['message_id'] = message_id

        if message.get('Subject'):
            msg_dict['subject'] = decode(message.get('Subject'))

        # Envelope fields not stored in mail.message but made available for message_new()
        msg_dict['from'] = decode(message.get('from'))
        msg_dict['to'] = decode(message.get('to'))
        msg_dict['cc'] = decode(message.get('cc'))

        if message.get('From'):
            msg_dict['email_from'] = decode(message.get('from'))

        if message.get('Date'):
            try:
                date_hdr = decode(message.get('Date'))
                parsed_date = dateutil.parser.parse(date_hdr, fuzzy=True)
                if parsed_date.utcoffset() is None:
                    # naive datetime, so we arbitrarily decide to make it
                    # UTC, there's no better choice. Should not happen,
                    # as RFC2822 requires timezone offset in Date headers.
                    stored_date = parsed_date.replace(tzinfo=pytz.utc)
                else:
                    stored_date = parsed_date.astimezone(tz=pytz.utc)
            except Exception:
                self.logger.warning('Failed to parse Date header %r in incoming mail '
                                'with message-id %r, assuming current date/time.'%(
                                message.get('Date'), message_id))
                stored_date = datetime.datetime.now()
            msg_dict['date'] = stored_date.strftime("%Y-%m-%d %H:%M:%S")

        msg_dict['body'], msg_dict['attachments'] = message_extract_payload(message)
        return msg_dict

class IMAPClient(FetchMailMixin):
    
    def __init__(self, name=None, imap_host=None, imap_port=143, imap_user=None, imap_pass=None, imap_ssl=False):
        self.name = name
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_user = unicode(imap_user).encode('utf-8')
        self.imap_pass = unicode(imap_pass).encode('utf-8')
        self.imap_ssl = imap_ssl
        self.conn = None
        
        self.logger = getLogger(self.__class__.__name__)
        # Imported here so it doesn't interfere with gevent's monkey-patching
        
        # stdlib
        from time import time
        self.time = time
        
    def connect(self):
        if self.imap_ssl:
            self.conn = IMAP4_SSL(self.imap_host, int(self.imap_port))
        else:
            self.conn = IMAP4(self.imap_host, int(self.imap_port))
        self.conn.login(self.imap_user, self.imap_pass)
        return self.conn
    
    def fetch_mail(self):
        """WARNING: meant for cron usage only - will commit() after each email!"""
        self.logger.info('start checking for new emails on imap server %s'%(self.name))
        count = 0
        imap_server = False
        messages = []
        try:
            imap_server = self.connect()
            imap_server.select()
            result, data = imap_server.search(None, '(UNSEEN)')
            for num in data[0].split():
                result, data = imap_server.fetch(num, '(RFC822)')
                parsed_msg = self.message_parse(data[0][1])
                imap_server.store(num, '+FLAGS', '\\Seen')
                messages.append(parsed_msg)
                count += 1
            self.logger.info("fetched/processed %s email(s) on imap server %s"%(count, self.name))
        except Exception:
            self.logger.exception("Failed to fetch mail from imap server %s."%(self.name))
        finally:
            if imap_server:
                imap_server.close()
                imap_server.logout()
        return messages

    def ping(self):
        self.logger.debug('About to ping an IMAP connection:[{}]'.format(self.name))
        start_time = self.time()
        conn = self.connect()
        if conn:
            conn.close()
        response_time = self.time() - start_time
        self.logger.debug('Ping OK, connection:[{0}], response_time:[{1:03.4f} s]'.format(self.name, response_time))
        return response_time

class POP3Client(FetchMailMixin):

    def __init__(self, name=None, pop3_host=None, pop3_port=110, pop3_user=None, pop3_pass=None, pop3_ssl=False):
        self.name = name
        self.pop3_host = pop3_host
        self.pop3_port = pop3_port
        self.pop3_user = unicode(pop3_user).encode('utf-8')
        self.pop3_pass = unicode(pop3_pass).encode('utf-8')
        self.pop3_ssl = pop3_ssl
        self.conn = None
        
        self.logger = getLogger(self.__class__.__name__)
        # Imported here so it doesn't interfere with gevent's monkey-patching
        
        # stdlib
        from time import time
        self.time = time

    def connect(self):
        if self.pop3_ssl:
            self.conn = POP3_SSL(self.pop3_host, int(self.pop3_port))
        else:
            self.conn = POP3(self.pop3_host, int(self.pop3_port))
        #TODO: use this to remove only unread messages
        #conn.user("recent:"+server.user)
        self.conn.user(self.pop3_user)
        self.conn.pass_(self.pop3_pass)
        return self.conn
    
    def fetch_mail(self):
        """WARNING: meant for cron usage only - will commit() after each email!"""
        self.logger.info('start checking for new emails on pop3 server %s'%(self.name))
        count = 0
        pop_server = False
        messages = []
        try:
            pop_server = self.connect()
            (numMsgs, totalSize) = pop_server.stat()
            pop_server.list()
            for num in range(1, numMsgs + 1):
                (header, msges, octets) = pop_server.retr(num)
                msg = '\n'.join(msges)
                parsed_msg = self.message_parse(msg)
                pop_server.dele(num)
                messages.append(parsed_msg)
            self.logger.info("fetched/processed %s email(s) on pop3 server %s"%(numMsgs, self.name))
        except Exception:
            self.logger.exception("Failed to fetch mail from pop3 server %s."%(self.name))
        finally:
            if pop_server:
                pop_server.quit()
        return messages

    def ping(self):
        self.logger.debug('About to ping an POP3 connection:[{}]'.format(self.name))
        start_time = self.time()
        conn = self.connect()
        if conn:
            conn.quit()
        response_time = self.time() - start_time
        self.logger.debug('Ping OK, connection:[{0}], response_time:[{1:03.4f} s]'.format(self.name, response_time))
        return response_time
    
class SMTPClient(object):
    def __init__(self, name=None, smtp_host=None, smtp_port=25, smtp_user=None, smtp_pass=None, smtp_encryption=None, smtp_debug=None):
        self.name = name
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = unicode(smtp_user).encode('utf-8')
        self.smtp_pass = unicode(smtp_pass).encode('utf-8')
        self.smtp_encryption = smtp_encryption
        self.smtp_debug = smtp_debug
        self.conn = None
        
        self.logger = getLogger(self.__class__.__name__)
        self.logger.write = self.logger.info
        smtplib.stderr = self.logger
        smtplib.stdout = self.logger
        # Imported here so it doesn't interfere with gevent's monkey-patching
        
        # stdlib
        from time import time
        self.time = time
        
    def connect(self):
        
        if self.smtp_encryption == 'ssl':
            if not 'SMTP_SSL' in smtplib.__all__:
                raise ZatoException(self.cid,"SMTP-over-SSL mode unavailable, Your Zato Server does not support SMTP-over-SSL. You could use STARTTLS instead. If SSL is needed, an upgrade to Python 2.6 on the server-side should do the trick.")
            self.conn = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
        else:
            self.conn = smtplib.SMTP(self.smtp_host, self.smtp_port)
        self.conn.set_debuglevel(self.smtp_debug)
        if self.smtp_encryption == 'starttls':
            # starttls() will perform ehlo() if needed first
            # and will discard the previous list of services
            # after successfully performing STARTTLS command,
            # (as per RFC 3207) so for example any AUTH
            # capability that appears only on encrypted channels
            # will be correctly detected for next step
            self.conn.starttls()

        if self.smtp_user:
            # Attempt authentication - will raise if AUTH service not supported
            # The user/password must be converted to bytestrings in order to be usable for
            # certain hashing schemes, like HMAC.
            # See also bug #597143 and python issue #5285
            self.conn.login(self.smtp_user, self.smtp_pass)
        return self.conn
    
    def build_email(self, email_from, email_to, subject, body, email_cc=None, email_bcc=None, reply_to=False,
               attachments=None, message_id=None, references=None, object_id=False, subtype='plain', headers=None,
               body_alternative=None, subtype_alternative='plain'):
        """Constructs an RFC2822 email.message.Message object based on the keyword arguments passed, and returns it.

           :param string email_from: sender email address
           :param list email_to: list of recipient addresses (to be joined with commas) 
           :param string subject: email subject (no pre-encoding/quoting necessary)
           :param string body: email body, of the type ``subtype`` (by default, plaintext).
                               If html subtype is used, the message will be automatically converted
                               to plaintext and wrapped in multipart/alternative, unless an explicit
                               ``body_alternative`` version is passed.
           :param string body_alternative: optional alternative body, of the type specified in ``subtype_alternative``
           :param string reply_to: optional value of Reply-To header
           :param string object_id: optional tracking identifier, to be included in the message-id for
                                    recognizing replies.
           :param string subtype: optional mime subtype for the text body (usually 'plain' or 'html'),
                                  must match the format of the ``body`` parameter. Default is 'plain',
                                  making the content part of the mail "text/plain".
           :param string subtype_alternative: optional mime subtype of ``body_alternative`` (usually 'plain'
                                              or 'html'). Default is 'plain'.
           :param list attachments: list of (filename, filecontents) pairs, where filecontents is a string
                                    containing the bytes of the attachment
           :param list email_cc: optional list of string values for CC header (to be joined with commas)
           :param list email_bcc: optional list of string values for BCC header (to be joined with commas)
           :param dict headers: optional map of headers to set on the outgoing mail (may override the
                                other headers, including Subject, Reply-To, Message-Id, etc.)
           :rtype: email.message.Message (usually MIMEMultipart)
           :return: the new RFC2822 email message
        """

        assert email_from, "You must either provide a sender address explicitly or configure "\
                           "a global sender address in the server configuration or with the "\
                           "--email-from startup parameter."

        # Note: we must force all strings to to 8-bit utf-8 when crafting message,
        #       or use encode_header() for headers, which does it automatically.

        headers = headers or {} # need valid dict later

        if not email_cc: email_cc = []
        if not email_bcc: email_bcc = []
        if not body: body = u''

        email_body_utf8 = unicode(body).encode('utf-8')
        email_text_part = MIMEText(email_body_utf8, _subtype=subtype, _charset='utf-8')
        msg = MIMEMultipart()

        if not message_id:
            if object_id:
                message_id = generate_tracking_message_id(object_id)
            else:
                message_id = make_msgid()
        msg['Message-Id'] = encode_header(message_id)
        if references:
            msg['references'] = encode_header(references)
        msg['Subject'] = encode_header(subject)
        msg['From'] = encode_rfc2822_address_header(email_from)
        del msg['Reply-To']
        if reply_to:
            msg['Reply-To'] = encode_rfc2822_address_header(reply_to)
        else:
            msg['Reply-To'] = msg['From']
        if not isinstance(email_to, (set,list,tuple)):
            email_to = (email_to,)
        msg['To'] = encode_rfc2822_address_header(COMMASPACE.join(email_to))
        if email_cc:
            if not isinstance(email_cc, (set,list,tuple)):
                email_cc = (email_cc,)
            msg['Cc'] = encode_rfc2822_address_header(COMMASPACE.join(email_cc))
        if email_bcc:
            if not isinstance(email_bcc, (set,list,tuple)):
                email_bcc = (email_bcc,)
            msg['Bcc'] = encode_rfc2822_address_header(COMMASPACE.join(email_bcc))
        msg['Date'] = formatdate()
        # Custom headers may override normal headers or provide additional ones
        for key, value in headers.iteritems():
            msg[unicode(key).encode('utf-8')] = encode_header(value)

        if subtype == 'html' and not body_alternative and html2text:
            # Always provide alternative text body ourselves if possible.
            text_utf8 = html2text(email_body_utf8.decode('utf-8')).encode('utf-8')
            alternative_part = MIMEMultipart(_subtype="alternative")
            alternative_part.attach(MIMEText(text_utf8, _charset='utf-8', _subtype='plain'))
            alternative_part.attach(email_text_part)
            msg.attach(alternative_part)
        elif body_alternative:
            # Include both alternatives, as specified, within a multipart/alternative part
            alternative_part = MIMEMultipart(_subtype="alternative")
            body_alternative_utf8 = unicode(body_alternative).encode('utf-8')
            alternative_body_part = MIMEText(body_alternative_utf8, _subtype=subtype_alternative, _charset='utf-8')
            alternative_part.attach(alternative_body_part)
            alternative_part.attach(email_text_part)
            msg.attach(alternative_part)
        else:
            msg.attach(email_text_part)

        if attachments:
            for (fname, fcontent) in attachments:
                filename_rfc2047 = encode_header_param(fname)
                part = MIMEBase('application', "octet-stream")

                # The default RFC2231 encoding of Message.add_header() works in Thunderbird but not GMail
                # so we fix it by using RFC2047 encoding for the filename instead.
                part.set_param('name', filename_rfc2047)
                part.add_header('Content-Disposition', 'attachment', filename=filename_rfc2047)

                part.set_payload(fcontent)
                Encoders.encode_base64(part)
                msg.attach(part)
        return msg
    
    def send_email(self, message):
        """Sends an email directly (no queuing).

        No retries are done, the caller should handle MailDeliveryException in order to ensure that
        the mail is never lost.

        :param message: the email.message.Message to send. The envelope sender will be extracted from the
                        ``Return-Path`` or ``From`` headers. The envelope recipients will be
                        extracted from the combined list of ``To``, ``CC`` and ``BCC`` headers.
        :return: the Message-ID of the message that was just sent, if successfully sent, otherwise raises
                 MailDeliveryException and logs root cause.
        """
        smtp_from = message['Return-Path'] or message['From']
        assert smtp_from, "The Return-Path or From header is required for any outbound email"

        # The email's "Envelope From" (Return-Path), and all recipient addresses must only contain ASCII characters.
        from_rfc2822 = extract_rfc2822_addresses(smtp_from)
        assert len(from_rfc2822) == 1, "Malformed 'Return-Path' or 'From' address - it may only contain plain ASCII characters"
        smtp_from = from_rfc2822[0]
        email_to = message['To']
        email_cc = message['Cc']
        email_bcc = message['Bcc']
        smtp_to_list = filter(None, flatten(map(extract_rfc2822_addresses,[email_to, email_cc, email_bcc])))
        assert smtp_to_list, "At least one valid recipient address should be specified for outgoing emails (To/Cc/Bcc)"

        try:
            message_id = message['Message-Id']

            # Add email in Maildir if smtp_host contains maildir.
            if self.smtp_host.startswith('maildir:/'):
                from mailbox import Maildir
                maildir_path = self.smtp_host[8:]
                mdir = Maildir(maildir_path, factory=None, create = True)
                mdir.add(message.as_string(True))
                return message_id

            try:
                self.conn.sendmail(smtp_from, smtp_to_list, message.as_string())
            finally:
                try:
                    # Close Connection of SMTP Server
                    self.conn.quit()
                except Exception:
                    # ignored, just a consequence of the previous exception
                    pass
        except Exception, e:
            msg = "Mail delivery failed via SMTP server '%s'.\n%s: %s" % (unicode(self.smtp_host),
                                                                             e.__class__.__name__,
                                                                             unicode(e))
            raise ZatoException(self.cid, msg)
        return message_id
    
    def ping(self):
        """ Pings an OE connection by logging a user in.
        """ 
        self.logger.debug('About to ping an SMTP connection:[{}]'.format(self.name))

        start_time = self.time()
        smtp = False
        smtp = self.connect(self.smtp_host, self.smtp_port, smtp_user=self.smtp_user,
                        smtp_pass=self.smtp_pass, smtp_encryption=self.smtp_encryption,
                        smtp_debug=self.smtp_debug)
        if smtp: 
            smtp.quit()
        response_time = self.time() - start_time

        self.logger.debug('Ping OK, connection:[{0}], response_time:[{1:03.4f} s]'.format(self.name, response_time))

        return response_time
    
class IMAPService(Service):
    """ Subclassing this service gives you access to the self.imap object
    which is a thin wrapper around imaplib.
    """
    def before_handle(self):
        self.imap = self
        
    def get(self, name):
        params = {
            'imap_port': 143,
            'imap_ssl': False,
        }
        missing = []
        for param in IMAP_PARAMS:
            key_prefix = IMAP_PARAMS[param]
            key = ':'.join((key_prefix, name))
            value = self.kvdb.conn.get(key)
            
            if not value and not params.get(param, False):
                missing.append(key)
            else:
                if param == 'imap_port':
                    value = int(value) 
                elif param == 'imap_ssl':
                    if value == 'True':
                        value = True
                    else:
                        value = False
                params[param] = value
                
        if missing:
            msg = 'One or more config key is missing or has no value: {}'.format(missing)
            self.logger.error(msg)
            raise ZatoException(self.cid, msg)

        client = IMAPClient(**params)
        client.connect()
        
        return client
    
    # It's the same thing right now but will be a different method when the client
    # is added to the core.
    ping = get
    
class POP3Service(Service):
    """ Subclassing this service gives you access to the self.pop3 object
    which is a thin wrapper around poplib.
    """
    def before_handle(self):
        self.pop3 = self
        
    def get(self, name):
        params = {
            'pop3_port': 110,
            'pop3_ssl': False,
        }
        missing = []
        for param in POP3_PARAMS:
            key_prefix = POP3_PARAMS[param]
            key = ':'.join((key_prefix, name))
            value = self.kvdb.conn.get(key)
            
            if not value and not params.get(param, False):
                missing.append(key)
            else:
                if param == 'pop3_port':
                    value = int(value) 
                elif param == 'pop3_ssl':
                    if value == 'True':
                        value = True
                    else:
                        value = False
                params[param] = value
                
        if missing:
            msg = 'One or more config key is missing or has no value: {}'.format(missing)
            self.logger.error(msg)
            raise ZatoException(self.cid, msg)

        client = POP3Client(**params)
        client.connect()
        
        return client
    
    # It's the same thing right now but will be a different method when the client
    # is added to the core.
    ping = get
    
class SMTPService(Service):
    """ Subclassing this service gives you access to the self.smtp object
    which is a thin wrapper around smtplib.
    """
    def before_handle(self):
        self.smtp = self
        
    def get(self, name):
        params = {
            'smtp_port': 25,
            'smtp_debug': False,
            'smtp_encryption': None,
        }
        missing = []
        for param in SMTP_PARAMS:
            key_prefix = SMTP_PARAMS[param]
            key = ':'.join((key_prefix, name))
            value = self.kvdb.conn.get(key)
            
            if not value and not params.get(param, False):
                missing.append(key)
            else:
                if param == 'smtp_port':
                    value = int(value) 
                elif param == 'smtp_debug':
                    if value == 'True':
                        value = True
                    else:
                        value = False
                params[param] = value
                
        if missing:
            msg = 'One or more config key is missing or has no value: {}'.format(missing)
            self.logger.error(msg)
            raise ZatoException(self.cid, msg)

        client = SMTPClient(**params)
        client.connect()
        
        return client
    
    # It's the same thing right now but will be a different method when the client
    # is added to the core.
    ping = get
    