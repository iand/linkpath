linkpath
=======
A Python library for querying the linked data web.

Overview
--------
This is a library for querying linked data on the web using a simple to learn
path language based on the [Fresnel Selector Language](http://www.w3.org/2005/04/fresnel-info/fsl/).
A LinkPath is evaluated against the whole web, fetching the data it needs by following links
between items. 

Homepage: http://github.com/iand/linkpath
Pypi: http://pypi.python.org/pypi/linkpath

Installing
----------
Install with easy_install:

    >sudo easy_install linkpath

If you already have it installed then simply upgrade with:

    >sudo easy_install --upgrade linkpath

Getting started
---------------
The basic pattern of usage is as follows:

```python
from linkpath import LinkPathProcessor

wp = LinkPathProcessor
results = wp.select('http://example.com/res/person1', "foaf:knows/*/foaf:givenName/text()")
for res in results:
  print res
```

LinkPaths
--------
A LinkPath looks like this:

    foaf:knows/foaf:Person/foaf:name/*

LinkPaths are applied to a starting resource, specified by supplying a URI.

Path steps are separated by slashes. The first step specifies the name
of an property to select from the starting resource, the second step specifies
criteria for the values of that property. The third step specifies
criteria for slecting properties of those values. The last step also 
specifies what is actually selected by the LinkPath. You can read the
LinkPath above as selecting the names of all the people known by the starting
URI.

The LinkPath always alternates between property and value (or arc and node):

    property/value/property/value/property/value/...

    arc/node/arc/node/arc/node/...

Every time the LinkPath processor encounters a node it looks up more data
about that node. At the moment this is just a simple HTTP GET but in the 
future I plan to add other mechanisms. Any RDF retrieved by this lookup
is added to the pool of data the processor is using to evaluate the LinkPath.

Filters can be applied to each step to further refine it:

   arc/node[filter]/arc/node

See the examples and specification for more details on filters.

Examples
--------

Find all the friends of the starting resource:

    foaf:knows/*
    
Find all the friends who are people:

    foaf:knows/foaf:Person
    
Find the given name of all friends:

    foaf:knows/*/foaf:givenName/text()

Find the given name of friends whose family name is Smith:

    foaf:knows/*[foaf:familyName/text()='Smith']/foaf:givenName/text()

Find all friends who are aged 32 (these are equivalent):

    foaf:knows/*[foaf:age/text()='32']
    foaf:knows/*[foaf:age/'32']

The previous two paths use esact text matching so will fail if the foaf:age
property contains '032', '+32' or '32.0'. Numeric comparison is better:

    foaf:knows/*[foaf:age/text()=32]

The usual numeric comparison operators are available:

    foaf:knows/*[foaf:age/text()>32]
    foaf:knows/*[foaf:age/text()<=32]
    foaf:knows/*[foaf:age/text()!=32]

Find friends whose given name is the same as their nickname

    foaf:knows/*[foaf:givenName/text()=foaf:nick/text()]

Find friends who have more than five friend

    foaf:knows/*[count(foaf:knows/*) > 5]

Find friends who have a foaf:based_near property:

    foaf:knows/*[foaf:based_near]

Find friends who don't have a foaf:based_near property:

    foaf:knows/*[not(foaf:based_near)]

Find friends who have both a foaf:givenName and a foaf:familyName:

    foaf:knows/*[foaf:givenName and foaf:familyName]

Find friends who have either a foaf:givenName or a foaf:familyName:

    foaf:knows/*[foaf:givenName or foaf:familyName]

Find friends whose family name begins with 'S'

    foaf:knows/*[starts-with(literal-value(foaf:familyName),'S')]

Find all the people related to the starting resource by a property that 
is a subproperty of foaf:knows

    *[rdfs:subPropertyOf/foaf:knows]/*

Find all the properties of the starting resource in the FOAF namespace:

    *[namespace-uri(.) = 'http://xmlns.com/foaf/0.1/']

Find all the properties of the starting resource that have a local name of label:

    *[local-name(.) = 'label']

Using linkpath command line
----------------------------
The linkpath package comes with a command line utility. Use it from the command line like this:
    
    linkpath [uri] [path]
    
Simply pass it a starting URI and a valid LinkPath and it will fetch the necessary data and evaluate
the path expression, printing out the results it finds.

Currently it only has mappings for the rdf, rdfs, owl, foaf and geo namespaces. I'll add a command
line switch to specify more soon.

As an example, here's how to find who I know that went to Harvard University:

    linkpath http://iandavis.com/id/me "foaf:knows/*[foaf:schoolHomepage/*[uri(.)='http://www.harvard.edu/']]/foaf:name/text()"

It takes a minute or so to run because there's no caching yet.

The LinkPath Language Specification
----------------------------
The LinkPath specification is adapted from the [Fresnel Selector Language](http://www.w3.org/2005/04/fresnel-info/fsl/).

TODO

Author
------
[Ian Davis](http://iandavis.com/), nospam@iandavis.com

Licence
-------
This work is hereby released into the Public Domain. 

To view a copy of the public domain dedication, visit 
[http://creativecommons.org/licenses/publicdomain](http://creativecommons.org/licenses/publicdomain) or send a letter to 
Creative Commons, 559 Nathan Abbott Way, Stanford, California 94305, USA.
