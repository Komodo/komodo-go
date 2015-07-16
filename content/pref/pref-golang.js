/* Copyright (c) 2000-2014 ActiveState Software Inc.
   See the file LICENSE.txt for licensing information. */

//---- globals
var appInfoEx = {golang:null, gocode:null, godef:null};
var programmingLanguage = "Go";
var _bundle = Components.classes["@mozilla.org/intl/stringbundle;1"]
            .getService(Components.interfaces.nsIStringBundleService)
            .createBundle("chrome://komodo/locale/pref/pref-languages.properties");
var log = ko.logging.getLogger("pref.pref-golang");
var prefs = Components.classes["@activestate.com/koPrefService;1"].
    getService(Components.interfaces.koIPrefService).prefs;
var $ = require("ko/dom");
//---- functions

function OnPreferencePageOK(prefset)
{
    return checkValidInterpreterSetting(prefset,
                                        "golangDefaultLocation",
                                        programmingLanguage);
}

// Populate the (tree) list of available Golang interpreters on the current
// system.
function PrefGolang_PopulateGolangInterps()
{
    var availInterpList = document.getElementById("golangDefaultLocation");
    var prefExecutable = parent.hPrefWindow.prefset.getString('golangDefaultLocation', '')

    // remove any existing items and add a "finding..." one
    availInterpList.removeAllItems();
    availInterpList.appendItem(_bundle.formatStringFromName("findingInterpreters.label", [programmingLanguage], 1));

    // get a list of installed Golang interpreters
    var numFound = new Object();
    var availInterps = appInfoEx.golang.FindExecutables(numFound);
    availInterpList.removeAllItems();
    availInterpList.appendItem(_bundle.GetStringFromName("findOnPath.label"),'');

    var found = false;
    // populate the tree listing them
    if (availInterps.length == 0 && !prefExecutable) {
        // tell the user no interpreter was found and direct them to
        // ActiveState to get one
        document.getElementById("no-avail-interps-message").removeAttribute("collapsed");
    } else {
        document.getElementById("no-avail-interps-message").setAttribute("collapsed", "true");
        for (var i = 0; i < availInterps.length; i++) {
            availInterpList.appendItem(availInterps[i],availInterps[i]);
            if (availInterps[i] == prefExecutable) {
                found = true;
                availInterpList.selectedIndex = i + 1;
            }
        }
    }
    if (!found) {
        if (prefExecutable) {
            availInterpList.appendItem(prefExecutable,prefExecutable);
            availInterpList.selectedIndex = availInterpList.childNodes.length - 1;
        } else {
            availInterpList.selectedIndex = 0;
        }
    }
}

function PrefGolang_PopulateGotoolInterps(name)
{
    var prefName = name + "DefaultLocation";
    var prefExecutable = parent.hPrefWindow.prefset.getString(prefName, '');
    var availInterpList = document.getElementById(prefName);
    
    availInterpList.removeAllItems();
    availInterpList.appendItem(_bundle.GetStringFromName("findOnPath.label"),'');

    // get a list of installed gocode/godef interpreters
    var availInterps = appInfoEx[name].FindExecutables({});
    var found = false;
    // populate the tree listing them
    for (var i = 0; i < availInterps.length; i++) {
        availInterpList.appendItem(availInterps[i],availInterps[i]);
        if (availInterps[i] == prefExecutable) {
            found = true;
            availInterpList.selectedIndex = i + 1;
        }
    }

    if (!found) {
        if (prefExecutable) {
            availInterpList.appendItem(prefExecutable,prefExecutable);
            availInterpList.selectedIndex = availInterpList.childNodes.length - 1;
        } else {
            availInterpList.selectedIndex = 0;
        }
    }
}

function PrefGolang_OnLoad()
{
    appInfoEx.golang = Components.classes["@activestate.com/koAppInfoEx?app=Go;1"].
            getService(Components.interfaces.koIAppInfoEx);
    appInfoEx.gocode = Components.classes["@activestate.com/koAppInfoEx?app=Gocode;1"].
            getService(Components.interfaces.koIAppInfoEx);
    appInfoEx.godef = Components.classes["@activestate.com/koAppInfoEx?app=Godef;1"].
            getService(Components.interfaces.koIAppInfoEx);
    PrefGolang_PopulateGolangInterps();
    PrefGolang_PopulateGotoolInterps('gocode');
    PrefGolang_PopulateGotoolInterps('godef');
    // Check for GOPATH: experiments show if this isn't set, neither
    // gocode nor godef will work.  But setting GOROOT isn't necessary.
    var envSvc = Components.classes["@activestate.com/koUserEnviron;1"]
                 .getService(Components.interfaces.koIUserEnviron);
    var hasGOPATH = envSvc.has("GOPATH");
    var gopathNotSetVbox = document.getElementById('gopath-not-set');
    if (hasGOPATH) {
        var goPath = envSvc.get("GOPATH");
        if (!goPath) {
            hasGOPATH = false;
        } else {
            let osPathSvc = Components.classes["@activestate.com/koOsPath;1"]
                    .getService(Components.interfaces.koIOsPath);
            if (!osPathSvc.exists(goPath) || !osPathSvc.isdir(goPath)) {
                log.warn("The GOPATH environment variable is set but "
                          + goPath
                          + " doesn't name a directory");
                hasGOPATH = false;
            }
        }
    }
    gopathNotSetVbox.collapsed = hasGOPATH;
}

function loadGolangExecutable()
{
    loadExecutableIntoInterpreterList("golangDefaultLocation");
}

function loadGocodeExecutable()
{
    loadExecutableIntoInterpreterList("gocodeDefaultLocation");
}

function loadGodefExecutable()
{
    loadExecutableIntoInterpreterList("godefDefaultLocation");
}

function PrefGolang_checkVersion()
{
    var availInterpList = document.getElementById('golangDefaultLocation');
    var interpreter = availInterpList.value;
    var availInterps = appInfoEx.golang.FindExecutables({});
    if (availInterpList.selectedItem && typeof(availInterpList.selectedItem.value) != 'undefined') {
        interpreter = availInterpList.selectedItem.value;
    }
    if (!interpreter && availInterps.length > 1) {
        interpreter = availInterps[1];
    }
    appInfoEx.golang.executablePath = interpreter;
    if (!appInfoEx.golang.valid_version) {
        document.getElementById("invalid-version-message").removeAttribute("collapsed");
    } else {
        document.getElementById("invalid-version-message").setAttribute("collapsed", "true");
    }
}

function switchToEnvironmentTab() {
    var showAdvanced = prefs.getBoolean("prefs_show_advanced", false);
    var mainPrefWindow = parent;
    if (!showAdvanced) {
        $("#toggleAdvanced", mainPrefWindow.document).attr("checked", "true")
        window.alert("\"Show Advanced\" checkbox was checked to move to Environment tab");
        mainPrefWindow.toggleAdvanced();
    }
    mainPrefWindow.hPrefWindow.helper.selectRowById("environItem");
    mainPrefWindow.hPrefWindow.switchPage();
}
