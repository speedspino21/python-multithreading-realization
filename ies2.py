
#!/usr/bin/python3
import argparse
import os
import re
import struct
import sys
import glob
import ctypes
import array
import logging
from datetime import datetime
from collections import OrderedDict
from contextlib import suppress
from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError
from xml.sax.saxutils import escape, unescape

import xml.etree.ElementTree as ET

import _thread
import threading
import time

re_localization = re.compile(r'<\$>([0-9]+)</>')
re_number = re.compile(r'^-?[0-9]+(\.([0-9]+)?)?$')
COL_TYPE_NUMBER = 0
COL_TYPE_STRING = 1
COL_TYPE_CALCULATED = 2


def xor_str(string):
    return array.array('B', [c ^ 1 for c in string]).tobytes()


class Struct(ctypes.Structure):
    _fields_ = []

    def __init__(self, fp=None):
        super().__init__()
        if fp is not None:
            self.read_from(fp)

    def read_from(self, fp):
        n = ctypes.sizeof(self)
        ctypes.memmove(ctypes.addressof(self), fp.read(n), n)


class IESHeader(Struct):
    _fields_ = [
        ('idspace', ctypes.c_char * 64),
        ('version', ctypes.c_short),
        ('info_size', ctypes.c_uint32),
        ('data_size', ctypes.c_uint32),
        ('total_size', ctypes.c_uint32),
        ('has_class_id', ctypes.c_bool),
        ('row_count', ctypes.c_uint16),
        ('col_count_total', ctypes.c_uint16),
        ('col_count_number', ctypes.c_uint16),
        ('col_count_strings', ctypes.c_uint16),
    ]


class IESHeader2(IESHeader):
    _fields_ = [
        ('module_space', ctypes.c_char * 64),
    ]


class IESHeader3(IESHeader2):
    _fields_ = [
        ('module_prefix', ctypes.c_char * 64),
    ]


class IESColumn(Struct):
    _fields_ = [
        ('column_name', ctypes.c_char * 64),
        ('full_name', ctypes.c_char * 64),
        ('col_type', ctypes.c_uint16),
        ('is_static', ctypes.c_bool),
        ('index', ctypes.c_uint16),
    ]

    def read_from(self, fp):
        super().read_from(fp)
        self.column_name = xor_str(self.column_name)
        self.full_name = xor_str(self.full_name)


def indent(elem, level=0, more_sibs=False, order=None):
    i = '\n'
    if level:
        i += (level-1) * '  '
    num_kids = len(elem)
    if num_kids:
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
            if level:
                elem.text += '  '
        count = 0
        for kid in elem:
            indent(kid, level+1, count < num_kids - 1)
            count += 1
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
            if more_sibs:
                elem.tail += '  '
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i
            if more_sibs:
                elem.tail += '  '


def parse_order(xml_file):
    score = {}
    r1 = re.compile(r'<Class(\s+([a-zA-Z0-9_]+)\s*=\s*"[^"]+")+\s*/>', re.IGNORECASE)
    r2 = re.compile('="[^"]+"\s*')
    with open(xml_file) as fp:
        data = fp.read().replace('\r', '')
        for m in r1.finditer(data):
            cls = m.group()[6:-2].strip()
            attrs = r2.split(cls)
            for i, a in enumerate(attrs):
                a = a.strip()
                try:
                    score[a] += i
                except KeyError:
                    score[a] = i
    return list(k[0] for k in sorted(score.items(), key=lambda x: x[1]))


def parse_dict(xml_file):
    result = {}
    dom = ElementTree.parse(xml_file)
    root = dom.getroot()
    """:type : ElementTree.Element"""
    for txt in root.iterfind('./Text'):
        result[txt.attrib['ClassID']] = txt.attrib['Text']
    return result


def autodetect_output_file(input_file):
    if isinstance(input_file, list):
        input_file = input_file[0]
    if input_file.endswith('.ies'):
        return input_file[:-3] + 'xml'
    else:
        return input_file + '.xml'


