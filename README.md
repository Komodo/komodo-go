[Komodo](http://www.activestate.com/komodo) extension to add support for the [Go
language](http://golang.org).

![Example screenshot](https://github.com/traviscline/komodo-go/raw/master/example.png)

This project lives on github at: <http://github.com/trentm/komodo-go>

I haven't yet put up a build to the [Komodo addons
site](http://community.activestate.com/addons) so you'll have to build it
yourself for now. I plan to upload something soon.

# Building

- Find the 'koext' binary that is within your Komodo install (within sdk/bin).
- Run 'koext build' from the repository root, it should produce an .xpi for you.
- Open this .xpi with Komodo to install it.
- Ensure 'go' and 'gocode' are on the PATH configured in your overall or project-specific Komodo settings
- For completion and go to definition ensure 'gocode' and 'godef' are on your paths as well.
- To install gocode and godef:
  - $ go get github.com/nsf/gocode
  - $ go get code.google.com/p/rog-go/exp/cmd/godef

# Features

- Syntax highlighting (including folding)
- File-type detection for .go files
- Linting
- Codeintel via [Gocode](https://github.com/nsf/gocode)
- Jump to definition via [godef](http://godoc.org/code.google.com/p/rog-go/exp/cmd/godef)

# Komodo dependencies

- Need the patched LexCPP.cxx lexer, which handles backquoted raw strings (this removed the need for Go to be a UDL-based language)
- Need the following patch to src/codeintel/src/komodo/koCodeIntel.py:
    @@ -2143,6 +2142,9 @@
                 "python4ExtraPaths": T(),
                 "ruby": T(komodo_name="rubyDefaultInterpreter"),
                 "rubyExtraPaths": T(),
    +            "golangDefaultLocation": T(),
    +            "gocodeDefaultLocation": T(),
    +            "godefDefaultLocation": T(),
             }
             # Set the result on the class, no need to recompute
             setattr(self.__class__, "_prefs_allowed", result)
