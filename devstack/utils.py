# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright (C) 2012 Yahoo! Inc. All Rights Reserved.
#
#    Copyright 2011 OpenStack LLC.
#    All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import contextlib
import os
import random
import re
import socket
import sys
import tempfile

import distutils.version
import netifaces
import progressbar
import termcolor

from devstack import colorlog
from devstack import exceptions as excp
from devstack import log as logging
from devstack import settings
from devstack import shell as sh
from devstack import version

# The pattern will match either a comment to the EOL, or a
# token to be subbed. The replacer will check which it got and
# act accordingly. Note that we need the MULTILINE flag
# for the comment checks to work in a string containing newlines
PARAM_SUB_REGEX = re.compile(r"#.*$|%([\w\d]+?)%", re.MULTILINE)
EXT_COMPONENT = re.compile(r"^\s*([\w-]+)(?:\((.*)\))?\s*$")
MONTY_PYTHON_TEXT_RE = re.compile("([a-z0-9A-Z\?!.,'\"]+)")
LOG = logging.getLogger("devstack.util")
DEF_IP = "127.0.0.1"
IP_LOOKER = '8.8.8.8'
DEF_IP_VERSION = settings.IPV4
PRIVATE_OCTS = []
ALL_NUMS = re.compile(r"^\d+$")
START_NUMS = re.compile(r"^(\d+)(\D+)")
STAR_VERSION = 0

# Thx cowsay
# See: http://www.nog.net/~tony/warez/cowsay.shtml
COWS = dict()
COWS['happy'] = r'''
{header}
        \   {ear}__{ear}
         \  ({eye}{eye})\_______
            (__)\       )\/\
                ||----w |
                ||     ||
'''
COWS['unhappy'] = r'''
{header}
  \         ||       ||
    \    __ ||-----mm||
      \ (  )/_________)//
        ({eye}{eye})/
        {ear}--{ear}
'''


def configure_logging(verbosity_level=1, dry_run=False):

    # Debug by default
    root_logger = logging.getLogger().logger
    root_logger.setLevel(logging.DEBUG)

    # Set our pretty logger
    console_logger = logging.StreamHandler(sys.stdout)
    console_format = '%(levelname)s: @%(name)s : %(message)s'
    if sh.in_terminal():
        console_logger.setFormatter(colorlog.TermFormatter(console_format))
    else:
        console_logger.setFormatter(logging.Formatter(console_format))
    root_logger.addHandler(console_logger)

    # Adjust logging verbose level based on the command line switch.
    log_level = logging.INFO
    if verbosity_level >= 3:
        log_level = logging.DEBUG
    elif verbosity_level == 2 or dry_run:
        log_level = logging.AUDIT
    root_logger.setLevel(log_level)


def load_template(component, template_name):
    full_pth = sh.joinpths(settings.STACK_TEMPLATE_DIR, component, template_name)
    contents = sh.load_file(full_pth)
    return (full_pth, contents)


def execute_template(*cmds, **kargs):
    params_replacements = kargs.pop('params', None)
    ignore_missing = kargs.pop('ignore_missing', False)
    cmd_results = list()
    for cmdinfo in cmds:
        cmd_to_run_templ = cmdinfo["cmd"]
        cmd_to_run = param_replace_list(cmd_to_run_templ, params_replacements, ignore_missing)
        stdin_templ = cmdinfo.get('stdin')
        stdin = None
        if stdin_templ:
            stdin_full = param_replace_list(stdin_templ, params_replacements, ignore_missing)
            stdin = joinlinesep(*stdin_full)
        exec_result = sh.execute(*cmd_to_run,
                                 run_as_root=cmdinfo.get('run_as_root', False),
                                 process_input=stdin,
                                 ignore_exit_code=cmdinfo.get('ignore_failure', False),
                                 **kargs)
        cmd_results.append(exec_result)
    return cmd_results


