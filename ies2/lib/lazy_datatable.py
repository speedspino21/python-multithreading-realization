import copy
import os
import re
from contextlib import suppress

from lxml import etree


class Class(object):
    def __init__(self, dt, base, local):
        super().__init__()
        self._dt = dt
        self._base = base
        self._local = local

    def copy(self):
        base = None if self._base is None else copy.deepcopy(self._base)
        local = None if self._local is None else copy.deepcopy(self._local)
        cls = Class(None, base, local)
        return cls

    def getparent(self):
        return self._dt

    def keys(self):
        base_keys = []
        local_keys = []
        if self._base is not None:
            base_keys = self._base.attrib.keys()
        if self._local is not None:
            local_keys = self._local.attrib.keys()
        return list(set(base_keys + local_keys))

    def items(self):
        return list(self.__iter__())

    def get(self, key, default=None):
        try:
            self.__getitem__(key)
        except KeyError:
            return default

    def __len__(self):
        return len(self.keys())

    def __iter__(self):
        if self._base is None:
            yield from self._local.attrib.items()
            return

        if self._local is None:
            yield from self._base.attrib.items()
            return

        base = self._base.attrib
        local = self._local.attrib
        for k, v in base.items():
            if k in local:
                yield k, local[k]
            else:
                yield k, base[k]

    def __getitem__(self, k):
        base = self._base.attrib if self._base is not None else {}
        local = self._local.attrib if self._local is not None else {}
        if k in local:
            return local[k]
        return base[k]

    def __setitem__(self, k, v):
        if not isinstance(v, str):
            v = str(v)

        if self._dt is None:
            if self._local is not None:
                self._local.attrib[k] = v
            elif self._base is not None:
                self._base.attrib[k] = v
            return

        self._dt.is_dirty = True

        if k == 'ClassID':
            old_k = self.__getitem__(k)
            if old_k in self._dt._by_class_id:
                del self._dt._by_class_id[old_k]
            self._dt._by_class_id[v] = self
        elif k == 'ClassName':
            old_k = self.__getitem__(k)
            if old_k in self._dt._by_class_name:
                del self._dt._by_class_name[old_k]
            self._dt._by_class_name[v] = self

        if self._dt.xml_localized is not None:
            if self._local is None:
                local_cls = etree.Element('Class')
                if self._base is not None:
                    for field in ('ClassID', 'ClassName'):
                        value = self._base.attrib.get(field)
                        if value is not None:
                            local_cls.attrib[field] = value
                self._local = local_cls
                self._dt._insert_cls(self._dt.xml_localized, local_cls)

            base = self._base.attrib if self._base is not None else {}
            local = self._local.attrib
            if k in base:
                if base[k] == v:
                    if k in local:
                        del local[k]
                    return
            local[k] = v
        else:
            self._base.attrib[k] = v

    def __contains__(self, o):
        if self._base is not None and o in self._base.attrib:
            return True
        if self._local is not None and o in self._local.attrib:
            return True
        return False

    def __delitem__(self, k):
        if self._dt is not None:
            self._dt.is_dirty = True
        if self._local is not None:
            local = self._local.attrib
            if k in local:
                del local[k]
        else:
            del self._base.attrib[k]


