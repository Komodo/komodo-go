#!/usr/bin/env python

"""Go language support for codeintel."""

import os
import sys
import json
import logging
import process
import time
import ciElementTree as ET
from codeintel2.accessor import AccessorCache
from codeintel2.citadel import CitadelLangIntel
from codeintel2.common import Trigger, TRG_FORM_CALLTIP, TRG_FORM_CPLN, CILEDriver, Definition
from codeintel2.langintel import ParenStyleCalltipIntelMixin, ProgLangTriggerIntelMixin, PythonCITDLExtractorMixin
from codeintel2.udl import UDLBuffer


try:
    from xpcom.server import UnwrapObject
    _xpcom_ = True
except ImportError:
    _xpcom_ = False


#---- globals

lang = "Go"
log = logging.getLogger("codeintel.go")
#log.setLevel(logging.DEBUG)


#---- Lexer class

from codeintel2.udl import UDLLexer
class GoLexer(UDLLexer):
    lang = lang


#---- LangIntel class


class GoLangIntel(CitadelLangIntel,
                          ParenStyleCalltipIntelMixin,
                          ProgLangTriggerIntelMixin,
                          PythonCITDLExtractorMixin):
    lang = lang
    citdl_from_literal_type = {"string": "string"}
    calltip_trg_chars = tuple('(')
    trg_chars = tuple(" (.")
    
    completion_name_mapping = {
        'var': 'variable',
        'func': 'function',
        'package': 'module',
        'type': 'class',
        'const': 'constant',
    }

    def codeintel_type_from_completion_data(self, completion_entry):
        """Given a dictionary containing 'class' and 'type' keys return a
        codeintel type. Used for selecting icon in completion list.
        """
        completion_type = self.completion_name_mapping.get(completion_entry['class']) or completion_entry['class']
        if completion_entry['type'].startswith('[]'):
            completion_type = '@variable'
        elif completion_entry['type'].startswith('map['):
            completion_type = '%variable'
        return completion_type

    def preceding_trg_from_pos(self, buf, pos, curr_pos, preceding_trg_terminators=None, DEBUG=False):
        #DEBUG = True
        if DEBUG:
            print "pos: %d" % (pos, )
            print "ch: %r" % (buf.accessor.char_at_pos(pos), )
            print "curr_pos: %d" % (curr_pos, )

        if pos != curr_pos and self._last_trg_type == "names":
            # The last trigger type was a 3-char trigger "names", we must try
            # triggering from the same point as before to get other available
            # trigger types defined at the same poisition or before.
            trg = ProgLangTriggerIntelMixin.preceding_trg_from_pos(
                    self, buf, pos+2, curr_pos, preceding_trg_terminators,
                    DEBUG=DEBUG)
        else:
            trg = ProgLangTriggerIntelMixin.preceding_trg_from_pos(
                    self, buf, pos, curr_pos, preceding_trg_terminators,
                    DEBUG=DEBUG)

        names_trigger = None
        style = None
        if pos > 0:
            accessor = buf.accessor
            if pos == curr_pos:
                # We actually care about whats left of the cursor.
                pos -= 1
            style = accessor.style_at_pos(pos)
            if DEBUG:
                style_names = buf.style_names_from_style_num(style)
                print "  style: %s (%s)" % (style, ", ".join(style_names))
            if style in (1,2):
                ac = AccessorCache(accessor, pos)
                prev_pos, prev_ch, prev_style = ac.getPrecedingPosCharStyle(style)
                if prev_style is not None and (pos - prev_pos) > 3:
                    # We need at least 3 character for proper completion handling.
                    names_trigger = self.trg_from_pos(buf, prev_pos + 4, implicit=False)


        if DEBUG:
            print "trg: %r" % (trg, )
            print "names_trigger: %r" % (names_trigger, )
            print "last_trg_type: %r" % (self._last_trg_type, )

        if names_trigger:
            if not trg:
                trg = names_trigger
            # Two triggers, choose the best one.
            elif trg.pos == names_trigger.pos:
                if self._last_trg_type != "names":
                    # The names trigger gets priority over the other trigger
                    # types, unless the previous trigger was also a names trg.
                    trg = names_trigger
            elif trg.pos < names_trigger.pos:
                trg = names_trigger

        if trg:
            self._last_trg_type = trg.type
        return trg

    def async_eval_at_trg(self, buf, trg, ctlr):
        if _xpcom_:
            trg = UnwrapObject(trg)
            ctlr = UnwrapObject(ctlr)

        # if a definition lookup, use godef
        if trg.type == "defn":
            return self.lookup_defn(buf, trg, ctlr)

        # otherwise use gocode
        return self.invoke_gocode(buf, trg, ctlr)

    def lookup_defn(self, buf, trg, ctlr):
        cmd = ['godef', '-i=true', '-t=true', '-f=%s' % buf.path, '-o=%s' % trg.pos]
        log.debug("running [%s]", cmd)
        try:
            p = process.ProcessOpen(cmd, env=buf.env.get_all_envvars())
        except OSError, e:
            log.error("Error executing '%s': %s", cmd[0], e)
            return

        output, error = p.communicate(buf.accessor.text)
        if error:
            log.debug("'gocode' stderr: [%s]", error)
            return

        lines = output.splitlines()
        log.debug(output)

        defparts = lines[0].rsplit(":",2)

        if len(defparts) == 2:
            # current file
            path = buf.path
            line = defparts[0]
        else:
            # other file
            path = defparts[0]
            line = defparts[1]
        name, typeDesc = lines[1].split(' ', 1)

        d = Definition("Go",path,
                       blobname=None,
                       lpath=None,
                       name=name,
                       line=line,
                       ilk='function' if typeDesc.startswith('func') else typeDesc,
                       citdl=None,
                       signature=typeDesc,
                       doc='\n'.join(lines[1:]),
                    )
        log.debug(d)
        ctlr.start(buf, trg)
        ctlr.set_defns([d])
        ctlr.done("success")

    def invoke_gocode(self, buf, trg, ctlr):
        pos = trg.pos
        if trg.type == "call-signature":
            pos = pos - 1

        cmd = ['gocode', '-f=json', 'autocomplete', buf.path, '%s' % pos]
        log.debug("running [%s]", cmd)
        try:
            p = process.ProcessOpen(cmd, env=buf.env.get_all_envvars())
        except OSError, e:
            log.error("Error executing '%s': %s", cmd[0], e)
            return

        output, error = p.communicate(buf.accessor.text)
        if error:
            log.warn("'%s' stderr: [%s]", cmd[0], error)

        try:
            completion_data = json.loads(output)
            completion_data = completion_data[1]
        except IndexError:
            # exit on empty gocode output
            return
        except ValueError, e:
            log.exception('Exception while parsing json')
            return

        ctlr.start(buf, trg)
        completion_data = [x for x in completion_data if x['class'] != 'PANIC'] # remove PANIC entries if present
        if trg.type == "object-members":
            ctlr.set_cplns([(self.codeintel_type_from_completion_data(entry), entry['name']) for entry in completion_data])
            ctlr.done("success")
        elif trg.type == "call-signature":
            entry = completion_data[0]
            ctlr.set_calltips(['%s %s' % (entry['name'], entry['type'])])
            ctlr.done("success")
        elif trg.type == "any" and trg.implicit == False:
            ctlr.set_cplns([(self.codeintel_type_from_completion_data(entry), entry['name']) for entry in completion_data])
            ctlr.done("success")


