/*
 * Module for decryption of data encrypted using the ZIP 2.0 simple encryption
 * algorithm.
 *
 * Details of encryption algo at:
 * http://www.pkware.com/documents/casestudies/APPNOTE.TXT
 * 
 * Author: Shashank(shashank.sunny.singh@gmail.com)
 */

#define PY_SSIZE_T_CLEAN

#include "Python.h"
#include "structmember.h"

static const int _CRC_POLY = 0xedb88320;
static int _CRC_TABLE[256];

static void
_build_crc_table(void)
{
    int i, j, crc;
    for (i = 0; i < 256; i++) {
        crc = i;
        for (j = 0; j < 8; j++) {
            if (crc & 1)
                crc = ((crc >> 1) & 0x7FFFFFFF) ^ _CRC_POLY;
            else
                crc = ((crc >> 1) & 0x7FFFFFFF);
        }
        _CRC_TABLE[i] = crc;
    }
}

static int
_crc32(char c, int crc)
{
    return ((crc >> 8) & 0xffffff) ^ _CRC_TABLE[(crc ^ c) & 0xff];
}

static void
_update_keys(char c, int* key0, int* key1, int* key2)
{
    *key0 = _crc32(c, *key0);
    *key1 = (*key1 + (*key0 & 255)) & 0xFFFFFFFF ;
    *key1 = (*key1 * 134775813 + 1) & 0xFFFFFFFF;
    *key2 = _crc32((*key1 >> 24) & 255, *key2);
}

static void
zipdecrypter_decrypt(char* cypher_text, const Py_ssize_t cypher_len,
        int* key0, int* key1, int* key2)
{
    Py_ssize_t i;

    for (i = 0; i < cypher_len; i++) {
        unsigned short k = (*key2 & 0xFFFF) | 2;
        *cypher_text = *cypher_text ^ (((k * (k^1)) >> 8) & 255);
        _update_keys(*cypher_text, key0, key1, key2);
        cypher_text++;
    }
}

static void
zipdecrypter_encrypt(char* cypher_text, const Py_ssize_t cypher_len,
        int* key0, int* key1, int* key2)
{
    Py_ssize_t i;

    for (i = 0; i < cypher_len; i++) {
        unsigned short k = (*key2 & 0xFFFF) | 2;
        char c = *cypher_text;
        *cypher_text = c ^ (((k * (k^1)) >> 8) & 255);
        _update_keys(c, key0, key1, key2);
        cypher_text++;
    }
}

typedef struct
{
    PyObject_HEAD
    int key0;
    int key1;
    int key2;
} ZipDecrypter;

static void
zipdecrypter_dealloc(ZipDecrypter *self)
{
    Py_TYPE(self)->tp_free((PyObject *) self);
}

static PyObject *
zipdecrypter_new(PyTypeObject *type, PyObject *args, PyObject* kwds)
{
    ZipDecrypter *self;

    self = (ZipDecrypter *) type->tp_alloc(type, 0);
    return (PyObject *) self;
}

static int
zipdecrypter_init(ZipDecrypter *self, PyObject *args, PyObject *kwds)
{
    Py_buffer pwd_buf;
    char *pwd;
    Py_ssize_t i;

    if (!PyArg_ParseTuple(args, "s*:ZipDecrypter.__init__", &pwd_buf))
        return -1;

    self->key0 = 305419896;
    self->key1 = 591751049;
    self->key2 = 878082192;

    pwd = (char*)pwd_buf.buf;

    for(i=0; i<pwd_buf.len; i++) {
        _update_keys(*pwd, &self->key0, &self->key1, &self->key2);
        pwd++;
    }

    PyBuffer_Release(&pwd_buf);

    return 0;
}

static PyObject *
zipdecrypter_call(ZipDecrypter *self, PyObject *args, PyObject *kwds)
{
    Py_buffer cipher_buf;
    PyObject *plain_buf=NULL;
    Py_ssize_t len;
    char *temp_buf;

    if (!PyArg_ParseTuple(args, "s*:ZipDecrypter.__call__", &cipher_buf))
        return NULL;

    len = cipher_buf.len;

    temp_buf = PyMem_Malloc(len);
    if(temp_buf == NULL) {
        PyErr_NoMemory();
        PyBuffer_Release(&cipher_buf);
        return NULL;
    }

    memcpy(temp_buf, cipher_buf.buf, cipher_buf.len);

    PyBuffer_Release(&cipher_buf);

    zipdecrypter_decrypt(temp_buf, len, &self->key0, &self->key1, &self->key2);

    plain_buf = PyBytes_FromStringAndSize(temp_buf, len);

    PyMem_Free(temp_buf);
    
    return plain_buf;

}

