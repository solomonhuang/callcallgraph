#!/usr/bin/env python3
# Copyright 2010 Rex Tsai <chihchun@kalug.linux.org.tw>
# Copyright 2008 Jose Fonseca
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import sys
import os
import subprocess
import json
import re
from pathlib import PurePath


import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import xdot
import pydot


class CallGraph(object):
    """CallGraph
    """
    def __init__(self, database):
        self.database = database
        self.graph = pydot.Graph()

    def cscope_search(self, mode, symbol):
        cmd = "cscope -d -l -L -%d %s" % (mode, symbol) 
        process = subprocess.Popen(cmd, stdout = subprocess.PIPE, shell = True, cwd = self.working_dir) 
        csoutput = process.stdout.read() 
        print("mode %s", str(mode))
        print(csoutput)
        del process
        cslines = [arr.strip().split(' ') for arr in csoutput.split('\n') if len(arr.split(' '))>1] 
        print(cslines)
        allFuns = set(map(lambda x:x[1], cslines))
        print(allFuns)

        funsCalled = {}
        for fl in cslines:
            if fl[0] in funsCalled:
                funsCalled[fl[0]] |= set([fl[1]])
            else:
                funsCalled[fl[0]] = set([fl[1]])

        return (allFuns, funsCalled)

    def find_functions_definition(self, symbol):
        self.cscope_search(1, symbol)

    def find_functions_calling(self, symbol):
        self.cscope_search(2, symbol)

    def find_functions_called(self, symbol):
        self.cscope_search(3, symbol)