def ies_to_xml(input, output, order, dictionary, encoding, use_float):
    with open(input, 'rb') as fp:
        fp.seek(0, os.SEEK_END)
        total_size = fp.tell()
        fp.seek(0, os.SEEK_SET)
        hdr = IESHeader()
        hdr.read_from(fp)

        if hdr.version == 1:
            pass
        elif hdr.version == 2:
            fp.seek(0, os.SEEK_SET)
            hdr = IESHeader2()
            hdr.read_from(fp)
        elif hdr.version == 3:
            fp.seek(0, os.SEEK_SET)
            hdr = IESHeader3()
            hdr.read_from(fp)
        else:
            raise Exception('Unknown ies version {}'.format(int(hdr.version)))

        if hdr.info_size != ctypes.sizeof(IESColumn) * hdr.col_count_total:
            raise Exception('Invalid info_size')

        if hdr.total_size != ctypes.sizeof(hdr) + hdr.info_size + hdr.data_size:
            raise Exception('Invalid total_size')

        if hdr.total_size != total_size:
            raise Exception('total_size does not match file size')

        cols = [IESColumn(fp) for _ in range(hdr.col_count_total)]

        try:
            encoding = encoding or 'UTF-8'
            with open(output, 'w+', encoding=encoding) as fw:
                xml_start_file = '<?xml version="1.0" encoding="' + encoding + '"?>\n'
                fw.write(xml_start_file)
                if encoding == 'UTF-8':
                    fw.write('<idspace id="{}">'.format(hdr.idspace.decode(encoding)))
                else:
                    fw.write('<idspace id="{}">'.format(hdr.idspace.decode("iso-8859-1")))
                for i in range(hdr.row_count):
                    try:
                        class_id, class_len = struct.unpack('<IH', fp.read(6))
                    except:
                        class_id, class_len = None, None
                    if encoding == 'UTF-8':
                        if class_len:
                            try:
                                class_name = fp.read(class_len).decode(encoding)
                            except:
                                class_name = fp.read(class_len).decode("iso-8859-5")
                        else:
                            class_name = None
                    else:
                        if class_len:
                            class_name = fp.read(class_len).decode("iso-8859-1")
                        else:
                            class_name = None
                    if use_float:
                        numbers = struct.unpack('<{}f'.format(hdr.col_count_number),
                                                fp.read(4 * hdr.col_count_number))
                    else:
                        try:
                            numbers = struct.unpack('<{}d'.format(hdr.col_count_number),
                                                    fp.read(8 * hdr.col_count_number))
                        except:
                            # struct.error: unpack requires a buffer of 8 bytes
                            numbers = struct.unpack('', fp.read(8 * hdr.col_count_number))
                    strings = []
                    for _ in range(hdr.col_count_strings):
                        try:
                            str_len = int(struct.unpack('<H', fp.read(2))[0])
                        except:
                            str_len = struct.unpack('', fp.read(2)) and int(struct.unpack('', fp.read(2))[0])
                        if str_len:
                            if encoding == 'UTF-8':
                                try:
                                    strings.append(
                                        unescape(xor_str(fp.read(str_len)).decode(encoding)))
                                except:
                                    strings.append(
                                        unescape(xor_str(fp.read(str_len)).decode('iso-8859-5')))
                            else:
                                strings.append(
                                    unescape(xor_str(fp.read(str_len)).decode("iso-8859-1")))
                        else:
                            strings.append('None')
                    try:
                        struct.unpack('{}B'.format(hdr.col_count_strings), fp.read(hdr.col_count_strings))  # is_cp
                    except:
                        struct.unpack('', fp.read(hdr.col_count_strings))  # is_cp
                    if dictionary:
                        for i, string in enumerate(strings):
                            for m in re_localization.finditer(string):
                                try:
                                    strings[i] = string.replace(m.group(), dictionary[m.group(1)])
                                except KeyError:
                                    logging.warning('Missing translation for text id {}'.format(m.group(1)))

                    attr = OrderedDict([
                        ('ClassID', str(class_id)),
                        ('ClassName', class_name)
                    ])

                    for col in cols:
                        if col.col_type == COL_TYPE_NUMBER:
                            if numbers:
                                value = ('%f' % numbers[col.index]).rstrip('0').rstrip('.')
                            else:
                                continue
                        elif col.col_type == COL_TYPE_STRING or col.col_type == COL_TYPE_CALCULATED:
                            value = strings[col.index]
                        else:
                            raise Exception('Unknown col_type {} in {}'.format(col.col_type, input))
                        if encoding == 'UTF-8':
                            full_name_decode = col.full_name.decode(encoding)
                        else:
                            full_name_decode = col.full_name.decode("iso-8859-1")
                        attr[full_name_decode] = value

                    fw.write('\n\t<Class ')
                    additional_escape = {'"': '&quot;'}
                    if order:
                        for k in order:
                            with suppress(KeyError):
                                if attr[k]:
                                    fw.write('{}="{}" '.format(k, escape(attr[k], additional_escape)))
                                del attr[k]
                    index = 1
                    for k, v in attr.items():
                        index += 1
                        if v:
                            try:
                                fw.write('{}="{}" '.format(k,
                                                           escape(v.encode('iso-8859-1').decode('ksc5601'),
                                                                     additional_escape)))
                            except:
                                # UnicodeEncodeError: 'latin-1' codec can't encode characters in position 13-14:
                                # ordinal not in range(256)
                                try:
                                    fw.write('{}="{}" '.format(k,
                                                               escape(v.encode('iso-8859-5').decode('ksc5601'),
                                                                         additional_escape)))
                                except:
                                    fw.write('{}="{}" '.format(k,
                                                               escape(v.encode('utf-8').decode('utf-8'),
                                                                      additional_escape)))
                    fw.write('/>')

                fw.write('\n</idspace>\n')
        except UnicodeDecodeError as e:
            logging.critical('Could not decode string: ', e.object[e.start:e.end])
        except UnicodeEncodeError as e:
            logging.critical('Could not encode string: ', e.object[e.start:e.end])


