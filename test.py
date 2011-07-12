import unittest
from LinkPath import LinkPathProcessor, AggregatingGraph
from rdflib import Graph, URIRef, Literal, BNode, RDF, RDFS, Namespace
from rdflib.parser import StringInputSource

EX = Namespace("http://example.com/schema/")


class TestLinkPathProcessor(unittest.TestCase):
  foaf_data = """
    @prefix foaf: <http://xmlns.com/foaf/0.1/> .
    @prefix ex: <http://example.com/schema/> .
    @prefix res: <http://example.com/res/> .
    @prefix geo: <http://www.w3.org/2003/01/geo/wgs84_pos#> .
    
    res:person1 
      a foaf:Person
      ; foaf:givenName "Wilbur"
      ; foaf:familyName "Jones"
      ; foaf:age "24"
      ; foaf:based_near res:place1
      ; foaf:knows res:person2, res:person3, res:person4
      .

    res:person2
      a foaf:Person
      ; foaf:givenName "Andrew"
      ; foaf:familyName "Smith"
      ; foaf:nick "Andy"
      ; foaf:age "32"
      ; foaf:based_near res:place1
      ; foaf:knows res:person1, res:person3
      .

    res:person3
      a foaf:Person, ex:Colleague
      ; foaf:givenName "Jenny"
      ; foaf:familyName "Smith"
      ; foaf:nick "Jenny"
      ; foaf:age "35"
      ; foaf:knows res:person1, res:person2, res:person4
      .

    res:person4
      a foaf:Person
      ; foaf:givenName "Emily"
      ; foaf:familyName "Roux"
      ; foaf:name "Emily Roux"
      ; foaf:age "20"
      ; foaf:based_near res:place2
      ; foaf:knows res:person3
      .
      
    res:place1
      a geo:SpatialThing
      ; foaf:name "London"
      .

    res:place2
      a geo:SpatialThing
      ; foaf:name "Brighton"
      .

    """


  def make_processor(self, data):
    g = FakeAggregatingGraph()
    d = Graph()
    d.parse(StringInputSource(data), format="n3")
    g.set_all(d)

    wp = LinkPathProcessor(g)
    wp.bind("foaf", "http://xmlns.com/foaf/0.1/")
    wp.bind("ex", "http://example.com/schema/")
    wp.bind("geo", "http://www.w3.org/2003/01/geo/wgs84_pos#")

    return wp

  def testSelectPropertyDereferencesUri(self):
    start_uri = "http://example.com/s"

    g = FakeAggregatingGraph()

    wp = LinkPathProcessor(g)
    wp.bind("ex", "http://example.com/schema/")
      
    uris = wp.select(start_uri, "ex:Type")
    assert g.receivedLookup(start_uri) == True, "LookupManager did not receive a lookup request"

  def testSelectType(self):
    wp = self.make_processor(self.foaf_data)
    res = wp.select("http://example.com/res/person1", "*/geo:SpatialThing")
    assert len(res) == 1, "was expecting 1 results"


  def testSelectTypeWithStep(self):
    wp = self.make_processor(self.foaf_data)
    res = wp.select("http://example.com/res/person1", "foaf:knows/*/foaf:based_near/geo:SpatialThing")
    assert len(res) == 2, "was expecting 2 results"

  def testSelectSpecificLiteralValueOfProperty(self):
    wp = self.make_processor(self.foaf_data)
    res = wp.select("http://example.com/res/person1", "foaf:knows/*/foaf:familyName/'Roux'")
    assert len(res) == 1, "was expecting 1 results"

  def testSelectAnyLiteralValueOfProperty(self):
    wp = self.make_processor(self.foaf_data)
    res = wp.select("http://example.com/res/person1", "foaf:givenName/text()")
    assert len(res) == 1, "was expecting one result"
    assert res[0] == Literal("Wilbur"), "was expecting Wilbur in results"

  def testOneFilter(self):
    wp = self.make_processor(self.foaf_data)

    # Select properties that have a value of type foaf:Person
    res = wp.select("http://example.com/res/person1", "*[foaf:Person]")
    assert len(res) == 1, "was expecting one result"
    assert res[0] == URIRef("http://xmlns.com/foaf/0.1/knows"), "was expecting http://xmlns.com/foaf/0.1/knows"

  def testOneAndFilter(self):
    wp = self.make_processor(self.foaf_data)

    res = wp.select("http://example.com/res/person1", "foaf:knows/*[foaf:givenName and foaf:based_near]")
    assert len(res) == 2, "was expecting 1 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4"


  def testOneOrFilter(self):
    wp = self.make_processor(self.foaf_data)

    res = wp.select("http://example.com/res/person1", "foaf:knows/*[foaf:givenName or foaf:based_near]")
    assert len(res) == 3, "was expecting 3 results"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4"

  def testMultipleFilters(self):
    wp = self.make_processor(self.foaf_data)

    res = wp.select("http://example.com/res/person1", "foaf:knows/*[foaf:givenName][foaf:based_near]")
    assert len(res) == 2, "was expecting 1 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4"

  def test_foaf1(self):
    wp = self.make_processor(self.foaf_data)

    # Find the first names of the people this person knows 
    res = wp.select('http://example.com/res/person1', "foaf:knows/*/foaf:givenName/text()")
    assert len(res) == 3, "was expecting 3 results"
    assert "Andrew" in res, "was expecting Andrew in result list"
    assert "Jenny" in res, "was expecting Jenny in result list"
    assert "Emily" in res, "was expecting Emily in result list"
  
  def test_foaf2(self):
    wp = self.make_processor(self.foaf_data)
    # Find the first names of the people this person knows whose familyName is Smith
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:familyName/text()='Smith']/foaf:givenName/text()")
    assert len(res) == 2, "was expecting 2 results"
    assert "Andrew" in res, "was expecting Andrew in result list"
    assert "Jenny" in res, "was expecting Jenny in result list"

  def test_literal_value(self):
    wp = self.make_processor(self.foaf_data)
    # Find the first names of the people this person knows whose familyName is Smith (using literal-value function)
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[literal-value(foaf:familyName)='Smith']/foaf:givenName/text()")
    assert len(res) == 2, "was expecting 2 results"
    assert "Andrew" in res, "was expecting Andrew in result list"
    assert "Jenny" in res, "was expecting Jenny in result list"

  def test_uri(self):
    wp = self.make_processor(self.foaf_data)
    # Check URI of selected resource
    res = wp.select('http://example.com/res/person1', "*/*[uri(.)='http://example.com/res/person2']")
    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"

  def test_exp(self):
    wp = self.make_processor(self.foaf_data)
    # Find all the colleagues known to person1 (verbose method)
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[rdf:type/*[uri(.) = exp('ex:Colleague')]")
    assert len(res) == 1, "was expecting 1 result1"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_namespace_uri(self):
    wp = self.make_processor(self.foaf_data)
    # Find all the properties in the foaf namespace

    res = wp.select('http://example.com/res/person1', "*[namespace-uri(.) = 'http://xmlns.com/foaf/0.1/']")
    assert len(res) == 5, "was expecting 1 result"

  def test_localname(self):
    wp = self.make_processor(self.foaf_data)
    
    # Find all the properties that have a local name of age
    res = wp.select('http://example.com/res/person1', "*[local-name(.) = 'age']")
    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://xmlns.com/foaf/0.1/age") in res, "was expecting http://xmlns.com/foaf/0.1/age in result list"


  def test_literal_equals(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who are aged 32
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/text()='32']")
    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"

  def test_literal_equals_2(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who are aged 32
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/'32']")
    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"

  def test_literal_greater_than(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who are aged > 32
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/text() > 32]")
    assert len(res) == 1, "was expecting 1 results"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_literal_less_than(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who are aged < 32
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/text() < 32]")
    
    assert len(res) == 1, "was expecting 1 results"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_literal_greater_than_equal(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who are aged >= 32
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/text() >= 32]")
    assert len(res) == 2, "was expecting 2 results"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_literal_less_than_equal(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who are aged <= 32
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/text() <= 32)]")
    assert len(res) == 2, "was expecting 2 results"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_literal_not_equals(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who are not aged 32
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/text()!=32]")
    assert len(res) == 2, "was expecting 2 results"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_literal_cannot_compare_with_uri(self):
    wp = self.make_processor(self.foaf_data)

    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/text()=foaf:name]")
    assert len(res) == 0, "was expecting 0 results"

  def test_literal_cannot_compare_magnitude_of_non_numerics(self):
    wp = self.make_processor(self.foaf_data)

    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:givenName/text()>foaf:familyName/text()]")
    assert len(res) == 0, "was expecting 0 results"

  def test_literal_cannot_compare_magnitude_of_non_numerics(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose given name is not their family name
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:givenName/text()!=foaf:familyName/text()]")
    assert len(res) == 3, "was expecting 3 results"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_equality_two_paths(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose given name is the same as their nickname
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:givenName/text()=foaf:nick/text()]")

    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_non_equality_two_paths(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose given name is not the same as their nickname
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:givenName/text()!=foaf:nick/text()]")

    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"

  def test_arcset_to_boolean(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who have a foaf:based_near property
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:based_near]")
    assert len(res) == 2, "was expecting 2 results"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_count(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who have more than one friend
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[count(foaf:knows/*) > 1]")
    assert len(res) == 2, "was expecting 2 results"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_nodeset_equality_to_boolean_true(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who have a foaf:based_near property
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:based_near/* = true()]")
    assert len(res) == 2, "was expecting 2 results"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_nodeset_inequality_to_boolean_true(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who have a foaf:based_near property
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:based_near/* != true()]")
    assert len(res) == 1, "was expecting 1 results"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_nodeset_inequality_to_boolean_false(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who have a foaf:based_near property
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:based_near/* != false()]")
    assert len(res) == 2, "was expecting 2 results"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_nodeset_equality_to_boolean_false(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who have a foaf:based_near property
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:based_near/* = false()]")
    assert len(res) == 1, "was expecting 1 results"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_not_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends who do not have a foaf:based_near property
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[not(foaf:based_near)]")

    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_string_length_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose family name is exactly four characters long
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[string-length(literal-value(foaf:familyName))=4]")

    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_string_length_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose family name starts with Sm
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[starts-with(literal-value(foaf:familyName),'Sm')]")

    assert len(res) == 2, "was expecting 2 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_contains_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose family name contains mit
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[contains(literal-value(foaf:familyName),'mit')]")

    assert len(res) == 2, "was expecting 2 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_substring_before_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose family name starts with Sm
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[substring-before(literal-value(foaf:familyName),'th') = 'Smi']")

    assert len(res) == 2, "was expecting 2 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_substring_after_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose family name starts with Sm
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[substring-after(literal-value(foaf:familyName),'Smi') = 'th']")

    assert len(res) == 2, "was expecting 2 result"
    assert URIRef("http://example.com/res/person2") in res, "was expecting http://example.com/res/person2 in result list"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"

  def test_concat_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose name is Emily Roux
    res = wp.select('http://example.com/res/person1', "+foaf:knows/*[concat(literal-value(foaf:givenName),' ', literal-value(foaf:familyName)) = 'Emily Roux']")

    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"

  def test_normalize_space_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose name is Emily Roux
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[literal-value(foaf:name)) = normalize-space(' Emily   Roux  ')]")

    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person4") in res, "was expecting http://example.com/res/person4 in result list"


  def test_number_function(self):
    wp = self.make_processor(self.foaf_data)

    # Find all friends whose name is Emily Roux
    res = wp.select('http://example.com/res/person1', "foaf:knows/*[foaf:age/text() >= number(concat('3', '5'))]")

    assert len(res) == 1, "was expecting 1 result"
    assert URIRef("http://example.com/res/person3") in res, "was expecting http://example.com/res/person3 in result list"


class FakeAggregatingGraph(AggregatingGraph):
  
  def __init__(self):
    self.lookup_counts = {}
    self.graphs = {}
    AggregatingGraph.__init__(self)
  
  def lookup(self, uri):
    s = str(uri)
    if not s in self.lookup_counts:
      self.lookup_counts[s] = 1
      if s in self.graphs:
        self.g += self.graphs[s]
        
    else:
      self.lookup_counts[s] += 1
    
      
  def set(self, uri, g):
    self.graphs[uri] = g
  
  def set_all(self, g):
    self.g += g


  def receivedLookup(self, uri):
    return (uri in self.lookup_counts)


if __name__=="__main__":
   unittest.main()
