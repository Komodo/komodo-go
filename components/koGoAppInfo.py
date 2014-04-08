#!/usr/bin/env python
# Copyright (c) 2000-2014 ActiveState Software Inc.
# See the file LICENSE.txt for licensing information.

import sys, os, re, string
import os.path
from xpcom import components, ServerException, nsError

import process
import koprocessutils
import logging
#from zope.cachedescriptors.property import LazyClassAttribute

log = logging.getLogger('koGoAppInfo')
#log.setLevel(logging.DEBUG)

dirSvc = components.classes["@activestate.com/koDirs;1"].\
            createInstance(components.interfaces.koIDirs)
componentsDir = sys.path.append(os.path.join(dirSvc.mozBinDir, "components"))
sys.path.append(componentsDir)
try:
    from koAppInfo import KoAppInfoEx
except ImportError:
    log.exception("Failed to import koAppInfo")
    class KoAppInfoEx(object):
        # Define stubs for KoAppInfoEx here
        pass
sys.path.pop()

class KoGolangInfoEx(KoAppInfoEx):
    _reg_clsid_ = "{9ef3a4c9-1834-4040-9c30-9481704ab967}"
    _reg_contractid_ = "@activestate.com/koAppInfoEx?app=Go;1"
    _reg_desc_ = "Go Information"

    exenames = ["go"]
    defaultInterpreterPrefName = "golangDefaultLocation"
    minVersionSupported = (1, 0)

    def getVersionForBinary(self, golangExe):
        if not os.path.exists(golangExe):
            raise ServerException(nsError.NS_ERROR_FILE_NOT_FOUND)
        argv = [golangExe, "version"]
        # Set GOROOT to point to this instance of go
        env = koprocessutils.getUserEnv()
        goRoot = env.get("GOROOT", None)
        env["GOROOT"] = os.path.dirname(os.path.dirname(golangExe))
        p = process.ProcessOpen(argv, stdin=None, env=env)
        stdout, stderr = p.communicate()
        pattern = re.compile("go version\s+go\s*(\d+(?:\.\d+){0,2})")
        match = pattern.match(stdout)
        if match:
            return match.group(1)
        else:
            msg = "Can't find a version in `%s -v` output of '%s'/'%s'" % (golangExe, stdout, stderr)
            raise ServerException(nsError.NS_ERROR_UNEXPECTED, msg)

class KoGocodeInfoEx(KoAppInfoEx):
    _reg_clsid_ = "{b73ce971-799d-456f-8ed0-eab3377f20d5}"
    _reg_contractid_ = "@activestate.com/koAppInfoEx?app=Gocode;1"
    _reg_desc_ = "Gocode Information"

    exenames = ["gocode"]
    defaultInterpreterPrefName = "gocodeDefaultLocation"

    def FindInstallationPaths(self):
        return self._locateExecutables('godef', 'godefDefaultLocation')
    
class KoGodefInfoEx(KoAppInfoEx):
    _reg_clsid_ = "{a6f9a47e-d3dc-404a-bc1b-b6918e2f1f09}"
    _reg_contractid_ = "@activestate.com/koAppInfoEx?app=Godef;1"
    _reg_desc_ = "Godef Information"

    exenames = ["godef"]
    defaultInterpreterPrefName = "godefDefaultLocation"

    def FindInstallationPaths(self):
        return self._locateExecutables('godef', 'godefDefaultLocation')
    
