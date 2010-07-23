#!/usr/bin/env python

"""Go language support for codeintel."""

import os
import sys
import logging

from codeintel2.common import *
from codeintel2.udl import UDLBuffer
from codeintel2.langintel import LangIntel


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

class GoLangIntel(LangIntel):
    lang = lang



#---- Buffer class

class GoBuffer(UDLBuffer):
    lang = lang
    cb_show_if_empty = True

    def trg_from_pos(self, pos, implicit=True):
        #TODO: Start here for codeintel.
        #print "XXX trg_from_pos(pos=%r)" % pos
        return None




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