def to_bytes(text):
    byte_val = 0
    if not text:
        return byte_val
    if text[-1].upper() == 'G':
        byte_val = int(text[:-1]) * 1024 ** 3
    elif text[-1].upper() == 'M':
        byte_val = int(text[:-1]) * 1024 ** 2
    elif text[-1].upper() == 'K':
        byte_val = int(text[:-1]) * 1024
    elif text[-1].upper() == 'B':
        byte_val = int(text[:-1])
    else:
        byte_val = int(text)
    return byte_val


@contextlib.contextmanager
def progress_bar(name, max_am, reverse=False):
    widgets = list()
    widgets.append('%s: ' % (name))
    widgets.append(progressbar.Percentage())
    widgets.append(' ')
    if reverse:
        widgets.append(progressbar.ReverseBar())
    else:
        widgets.append(progressbar.Bar())
    widgets.append(' ')
    widgets.append(progressbar.ETA())
    p_bar = progressbar.ProgressBar(maxval=max_am, widgets=widgets)
    p_bar.start()
    try:
        yield p_bar
    finally:
        p_bar.finish()


@contextlib.contextmanager
def tempdir():
    # This seems like it was only added in python 3.2
    # Make it since its useful...
    tdir = tempfile.mkdtemp()
    try:
        yield tdir
    finally:
        sh.deldir(tdir)


def import_module(module_name, quiet=True):
    try:
        __import__(module_name)
        return sys.modules.get(module_name, None)
    except ImportError:
        if quiet:
            return None
        else:
            raise


def versionize(input_version):
    segments = input_version.split(".")
    cleaned_segments = list()
    for piece in segments:
        piece = piece.strip()
        if len(piece) == 0:
            msg = "Disallowed empty version segment found"
            raise ValueError(msg)
        piece = piece.strip("*")
        if len(piece) == 0:
            cleaned_segments.append(STAR_VERSION)
        elif ALL_NUMS.match(piece):
            cleaned_segments.append(int(piece))
        else:
            piece_match = START_NUMS.match(piece)
            if not piece_match:
                msg = "Unknown version identifier %s" % (piece)
                raise ValueError(msg)
            else:
                cleaned_segments.append(int(piece_match.group(1)))
    if not cleaned_segments:
        msg = "Disallowed empty version found"
        raise ValueError(msg)
    num_parts = [str(p) for p in cleaned_segments]
    return distutils.version.LooseVersion(".".join(num_parts))


def sort_versions(versions, descending=True):
    if not versions:
        return list()
    version_cleaned = list()
    for v in versions:
        version_cleaned.append(versionize(v))
    versions_sorted = sorted(version_cleaned)
    if not descending:
        versions_sorted.reverse()
    return versions_sorted


def get_host_ip():
    """
    Returns the actual ip of the local machine.

    This code figures out what source address would be used if some traffic
    were to be sent out to some well known address on the Internet. In this
    case, a private address is used, but the specific address does not
    matter much.  No traffic is actually sent.

    Adjusted from nova code...
    """
    ip = None
    try:
        csock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        csock.connect((IP_LOOKER, 80))
        (addr, _) = csock.getsockname()
        csock.close()
        ip = addr
    except socket.error:
        pass
    # Ettempt to find it
    if not ip:
        interfaces = get_interfaces()
        for (_, net_info) in interfaces.items():
            ip_info = net_info.get(DEF_IP_VERSION)
            if ip_info:
                a_ip = ip_info.get('addr') or ""
                first_oct = a_ip.split(".")[0]
                if first_oct and first_oct not in PRIVATE_OCTS:
                    ip = a_ip
                    break
    # Just return a localhost version then
    if not ip:
        ip = DEF_IP
    return ip


def is_interface(intfc):
    if intfc in get_interfaces():
        return True
    return False


