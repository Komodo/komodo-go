#!/usr/bin/env python

"""Go language support for codeintel."""

import os
import sys
import json
import logging
import process
import time

try:
    from zope.cachedescriptors.property import LazyClassAttribute
except ImportError:
    import warnings
    warnings.warn("Unable to import zope.cachedescriptors.property")
    # Fallback to regular properties.
    LazyClassAttribute = property

import ciElementTree as ET
import which

import SilverCity
from SilverCity.Lexer import Lexer
from SilverCity import ScintillaConstants
from codeintel2.accessor import AccessorCache
from codeintel2.citadel import CitadelLangIntel, CitadelBuffer
from codeintel2.common import Trigger, TRG_FORM_CALLTIP, TRG_FORM_CPLN, CILEDriver, Definition, CodeIntelError
from codeintel2.langintel import ParenStyleCalltipIntelMixin, ProgLangTriggerIntelMixin, PythonCITDLExtractorMixin
from codeintel2.udl import UDLBuffer
from codeintel2.tree import tree_from_cix


try:
    from xpcom.server import UnwrapObject
    _xpcom_ = True
except ImportError:
    _xpcom_ = False


#---- globals

lang = "Go"
log = logging.getLogger("codeintel.go")
#log.setLevel(logging.DEBUG)

try:
    sys.path.append(os.path.dirname(__file__))
    from langinfo_go import GoLangInfo
except:
    class GoLangInfo:
        reserved_keywords = set([])
        predeclared_identifiers = set([])
        predeclared_functions = set([])
        default_encoding = "utf-8"
    import styles
    if not styles.StateMap.has_key(lang):
        map = styles.StateMap['C++'].copy()
        styles.addSharedStyles(map)
        styles.StateMap[lang] = map
finally:
    sys.path.pop()
    

#---- Lexer class

class GoLexer(Lexer):
    lang = lang
    def __init__(self):
        self._properties = SilverCity.PropertySet()
        self._lexer = SilverCity.find_lexer_module_by_id(ScintillaConstants.SCLEX_CPP)
        self._keyword_lists = [
            SilverCity.WordList(' '.join(sorted(GoLangInfo.reserved_keywords))),
            SilverCity.WordList(' '.join(
                            sorted(GoLangInfo.predeclared_identifiers.
                                   union(GoLangInfo.predeclared_functions)))),
        ]


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
        # if a definition lookup, use godef
        if trg.type == "defn":
            return self.lookup_defn(buf, trg, ctlr)

        # otherwise use gocode
        return self.invoke_gocode(buf, trg, ctlr)

    def lookup_defn(self, buf, trg, ctlr):
        env = buf.env
        godef_path = self._get_gotool('godef', env)
        # We can't store the path and watch prefs because this isn't a
        # true xpcom object.
        if godef_path is None:
            godef_path = 'godef'
        cmd = [godef_path, '-i=true', '-t=true', '-f=%s' % buf.path, '-o=%s' % trg.pos]
        log.debug("running [%s]", cmd)
        p = process.ProcessOpen(cmd, env=buf.env.get_all_envvars())

        output, error = p.communicate(buf.accessor.text)
        if error:
            log.debug("'gocode' stderr: [%s]", error)
            raise CodeIntelError(error)

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

        env = buf.env
        gocode_path = self._get_gotool('gocode', buf.env)
        # We can't store the path and watch prefs because this isn't a
        # true xpcom object.
        if gocode_path is None:
            gocode_path = 'gocode'
        cmd = [gocode_path, '-f=json', 'autocomplete', buf.path, '%s' % pos]
        log.debug("running [%s]", cmd)
        try:
            p = process.ProcessOpen(cmd, env=env.get_all_envvars())
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

    def _get_gotool(self, tool_name, env):
        # First try the pref
        # Then try which
        # Then try the golang pref
        # Finally try which golang
        path = [d.strip()
                for d in env.get_envvar("PATH", "").split(os.pathsep)
                if d.strip()]
        tool_path = env.get_pref(tool_name + "DefaultLocation", "")
        if tool_path and os.path.exists(tool_path):
            return tool_path
        ext = sys.platform.startswith("win") and ".exe" or ""
        golang_path = env.get_pref("golangDefaultLocation", "")
        if golang_path:
            tool_path = os.path.join(os.path.dirname(golang_dir), tool_name + ext)
            if os.path.exists(tool_path):
                return tool_path
        try:
            return which.which(tool_name, path=path)
        except which.WhichError:
            pass
        try:
            golang_path = which.which('golang', path=path)
        except which.WhichError:
            return None
        tool_path = os.path.join(os.path.basename(golang_path, tool_name)) + ext
        if os.path.exists(tool_path):
            return tool_path
        return None
        
#---- Buffer class

class GoBuffer(CitadelBuffer):
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
    _gooutline_executable_and_error = None

    @LazyClassAttribute
    def golib_dir(self):
        ext_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        return os.path.join(ext_path, "golib")

    def compile_gooutline(self, env=None):
        if self._gooutline_executable_and_error is None:
            self._gooutline_executable_and_error = (None, "Unknown Error")
            outline_src = os.path.join(self.golib_dir, "outline.go")
            # XXX - "go" should be an interpreter preference.
            cmd = ["go", "build", outline_src]
            cwd = self.golib_dir
            try:
                # Compile the executable.
                p = process.ProcessOpen(cmd, cwd=cwd, env=env, stdin=None)
                output, error = p.communicate()
                if error:
                    log.warn("'%s' stderr: [%s]", cmd, error)
                outline_exe = outline_src.rstrip(".go")
                if sys.platform.startswith("win"):
                    outline_exe += ".exe"
                # Remember the executable.
                self._gooutline_executable_and_error = (outline_exe, None)
            except Exception, ex:
                error_message = "Unable to compile 'outline.go'" + str(ex)
                self._gooutline_executable_and_error = (None, error_message)
        if self._gooutline_executable_and_error[0]:
            return self._gooutline_executable_and_error[0]
        raise CodeIntelError(self._gooutline_executable_and_error[1])

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

        env = buf.env.get_all_envvars()
        try:
            gooutline_exe_path = self.compile_gooutline(env)
        except Exception, e:
            log.error("Error compiling outline: %s", e)
            raise

        cmd = [gooutline_exe_path, buf.path]
        log.debug("running [%s]", cmd)
        try:
            p = process.ProcessOpen(cmd, env=env)
        except OSError, e:
            log.error("Error executing '%s': %s", cmd, e)
            return

        output, error = p.communicate()
        if error:
            log.warn("'%s' stderr: [%s]", cmd[0], error)

        xml = '<codeintel version="2.0">\n' + output + '</codeintel>'
        return tree_from_cix(xml)


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

