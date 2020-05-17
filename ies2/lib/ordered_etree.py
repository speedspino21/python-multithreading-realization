import warnings
from xml.etree.ElementTree import Comment, ProcessingInstruction, _escape_cdata, _escape_attrib, QName, TreeBuilder, \
    ParseError
from xml.etree import ElementTree
from collections import OrderedDict


class OrderedXMLTreeBuilder(object):
    """Element structure builder for XML source data based on the expat parser.

    *html* are predefined HTML entities (not supported currently),
    *target* is an optional target object which defaults to an instance of the
    standard TreeBuilder class, *encoding* is an optional encoding string
    which if given, overrides the encoding specified in the XML file:
    http://www.iana.org/assignments/character-sets

    """

    def __init__(self, html=0, target=None, encoding=None):
        try:
            from xml.parsers import expat
        except ImportError:
            try:
                import pyexpat as expat
            except ImportError:
                raise ImportError(
                        "No module named expat; use SimpleXMLTreeBuilder instead"
                )
        parser = expat.ParserCreate(encoding, "}")
        if target is None:
            target = TreeBuilder()
        # underscored names are provided for compatibility only
        self.parser = self._parser = parser
        self.target = self._target = target
        self._error = expat.error
        self._names = {} # name memo cache
        # main callbacks
        parser.DefaultHandlerExpand = self._default
        if hasattr(target, 'start'):
            parser.StartElementHandler = self._start
        if hasattr(target, 'end'):
            parser.EndElementHandler = self._end
        if hasattr(target, 'data'):
            parser.CharacterDataHandler = target.data
        # miscellaneous callbacks
        if hasattr(target, 'comment'):
            parser.CommentHandler = target.comment
        if hasattr(target, 'pi'):
            parser.ProcessingInstructionHandler = target.pi
        # Configure pyexpat: buffering, new-style attribute handling.
        parser.buffer_text = 1
        parser.ordered_attributes = 1
        parser.specified_attributes = 1
        self._doctype = None
        self.entity = {}
        try:
            self.version = "Expat %d.%d.%d" % expat.version_info
        except AttributeError:
            pass # unknown

    def _setevents(self, events_queue, events_to_report):
        # Internal API for XMLPullParser
        # events_to_report: a list of events to report during parsing (same as
        # the *events* of XMLPullParser's constructor.
        # events_queue: a list of actual parsing events that will be populated
        # by the underlying parser.
        #
        parser = self._parser
        append = events_queue.append
        for event_name in events_to_report:
            if event_name == "start":
                parser.ordered_attributes = 1
                parser.specified_attributes = 1
                def handler(tag, attrib_in, event=event_name, append=append,
                            start=self._start):
                    append((event, start(tag, attrib_in)))
                parser.StartElementHandler = handler
            elif event_name == "end":
                def handler(tag, event=event_name, append=append,
                            end=self._end):
                    append((event, end(tag)))
                parser.EndElementHandler = handler
            elif event_name == "start-ns":
                def handler(prefix, uri, event=event_name, append=append):
                    append((event, (prefix or "", uri or "")))
                parser.StartNamespaceDeclHandler = handler
            elif event_name == "end-ns":
                def handler(prefix, event=event_name, append=append):
                    append((event, None))
                parser.EndNamespaceDeclHandler = handler
            else:
                raise ValueError("unknown event %r" % event_name)

    def _raiseerror(self, value):
        err = ParseError(value)
        err.code = value.code
        err.position = value.lineno, value.offset
        raise err

    def _fixname(self, key):
        # expand qname, and convert name string to ascii, if possible
        try:
            name = self._names[key]
        except KeyError:
            name = key
            if "}" in name:
                name = "{" + name
            self._names[key] = name
        return name

    def _start(self, tag, attr_list):
        # Handler for expat's StartElementHandler. Since ordered_attributes
        # is set, the attributes are reported as a list of alternating
        # attribute name,value.
        fixname = self._fixname
        tag = fixname(tag)
        attrib = OrderedDict()
        if attr_list:
            for i in range(0, len(attr_list), 2):
                attrib[fixname(attr_list[i])] = attr_list[i+1]
        return self.target.start(tag, attrib)

    def _end(self, tag):
        return self.target.end(self._fixname(tag))

    def _default(self, text):
        prefix = text[:1]
        if prefix == "&":
            # deal with undefined entities
            try:
                data_handler = self.target.data
            except AttributeError:
                return
            try:
                data_handler(self.entity[text[1:-1]])
            except KeyError:
                from xml.parsers import expat
                err = expat.error(
                        "undefined entity %s: line %d, column %d" %
                        (text, self.parser.ErrorLineNumber,
                         self.parser.ErrorColumnNumber)
                )
                err.code = 11 # XML_ERROR_UNDEFINED_ENTITY
                err.lineno = self.parser.ErrorLineNumber
                err.offset = self.parser.ErrorColumnNumber
                raise err
        elif prefix == "<" and text[:9] == "<!DOCTYPE":
            self._doctype = [] # inside a doctype declaration
        elif self._doctype is not None:
            # parse doctype contents
            if prefix == ">":
                self._doctype = None
                return
            text = text.strip()
            if not text:
                return
            self._doctype.append(text)
            n = len(self._doctype)
            if n > 2:
                type = self._doctype[1]
                if type == "PUBLIC" and n == 4:
                    name, type, pubid, system = self._doctype
                    if pubid:
                        pubid = pubid[1:-1]
                elif type == "SYSTEM" and n == 3:
                    name, type, system = self._doctype
                    pubid = None
                else:
                    return
                if hasattr(self.target, "doctype"):
                    self.target.doctype(name, pubid, system[1:-1])
                elif self.doctype != self._XMLParser__doctype:
                    # warn about deprecated call
                    self._XMLParser__doctype(name, pubid, system[1:-1])
                    self.doctype(name, pubid, system[1:-1])
                self._doctype = None

    def doctype(self, name, pubid, system):
        """(Deprecated)  Handle doctype declaration

        *name* is the Doctype name, *pubid* is the public identifier,
        and *system* is the system identifier.

        """
        warnings.warn(
                "This method of XMLParser is deprecated.  Define doctype() "
                "method on the TreeBuilder target.",
                DeprecationWarning,
        )

    # sentinel, if doctype is redefined in a subclass
    __doctype = doctype

    def feed(self, data):
        """Feed encoded data to parser."""
        try:
            self.parser.Parse(data, 0)
        except self._error as v:
            self._raiseerror(v)

    def close(self):
        """Finish feeding data to parser and return element structure."""
        try:
            self.parser.Parse("", 1) # end of data
        except self._error as v:
            self._raiseerror(v)
        try:
            close_handler = self.target.close
        except AttributeError:
            pass
        else:
            return close_handler()
        finally:
            # get rid of circular references
            del self.parser, self._parser
            del self.target, self._target


