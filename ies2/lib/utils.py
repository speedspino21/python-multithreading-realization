try:
    from lxml import etree
except ImportError:
    from xml import etree
import codecs, re

re_class   = re.compile(r'(?P<indent>\s*)(?P<class><Class(\s+[a-zA-Z0-9_]+\s*=\s*"[^"]*")*\s*/>)\s*', re.IGNORECASE)
re_xml_elm = re.compile(r'(?P<name>[a-z0-9_]+)\s*=\s*"(?P<value>[^"]*)"', re.IGNORECASE)


def indent_xml(elem, level=0):
    i = "\n" + level*"\t"
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "\t"
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent_xml(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def save_xml(dom, filename, KEY_ORDER=None, encoding='ISO-8859-1'):

    indent_xml(dom)

    if dom.tag == 'idspace' or dom.tag == 'gediff':
        lines = etree.tostring(dom, encoding=encoding, xml_declaration=True).split('\n')

        if hasattr(filename, 'write'):
            fp = filename
        else:
            fp = open(filename, 'w+')

        for ln in lines:
            m = re_class.match(ln)
            if m:
                parts = m.groupdict()
                keyvals = { }
                for m in re.finditer(re_xml_elm, ln):
                    d = m.groupdict()
                    keyvals[d['name']] = d['value']

                fp.write( parts['indent'] )
                #fp.write('<Class \n')
                fp.write('<Class')

                if KEY_ORDER is None:
                    my_order = keyvals.keys()
                    sorted(my_order)
                else:
                    my_order = KEY_ORDER
                    for k in keyvals.keys():
                        if k not in my_order:
                            my_order.append(k)

                for findwhat in my_order:
                    if keyvals.has_key(findwhat):
                        #fp.write( parts['indent'] )
                        #fp.write('\t')
                        fp.write(' ')
                        fp.write( findwhat )
                        fp.write( '="' )
                        fp.write( keyvals[findwhat] )
                        #fp.write( '"\n' )
                        fp.write( '"' )
                    else:
                        for (k, v) in keyvals.items():
                            if k.lower() == findwhat.lower():
                                fp.write( parts['indent'] )
                                #fp.write('\t')
                                fp.write(' ')
                                fp.write( findwhat )
                                fp.write( '="' )
                                fp.write( v )
                                #fp.write( '"\n' )
                                fp.write( '"' )
                                break

                fp.write( parts['indent'] )
                fp.write( '/>\n' )
            else:
                fp.write(ln.replace("'1.0'", '"1.0"').replace("'ISO-8859-1'", '"ISO-8859-1"'))
                fp.write('\n')
        fp.close()
    else:
        etree.ElementTree(dom).write(filename, encoding=encoding, xml_declaration=True)

class CaseInsensitiveDict(dict):
    def __setitem__(self, key, value):
        super(CaseInsensitiveDict, self).__setitem__(key.lower(), value)

    def __getitem__(self, key):
        return super(CaseInsensitiveDict, self).__getitem__(key.lower())

def do_for_tag(dom, tag_name, callback):
    for item in dom:
        if not isinstance(item.tag, str):
            continue
        if item.tag.lower() == 'category':
            do_for_tag(item, tag_name, callback)
        elif item.tag == tag_name or item.tag.lower() == tag_name.lower():
            callback(item)

def parse_datatable(filename):
    classes = []
    type = filename[:-4]

    def parse_classes(root):
        for item in root:
            if item.tag.lower() == 'category':
                parse_classes(item)
            elif item.tag.lower() == 'class':
                d = dict(item.attrib)
                d['__type__'] = type
                classes.append(d)

    dom = etree.parse(filename, etree.XMLParser(target=etree.TreeBuilder(), remove_comments=True))
    if dom == None:
        return None
    parse_classes(dom)
    return classes

import os, re, sys

bad_func = re.compile(r'func\s+(?P<name>[a-zA-Z0-9_]+)\s*\(([a-zA-Z0-9_]+\s*,\s*)*([a-zA-Z0-9_]+)?\s*\)\s*{\s*}')
all_func = re.compile(r'func\s+(?P<name>[a-zA-Z0-9_]+)\s*\(([a-zA-Z0-9_]+\s*,\s*)*([a-zA-Z0-9_]+)?\s*\)')

def parse_functions(path, discard_empty=False, skip_files=[]):
    good_functions = []
    for root, _dirs, files in os.walk(path):
        for file in files:
            if file in skip_files:  # skip dummy buff functions
                continue
            scp_path = os.path.join(root, file)
            with open(scp_path) as fp:
                scp_data = fp.read()
                functions = []
                # find all functions
                for m in all_func.finditer(scp_data):
                    functions.append(m.groupdict()['name'])
                # remove empty functions
                if discard_empty:
                    for m in bad_func.finditer(scp_data):
                        functions.remove(m.groupdict()['name'])
                good_functions.extend(functions)
    return good_functions

















