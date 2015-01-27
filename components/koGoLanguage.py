#!python
# Copyright (c) 2001-2014 ActiveState Software Inc.
# See the file LICENSE.txt for licensing information.

"""Go-specific Language Services implementations."""

import tempfile
import logging
import os
from os.path import exists
import re

import koprocessutils
import process
from xpcom import components, ServerException
from langinfo_go import GoLangInfo
from koLanguageServiceBase import KoLanguageBase, KoLexerLanguageService, \
                                  FastCharData, KoLanguageBaseDedentMixin
from koLintResult import KoLintResult, SEV_ERROR
from koLintResults import koLintResults

log = logging.getLogger('koGoLanguage')
#log.setLevel(logging.DEBUG)

sci_constants = components.interfaces.ISciMoz

class koGoLanguage(KoLanguageBase, KoLanguageBaseDedentMixin):
    name = "Go"
    _reg_desc_ = "%s Language" % name
    _reg_contractid_ = "@activestate.com/koLanguage?language=%s;1" \
                       % (name)
    _reg_clsid_ = "{2d6ed8b6-f079-441a-8b5a-10ef781cb989}"
    _reg_categories_ = [("komodo-language", name)]
    _com_interfaces_ = KoLanguageBase._com_interfaces_ + \
                       [components.interfaces.koIInterpolationCallback]

    modeNames = ['go']
    primary = 1
    internal = 0
    accessKey = 'g'
    defaultExtension = ".go"
    commentDelimiterInfo = {
        "line": [ "//" ],
        "block": [ ("/*", "*/") ],
        "markup": "*",
    }
    _dedenting_statements = [u'goto', u'return', u'break', u'continue']
    
    namedBlockRE = "^[ \t]*?(func\s+(?:\(.*?\)\s*)?\w|package\s+\w)"
    namedBlockDescription = 'Go functions, methods and packages'
    supportsSmartIndent = "brace"
    # The following sample contains embedded tabs because that's the Go way.
    sample = r"""\
package commands

import (
	"encoding/json"
)
type Filters []string
func (f *Filters) String() string {
	a := "a string"
	b := 'c' // a char
	c := 43 // a num
	return fmt.Sprint(*f)
}
/* Block comment
on these two lines */
    """

    def __init__(self):
        KoLanguageBase.__init__(self)
        self._style_info.update(
            _block_comment_styles = [sci_constants.SCE_C_COMMENT,
                                     sci_constants.SCE_C_COMMENTDOC,
                                     sci_constants.SCE_C_COMMENTDOCKEYWORD,
                                     sci_constants.SCE_C_COMMENTDOCKEYWORDERROR],
            _variable_styles = [components.interfaces.ISciMoz.SCE_C_IDENTIFIER]
            )
        self._setupIndentCheckSoftChar()
        self._fastCharData = \
            FastCharData(trigger_char=";",
                         style_list=(sci_constants.SCE_C_OPERATOR,),
                         skippable_chars_by_style={ sci_constants.SCE_C_OPERATOR : "])",},
                         for_check=True)
        # And add the new default prefs if they don't exist
        globalPrefs = components.classes["@activestate.com/koPrefService;1"]\
                          .getService(components.interfaces.koIPrefService).prefs
        # Chunk adding prefs based on which ones they were added with.
        if not globalPrefs.hasPref("gocodeDefaultLocation"):
            globalPrefs.setStringPref("gocodeDefaultLocation", "")
        if not globalPrefs.hasPref("godefDefaultLocation"):
            globalPrefs.setStringPref("godefDefaultLocation", "")
        if not globalPrefs.hasPref("golangDefaultLocation"):
            globalPrefs.setStringPref("golangDefaultLocation", "")
            globalPrefs.setStringPref("Go/newEncoding", "utf-8")
            globalPrefs.setLongPref("Go/indentWidth", 8)
            globalPrefs.setBooleanPref("Go/useTabs", True)

        # Add the go formatter.
        if not globalPrefs.getBoolean("haveInstalledGoFormatter", False):
            formatters = globalPrefs.getPref("configuredFormatters")
            go_formatter_prefset = components.classes['@activestate.com/koPreferenceSet;1'].createInstance(components.interfaces.koIPreferenceSet)
            uuid = "{cf500001-ec59-4047-86e7-369d257f4b80}"
            go_formatter_prefset.id = uuid
            go_formatter_prefset.setStringPref("lang", "Go")
            go_formatter_prefset.setStringPref("name", "GoFmt")
            go_formatter_prefset.setStringPref("uuid", uuid)
            go_formatter_prefset.setStringPref("formatter_name", "generic")
            args_prefset = components.classes['@activestate.com/koPreferenceSet;1'].createInstance(components.interfaces.koIPreferenceSet)
            args_prefset.id = "genericFormatterPrefs"
            args_prefset.setStringPref("executable", "%(go)")
            args_prefset.setStringPref("arguments", "fmt")
            go_formatter_prefset.setPref("genericFormatterPrefs", args_prefset)
            formatters.appendString(uuid)
            globalPrefs.setPref(uuid, go_formatter_prefset)
            globalPrefs.setBoolean("haveInstalledGoFormatter", True)

        # Add extensible items.
        interpolateSvc = components.classes["@activestate.com/koInterpolationService;1"].\
                            getService(components.interfaces.koIInterpolationService)
        try:
            interpolateSvc.addCode('go', self)
        except Exception:
            log.warn("Unable to add 'go' interpolation shortcut")

    def interpolationCallback(self, code, fileName, lineNum, word, selection,
                              projectFile, prefs):
        if code == 'go':
            golangInfoEx = components.classes["@activestate.com/koAppInfoEx?app=Go;1"].\
                        getService(components.interfaces.koIAppInfoEx)
            return golangInfoEx.executablePath
        raise RuntimeError("Unexpected go code %r" % (code, ))

    def getLanguageService(self, iid):
        return KoLanguageBase.getLanguageService(self, iid)

    def get_lexer(self):
        if self._lexer is None:
            self._lexer = KoLexerLanguageService()
            self._lexer.setLexer(components.interfaces.ISciMoz.SCLEX_CPP)
            self._lexer.supportsFolding = 1
            self._lexer.setProperty('lexer.cpp.allow.dollars', '0')
            self._lexer.setProperty('fold.cpp.syntax.based', '1')
            self._lexer.setProperty('lexer.cpp.backquoted.strings', '1')
            self._lexer.setKeywords(0, GoLangInfo.reserved_keywords)
            # The CPP lexer reserves keywords(2) for comment doc keywords and
            # keywords(3) for "SCE_C_GLOBALCLASS", so treat the
            # predeclared_identifiers (like 'bool') and
            # the predefined_functions (like 'append') as the same.
            other_words = (GoLangInfo.predeclared_identifiers.
                           union(GoLangInfo.predeclared_functions))
            self._lexer.setKeywords(1, other_words)
        return self._lexer

