
"""LangInfo definition for "Go" language."""

from langinfo import LangInfo
from xpcom.components import interfaces as ci
from xpcom.components import classes as cc
from xpcom import components

import os
import sys
import json
import logging
import process
import time
import re
import which
import tempfile

log = logging.getLogger("codeintel-go")

lang = "Go"
import styles
if not styles.StateMap.has_key(lang):
    map = styles.StateMap['C++'].copy()
    styles.addSharedStyles(map)
    styles.StateMap[lang] = map

typeMap = {
    "func": "FUN",
    "package": "MOD"
}

class GoLangIntel():

    def _get_prefs(self):
        prefs = None
        
        project = cc["@activestate.com/koPartService;1"]\
                .getService(ci.koIPartService).currentProject
        if project:
            prefs = project.prefset

        if not prefs:
            prefs = Cc["@activestate.com/koPrefService;1"].getService(Ci.koIPrefService).prefs

        return prefs

    @components.ProxyToMainThread
    def _get_view_prefs(self):
        view = cc["@activestate.com/koViewService;1"]\
               .getService(ci.koIViewService).currentView \
               .QueryInterface(ci.koIScintillaView)
        if view:
            return view.prefs

    def _get_env_dict(self):
        ret = {}

        prefs = self._get_view_prefs()
        envStr = prefs.getString("userEnvironmentStartupOverride", "")
        envList = envStr.split('\n')

        userEnvSvc = cc["@activestate.com/koUserEnviron;1"].getService()
        for piece in userEnvSvc.GetEnvironmentStrings():
            equalSign = piece.find('=')
            ret[piece[:equalSign]] = piece[equalSign+1:]

        for entry in envList:
            try:
                entry = entry.split("=", 1)
                if len(entry) != 2:
                    continue
                key, value = entry
                ret[key] = value;
            except ValueError:
                log.error("error on value %s" % entry)

        return ret

    def _get_gotool(self, tool, env = {}):
        prefs = self._get_prefs()
        tool_path = prefs.getString(tool + "DefaultLocation", "")

        if tool_path and tool_path != "":
            return tool_path

        path = "PATH" in env and env["PATH"] or ""
        path = [d.strip()
                for d in path.split(os.pathsep)
                if d.strip()]

        tool_name = tool
        if tool_name == "golang":
            tool_name = "go"

        try:
            return which.which(tool_name, path=path)
        except which.WhichError:
            pass

        go_exe = None
        if tool != "golang":
            go_exe = self._get_gotool("golang", env)

        ext = sys.platform.startswith("win") and ".exe" or ""

        if go_exe:
            tool_path = os.path.join(os.path.dirname(go_exe), tool_name + ext)
            if os.path.exists(tool_path):
                return tool_path

        go_path = "GOPATH" in env and env["GOPATH"] or None
        if go_path:
            tool_path = os.path.join(go_path, "bin", tool_name + ext)
            if os.path.exists(tool_path):
                return tool_path

        return tool # go for broke

    def getCompletions(self, buf, pos, path, parentPath, importPaths):
        log.debug("getCompletions")

        _pos = pos
        query = ""
        while re.match(r"\w", buf[_pos-1]):
            query = buf[_pos-1] + query
            _pos = _pos - 1

        if not query:
            _wpos = pos
            while re.match(r"[\t ]", buf[_wpos-1]):
                _wpos = _wpos - 1
            if buf[_wpos-1] == "\n":
                return

        if buf[_pos-7:_pos-1] == "import":
            return self._getImportCompletions(query, buf, _pos, path, parentPath, importPaths)

        return self._getCompletions(query, buf, pos, path, parentPath, importPaths)

    def _getCompletions(self, query, buf, pos, path, parentPath, importPaths):
        log.debug("_getCompletions")

        log.debug(1)
        env = self._get_env_dict()
        log.debug(2)
        go_exe = self._get_gotool("golang", env)
        log.debug(3)
        gocode_path = self._get_gotool('gocode', env)
        log.debug(4)

        # We can't store the path and watch prefs because this isn't a
        # true xpcom object.
        cmd = [gocode_path, '-debug', '-f=json', 'autocomplete', path, '%s' % pos]
        log.debug("running [%s]", cmd)
        try:
            p = process.ProcessOpen(cmd, env=env)
        except OSError, e:
            log.error("Error executing '%s': %s", cmd[0], e)
            return

        output, error = p.communicate(buf)
        if error:
            log.warn("'%s' stderr: [%s]", cmd[0], error)

        try:
            completion_data = json.loads(output)
            log.debug('full completion_data: %r', completion_data)
            completion_data = completion_data[1]
        except IndexError:
            # exit on empty gocode output
            return
        except ValueError, e:
            log.exception('Exception while parsing json')
            return

        completion_data = [x for x in completion_data if x['class'] != 'PANIC'] # remove PANIC entries if present
        if not completion_data:
            return

        symbols = []
        for completion in completion_data:
            typ = completion["class"]
            if typ in typeMap:
                typ = typeMap[typ]
            symbols.append({
                "name": completion["name"],
                "typehint": completion["type"],
                "type": typ,
                "filename": "",
                "line": None,
                "pos": 0,
                "active": False,
                "isScope": False,
                "level": 0,
                "members": [],
                "api": "legacy"
            })

        return {
            "symbol": "",
            "query": query,
            "docblock": "",
            "signature": "",
            "entries": symbols,
            "language": "Go"
        }
        
    def _getImportCompletions(self, query, buf, pos, path, parentPath, env):
        log.debug("_getImportCompletions")

        env = self._get_env_dict(env)
        go_exe = self._get_gotool("golang", env)

        if not go_exe:
            raise CodeIntelGoException("Unable to locate go executable")

        cmd = [go_exe, 'list', 'std']
        cwd = parentPath

        log.debug("running cmd %r", cmd)
        try:
            p = process.ProcessOpen(cmd, cwd=cwd, env=env)
        except OSError, e:
            raise CodeIntelGoException("Error executing '%s': %s" % (cmd, e))
        output, error = p.communicate()
        if error:
            log.warn("cmd %r error [%s]", cmd, error)
            raise CodeIntelGoException(error)
        package_names = [x.strip() for x in output.splitlines() if x]
        log.debug("retrieved %d package names", len(package_names))

        symbols = []
        for package in package_names:
            if not package.lower().startswith(query):
                continue

            symbols.append({
                "name": package,
                "typehint": None,
                "type": "MOD",
                "filename": None,
                "line": -1,
                "pos": 0,
                "active": False,
                "isScope": True,
                "level": 0,
                "members": [],
                "api": "legacy"
            })

        return {
            "symbol": "import",
            "query": query,
            "docblock": """
An import declaration states that the source file containing the declaration depends on functionality of the imported package and enables access to exported identifiers of that package. The import names an identifier (PackageName) to be used for access and an ImportPath that specifies the package to be imported.
            """,
            "signature": "<PackageName> - package to be imported",
            "entries": symbols,
            "language": "Go"
        }

    def getDefinition(self, buf, pos, path, parentPath, importPaths):
        log.debug("getDefinition")

        env = self._get_env_dict()
        godef_path = self._get_gotool("godef", env)

        cmd = [godef_path, '-i=true', '-t=true', '-f=%s' % path, '-o=%s' % pos]
        log.debug("running [%s]", cmd)
        p = process.ProcessOpen(cmd, env=env)

        output, error = p.communicate(buf)
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
        
        return {"filename": path, "line": line}