class DataTable(object):
    def __init__(self, directory, datatable_name, locale=None):
        self._directory = directory
        self._datatable_name = datatable_name
        self._source_locale = locale
        self.is_dirty = False
        self._by_class_id = {}
        self._by_class_name = {}
        self.xml_localized = None
        self.xml = None
        self.import_key = 'ClassID'

        try:
            base_path = os.path.join(self._directory, 'datatable_{}.xml'.format(datatable_name))
            try:
                self.xml = etree.parse(base_path).getroot()
            except OSError:
                self.xml = None

            if locale is None:
                return

            local_path = os.path.join(self._directory, self._source_locale, 'datatable_{}.xml'.format(datatable_name))
            try:
                self.xml_localized = etree.parse(local_path).getroot()
            except OSError:
                return
        finally:
            self._index_table()

    def _index_table(self):
        has_class_name = True
        for cls in self.find_cls_xpath('.//Class'):
            self._by_class_id[cls['ClassID']] = cls
            if 'ClassName' in cls:
                self._by_class_name[cls['ClassName']] = cls
            else:
                has_class_name = False
        if has_class_name:
            self.import_key = 'ClassName'

    def get_by_class_id(self, class_id):
        try:
            return self._by_class_id[class_id]
        except KeyError:
            return None

    def get_by_class_name(self, class_name):
        try:
            return self._by_class_name[class_name]
        except KeyError:
            return None

    def insert_cls(self, cls):
        self.is_dirty = True
        cls._dt = self
        if self.xml_localized is not None:
            res = self._insert_cls(self.xml_localized, cls._local)
        else:
            res = self._insert_cls(self.xml, cls._base)
        if res:
            self._by_class_id[cls['ClassID']] = cls
            if 'ClassName' in cls:
                self._by_class_name[cls['ClassName']] = cls
        else:
            cls._dt = None
        return res

    def _insert_cls(self, dest, cls):
        class_id = int(cls.attrib['ClassID'])
        if class_id == -1 or dest.attrib['id'] in ('ChangeItemRatioDelect', 'ChangeItemRatio'):
            cls.attrib['ClassID'] = str(int(next(dest.iterchildren(reversed=True)).attrib['ClassID']) + 1)
            dest.append(cls)
        else:
            parent_cls = dest.find('.//Class[@ClassID="{}"]'.format(class_id))
            if parent_cls is not None:
                # This class already exists
                return False
            next_cls = dest.xpath('.//Class[@ClassID>$class_id]', class_id=class_id)
            if len(next_cls) > 0:
                next_cls = next_cls[0]
                parent = next_cls.getparent()
                parent.insert(parent.index(next_cls), cls)
            else:
                dest.append(cls)
        return True

    def save(self):
        if self.xml is not None:
            # Save main xml file
            xml_path = os.path.join(self._directory, 'datatable_{}.xml'.format(self._datatable_name))
            with open(xml_path, 'w+b') as fp:
                self._indent_tree(self.xml)
                etree.ElementTree(self.xml).write(fp, encoding='utf-8', xml_declaration=True, pretty_print=True)

        if self.xml_localized is not None:
            # Save localized xml file
            xml_path = os.path.join(self._directory, self._source_locale, 'datatable_{}.xml'.format(self._datatable_name))
            with open(xml_path, 'w+b') as fp:
                self._indent_tree(self.xml_localized)
                etree.ElementTree(self.xml_localized).write(fp, encoding='utf-8', xml_declaration=True, pretty_print=True)

    def find_cls_xpath(self, xpath):
        all_localized = self.xml_localized.xpath(xpath) if self.xml_localized is not None else []
        for el in self.xml.xpath(xpath):
            localized = None
            if self.xml_localized is not None:
                localized = self.xml_localized.find(f'.//Class[@ClassID="{el.attrib["ClassID"]}"]')
                if localized is not None:
                    with suppress(ValueError):
                        all_localized.remove(localized)
            yield Class(self, el, localized)
        for localized in all_localized:
            yield Class(self, None, localized)

    def get_cls_xpath(self, xpath):
        try:
            return next(self.find_cls_xpath(xpath))
        except StopIteration:
            return None

    def find_cls(self, *, condition='or', **kwargs):
        if len(kwargs):
            yield from self.find_cls_xpath('.//Class[' + (' {} '.format(condition)).join(
                    ['@{}=\'{}\''.format(k, v) for k, v in kwargs.items()]) + ']')
        else:
            yield from self.find_cls_xpath('.//Class')

    def get_cls(self, *, condition='or', **kwargs):
        try:
            return next(self.find_cls(condition=condition, **kwargs))
        except StopIteration:
            return None

    @staticmethod
    def _indent_tree(tree, level=1, indent='\t'):
        for i, el in enumerate(tree):
            el.tail = '\n'
            if i < len(tree) - 1:
                el.tail += level * indent
            for child in el:
                DataTable._indent_tree(child, level + 1, indent)