class KoGolangLinter(object):
    _com_interfaces_ = [components.interfaces.koILinter,
                        components.interfaces.nsIObserver]
    _reg_clsid_ = "{5bd15d0e-4763-435b-a936-00a7921f9bf9}"
    _reg_contractid_ = "@activestate.com/koLinter?language=Go;1"
    _reg_categories_ = [
         ("category-komodo-linter", 'Go'),
         ]
    
    def __init__(self):
        self.golangInfoEx = components.classes["@activestate.com/koAppInfoEx?app=Go;1"].\
                    getService(components.interfaces.koIAppInfoEx)
        self.prefService = components.classes["@activestate.com/koPrefService;1"].\
            getService(components.interfaces.koIPrefService)
        self._prefs = self.prefService.prefs
        self._update_go_tools(self.golangInfoEx.executablePath)
        
        try:
            self._prefs.prefObserverService.addObserver(self, "golangDefaultLocation", 0)
        except Exception, e:
            print e
            
    def observe(self, subject, topic, data):
        if topic == "golangDefaultLocation":
            self._update_go_tools(self._prefs.getString("golangDefaultLocation"))

    def _update_go_tools(self, goLocation):
        self._fmt_cmd_start = None
        #self._vet_cmd_start = None
        if goLocation:
            if goLocation.lower().endswith(".exe"):
                go_format_tool_path = goLocation[0:-4] + "fmt.exe"
            else:
                go_format_tool_path = goLocation + "fmt"
            if exists(go_format_tool_path):
                self._fmt_cmd_start = [go_format_tool_path, '-e']
            #if exists(goLocation):
            #    self._vet_cmd_start = [goLocation, 'vet']
    
    def lint(self, request):
        if self._fmt_cmd_start is None:
            return
        text = request.content.encode(request.encoding.python_encoding_name)
        return self.lint_with_text(request, text)
        
    _ptn_err = re.compile(r'^(.*?):(\d+):(\d+):\s*(.*)')
    _problem_token = re.compile(r"found\s+'.*?'\s+((?:\".*?\")|\S+)")
    def lint_with_text(self, request, text):
        if self._fmt_cmd_start is None:
            return
        cwd = request.cwd or None
        results = koLintResults()
        tmpfilename = tempfile.mktemp() + ".go"
        fout = open(tmpfilename, 'wb')
        fout.write(text)
        fout.close()
        cmd = self._fmt_cmd_start + [tmpfilename]
        env = koprocessutils.getUserEnv()
        bad_keys = []
        for k, v in env.items():
            if not isinstance(v, (str, unicode)):
                bad_keys.append(k)
        for k in bad_keys:
            del env[k]
        try:
            p = process.ProcessOpen(cmd, cwd=cwd, env=env, stdin=None)
            stdout, stderr = p.communicate()
            if not stderr:
                return results
        except:
            log.exception("Failed to run %s, cwd %r", cmd, cwd)
            return results
        finally:
            os.unlink(tmpfilename)
        errLines = stderr.splitlines(0) # Don't need the newlines.
        textLines = text.splitlines(0)
        for line in errLines:
            m = self._ptn_err.match(line)
            if m:
                fname = m.group(1)
                if tmpfilename not in fname:
                    continue
                lineNo = int(m.group(2))
                columnStart = int(m.group(3))
                desc = m.group(4)
                m1 = self._problem_token.search(desc)
                if m1:
                    columnEnd = columnStart + len(m1.group(1))
                else:
                    columnEnd = columnStart + 1
                result = KoLintResult(description=desc,
                                       severity=SEV_ERROR,
                                       lineStart=lineNo,
                                       lineEnd=lineNo,
                                       columnStart=columnStart,
                                       columnEnd=columnEnd)
                results.addResult(result)
        return results
        
