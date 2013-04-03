
"""Komodo Go language service"""

import logging
from koUDLLanguageBase import KoUDLLanguage


log = logging.getLogger("koGoLanguage")
#log.setLevel(logging.DEBUG)


def registerLanguage(registry):
    log.debug("Registering language Go")
    registry.registerLanguage(KoGoLanguage())


class KoGoLanguage(KoUDLLanguage):
    name = "Go"
    lexresLangName = "Go"
    _reg_desc_ = "%s Language" % name
    _reg_contractid_ = "@activestate.com/koLanguage?language=%s;1" % name
    _reg_categories_ = [("komodo-language", name)]
    _reg_clsid_ = "e97cb498-5c50-4d60-95f4-eaa6cda6e877"
    defaultExtension = '.go'
    lang_from_udl_family = {"SSL": "Go"}

    commentDelimiterInfo = {
        "line": [ "//" ],
        "block": [ ("/*", "*/") ]
    }
    supportsSmartIndent = "brace"

    sample = """package main

import "fmt"
import "net/http"

func handler(w http.ResponseWriter, r *http.Request) {
	fmt.Fprint(w, "Hello world.")
}
func main() {
	http.HandleFunc("/", handler)
	http.ListenAndServe(":8080", nil)
}
"""