def get_interfaces():
    interfaces = dict()
    for intfc in netifaces.interfaces():
        interface_info = dict()
        interface_addresses = netifaces.ifaddresses(intfc)
        ip6 = interface_addresses.get(netifaces.AF_INET6)
        if ip6 and len(ip6):
            # Just take the first
            interface_info[settings.IPV6] = ip6[0]
        ip4 = interface_addresses.get(netifaces.AF_INET)
        if ip4 and len(ip4):
            # Just take the first
            interface_info[settings.IPV4] = ip4[0]
        # Note: there are others but this is good for now..
        interfaces[intfc] = interface_info
    return interfaces


def format_secs_taken(secs):
    output = "%.03f seconds" % (secs)
    output += " or %.02f minutes" % (secs / 60.0)
    return output


def joinlinesep(*pieces):
    return os.linesep.join(pieces)


def param_replace_list(values, replacements, ignore_missing=False):
    new_values = list()
    if not values:
        return new_values
    for v in values:
        if v is not None:
            new_values.append(param_replace(str(v), replacements, ignore_missing))
    return new_values


def find_params(text):
    params_found = set()
    if not text:
        return params_found

    def finder(match):
        org_txt = match.group(0)
        # Check if it's a comment, if so just return what it was and ignore
        # any tokens that were there
        if org_txt.startswith("#"):
            return org_txt
        param_name = match.group(1)
        if param_name not in params_found:
            params_found.add(param_name)
        return org_txt

    PARAM_SUB_REGEX.sub(finder, text)
    return params_found


def param_replace(text, replacements, ignore_missing=False):

    if not replacements:
        replacements = dict()

    if not text:
        return ""

    if ignore_missing:
        LOG.debug("Performing parameter replacements (ignoring missing) on text [%s]" % (text))
    else:
        LOG.debug("Performing parameter replacements (not ignoring missing) on text [%s]" % (text))

    possible_params = find_params(text)
    LOG.debug("Possible replacements are [%s]" % (", ".join(possible_params)))

    def replacer(match):
        org_txt = match.group(0)
        param_name = match.group(1)
        # Check if it's a comment, if so just return what it was and ignore
        # any tokens that were there
        if org_txt.startswith('#'):
            LOG.debug("Ignoring comment line")
            return org_txt
        replacer = replacements.get(param_name)
        if replacer is None and ignore_missing:
            replacer = org_txt
        elif replacer is None and not ignore_missing:
            msg = "No replacement found for parameter %s" % (org_txt)
            raise excp.NoReplacementException(msg)
        else:
            replacer = str(replacer)
            LOG.debug("Replacing [%s] with [%s]" % (org_txt, replacer))
        return replacer

    replaced_text = PARAM_SUB_REGEX.sub(replacer, text)
    LOG.debug("Replacement/s resulted in text [%s]" % (replaced_text))
    return replaced_text