class CCGWindow(xdot.DotWindow):
    """CallCallGraph Window
    """
    def __init__(self):
        self.base_title = "Call Call Graph"
        self.working_dir = None
        self.interest = {}
        self.filename = None
        self.config = dict()
        self.config['ignore_symbols'] = []
        self.ignore_symbols = {}
        self.dotcode = None

        xdot.DotWindow.__init__(self, width=600, height=512)
        toolbar = self.uimanager.get_widget('/ToolBar')

        item = Gtk.ToolButton(Gtk.STOCK_SAVE)
        item.set_tooltip_markup("Save")
        item.connect('clicked', self.on_save)
        item.show()
        toolbar.insert(item, 0)

        item = Gtk.ToolButton(Gtk.STOCK_NEW)
        item.set_tooltip_markup("New project")
        item.connect('clicked', self.on_new_project)
        item.show()
        toolbar.insert(item, 0)

        vbox = self.get_child()
        hbox = Gtk.HBox()

        label = Gtk.Label("Search symbol: ")
        hbox.pack_start(label, False, True, True)
        label.show()

        entry = Gtk.Entry()
        entry.connect('activate', self.on_symbol_enter)
        hbox.pack_start(entry, True, True, 10)
        entry.show()

        item = Gtk.ToolButton(Gtk.STOCK_NEW)
        item.set_tooltip_markup("Ignore symbols")
        hbox.pack_end(item, False, True, 10)
        item.show()

        label = Gtk.Label("Ignore symbols: ")
        hbox.pack_end(label, False, True, True)
        label.show()

        vbox.pack_start(hbox, False, True, True)
        vbox.reorder_child(hbox, 1)
        hbox.show()

    def on_reload(self, action):
        print("reload")
        self.interest = {}
        self.set_dotcode("digraph G {}")

    def on_save(self, action):
        chooser = Gtk.FileChooserDialog("Save your work", self,
                                        Gtk.FileChooserAction.SAVE,
                                        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                         Gtk.STOCK_OK, Gtk.ResponseType.OK))
        chooser.set_default_response(Gtk.ResponseType.OK)
        filter = Gtk.FileFilter()
        filter.set_name("Graphviz dot files")
        filter.add_pattern("*.dot")
        chooser.add_filter(filter)
        filter = Gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        chooser.add_filter(filter)
        if chooser.run() == Gtk.ResponseType.OK:
            self.filename = chooser.get_filename()
            with open(self.filename, "w") as file:
                file.write(self.dotcode)
        else:
            self.filename = None

        chooser.destroy()

    def on_new_project(self, widget):
        chooser = Gtk.FileChooserDialog("Open the source code directory", self,
                                        Gtk.FileChooserAction.SELECT_FOLDER,
                                        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                         Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        chooser.set_default_response(Gtk.ResponseType.OK)
        if chooser.run() == Gtk.ResponseType.OK:
            filename = chooser.get_filename()
            print(filename)
            self.working_dir = filename
            self.interest = {}
            self.filename = None
            p = PurePath(self.working_dir, ".callcallgraph.json")
            try:
                with open(str(p), "r") as conf:
                    self.config = json.loads(conf.read())
            except FileNotFoundError:
                with open(str(p), "w") as conf:
                    conf.write(json.dumps(self.config, indent=4))
            self.ignore_symbols = set(map(lambda x: re.compile(x), self.config['ignore_symbols']))
            
            self.update_database()
            self.update_graph()

        chooser.destroy()

    def is_symbol_ignored(self, symbol):
        for p in self.ignore_symbols:
            if p.match(symbol) != None:
                return True
        return False

    def on_symbol_enter(self, widget):
        symbol = widget.get_text()
        widget.set_text('')
        if self.working_dir is None:
            # FIXME: let's have a dialog for the user.
            self.on_new_project(None)
        if self.is_symbol_ignored(symbol):
            return
        self.addSymbol(symbol)

    def addSymbol(self, symbol, lazy=0):
        # TODO: sould Saving the filename and line number.
        print(symbol)
        if(symbol == '//'):
            return

        if(lazy == 0):
            defs, calls = self.functionDefincation(symbol)
            if len(defs) >= 1:
                self.interest[symbol] = 1
            self.update_graph()
        else:
            self.interest[symbol] = 1

    def cscope(self, mode, func):
        # TODO: check the cscope database is exist.
        cmd = "/usr/bin/cscope -d -l -L -%d %s" % (mode, func)
        print(cmd)
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True,
                              cwd=self.working_dir) as proc:
            csoutput = str(proc.stdout.read(), encoding="utf-8")
        print(csoutput)
        cslines = [arr.strip().split(' ') for arr in csoutput.split('\n') if len(arr.split(' '))>1] 
        print(cslines)
        allFuns = set(map(lambda x:x[1], cslines))
        print(allFuns)

        funsCalled = {}
        for fl in cslines:
            if fl[0] in funsCalled:
                funsCalled[fl[0]] |= set([fl[1]])
            else:
                funsCalled[fl[0]] = set([fl[1]])

        print(funsCalled)
        return (allFuns, funsCalled)

    def functionDefincation(self, func):
        return self.cscope(1, func)

    def functionsCalled(self, func):
        # Find functions called by this function:
        return self.cscope(2, func)

    def functionsCalling(self, func):
        # Find functions calling this function:
        return self.cscope(3, func)

    def update_graph(self):
        """ update dot code based on the interested keys """
        funcs = set(self.interest.keys())
        #print("len of funcs %d" % (len(funcs)))
        if len(funcs) <= 0:
            # self.widget.graph = xdot.Graph()
            return

        nodes = dict()
        for func in funcs:
            if self.is_symbol_ignored(func):
                continue
            if func not in nodes:
                nodes[func] = list()
            
            allFuncs, funsCalled = self.functionsCalled (func)
            for m in allFuncs:
                if self.is_symbol_ignored(m):
                    continue
                if m not in nodes[func]:
                    nodes[func].append(m)

            allFuncs, funsCalling = self.functionsCalling (func)
            for m in allFuncs:
                if self.is_symbol_ignored(m):
                    continue
                if m not in nodes:
                    nodes[m] = list()
                nodes[m].append(func)

        dotcode = "digraph G {\n"
        for node in nodes.keys():
            dotcode += ' '*2 + '"%s";\n' % node
            for nbr in nodes[node]:
                dotcode += ' '*4 + '"%s" -> "%s";\n' % (node, nbr)
        dotcode += "}\n"

        self.set_dotcode(dotcode)

    def update_database(self):
        if not os.path.isfile(self.working_dir + "/cscope.out"):
            dialog = Gtk.MessageDialog(parent=self, type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO)
            dialog.set_default_response(Gtk.ResponseType.YES)
            dialog.set_markup("Create cscope database for %s now ?" % self.working_dir )
            ret = dialog.run()
            dialog.destroy()
            if ret == Gtk.ResponseType.YES:
                cmd = "cscope -bkRu"
                process = subprocess.call(cmd, shell=True, cwd=self.working_dir) 
                del process
        pass

    def set_dotcode(self, dotcode, filename=None):
        print("\n\ndotcode:\n" + dotcode + "\n\n")
        self.dotcode = dotcode
        super(CCGWindow, self).set_dotcode(dotcode, filename)
    #    if self.set_dotcode(dotcode, filename):
    #        #self.set_title(os.path.basename(filename) + ' - Code Visualizer')
    #        self.widget.zoom_to_fit()



def main():
    window = CCGWindow()
    window.connect('delete-event', Gtk.main_quit)
    Gtk.main()


if __name__ == '__main__':
    main()
