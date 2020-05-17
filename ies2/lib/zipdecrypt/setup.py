from distutils.core import setup, Extension
setup(name="_zipdecrypt", version="1.0", ext_modules=[Extension("_zipdecrypt", ["_zipdecrypt.c"])])