def xml_to_ies(input, output, order, dictionary, encoding, use_float):
    try:
        if encoding == 'EUC-KR':
            xmlp = ET.XMLParser(encoding='ksc5601')
            dom = ET.parse(input, parser=xmlp)
        else:
            xmlp = ET.XMLParser(encoding=encoding)
            dom = ET.parse(input, parser=xmlp)
    except Exception as e:
        try:
            encoding = 'iso-8859-5'
            xmlp = ET.XMLParser(encoding='iso-8859-5')
            dom = ET.parse(input, parser=xmlp)
        except Exception as e:
            return

    root = dom.getroot()

    fields = list(root.findall('.//Class'))

    # In case this is localized file - load class from main file and use it's data to fill in rest of the table.
    # Also insert ClassSchema
    if len(os.path.basename(os.path.dirname(input))) == 3:
        original_file_name = os.path.join(os.path.dirname(os.path.dirname(input)), os.path.basename(input))
        if os.path.isfile(original_file_name):
            dom_main = ElementTree.parse(original_file_name)
            root_main = dom_main.getroot()
            # These attributes must match main file so copy them over
            if 'module' in root_main.attrib:
                root.attrib['module'] = root_main.attrib['module']
            if 'module_prefix' in root_main.attrib:
                root.attrib['module_prefix'] = root_main.attrib['module_prefix']
            schema = root_main.find('./Schema')
            if schema is not None:
                root.append(schema)
            # Fill in missing fields from base class
            for cls in fields:
                class_id = cls.get('ClassID')
                if class_id:
                    orig_cls = root_main.find(f'./Class[@ClassID="{class_id}"]')
                else:
                    class_name = cls.get('ClassName')
                    orig_cls = root_main.find(f'./Class[@ClassName="{class_name}"]')
                if orig_cls is not None:
                    for k, v in orig_cls.attrib.items():
                        if k not in cls.attrib:
                            cls.attrib[k] = v

    module_space = root.attrib.get('module')
    module_prefix = root.attrib.get('module_prefix')

    if module_prefix:
        hdr = IESHeader3()
        hdr.version = 3
        hdr.module_prefix = module_prefix.encode(encoding)
        hdr.module_space = module_space.encode(encoding)
    elif module_space:
        hdr = IESHeader2()
        hdr.version = 2
        hdr.module_space = module_space.encode(encoding)
    else:
        hdr = IESHeader()
        hdr.version = 1

    hdr.idspace = root.attrib['id'].encode(encoding)
    hdr.has_class_id = all(['ClassID' in cls.attrib for cls in fields])
    if not hdr.has_class_id:
        if any(['ClassID' in cls.attrib for cls in fields]):
            raise Exception('All classes either must have ClassID or must not have it.')

    columns_number = []
    columns_string = []
    columns = {}

    column_schema = root.find('./Schema/ClassSchema')
    if column_schema is not None:
        column_schema = column_schema.attrib
    else:
        column_schema = {}

    # Create columns and detect their types
    hdr.row_count = len(fields)
    string_data_size = 0
    hdr.col_count_total = 0
    hdr.col_count_number = 0
    hdr.col_count_strings = 0
    for cls in fields:
        for col_name, value in cls.attrib.items():
            col = columns.get(col_name)

            schema_type = column_schema.get(col_name)
            if schema_type is not None:
                if schema_type == 'STRING':
                    column_type = COL_TYPE_STRING
                elif schema_type == 'NUMBER':
                    column_type = COL_TYPE_NUMBER
                elif schema_type == 'CALCULATED':
                    column_type = COL_TYPE_CALCULATED
                else:
                    raise Exception('Invalid ClassSchema')
            else:
                if col_name.startswith('CP_'):
                    column_type = COL_TYPE_CALCULATED
                elif re_number.match(value.strip()) is not None:
                    column_type = COL_TYPE_NUMBER
                else:
                    column_type = COL_TYPE_STRING

            if col is None:
                col = IESColumn()
                col.full_name = xor_str(col_name.encode(encoding))
                col.is_static = col_name.startswith('SP_')
                col.col_type = column_type
                if col_name.startswith('SP_') or col_name.startswith('CP_'):
                    col.column_name = xor_str(col_name[3:].encode(encoding))
                else:
                    col.column_name = xor_str(col_name.encode(encoding))

                hdr.col_count_total += 1
                if col.col_type == COL_TYPE_NUMBER:
                    col.index = hdr.col_count_number
                    hdr.col_count_number += 1
                    columns_number.append(col_name)
                else:
                    col.index = hdr.col_count_strings
                    hdr.col_count_strings += 1
                    columns_string.append(col_name)
                    string_data_size += 2 + len(value.encode(encoding))

                columns[col_name] = col
            else:
                if col.col_type != column_type:
                    raise Exception('Column {} type mismatch in {} ClassID={}. Add ClassSchema entry.'.format(
                        cls.attrib.get('ClassID', -1), col_name, os.path.basename(input)))

    hdr.info_size = ctypes.sizeof(IESColumn) * hdr.col_count_total

    assert hdr.col_count_total == hdr.col_count_number + hdr.col_count_strings

    with open(output, 'w+b') as fp:
        # ef = ET.fromstring(f.read())
        fp.write(ctypes.string_at(ctypes.addressof(hdr), ctypes.sizeof(hdr)))

        for col in columns.values():
            fp.write(ctypes.string_at(ctypes.addressof(col), ctypes.sizeof(col)))

        data_begin = fp.tell()
        for j, cls in enumerate(fields):
            class_name = cls.attrib.get('ClassName', '')
            fp.write(struct.pack('IH', int(cls.attrib.get('ClassID', 0)), len(class_name)))
            if class_name:
                fp.write(xor_str(class_name.encode(encoding)))

            for col_name in columns_number:
                fp.write(struct.pack('f' if use_float else 'd', float(cls.attrib.get(col_name, 0.0))))

            is_scr = [False] * hdr.col_count_strings
            for i, col_name in enumerate(columns_string):
                value = cls.get(col_name, '')
                if value == 'None':
                    value = ''
                else:
                    is_scr[i] = value.startswith('SCP_') or value.startswith('SCR_')
                value = value.encode(encoding)
                fp.write(struct.pack('H', len(value)))
                if value:
                    fp.write(xor_str(value))

            fp.write(struct.pack('B' * len(is_scr), *is_scr))

        hdr.data_size = fp.tell() - data_begin
        hdr.total_size = ctypes.sizeof(hdr) + hdr.info_size + hdr.data_size
        fp.seek(0, os.SEEK_SET)
        fp.write(ctypes.string_at(ctypes.addressof(hdr), ctypes.sizeof(hdr)))

    os.utime(output, (-1, os.path.getmtime(input)))