def _serialize_xml(write, elem, qnames, namespaces,
                   short_empty_elements, **kwargs):
    tag = elem.tag
    text = elem.text
    if tag is Comment:
        write("<!--%s-->" % text)
    elif tag is ProcessingInstruction:
        write("<?%s?>" % text)
    else:
        tag = qnames[tag]
        if tag is None:
            if text:
                write(_escape_cdata(text))
            for e in elem:
                _serialize_xml(write, e, qnames, None,
                               short_empty_elements=short_empty_elements)
        else:
            write("<" + tag)
            items = list(elem.items())
            if items or namespaces:
                if namespaces:
                    for v, k in namespaces.items():  # sort on prefix
                        if k:
                            k = ":" + k
                        write(" xmlns%s=\"%s\"" % (
                            k,
                            _escape_attrib(str(v))
                        ))
                for k, v in items:  # lexical order
                    if isinstance(k, QName):
                        k = k.text
                    if isinstance(v, QName):
                        v = qnames[v.text]
                    else:
                        v = _escape_attrib(str(v))
                    write(" %s=\"%s\"" % (qnames[k], v))
            if text or len(elem) or not short_empty_elements:
                write(">")
                if text:
                    write(_escape_cdata(text))
                for e in elem:
                    _serialize_xml(write, e, qnames, None,
                                   short_empty_elements=short_empty_elements)
                write("</" + tag + ">")
            else:
                write(" />")
    if elem.tail:
        write(_escape_cdata(elem.tail))


ElementTree._serialize_xml = _serialize_xml