class LazyDataTables(object):
    item_datatables = ('item_armor', 'item_back', 'item_belt', 'item_book', 'item_boots', 'item_breast', 'item_scroll',
                       'item_costume', 'item_consume', 'item_earring', 'item_face', 'item_glove', 'item_head',
                       'item_neck', 'item_ring', 'item_shoulder', 'item_weapon', 'item_etc', 'item_recipe',
                       'item_assist')
    monster_datatables = ('monster_1', 'monster_2', 'monster_3', 'monster_4')

    def __init__(self, directory, source_locale=None):
        self._directory = directory
        self.data_tables = {}
        self._source_locale = source_locale

    @staticmethod
    def filename_to_datatable(filename):
        if '/' in filename:
            filename = os.path.basename(filename)
            m = re.match(r'datatable_(.*)\.xml', filename)
            if m is not None:
                datatable = m.group(1)
                if datatable in LazyDataTables.monster_datatables:
                    return 'monster'
                if datatable in LazyDataTables.item_datatables:
                    return 'item'
                return datatable

    def _get_datatable(self, datatable_name):
        try:
            return self.data_tables[datatable_name]
        except KeyError:
            datatable = self.data_tables[datatable_name] = DataTable(self._directory, datatable_name, self._source_locale)
            return datatable

    def get_datatables(self, datatable_name):
        if isinstance(datatable_name, str):
            datatable_names = [datatable_name]
        else:
            datatable_names = datatable_name[:]

        if 'item' in datatable_names:
            datatable_names.extend(self.item_datatables)

        if 'monster' in datatable_names:
            datatable_names.extend(self.monster_datatables)

        for datatable_name in datatable_names:
            dt = self._get_datatable(datatable_name)
            if dt is not None:
                yield dt

    def get_datatable(self, datatable_name):
        return next(self.get_datatables(datatable_name))

    def find_cls_xpath(self, datatable, xpath):
        for dt in self.get_datatables(datatable):
            yield from dt.find_cls_xpath(xpath)

    def get_cls_xpath(self, datatable, xpath):
        for dt in self.get_datatables(datatable):
            return dt.get_cls_xpath(xpath)
        return None

    def find_cls(self, datatable, *, condition='or', **kwargs):
        for dt in self.get_datatables(datatable):
            yield from dt.find_cls(condition=condition, **kwargs)

    def get_cls(self, datatable, *, condition='or', **kwargs):
        for dt in self.get_datatables(datatable):
            cls = dt.get_cls(condition=condition, **kwargs)
            if cls is not None:
                return cls
        return None

    def save(self):
        for dt in self.data_tables.values():
            if dt.is_dirty:
                dt.save()

    def insert_cls(self, datatable, cls):
        dest = next(self.get_datatables(datatable))
        return dest.insert_cls(cls)

    def get_owner(self, cls):
        for name, xml in self.data_tables.items():
            if xml == cls.getparent():
                return name

    def mark_dirty(self, owner_datatable):
        for dt in self.get_datatables(owner_datatable):
            dt.is_dirty = True

    def get_by_class_id(self, datatable, class_id):
        for dt in self.get_datatables(datatable):
            cls = dt.get_by_class_id(class_id)
            if cls is not None:
                return cls

    def get_by_class_name(self, datatable, class_name):
        for dt in self.get_datatables(datatable):
            cls = dt.get_by_class_name(class_name)
            if cls is not None:
                return cls

    def create_cls(self, table, class_id):
        dt = self._get_datatable(table)
        if dt.xml_localized is not None:
            local_el = etree.SubElement(dt.xml_localized, 'Class', {'ClassID': class_id})
            el = None
        else:
            el = etree.SubElement(dt.xml, 'Class', {'ClassID': class_id})
            local_el = None
        cls = Class(dt, el, local_el)
        self.insert_cls(table, cls)
        return cls