#---- Buffer class

class GoBuffer(UDLBuffer):
    lang = lang
    cpln_fillup_chars = "~`!@#$%^&()-=+{}[]|\\;:'\",.<>?/ "
    cpln_stop_chars = "~`!@#$%^&*()-=+{}[]|\\;:'\",.<>?/ "
    
    ssl_lang = lang

    def trg_from_pos(self, pos, implicit=True):
        #print "XXX trg_from_pos(pos=%r)" % pos

        if pos < 2:
            return None
        accessor = self.accessor
        last_pos = pos - 1
        last_char = accessor.char_at_pos(last_pos)

        if last_char == '.': # must be "complete-object-members" or None
            return Trigger(self.lang, TRG_FORM_CPLN,
                           "object-members", pos, implicit)
        elif last_char == '(':
            return Trigger(self.lang, TRG_FORM_CALLTIP, "call-signature", pos, implicit)

        return Trigger(self.lang, TRG_FORM_CPLN, "any", pos, implicit)

#---- CILE Driver class

class GoCILEDriver(CILEDriver):
    lang = lang

    def scan_purelang(self, buf, mtime=None, lang="Go"):
        """Scan the given GoBuffer return an ElementTree (conforming
        to the CIX schema) giving a summary of its code elements.

        @param buf {GoBuffer} is the Go buffer to scan
        @param mtime {int} is a modified time for the file (in seconds since
            the "epoch"). If it is not specified the _current_ time is used.
            Note that the default is not to stat() the file and use that
            because the given content might not reflect the saved file state.
        """
        # Dev Notes:
        # - This stub implementation of the Go CILE return an "empty"
        #   summary for the given content, i.e. CIX content that says "there
        #   are no code elements in this Go content".
        # - Use the following command (in the extension source dir) to
        #   debug/test your scanner:
        #       codeintel scan -p -l Go <example-Go-file>
        #   "codeintel" is a script available in the Komodo SDK.
        log.info("scan '%s'", buf.path)
        if mtime is None:
            mtime = int(time.time())

        # The 'path' attribute must use normalized dir separators.
        if sys.platform.startswith("win"):
            path = buf.path.replace('\\', '/')
        else:
            path = buf.path

        tree = ET.Element("codeintel", version="2.0",
                          xmlns="urn:activestate:cix:2.0")
        file = ET.SubElement(tree, "file", lang=lang, mtime=str(mtime))
        blob = ET.SubElement(file, "scope", ilk="blob", lang=lang,
                             name=os.path.basename(path))

        #TODO:
        # - A 'package' -> 'blob'. Problem is a single go package can be from
        #   multiple files... so really would want `lib.get_blobs(name)` instead
        #   of `lib.get_blob(name)` in the codeintel API. How does Ruby deal with
        #   this? Perl?
        # - How do the multi-platform stdlib syscall_linux.go et al fit together?

        # Dev Note:
        # This is where you process the Go content and add CIX elements
        # to 'blob' as per the CIX schema (cix-2.0.rng). Use the
        # "buf.accessor" API (see class Accessor in codeintel2.accessor) to
        # analyze. For example:
        # - A token stream of the content is available via:
        #       buf.accessor.gen_tokens()
        #   Use the "codeintel html -b <example-Go-file>" command as
        #   a debugging tool.
        # - "buf.accessor.text" is the whole content of the file. If you have
        #   a separate tokenizer/scanner tool for Go content, you may
        #   want to use it.

        return tree



#---- registration

def register(mgr):
    """Register language support with the Manager."""
    mgr.set_lang_info(
        lang,
        silvercity_lexer=GoLexer(),
        buf_class=GoBuffer,
        langintel_class=GoLangIntel,
        import_handler_class=None,
        cile_driver_class=GoCILEDriver,
        is_cpln_lang=True)