def _get_welcome_stack():
    possibles = list()
    # Thank you figlet ;)
    # See: http://www.figlet.org/
    possibles.append(r'''
  ___  ____  _____ _   _ ____ _____  _    ____ _  __
 / _ \|  _ \| ____| \ | / ___|_   _|/ \  / ___| |/ /
| | | | |_) |  _| |  \| \___ \ | | / _ \| |   | ' /
| |_| |  __/| |___| |\  |___) || |/ ___ \ |___| . \
 \___/|_|   |_____|_| \_|____/ |_/_/   \_\____|_|\_\

''')
    possibles.append(r'''
  ___  ___ ___ _  _ ___ _____ _   ___ _  __
 / _ \| _ \ __| \| / __|_   _/_\ / __| |/ /
| (_) |  _/ _|| .` \__ \ | |/ _ \ (__| ' <
 \___/|_| |___|_|\_|___/ |_/_/ \_\___|_|\_\

''')
    possibles.append(r'''
____ ___  ____ _  _ ____ ___ ____ ____ _  _
|  | |__] |___ |\ | [__   |  |__| |    |_/
|__| |    |___ | \| ___]  |  |  | |___ | \_

''')
    possibles.append(r'''
  _  ___ ___  _  _  __  ___  _   __  _  _
 / \| o \ __|| \| |/ _||_ _|/ \ / _|| |//
( o )  _/ _| | \\ |\_ \ | || o ( (_ |  (
 \_/|_| |___||_|\_||__/ |_||_n_|\__||_|\\

''')
    possibles.append(r'''
   _   ___  ___  _  __  ___ _____  _    __  _
 ,' \ / o |/ _/ / |/ /,' _//_  _/.' \ ,'_/ / //7
/ o |/ _,'/ _/ / || /_\ `.  / / / o // /_ /  ,'
|_,'/_/  /___//_/|_//___,' /_/ /_n_/ |__//_/\\

''')
    possibles.append(r'''
 _____  ___    ___    _   _  ___   _____  _____  ___    _   _
(  _  )(  _`\ (  _`\ ( ) ( )(  _`\(_   _)(  _  )(  _`\ ( ) ( )
| ( ) || |_) )| (_(_)| `\| || (_(_) | |  | (_) || ( (_)| |/'/'
| | | || ,__/'|  _)_ | , ` |`\__ \  | |  |  _  || |  _ | , <
| (_) || |    | (_( )| |`\ |( )_) | | |  | | | || (_( )| |\`\
(_____)(_)    (____/'(_) (_)`\____) (_)  (_) (_)(____/'(_) (_)

''')
    return random.choice(possibles).strip("\n\r")


def center_text(text, fill, max_len):
    centered_str = '{0:{fill}{align}{size}}'.format(text, fill=fill, align="^", size=max_len)
    return centered_str


def _welcome_slang():
    potentials = list()
    potentials.append("And now for something completely different!")
    return random.choice(potentials)


def color_text(text, color, bold=False,
                    underline=False, blink=False,
                    always_color=False):
    text_attrs = list()
    if bold:
        text_attrs.append('bold')
    if underline:
        text_attrs.append('underline')
    if blink:
        text_attrs.append('blink')
    if sh.in_terminal() or always_color:
        return termcolor.colored(text, color, attrs=text_attrs)
    else:
        return text


def _color_blob(text, text_color):

    def replacer(match):
        contents = match.group(1)
        return color_text(contents, text_color)

    return MONTY_PYTHON_TEXT_RE.sub(replacer, text)