def __validation_sizeof_ies():
    if ctypes.sizeof(IESHeader) != 92:
        raise Exception('IESHeader size is invalid')

    if ctypes.sizeof(IESHeader2) != 156:
        raise Exception('IESHeader2 size is invalid')

    if ctypes.sizeof(IESHeader3) != 220:
        raise Exception('IESHeader3 size is invalid')

    if ctypes.sizeof(IESColumn) != 134:
        raise Exception('IESColumn size is invalid')

def __generate_files(input, output, dictionary, encoding, order, float_val):
    order = None
    
    if order:
        order = os.path.abspath(order)
        order_file = os.path.join(order, os.path.splitext(os.path.basename(input))[0] + '.xml')
        try:
            order = parse_order(order_file)
        except FileNotFoundError:
            logging.warning('Order not parsed, file {} missing'.format(order_file))
    if input.endswith('.ies') and output.endswith('.xml'):
        ies_to_xml(input, output, order, dictionary, encoding, float_val)
    elif input.endswith('.xml') and output.endswith('.ies'):
        xml_to_ies(input, output, order, dictionary, encoding, float_val)
    else:
        raise Exception('Unknown file format combo. Must be ies+xml.')

# noinspection PyUnresolvedReferences
def main():
    parser = argparse.ArgumentParser(description='ies to xml converter for Granado Espada by bit (rGE, 2015)')
    parser.add_argument('-o',
                        '--order',
                        help='XML directory for using as source of xml attribute ordering.')
    parser.add_argument('-e',
                        '--encoding',
                        action='store',
                        help='String encoding in ies files.')
    parser.add_argument('-d',
                        '--dict',
                        help='Use dictionary_local.xml to replace localized string placeholders.')
    parser.add_argument('-f',
                        '--float',
                        action='store_true',
                        help='Use single-precision floats for numbers array.')
    parser.add_argument('input',
                        help='Input folder (ies). '
                             'If this parameter is wildcard then output parameter will be ignored.')
    parser.add_argument('output',
                        help='Output file (xml)',
                        nargs='?')

    args = parser.parse_args()

    __validation_sizeof_ies()

    input_folder = args.input
    encoding = args.encoding.upper()

    args.input = []
    args.output = []
    if not os.path.exists("folder_output"):
        os.mkdir("folder_output")

    for file_name in os.listdir(input_folder):
        args.input.append(input_folder + '/' + file_name)
        if file_name.endswith('.ies'):
            args.output.append("folder_output" + '/' + file_name[:-3] + 'xml')
        else:
            args.output.append("folder_output" + '/' + file_name[:-3] + 'ies')
        
    if args.dict:
        dictionary = parse_dict(args.dict)
    else:
        dictionary = None

    # Multithreading
    threads = []
    try:
        for input, output in zip(args.input, args.output):
            threads.append(threading.Thread(target =  __generate_files, args = (input, output, dictionary, encoding,
                                                    args.order, args.float)))
    except Exception as exp:
        print(exp)
        print("Error: Thread not initiated")
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

if __name__ == '__main__':
    start_time = datetime.now()
    main()
    print('Finished in', datetime.now() - start_time)
