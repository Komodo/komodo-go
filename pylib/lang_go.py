#!/usr/bin/env python

"""Go language support for codeintel."""

import json
import logging
import process
import koprocessutils
from codeintel2.accessor import AccessorCache
from codeintel2.citadel import CitadelLangIntel
from codeintel2.common import Trigger, TRG_FORM_CALLTIP, TRG_FORM_CPLN, CILEDriver
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

    def __init__(self, *args, **kwargs):
        self.gocode_present = self.check_for_gocode()

    def check_for_gocode(self):
        try:
            env = koprocessutils.getUserEnv()
            process.ProcessOpen(['gocode'], env=env)
            return True
        except OSError:
            log.error('"gocode" binary not found, cannot offer completion for golang.')
            return False
        
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

        if not self.gocode_present:
            return

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
        if not self.gocode_present:
            return
        if _xpcom_:
            trg = UnwrapObject(trg)
            ctlr = UnwrapObject(ctlr)
        
        pos = trg.pos
        if trg.type == "call-signature":
            pos = pos - 1

        env = koprocessutils.getUserEnv()
        cmd = ['gocode', '-f=json', 'autocomplete', buf.path, '%s' % pos]
        p = process.ProcessOpen(cmd, env=env)

        output, error = p.communicate(buf.accessor.text)
        
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

    def scan_purelang(self, buf):
        import cile_go
        return cile_go.scan_buf(buf)




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
        # Dev Note: set to false if this language does not support
        # autocomplete/calltips.
        is_cpln_lang=True)