def _goodbye_header(worked):
    # Cowsay headers
    # See: http://www.nog.net/~tony/warez/cowsay.shtml
    potentials_oks = list()
    potentials_oks.append(r'''
 ___________
/ You shine \
| out like  |
| a shaft   |
| of gold   |
| when all  |
| around is |
\ dark.     /
 -----------
''')
    potentials_oks.append(r'''
 ______________________________
< I'm a lumberjack and I'm OK. >
 ------------------------------
''')
    potentials_oks.append(r'''
 ____________________
/ Australia!         \
| Australia!         |
| Australia!         |
\ We love you, amen. /
 --------------------
''')
    potentials_oks.append(r'''
 ______________
/ Say no more, \
| Nudge nudge  |
\ wink wink.   /
 --------------
''')
    potentials_oks.append(r'''
 ________________
/ And there was  \
\ much rejoicing /
 ----------------
''')
    potentials_oks.append(r'''
 __________
< Success! >
 ----------''')
    potentials_fails = list()
    potentials_fails.append(r'''
 __________
< Failure! >
 ----------
''')
    potentials_fails.append(r'''
 ___________
< Run away! >
 -----------
''')
    potentials_fails.append(r'''
 ______________________
/ NOBODY expects the   \
\ Spanish Inquisition! /
 ----------------------
''')
    potentials_fails.append(r'''
 ______________________
/ Spam spam spam spam  \
\ baked beans and spam /
 ----------------------
''')
    potentials_fails.append(r'''
 ____________________
/ Brave Sir Robin    \
\ ran away.          /
 --------------------
''')
    potentials_fails.append(r'''
 _______________________
< Message for you, sir. >
 -----------------------
''')
    potentials_fails.append(r'''
 ____________________
/ We are the knights \
\ who say.... NI!    /
 --------------------
''')
    potentials_fails.append(r'''
 ____________________
/ Now go away or I   \
| shall taunt you a  |
\ second time.       /
 --------------------
''')
    potentials_fails.append(r'''
 ____________________
/ It's time for the  \
| penguin on top of  |
| your television to |
\ explode.           /
 --------------------
''')
    potentials_fails.append(r'''
 _____________________
/ We were in the nick \
| of time. You were   |
\ in great peril.     /
 ---------------------
''')
    potentials_fails.append(r'''
 ___________________
/ I know a dead     \
| parrot when I see |
| one, and I'm      |
| looking at one    |
\ right now.        /
 -------------------
''')
    potentials_fails.append(r'''
 _________________
/ Welcome to the  \
| National Cheese |
\ Emporium        /
 -----------------
''')
    potentials_fails.append(r'''
 ______________________
/ What is the airspeed \
| velocity of an       |
\ unladen swallow?     /
 ----------------------
''')
    potentials_fails.append(r'''
 ______________________
/ Now stand aside,     \
\ worthy adversary.    /
 ----------------------
''')
    potentials_fails.append(r'''
 ___________________
/ Okay, we'll call  \
\ it a draw.        /
 -------------------
''')
    potentials_fails.append(r'''
 _______________
/ She turned me \
\ into a newt!  /
 ---------------
''')
    potentials_fails.append(r'''
 ___________________
< Fetchez la vache! >
 -------------------
''')
    potentials_fails.append(r'''
 __________________________
/ We'd better not risk     \
| another frontal assault, |
\ that rabbit's dynamite.  /
 --------------------------
''')
    potentials_fails.append(r'''
 ______________________
/ This is supposed to  \
| be a happy occasion. |
| Let's not bicker and |
| argue about who      |
\ killed who.          /
 ----------------------
''')
    potentials_fails.append(r'''
 _______________________
< You have been borked. >
 -----------------------
''')
    potentials_fails.append(r'''
 __________________
/ We used to dream  \
| of living in a    |
\ corridor!         /
 -------------------
''')
    if not worked:
        msg = random.choice(potentials_fails).strip("\n\r")
        colored_msg = _color_blob(msg, 'red')
    else:
        msg = random.choice(potentials_oks).strip("\n\r")
        colored_msg = _color_blob(msg, 'green')
    return colored_msg


def goodbye(worked):
    if worked:
        cow = COWS['happy']
        eye_fmt = color_text('o', 'green')
        ear = color_text("^", 'green')
    else:
        cow = COWS['unhappy']
        eye_fmt = color_text("o", 'red')
        ear = color_text("v", 'red')
    cow = cow.strip("\n\r")
    header = _goodbye_header(worked)
    msg = cow.format(eye=eye_fmt, ear=ear,
                     header=header)
    print(msg)


def welcome(ident):
    lower = "| %s %s |" % (ident, version.version_string())
    welcome_header = _get_welcome_stack()
    max_line_len = len(max(welcome_header.splitlines(), key=len))
    footer = color_text(settings.PROG_NICE_NAME, 'green')
    footer += ": "
    footer += color_text(lower, 'blue', True)
    uncolored_footer = (settings.PROG_NICE_NAME + ": " + lower)
    if max_line_len - len(uncolored_footer) > 0:
        # This format string will center the uncolored text which
        # we will then replace with the color text equivalent.
        centered_str = center_text(uncolored_footer, " ", max_line_len)
        footer = centered_str.replace(uncolored_footer, footer)
    print(welcome_header)
    print(footer)
    real_max = max(max_line_len, len(uncolored_footer))
    slang = center_text(_welcome_slang(), ' ', real_max)
    print(color_text(slang, 'magenta', bold=True))
    return ("-", real_max)
