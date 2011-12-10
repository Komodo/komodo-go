# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
# 
# The contents of this file are subject to the Mozilla Public License
# Version 1.1 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
# 
# Software distributed under the License is distributed on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
# License for the specific language governing rights and limitations
# under the License.
# 
# The Original Code is Komodo code.
# 
# The Initial Developer of the Original Code is ActiveState Software Inc.
# Portions created by ActiveState Software Inc are Copyright (C) 2000-2007
# ActiveState Software Inc. All Rights Reserved.
# 
# Contributor(s):
#   ActiveState Software Inc
# 
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
# 
# ***** END LICENSE BLOCK *****

# Komodo Go language service.

import os
import re
import sys
import logging
import process
import tempfile
import subprocess
import koprocessutils

from xpcom import components

from koLintResult import KoLintResult
from koLintResults import koLintResults

log = logging.getLogger("koGoLanguage")
#log.setLevel(logging.DEBUG)


class KoGoLinter(object):
    _com_interfaces_ = [components.interfaces.koILinter]
    _reg_desc_ = "Go Linter"
    _reg_clsid_ = "{5a44b028-92e0-4159-bffd-92fd5658b322}"
    _reg_contractid_ = "@activestate.com/koLinter?language=Go;1"
    _reg_categories_ = [
        ("category-komodo-linter", 'Go'),
    ]

    def __init__(self):
        self._sysUtils = components.classes["@activestate.com/koSysUtils;1"].\
            getService(components.interfaces.koISysUtils)
        self._koDirSvc = components.classes["@activestate.com/koDirs;1"].\
            getService(components.interfaces.koIDirs)

    def lint(self, request):
        log.info(request)
        encoding_name = request.encoding.python_encoding_name
        text = request.content.encode(encoding_name)
        return self.lint_with_text(request, text)

    def lint_with_text(self, request, text):
        log.info(request)
        if not text.strip():
            return None
        # consider adding lint preferences? maybe for compiler selection, paths, etc?
        results = koLintResults()
        p = process.ProcessOpen(['gotype'], cwd=request.cwd, env=koprocessutils.getUserEnv())
        output, errors = p.communicate(text)
        log.debug("gotype output: output:[%s], error:[%s]", output, errors)
        if errors:
            for line in errors.splitlines():
                results.addResult(self._buildResult(text, line))
        if output:
            results.addResult(self._buildResult(text, "Unexpected error"))
        return results

    def _buildResult(self, text, message):
        r = KoLintResult()
        r.severity = r.SEV_ERROR
        r.description = message
        
        m = re.match('<standard input>:(\d+):(\d+): (.*)', message)
        if m:
            line_no, column_no, error_message = m.groups()
            line_no, column_no = int(line_no), int(column_no)
            line_contents = text.splitlines()[int(line_no)-1].rstrip()
            r.description = error_message
            r.lineStart = r.lineEnd = line_no
            #r.columnStart = len(line_contents) - len(line_contents.strip()) + 1
            r.columnStart = column_no
            r.columnEnd = len(line_contents) + 1

        return r
