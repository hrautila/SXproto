# Copyright (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING.LESSER file included in this archive

import sys
import xml.parsers.expat as xmlparser
from sxproto.fixtypes import *

_copying = """
# Copyright (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING.LESSER file included in this archive
"""

header = None
trailer = None
messages = {}

cur_m = None
cur_f = None
cur_g = None

components = {}
fields = {}
groups = {}

in_messages = False
in_components = False
in_fields = False
in_header = False
in_trailer = False

class Composite(object):
    def __init__(self):
        self._elements = []

    def __str__(self):
        return "%s" % ', '.join([str(x) for x in self._elements])
    
    def add_component(self, f):
        if f is not None:
            self._elements.append(f)

    def components(self):
        return self._elements
    
class Message(Composite):
    def __init__(self, name):
        Composite.__init__(self)
        self.name = name
        self.msgtype = None
        self.application = None

    def __str__(self):
        return "%s: type=%s, application=%s" % (self.name, self.msgtype, self.application)

class Header(Composite):
    def __init__(self):
        Composite.__init__(self)

class Trailer(Composite):
    def __init__(self):
        Composite.__init__(self)

class MessageGroup(Composite):
    def __init__(self, name):
        Composite.__init__(self)
        self.name = name
        self.required = False

    def __str__(self):
        return "Group %s <required=%s> [%d parts]" % (self.name, self.required, len(self._elements))
    
class MessageField(object):
    def __init__(self, name):
        self.name = name
        self.required = False
    
    def __str__(self):
        return "MessageField %s <required=%s>" % (self.name, self.required)
    
class Component(Composite):
    def __init__(self, name):
        Composite.__init__(self)
        self.name = name

    def __str__(self):
        return "Component %s [%d parts]" % (self.name, len(self._elements))

class Field(object):
    def __init__(self, name):
        self.name = name
        self.ftype = None
        self.fnumber = 0
        self._values = []

    def __str__(self):
        return "Field %s <%03d, %s>" % (self.name, self.fnumber, self.ftype)

    def add_enum(self, e):
        self._values.append(e)

class FieldEnum(object):
    def __init__(self):
        self.enum = None
        self.desc = None
        

def handle_start_element(name, attrs):
    global cur_m, cur_f, cur_g, cur_c
    global in_messages, in_header, in_components, in_fields, in_trailer
    global messages, components, fields, groups
    global header, trailer
    
    #print "in_m %s, in_h %s, in_c %s, in_f %s" % (in_messages, in_header, in_components, in_fields)
    if in_fields:
        if name == 'field':
            cur_f = Field(attrs['name'])
            cur_f.ftype = attrs['type']
            cur_f.fnumber = int(attrs['number'])
            fields[cur_f.name] = cur_f
            
        elif name == 'value':
            enum = FieldEnum()
            enum.enum = attrs['enum']
            enum.desc = attrs['description']
            cur_f.add_enum(enum)

    else: ## in_messages or in_header or in_components or in_trailer:
        if name == 'message':
            # start new message
            cur_m = Message(attrs['name'])
            cur_m.msgtype = attrs['msgtype']
            cur_m.application = attrs['msgcat'] == 'app'
            messages[cur_m.name] = cur_m

        elif name == 'field':
            cur_f = MessageField(attrs['name'])
            cur_f.required = bool(attrs['required'])
            if cur_g is not None:
                cur_g.add_component(cur_f)
            elif in_header:
                header.add_component(cur_f)
            elif in_trailer:
                trailer.add_component(cur_f)
            elif in_messages:
                cur_m.add_component(cur_f)
            elif in_components:
                cur_c.add_component(cur_f)

        elif name == 'group':
            cur_g = MessageGroup(attrs['name'])
            groups[cur_g.name] = cur_g
            cur_g.required = bool(attrs['required'])
            if in_header:
                header.add_component(cur_g)
                return
            if in_messages:
                cur_m.add_component(cur_g)
            elif in_components:
                cur_c.add_component(cur_g)

        elif name == 'component':
            cur_c = Component(attrs['name'])
            if not in_components:
                cur_c.required = bool(attrs['required'])
                if cur_g is not None:
                    cur_g.add_component(cur_c)
                else:
                    cur_m.add_component(cur_c)

            else:
                cur_c = Component(attrs['name'])
                components[cur_c.name] = cur_c
                

        
