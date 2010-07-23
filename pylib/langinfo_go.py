
"""LangInfo definition for "Go" language."""

from langinfo import LangInfo


class GoLangInfo(LangInfo):
    """http://golang.org"""
    name = "Go"
    conforms_to_bases = ["Text"]
    exts = [".go"]
    keywords = set("""
        break        default      func         interface    select
        case         defer        go           map          struct
        chan         else         goto         package      switch
        const        fallthrough  if           range        type
        continue     for          import       return       var
        """.split())
    default_encoding = "utf-8"