class GoLangInfo(LangInfo):
    """http://golang.org"""
    name = lang
    conforms_to_bases = ["Text"]
    exts = [".go"]
    # From http://golang.org/ref/spec#Keywords
    reserved_keywords = set("""
        break        default      func         interface    select
        case         defer        go           map          struct
        chan         else         goto         package      switch
        const        fallthrough  if           range        type
        continue     for          import       return       var
    """.split())
    # From http://golang.org/ref/spec#Predeclared_identifiers
    predeclared_identifiers = set("""
        bool byte complex64 complex128 error float32 float64
        int int8 int16 int32 int64 rune string
        uint uint8 uint16 uint32 uint64 uintptr

        true false iota nil""".split())
    predeclared_functions = set("""
        append cap close complex copy delete imag len
        make new panic print println real recover
        """.split())
    default_encoding = "utf-8"

    section_regexes = [
       ("function", re.compile(r'''
            [^\n][\s]*                              # Start of line
            func[ \t]+(\w+)[ \t]*\(                 # The function definition
            ''', re.M | re.X)),
       ("object", re.compile(r'''
            [^\n][\s]*                              # Start of line
            type[ \t]+(\w+)[ \t]*struct             # object definition
            ''', re.M | re.X)),
       ("interface", re.compile(r'''
            [^\n][\s]*                              # Start of line
            type[ \t]+(\w+)[ \t]*interface          # interface definition
            ''', re.M | re.X)),
       ("class", re.compile(r'''
            [^\n][\s]*                            # Start of line
            const\s+(\w+)\s+\w+\s=                # constant
            ''', re.M | re.X)),
    ]

    legacy_codeintel = GoLangIntel()
        
class CodeIntelGoException(Exception):
    pass