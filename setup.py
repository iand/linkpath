from setuptools import setup
setup(
    name = 'linkpath',
    version = '0.1.1',
    description = 'A Python library for querying the linked data web',
    author='Ian Davis',
    author_email='nospam@iandavis.com',
    url='https://github.com/iand/linkpath',
    classifiers=['Programming Language :: Python','License :: Public Domain', 'Operating System :: OS Independent', 'Development Status :: 4 - Beta', 'Intended Audience :: Developers', 'Topic :: Software Development :: Libraries :: Python Modules', 'Topic :: Database'],
    packages =['linkpath'],
    install_requires=['httplib2', 'rdflib>=3.1.0'],
    scripts = ["scripts/linkpath"],
    
)