def handle_end_element(name):
    if name == 'message':
        global cur_m
        cur_m = None
    elif name == 'field':
        global cur_f
        cur_f = None
    elif name == 'group':
        global cur_g
        cur_g = None
    elif name == 'component':
        global cur_c
        cur_c = None
        
def start_element(name, attrs):
    #print 'Start element: ', name, attrs
    global in_messages, in_header, in_components, in_fields
    global header, trailer
    if name == 'messages':
        in_messages = True
    elif name == 'components':
        in_components = True
    elif name == 'fields':
        in_fields = True
    elif name == 'header':
        header = Header()
        in_header = True
    elif name == 'tailer':
        in_trailer = True
        trailer = Trailer()
    else:
        handle_start_element(name, attrs)
    
def end_element(name):
    global in_messages, in_header, in_components, in_fields
    global header, trailer
    if name == 'messages':
        in_messages = False
    elif name == 'components':
        in_components = False
    elif name == 'fields':
        in_fields = False
    elif name == 'header':
        in_header = False
    elif name == 'trailer':
        in_trailer = False
    else:
        handle_end_element(name)
    #print 'End element  : ', name

def char_data(data):
    pass

def _indent(x):
    i = ''
    for k in xrange(x):
        i += '  '
    return i



def write_field_types(filep, source_file):
    global messages, fields, composites, groups
    
    api_list = ["FIX_HEADER_FIELD_IDS", "FIX_TRAILER_FIELD_IDS",
                '_fix_field_types', '_fix_message_types', '_fix_group_types',
                '_fix_field_numbers', '_fix_group_numbers',  '_fix_msgtype_table']
    
    # ["fix_desc_for_name", "fix_desc_for_id", "fix_desc_add",
    #            "fix_group_for_name", "fix_group_for_id", "fix_group_add", 
    #            "fix_msgtype_for_name", "fix_name_for_msgtype", "fix_message_is_application"]
    
    filep.write("# automatically generated, do not edit\n\n# (source: %s)\n\n" % source_file)
    filep.write(_copying)

    filep.write("from sxsuite.fix.context import FixFieldDescriptor, FixGroupDescriptor\n\n")

    filep.write("__all__ = %s\n\n" % api_list)
    filep.write("FIX_HEADER_FIELD_IDS = [\n")
    h_list = []
    for x in header.components():
        if isinstance(x, MessageGroup):
            pass
        else:
            h_list.append(fields[x.name].fnumber)

    filep.write("\t%s]\n\n" % ", ".join([str(y) for y  in h_list]))
    
    filep.write("FIX_TRAILER_FIELD_IDS = [10, 89, 93]\n\n")

    filep.write("_fix_field_types = {\n")
    names = fields.keys()
    names.sort()
    for name in names:
        field = fields[name]
        pytype = fix_pytype(field.ftype)
        if pytype == int:
            ptyp = 'int'
        elif pytype == float:
            ptyp = 'float'
        else:
            ptyp = 'str'

        if field.ftype == 'NUMINGROUP':
            filep.write("\t'%s': FixGroupDescriptor('%s', %d),\n" %
                        (name, name, field.fnumber))
        else:
            filep.write("\t'%s': FixFieldDescriptor('%s', %d, '%s', %s),\n" %
                        (name, name, field.fnumber, field.ftype, ptyp))

    filep.write("}\n\n")

    filep.write("_fix_message_types = {\n")
    names = messages.keys()
    names.sort()
    for name in names:
        filep.write("\t'%s': ('%s', %s),\n" %
                    (name, messages[name].msgtype, messages[name].application ))

    filep.write("}\n\n")

    filep.write("_fix_group_types = {\n")
    names = groups.keys()
    names.sort()
    for name in names:
        group = groups[name]
        filep.write("\t'%s': [\n" % name)
        for c in group.components():
            if isinstance(c, Component):
                for x in c.components():
                    filep.write("\t\t(%d, '%s'),\n" % (fields[x.name].fnumber, x.name))
            else:
                filep.write("\t\t(%d, '%s'),\n" % (fields[c.name].fnumber, c.name))
        filep.write("\t\t],\n")

    filep.write("}\n\n")

    filep.write("_fix_field_numbers = {}\n")
    filep.write("for desc in _fix_field_types.values():\n")
    filep.write("\t_fix_field_numbers[desc.number]=desc\n")
    filep.write("\n\n")

    filep.write("_fix_group_numbers = {}\n")
    filep.write("for name, desc in _fix_group_types.items():\n")
    filep.write("\t_fix_group_numbers[_fix_field_types[name].number]=desc\n")
    filep.write("\n\n")

    filep.write("_fix_msgtype_table = {}\n")
    filep.write("for name in _fix_message_types:\n")
    filep.write("\t_fix_msgtype_table[_fix_message_types[name][0]]=name\n")
    filep.write("\n\n")


