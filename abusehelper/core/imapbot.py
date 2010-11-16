import re
import socket
import getpass
import imaplib
import email.parser

from cStringIO import StringIO
from abusehelper.core import events, bot, services
from idiokit import threado, timer

@threado.stream
def thread(inner, call, *args, **keys):
    thread = inner.thread(call, *args, **keys)
    while not thread.has_result():
        yield inner, thread
    inner.finish(thread.result())

@threado.stream
def collect(inner):
    collection = list()
    try:
        while True:
            item = yield inner
            collection.append(item)
    except threado.Finished:
        inner.finish(collection)

class IMAPBot(bot.FeedBot):
    poll_interval = bot.IntParam(default=300)
    filter = bot.Param(default="(UNSEEN)")

    mail_server = bot.Param()
    mail_port = bot.IntParam(default=993)
    mail_user = bot.Param()
    mail_password = bot.Param(default=None)
    mail_box = bot.Param(default="INBOX")

    def __init__(self, **keys):
        bot.FeedBot.__init__(self, **keys)

        if self.mail_password is None:
            self.mail_password = getpass.getpass("Mail password: ")
        self.queue = threado.Channel()

    @threado.stream
    def feed(inner, self):
        yield inner.sub(self.run_mailbox() | self.noop() | self.poll())

    # Mailbox handling

    @threado.stream
    def run_mailbox(inner, self, min_delay=5.0, max_delay=60.0):
        mailbox = None

        try:
            while True:
                item = yield inner, self.queue
                if inner.was_source:
                    continue
                for _ in inner:
                    pass

                while True:
                    delay = min(min_delay, max_delay)
                    while mailbox is None:
                        try:
                            mailbox = yield inner.sub(thread(self.connect))
                        except (imaplib.IMAP4.abort, socket.error), error:
                            self.log.error("Failed IMAP connection: %r", error)
                        else:
                            break
                        
                        self.log.info("Retrying connection in %.02f seconds", delay)
                        yield inner, timer.sleep(delay)
                        delay = min(2 * delay, max_delay)
                            
                    channel, name, args, keys = item
                    if channel.has_result():
                        break

                    try:
                        method = getattr(mailbox, name)
                        result = yield inner.sub(thread(method, *args, **keys))
                    except (imaplib.IMAP4.abort, socket.error), error:
                        yield inner.sub(thread(self.disconnect, mailbox))
                        self.log.error("Lost IMAP connection: %r", error)
                        mailbox = None
                    except imaplib.IMAP4.error:
                        channel.rethrow()
                        break
                    else:
                        channel.finish(result)
                        break
        finally:
            if mailbox is not None:
                yield inner.sub(thread(self.disconnect, mailbox))

    def connect(self):
        self.log.info("Connecting to IMAP server %r port %d",
                      self.mail_server, self.mail_port)
        mailbox = imaplib.IMAP4_SSL(self.mail_server, self.mail_port)
        
        self.log.info("Logging in to IMAP server %s port %d",
                      self.mail_server, self.mail_port)
        mailbox.login(self.mail_user, self.mail_password)
        try:
            status, msgs = mailbox.select(self.mail_box, readonly=False)

            if status != "OK":
                for msg in msgs:
                    raise imaplib.IMAP4.abort(msg)
        except:
            mailbox.logout()
            raise

        self.log.info("Logged in to IMAP server %s port %d",
                      self.mail_server, self.mail_port)
        return mailbox

    def disconnect(self, mailbox):
        try:
            mailbox.close()
        except (imaplib.IMAP4.error, socket.error):
            pass

        try:
            mailbox.logout()
        except (imaplib.IMAP4.error, socket.error):
            pass

    @threado.stream
    def call(inner, self, name, *args, **keys):
        channel = threado.Channel()
        self.queue.send(channel, name, args, keys)
        
        try:
            while not channel.has_result():
                yield inner, channel
                for _ in inner: pass
        except:
            raise
        else:
            inner.finish(channel.result())
        finally:
            channel.finish()

    # Keep-alive

    @threado.stream
    def noop(inner, self, noop_interval=10.0):
        while True:
            yield inner.sub(self.call("noop"))
            yield inner, timer.sleep(noop_interval)

    # Main polling

    @threado.stream
    def poll(inner, self):
        while True:
            yield inner.sub(self.fetch_mails(self.filter))
            yield inner, timer.sleep(self.poll_interval)

    @threado.stream
    def get_header(inner, self, uid, section):
        body_rex_str = r"\s*\d+\s+\(UID %s\s+BODY\[%s\]\s+" % (uid, section)
        body_rex = re.compile(body_rex_str, re.I)
        
        fetch = "(UID BODY.PEEK[%s])" % section
        result, data = yield inner.sub(self.call("uid", "FETCH", uid, fetch))

        # Filter away parts that don't closely enough resemble tuple
        # ("<MSGNUM> (UID <MSGUID> BODY[<SECTION>] {<SIZE>}", "<HEADERS>")
        data = [x for x in data if isinstance(x, tuple) and len(x) >= 2]
        data = [x[1] for x in data if body_rex.match(x[0])]

        # Accept only non-empty header data
        data = [x for x in data if x]
        if not data:
            inner.finish()
        inner.finish(email.parser.Parser().parsestr(data[0], headersonly=True))

    def fetcher(self, uid, path):
        @threado.stream
        def fetch(inner):
            fetch = "(BODY.PEEK[%s])" % path
            result, data = yield inner.sub(self.call("uid", "FETCH", uid, fetch))
            
            for parts in data:
                if not isinstance(parts, tuple) or len(parts) != 2:
                    continue
                reader = StringIO(parts[1])
                inner.finish(StringIO(parts[1]))
        return fetch

    @threado.stream
    def walk_mail(inner, self, uid, path=(), headers=[]):
        if not path:
            header = yield inner.sub(self.get_header(uid, "HEADER"))
            if header is None:
                return
            headers = headers + [header]

        path = list(path) + [0]
        while True:
            path[-1] += 1
            path_str = ".".join(map(str, path))        

            header = yield inner.sub(self.get_header(uid, path_str + ".MIME"))
            if header is None:
                return

            if header.get_content_maintype() == "multipart":
                yield inner.sub(self.walk_mail(uid, path, headers + [header]))
            else:
                inner.send(path_str, tuple(headers + [header]))

    @threado.stream
    def fetch_mails(inner, self, filter):
        result, data = yield inner.sub(self.call("uid", "SEARCH", None, filter))
        if not data or not data[0]:
            return

        for uid in data[0].split():
            collected = yield inner.sub(self.walk_mail(uid) | collect())

            parts = list()
            for path, headers in collected:
                parts.append((headers, self.fetcher(uid, path)))
                
            if parts:
                top_header = parts[0][0][0]
                subject = top_header["Subject"] or "<no subject>"
                sender = top_header["From"] or "<unknown sender>"
                self.log.info("Handling mail %r from %r", subject, sender)
                yield inner.sub(self.handle(parts))
                self.log.info("Done with mail %r from %r", subject, sender)

            # UID STORE command flags have to be in parentheses, otherwise
            # imaplib quotes them, which is not allowed.
            yield inner.sub(self.call("uid", "STORE", uid, "+FLAGS", "(\\Seen)"))

    @threado.stream
    def handle(inner, self, parts):
        handle_default = getattr(self, "handle_default", None)

        for headers, fetch in parts:
            content_type = headers[-1].get_content_type()
            suffix = content_type.replace("-", "__").replace("/", "_")

            handler = getattr(self, "handle_" + suffix, handle_default)
            if handler is None:
                continue

            fileobj = yield inner.sub(fetch())
            skip_rest = yield inner.sub(handler(headers, fileobj))
            if skip_rest:
                return

# Warning: The code below is deprecated and preserved only for
# compatibility purposes. Use shadowservermail for running standalone
# ShadowServer mail bots, and use IMAPBot class for subclassing.

import warnings

class IMAPService(IMAPBot):
    filter = bot.Param(default=r'(BODY "http://" UNSEEN)')
    url_rex = bot.Param(default=r"http://\S+")
    filename_rex = bot.Param(default=r"(?P<eventfile>.*)")
    
    def __init__(self, *args, **keys):
        warnings.warn("IMAPService is deprecated. Use shadowservermail "+
                      "module for running ShadowServer mail bots instead, "+
                      "and use IMAPBot class for subclassing.",
                      DeprecationWarning, stacklevel=3)

        # A hack to avoid problems with cyclical imports.
        from abusehelper.core import shadowservermail
        IMAPService.__bases__ = (shadowservermail.ShadowServerMail,)

        super(IMAPService, self).__init__(*args, **keys)

if __name__ == "__main__":
    warnings.warn("Running imapbot module as a standalone bot is deprecated. "+
                  "Use shadowservermail module instead.",
                  DeprecationWarning, stacklevel=2)
    IMAPService.from_command_line().execute()