static PyObject *
zipdecrypter_e(ZipDecrypter *self, PyObject *args, PyObject *kwds)
{
    Py_buffer cipher_buf;
    PyObject *plain_buf=NULL;
    Py_ssize_t len;
    char *temp_buf;

    if (!PyArg_ParseTuple(args, "s*:ZipDecrypter.__call__", &cipher_buf))
        return NULL;

    len = cipher_buf.len;

    temp_buf = PyMem_Malloc(len);
    if(temp_buf == NULL) {
        PyErr_NoMemory();
        PyBuffer_Release(&cipher_buf);
        return NULL;
    }

    memcpy(temp_buf, cipher_buf.buf, cipher_buf.len);

    PyBuffer_Release(&cipher_buf);

    zipdecrypter_encrypt(temp_buf, len, &self->key0, &self->key1, &self->key2);

    plain_buf = PyBytes_FromStringAndSize(temp_buf, len);

    PyMem_Free(temp_buf);
    
    return plain_buf;

}

PyDoc_STRVAR(zipdecrypter_doc,
        "Support for decryption of data encrypted using the ZIP 2.0 simple \n\
encryption algorithm\n\
zipDecrypter(cipher_byte_buffer) -> decrypted_byte_buffer.\n\
\n\
Decrypts the given encrypted data (cipher text)\n\
as the input byte buffer and returns a new byte\n\
buffer containing the decrypted data(plain text).");

static PyMethodDef ZipDecrypter_methods[] = {
    {"e", (PyCFunction)zipdecrypter_e, METH_VARARGS, "Encrypt bytes"},
    {NULL}  /* Sentinel */
};

static PyTypeObject ZipDecrypter_Type = {
  PyVarObject_HEAD_INIT(NULL, 0)
    "_zipdecrypt.ZipDecrypter", /* tp_name */
    sizeof (ZipDecrypter), /* tp_basicsize */
    0, /* tp_itemsize */
    (destructor) zipdecrypter_dealloc, /* tp_dealloc */
    0, /* tp_print */
    0, /* tp_getattr */
    0, /* tp_setattr */
    0, /* tp_compare */
    0, /* tp_repr */
    0, /* tp_as_number */
    0, /* tp_as_sequence */
    0, /* tp_as_mapping */
    0, /* tp_hash */
    (ternaryfunc)zipdecrypter_call, /* tp_call */
    0, /* tp_str */
    0, /* tp_getattro */
    0, /* tp_setattro */
    0, /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT |
    Py_TPFLAGS_BASETYPE, /* tp_flags */
    zipdecrypter_doc, /* tp_doc */
    0, /* tp_traverse */
    0, /* tp_clear */
    0, /* tp_richcompare */
    0, /* tp_weaklistoffset */
    0, /* tp_iter */
    0, /* tp_iternext */
    ZipDecrypter_methods, /* tp_methods */
    0, /* tp_members */
    0, /* tp_getset */
    0, /* tp_base */
    0, /* tp_dict */
    0, /* tp_descr_get */
    0, /* tp_descr_set */
    0, /* tp_dictoffset */
    (initproc)zipdecrypter_init, /* tp_init */
    0, /* tp_alloc */
    zipdecrypter_new, /* tp_new */
    0, /* tp_free */
};

PyDoc_STRVAR(module_doc,
        "Provides support for decrypting ZIP archives encrypted.\n\
using the ZIP 2.0 simple encryption algorithm\n\
");

static struct PyModuleDef zipdecryptmodule = {
   PyModuleDef_HEAD_INIT,
   "_zipdecrypt",
   module_doc,
   -1,
   NULL,
   NULL,
        NULL,
        NULL,
        NULL
};

PyObject*
PyInit__zipdecrypt(void)
{
    PyObject *m = PyModule_Create(&zipdecryptmodule);
    if (!m)
   return NULL;

    if (PyType_Ready(&ZipDecrypter_Type) < 0)
        return NULL;

    Py_INCREF(&ZipDecrypter_Type);
    if (PyModule_AddObject(m, "ZipDecrypter",
            (PyObject *) & ZipDecrypter_Type) < 0)
        return NULL;

    _build_crc_table();

    return m;
}