def write_message_types(filep, source_file):
    global messages

    names = messages.keys()
    names.sort()

    ses_messages = ['Heartbeat', 'Logon', 'Logout', 'Reject', 'ResendRequest', 'SequenceReset', 'TestRequest']
    filep.write("# automatically generated, do not edit\n\n# (source: %s)\n\n" % source_file)
    filep.write("from sxsuite.fix.message import FixObject\n\n")
    filep.write("from sxsuite.fix.message import %s\n\n" % ','.join(ses_messages))
    
    for name in names:
        # only application messages
        if messages[name].application:
            filep.write("class %s(FixObject):\n" % name)
            filep.write("\tpass\n\n")
        
    
def write_utils(filep):
    
    filep.write("def fix_desc_for_name(name):\n")
    filep.write("\treturn _fix_field_types[name]\n")
    filep.write("\n\n")

    filep.write("def fix_desc_for_id(num):\n")
    filep.write("\treturn _fix_field_numbers[num]\n")
    filep.write("\n\n")

    filep.write("def fix_group_for_name(name):\n")
    filep.write("\treturn _fix_group_types[name]\n")
    filep.write("\n\n")

    filep.write("def fix_group_for_id(num):\n")
    filep.write("\treturn _fix_group_numbers[num]\n")
    filep.write("\n\n")

    filep.write("def fix_group_add(name, num, gspec):\n")
    filep.write("\tgdesc = FixGroupDescriptor(name, num)\n")
    filep.write("\t_fix_field_types[name] = gdesc\n")
    filep.write("\t_fix_field_numbers[num] = gdesc\n")
    filep.write("\t_fix_group_types[name] = gspec\n")
    filep.write("\t_fix_group_numbers[num] = _fix_group_types[name]\n")
    filep.write("\n\n")

	
    filep.write("def fix_desc_add(name, num, ftype):\n")
    filep.write("\tdesc = FixFieldDescriptor(name, num, ftype, fix_pytype(ftype))\n")
    filep.write("\t_fix_field_types[name] = desc\n")
    filep.write("\t_fix_field_numbers[num] = desc\n")
    filep.write("\n\n")

    filep.write("def fix_msgtype_for_name(name):\n")
    filep.write("\treturn _fix_message_types[name][0]\n")
    filep.write("\n\n")

    filep.write("def fix_message_is_application(name):\n")
    filep.write("\treturn _fix_message_types[name][1]\n")
    filep.write("\n\n")

    filep.write("def fix_name_for_msgtype(mtyp):\n")
    filep.write("\treturn _fix_msgtype_table[mtyp]\n")
    filep.write("\n")



def main(argv):
    import getopt

    try:
        opts, args = getopt.getopt(argv, "f:m:N", ["fields=", "messages=", "noout"])
    except getopt.GetoptError, e:
        print str(e)
        sys.exit(1)

    fields_file = "fixfields.py"
    messagetypes_file = "fixmtypes.py"
    source_file = ''
    no_output = False

    for o, a in opts:
        if o in ("-f", "--fields"):
            fields_file = a
        elif o in ("-m", "--messages"):
            messagetypes_file = a
        elif o in ("-N", "--noout"):
            no_output = True
        
    if not args:
        print "Usage: fixxml.py [-f path -m path] xmlfile"
        sys.exit(1)
    
    parser = xmlparser.ParserCreate()
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element

    source_file = args[0]
    with open(source_file, "r") as fp:
        parser.ParseFile(fp)

    if no_output:
        names = groups.keys()
        names.sort()
        print "** GROUPS **"
        for name in names:
            print "%s: %s" % (name, groups[name])
            for x in groups[name].components():
                if isinstance(x, Component):
                    for y in x.components():
                        print "\t%s" % str(y)
                else:
                    print "\t%s" % str(x)
    
        names = components.keys()
        names.sort()
        print "** COMPONENTS **"
        for name in names:
            print "%s: %s" % (name, components[name])
            for x in components[name].components():
                print "\t%s" % str(x)

        sys.exit(0)
    
    with open(fields_file, "w") as fp:
        write_field_types(fp, source_file)

    with open(messagetypes_file, "w") as fp:
        write_message_types(fp, source_file)

main(sys.argv[1:])
