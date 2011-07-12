__all__ = ["LinkPathProcessor", "AggregatingGraph", "ParseError", "EvaluationError"]

import rdflib
import httplib2
import re
import sys
from rdflib import RDF, URIRef, Literal, BNode
from rdflib.parser import StringInputSource
from rdflib.plugins.parsers.notation3 import BadSyntax

def isnumeric(s):
  try:
    float(s)
  except ValueError, e:
    return False
  return True


class ParseError(Exception):
  pass

class EvaluationError(Exception):
  pass

class AggregatingGraph:
  def __init__(self):
    self.g = rdflib.Graph()
    self.prefixes = {}
    self.lookups = {}
    self.client = httplib2.Http()
    self.client.follow_all_redirects = True

    self.bind('rdf', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#')
    self.bind('rdfs', 'http://www.w3.org/2000/01/rdf-schema#')
    self.bind('owl', 'http://www.w3.org/2002/07/owl#')
    
    
  def lookup(self, uri):
    s = str(uri)
    if not s.startswith("http:"):
      return
    if s not in self.lookups:
      self.lookups[s] = 1
      lookup_uri = re.sub("\#.+$", '', uri)
      response, body = self.client.request(lookup_uri, "GET",headers={"accept" : "text/turtle, application/rdf+xml;q=0.9, application/xml;q=0.1, text/xml;q=0.1"})
      if response.status in range(200, 300):
        self.lookups[s] = 1
        try:
          if 'text/turtle' in response['content-type']:
            self.g.parse(StringInputSource(body), format="n3")
          elif 'application/rdf+xml' in response['content-type'] or 'application/xml' in response['content-type']:
            self.g.parse(StringInputSource(body), format="xml")
        except BadSyntax:
          pass
        

  def bind(self, prefix, ns):
    self.prefixes[prefix] = ns

  def qname_to_uri(self, qname):
    (prefix, local) = qname.split(":")
    if prefix in self.prefixes:
      return URIRef("%s%s" % (self.prefixes[prefix], local))
    else:
      return None

  def get_subject_properties(self, s, distinct):
    self.lookup(s)
    props = list(self.g.predicates(s, None))
    if distinct:
      return list(set(props))
    else:
      return props
    
  def get_subject_property_values(self, s, p):
    self.lookup(s)
    return [o for (s1,p1,o) in self.g.triples((s,p,None))]

  def has_triple(self, s,p,o):
    self.lookup(s)
    if (s,p,o) in self.g:
      return True
    else:
      return False

class Location:
  def __init__(self, value, g):
    self.value = value
    self.g = g
    
  def is_type(self, uri):
    return self.g.has_triple(self.value, RDF['type'], uri)


  def compare(self, other, op='='):
    if op == '=':
      return self.value == other.value
    elif op == '!=':
      return self.value != other.value
    else:
      if not isinstance(self.value, Literal) or not isinstance(other.value, Literal):
        return False
    
    
    if not isnumeric(self.value) or not isnumeric(other.value):
        return False
    
    left = float(self.value)
    right = float(other.value)
    
    if op == '>':
      return left > right;
    elif op == '<':
      return left < right;
    elif op == '<=':
      return left <= right;
    elif op == '>=':
      return left >= right;
    
    
    
    return False



class Node(Location):
  def __init__(self, value, g):
    Location.__init__(self, value, g)

  def __str__(self):
    return str(self.value)

  def is_arc(self):
    return False
    
  def is_literal(self):
    return isinstance(self.value, Literal)

  def is_uri(self):
    return isinstance(self.value, URIRef)

  def get_arcs(self, distinct=False):
    arcs = []
    properties = self.g.get_subject_properties(self.value, distinct)
    for p in properties:
      arcs.append(Arc(p, self.value,self.g))

    return arcs




class Arc(Location):
  def __init__(self, value, node, g):
    self.node = node
    Location.__init__(self,value, g)

  def __str__(self):
    return "%s -> %s" % (self.node, self.value)

  def is_arc(self):
    return True

  def is_literal(self):
    return False

  def is_uri(self):
    return True

  def get_nodes(self):
    nodes = []
    for n in self.g.get_subject_property_values(self.node, self.value):
      nodes.append(Node(n,self.g))

    return nodes


class LinkPathProcessor:
  def __init__(self, g = None):
    if g:
      self.g = g
    else:
      self.g = AggregatingGraph()


  def bind(self, prefix, ns):
    self.g.bind(prefix, ns)

  def select(self, uri, path, trace=False):
    uris = []

    parsed_path = self.parse_path(path)
    candidates = Node(URIRef(uri),self.g).get_arcs()
    ret = parsed_path.select(candidates, self.g, None, trace)
    
    results = []
    for r in ret:
      if r.value not in results:
        results.append(r.value)

    return results

  def parse_path(self, v):
    (step, v) = self.m_locationpath(v)
    return step;

  def m(self, regex, v, options = re.I|re.S):
    matches = re.search(r'^\s*%s(.*)$'%regex, v, options)
    if matches:
      return (matches.group(0), matches.group(1), matches.group(2))
    else:
      return False

  def m_split(self, pattern, v):
    r = self.m(pattern, v)
    if r:
      return (r[1], r[2])

    return (False, v)

  def m_locationpath(self, v):
    steps = []
    (r, v) = self.m_step(v)
    if r:
      steps.append(r)

      (r, v) = self.m_slash(v)
      while r:
        (r, v) = self.m_step(v)
        if r:
          steps.append(r)
          (r, v) = self.m_slash(v)

    return (LocPath(steps), v)

  def m_step(self,v):
    (r, v) = self.m_test(v)
    if r: 
      return (r, v)
  
    (r, v) = self.m_literal(v)
    if r: 
      return (r, v)

    (r, v) = self.m_textdef(v)
    if r: 
      return (r, v)

    return (False, v)

  def m_test(self,v):
    (axis, v) = self.m_axis(v)

    selector= '';
    r = self.m(r'(\*)', v)
    if r:
      selector = WildCardMatcher()
      v = r[2]
    else:
      r = self.m(r'([a-z0-9_]+:[a-z0-9_]+)', v)
      if r:
        selector = TypeMatcher(r[1])
        v = r[2]
      else:
        return (False, v);

    filters = []
    (r, v) = self.m_openbracket(v)
    while r:
      (r, v) = self.m_orexpr(v)
      if r:
        filters.append(r)
      
        (r_br, v) = self.m_closebracket(v)
        (r, v) = self.m_openbracket(v)

    return (StepMatcher(selector, axis, filters), v);

  def m_axis(self, v):
    return self.m_split(r'(in|out)::', v)

  def m_slash(self,v):
    return self.m_split(r'(\/)', v)

  def m_orexpr(self,v):
    (r, v) = self.m_andexpr(v)
    if r: 
      left = r
      (r, v) = self.m_split(r'(\s+or\s+)',v)
      if r:
        (r, v) = self.m_andexpr(v)
        if r:
          return (OrExpr(left, r), v)
        else:
          pass # TODO: raise parse error
      else:
        return (OrExpr(left), v)
        
    return (False, v)
    

  def m_andexpr(self, v):
    (r, v) = self.m_compexpr(v)
    if r:
      left = r
      (r, v) = self.m_split(r'(\s+and\s+)',v)
      if r:
        (r, v) = self.m_andexpr(v)
        if r:
          return (AndExpr(left, r), v)
        else:
          pass # TODO: raise parse error
      else:
        return (AndExpr(left), v)
        
    return (False, v)

  def m_compexpr(self,v):
    (r, v) = self.m_unaryexpr(v)
    if r:
      left = r
      (r, v) = self.m_operator(v)
      if r:
        op = r
        (r, v) = self.m_unaryexpr(v)
        if r:
          return (CompExpr(left, op, r), v)
        else:
          pass  # TODO: raise parse error
      else:
        return (CompExpr(left), v)

    return (False, v)

  def m_unaryexpr(self, v):
    (r, v) = self.m_defcall(v)
    if r:
      return (r,v)
      
    (r, v) = self.m_literalholder(v)
    if r:
      return (r,v)

    (r, v) = self.m_numberholder(v)
    if r:
      return (r,v)

    (r, v) = self.m_booleanholder(v)
    if r:
      return (r,v)

    (r, v) = self.m_split(r'(\.)', v)
    if r:
      return (SelfHolder(),v)

    (r, v) = self.m_locationpath(v)
    if r:
      return (PathFunction(r),v)

    return (False, v)


  def m_literalholder(self, v):
    (r, v) = self.m_string(v)
    if r:
      return (LiteralHolder(r),v)
    return (False, v)

  def m_numberholder(self, v):
    (r, v) = self.m_split(r'([0-9]+)', v)
    if r:
      return (NumberHolder(r),v)

    return (False, v)


  def m_booleanholder(self, v):
    (r, v) = self.m_split(r'(true\(\))', v)
    if r:
      return (BooleanHolder(True),v)

    (r, v) = self.m_split(r'(false\(\))', v)
    if r:
      return (BooleanHolder(False),v)

    return (False, v)
 

  def m_literal(self,v):
    (r, v) = self.m_string(v)
    if r != False:
      return (LiteralMatcher(r), v)
      
    return (False, v)

  def m_number(self, v):
    (r, v) = self.m_split(r'([0-9]+)', v)
    if r:
      return (NumberMatcher(r),v)

    return (False, v)

  def m_textdef(self,v):
    (r,v) = self.m_split(r'(text\(\))', v)
    if r:
      return (AnyLiteralMatcher(), v)

    return (False, v)

  def m_operator(self,v):
    return self.m_split(r'(=|>=|<=|>|<|!=)', v) # ordering of these alternatives is very important

  def m_defcall(self,v):
    vorig = v
    (r, v) = self.m_split('(count|local-name|namespace-uri|uri|literal-value|literal-dt|exp|string-length|normalize-space|boolean|not|starts-with|contains|substring-before|substring-after|concat|number)\(', v)
    if r:
      func = r
      args = []
      (arg, v) = self.m_oneargument(v)
      while arg:
        args.append(arg)
        (brace,v) = self.m_split(r'(\))', v)
        if brace:
          break
        (comma,v) = self.m_split(r'(,)', v)
        if comma:
          (arg, v) = self.m_oneargument(v)
        else:
          raise ParseError("Expecting a comma or a closing bracket at %s (args were: %s, remainder is %s)" % (vorig, args, v))

      if len(args):
      
        if func in ["count", "local-name", "namespace-uri", "uri", "literal-value", "literal-dt", "exp", "string-length", "normalize-space", "boolean", "not", "number"]:
          if len(args) == 1:
            if func == 'count':
              return (CountFunction(args[0]), v)
            elif func == 'local-name':
              return (LocalNameFunction(args[0]), v)
            elif func == 'namespace-uri':
              return (NamespaceUriFunction(args[0]), v)
            elif func == 'uri':
              return (UriFunction(args[0]), v)
            elif func == 'literal-value':
              return (LiteralValueFunction(args[0]), v)
            elif func == 'literal-dt':
              return (LiteralDtFunction(args[0]), v)
            elif func == 'exp':
              return (ExpFunction(args[0]), v)
            elif func == 'string-length':
              return (StringLengthFunction(args[0]), v)
            elif func == 'normalize-space':
              return (NormalizeSpaceFunction(args[0]), v)
            elif func == 'boolean':
              return (BooleanFunction(args[0]), v)
            elif func == 'not':
              return (NotFunction(args[0]), v);
            elif func == 'normalize-space':
              return (NormalizeSpaceFunction(args[0]), v);
            elif func == 'number':
              return (NumberFunction(args[0]), v);
          else:
            raise ParseError("Expecting exactly one argument for %s function at %s" % (func, vorig))

        elif func in ["contains", "starts-with", "substring-before", "substring-after"]:
          if len(args) == 2:
            if func == 'starts-with':
              return (StartsWithFunction(args[0], args[1]), v)
            elif func == 'contains':
              return (ContainsFunction(args[0], args[1]), v)
            elif func == 'substring-before':
              return (SubstringBeforeFunction(args[0], args[1]), v)
            elif func == 'substring-after':
              return (SubstringAfterFunction(args[0], args[1]), v)
          else:
            raise ParseError("Expecting exactly two arguments for %s function at %s" % (func, vorig))
            
        elif func in ["concat"]:
          if func == 'concat':
            return (ConcatFunction(args), v)

      else:
        raise ParseError("Expecting at least one argument at %s" % vorig)

    return (False, v)


  def m_oneargument(self,v):
    (r, v) = self.m_unaryexpr(v)
    if r:
      return (r, v)

    return (False, v)

  def m_string(self,v):
    (r,v) = self.m_split(r'("[^"]*")', v)
    if r:
      return (r[1:-1], v)
      
    (r,v) = self.m_split(r'(\'[^\']*\')', v)
    if r:
      return (r[1:-1], v)

    return (False, v)


  def m_openbracket(self,v):
    return self.m_split(r'(\[)', v);


  def m_closebracket(self,v):
    return self.m_split(r'(\])', v);


class LocPath:
  def __init__(self, steps = []):
    self.steps = steps
  
  def __str__(self):
    ret = ''
    if len(self.steps) > 0:
      ret = str(self.steps[0])
      for i in range(1, len(self.steps)):
        ret += '/' + str(self.steps[i])
    return ret


  def select(self, candidates, g, context, trace = False):
    if trace:
      print "Path: %s" % self

    selected = []
    for i in range(0, len(self.steps)):
      step = self.steps[i]
      selected = []
      if trace:
        print "Path: Filtering %s candidates using %s" % (len(candidates), step)

      for candidate in candidates:
        if step.matches(candidate, g, context, trace):
          selected.append(candidate)

      if trace:
        print "Path: %s resources passed the filter" % len(selected)


      if i < (len(self.steps) - 2):
        # get a distinct list of candidates (an optimisation)
        candidates = self.get_candidates(selected, g, True, trace)
      elif i == (len(self.steps) - 2):
        # next step is last so get candidates including duplicates
        candidates = self.get_candidates(selected, g, True, trace)

    return selected

  def get_candidates(self, resources, g, distinct = True, trace = False):
      
    candidates = []
    for resource in resources:
      if not resource.is_literal():
        if resource.is_arc():
          if trace:
            print "Path: Selecting nodes that are values of %s" % resource
            
          candidates.extend(resource.get_nodes())
        else:
          if trace:
            print "Path: Selecting arcs that are properties of %s" % resource
          
          candidates.extend(resource.get_arcs(resource))

    if trace:
      print "Path: Selected %s candidates" % len(candidates)
      
    return candidates



class WildCardMatcher:
  def __str__(self):
    return '*'

  def matches(self, candidate, g, context, trace = False):
    if trace:
      print "WildCardMatcher: Automatically matching %s" % (candidate)
    
    return True

    
class TypeMatcher:
  def __init__(self, t):
    self.type = t
  
  def __str__(self):
    return self.type

  def matches(self,candidate,g, context, trace = False):
    if trace:
      print "TypeMatcher: Testing %s using %s" % (candidate, self);

    it_matches = False

    test_uri = g.qname_to_uri(self.type);
    if test_uri:

      if candidate.is_arc():
        # We are testing an arc
        if trace:
          print "TypeMatcher: Testing to see if %s is same as %s" % (candidate, test_uri)
        if candidate.value == test_uri:
          it_matches = True

      else:
        # We are testing a node
        if trace:
          print "TypeMatcher: Testing to see if %s has type of %s" %  (candidate ,test_uri)
        
        it_matches = candidate.is_type(test_uri)
        
   
    if trace:
      if it_matches:
        print "TypeMatcher: MATCHED using %s" % self
      else:
        print "TypeMatcher: NO MATCH using %s" % self
    

    return it_matches

class StepMatcher:
  def __init__(self, selector, axis, filters):
    self.selector = selector
    self.axis = axis
    self.filters = filters

  def __str__(self):
    ret = '';
    if self.axis and self.axis != 'out':
      ret += self.axis + '::'

    ret += str(self.selector)
    for filter in self.filters:
      ret += "[" + str(filter) + "]"
      
    return ret;

  def matches(self, candidate, g, context, trace = False):
    if trace:
      print "StepMatcher: Matching %s using %s" % (candidate, self)

    it_matches = False
    if self.selector.matches(candidate, g, context, trace):
      if len(self.filters) == 0:
        it_matches = True
      else:
        filter_passes = 0
        filter_resources = self.get_candidates([candidate], g, trace)
        
        for filter in self.filters:
          if trace:
            print "StepMatcher: Applying filter %s" % filter
            
          if filter.matches(filter_resources, g, candidate, trace):
            filter_passes += 1
          
        if filter_passes == len(self.filters):
          it_matches = True;

    if trace:
      if it_matches:
        print "StepMatcher: MATCHED using %s" % self
      else:
        print "StepMatcher: NO MATCH using %s" % self

    return it_matches


  def get_candidates(self, resources, g, trace = False):
    candidates = []
    for resource in resources:
      if not resource.is_literal():
        if resource.is_arc():
          if trace:
            print "StepMatcher: Selecting nodes that are values of %s" % resource
          candidates.extend(resource.get_nodes())
        else:
          if trace:
            print "StepMatcher: Selecting arcs that are properties of %s" % resource
          candidates.extend(resource.get_arcs())

    if trace:
      print "StepMatcher: Selected %s candidates" % len(candidates)

    return candidates



class LiteralMatcher:
  def __init__(self, text, dt = None):
    self.text = text
    self.dt = dt

  def __str__(self):
    return "'%s'" % self.text
    
  def matches(self, candidate, g, context, trace = False):
    if trace:
      print "LiteralMatcher: Testing %s using %s" % (candidate, self)

    it_matches = False

    if trace:
      print "LiteralMatcher: Testing to see if %s is same as %s" % (candidate, self.text)
      
    if candidate.is_literal() and str(candidate.value) == self.text:
      if trace:
        print "LiteralMatcher: It is, adding %s to selected queue" % candidate
      it_matches = True

    if trace:
      if it_matches:
        print "LiteralMatcher: MATCHED using %s" % self
      else:
        print "LiteralMatcher: NO MATCH using %s" % self
    
    return it_matches


class AnyLiteralMatcher:
  def __str__(self):
    return "text()"
  
  def matches(self, candidate, g, context, trace = False):
    if trace:
      print "AnyLiteralMatcher: Testing %s using %s" % (candidate, self)

    it_matches = False

    if candidate.is_literal():
      if trace:
        print "AnyLiteralMatcher: It is, adding %s to selected queue" % candidate
      it_matches = True


    if trace:
      if it_matches:
        print "AnyLiteralMatcher: MATCHED using %s" % self
      else:
        print "AnyLiteralMatcher: NO MATCH using %s" % self
    
    return it_matches

class LiteralHolder:
  def __init__(self, text, dt = None):
    self.text = text
    self.dt = dt

  def __str__(self):
    return "'%s'" % self.text # TODO: dt

  def evaluate(self, value, g, context, trace = False):
    return self.text


class NumberHolder:
  def __init__(self, num):
    self.number = float(num) # TODO test for NaN

  def __str__(self):
    return str(self.number)

  def evaluate(self, value, g, context, trace = False):
    return self.number



class SelfHolder:
  def __str__(self):
    return "."

  def evaluate(self, value, g, context, trace = False):
    return [context]


class BooleanHolder:
  def __init__(self, val):
    self.value = val

  def __str__(self):
    if self.value:
      return "true()"
    else:
      return "false()"

  def evaluate(self, value, g, context, trace = False):
    return self.value


class CompExpr:
  def __init__(self, left, op=None, right=None):
    self.left = left
    self.operator = op
    self.right = right

  def __str__(self):
    ret = str(self.left)
    if self.operator and self.right:
      ret += ' %s %s' % (self.operator, self.right)
    return ret


  def matches(self, candidates, g, context, trace = False):
    it_matches = False

    if trace:
      print "CompExpr: Selecting resources using left of %s, op of %s and right of %s " % (self.left, self.operator, self.right)
      
    selected = self.left.evaluate(candidates, g, context, trace);
 
    if self.operator and self.right:
      if trace:
        print "CompExpr: Selecting resources using right of %s" % self.right
        
      selected_right = self.right.evaluate(candidates, g, context, trace)

      
      if type(selected) == list:
        if trace:
          print "CompExpr: Left of comparison selected a set of %s resources" % len(selected)

        if type(selected_right) == list:
          if trace:
            print "CompExpr: Right of comparison selected a set of  %s resources" % len(selected_right)
          it_matches = self.compare_list_to_list(selected, selected_right);
        elif type(selected_right) == bool:
          if trace:
            print "CompExpr: Right of comparison selected a boolean of value %s" % selected_right
          it_matches = self.compare_list_to_boolean(selected, selected_right);
        elif type(selected_right) == int or  type(selected_right) == float:
          if trace:
            print "CompExpr: Right of comparison selected a number of value %s" % selected_right
          it_matches = self.compare_list_to_numeric(selected, selected_right);
        elif type(selected_right) == str or type(selected_right) == unicode:
          if trace:
            print "CompExpr: Right of comparison selected a string of value %s" % selected_right
          it_matches = self.compare_list_to_string(selected, selected_right);
      elif type(selected) == bool:
        if trace:
          print "CompExpr: Left of comparison selected a boolean of value %s" % selected

        if type(selected_right) == list:
          if trace:
            print "CompExpr: Right of comparison selected a set of %s resources" % len(selected_right)
          it_matches = self.compare_list_to_boolean(selected_right, selected);
        elif type(selected_right) == bool:
          if trace:print "CompExpr: Right of comparison selected a boolean of value %s" % selected_right
          if (selected_right == True and selected == True) or (selected_right == False and selected == False):
            it_matches = True
        elif type(selected_right) == int or  type(selected_right) == float:
          if trace:
            print "CompExpr: Right of comparison selected a number of value %s" % selected_right
          # TODO
        elif type(selected_right) == str or type(selected_right) == unicode:
          if trace:print "CompExpr: Right of comparison selected a string of value " % selected_right
          it_matches = self.compare_boolean_to_string(selected, selected_right);
      elif type(selected) == int or type(selected) == float:
        if trace:print "CompExpr: Left of comparison selected a number of value %s" % selected
        if type(selected_right) == list:
          if trace:
            print "CompExpr: Right of comparison selected a set of %s resources" % len(selected_right)
          it_matches = self.compare_list_to_numeric(selected_right, selected);
        elif type(selected_right) == bool:
          if trace:
            print "CompExpr: Right of comparison selected a boolean of value %s" % selected_right
          # TODO
        elif type(selected_right) == int or  type(selected_right) == float:
          if trace:
            print "CompExpr: Right of comparison selected a number of value %s" % selected_right
          
          it_matches = self.compare_numerics(selected, selected_right)
        elif type(selected_right) == str or type(selected_right) == unicode:
          if trace:
            print "CompExpr: Right of comparison selected a string of value %s" % selected_right
          # TODO
      elif type(selected) == str or type(selected) == unicode:

        if trace:
          print "CompExpr: Left of comparison selected a string of value %s" % selected_right
        
        if type(selected_right) == list:
          if trace:
            print "CompExpr: Right of comparison selected a set of %s resources" % len(selected_right)
          it_matches = self.compare_list_to_string(selected_right, selected);
        elif type(selected_right) == bool:
          if trace:
            print "CompExpr: Right of comparison selected a boolean of value " % selected_right
          it_matches = self.compare_boolean_to_string(selected_right, selected);
        elif type(selected_right) == int or  type(selected_right) == float:
          if trace:
            print "CompExpr: Right of comparison selected a number of value %s" % selected_right
          # TODO
        elif type(selected_right) == str or type(selected_right) == unicode:
          if trace:
            print "CompExpr: Right of comparison selected a string of value %s" % selected_right
          
          if self.operator == '=' and selected == selected_right:
            it_matches = True
          elif self.operator == '!=' and selected != selected_right:
            it_matches = True

    else:
      if trace:
        print "CompExpr: No operator or right expression"
        print "CompExpr: Type of left: %s" % type(selected)
        print "CompExpr: Value of left: %s" % selected
      it_matches = self.bool_value(selected)

    if trace:
      if it_matches:
        print "CompExpr: MATCHED using %s" % self
      else:
        print "CompExpr: NO MATCH using %s" % self
    
    return it_matches

  def compare_numerics(self, left, right):
    if self.operator == '=' and left == right:
      return True
    elif self.operator == '!=' and left != right:
      return True
    elif self.operator == '<' and left < right:
      return True
    elif self.operator == '>' and left > right:
      return True
    elif self.operator == '<=' and left <= right:
      return True
    elif self.operator == '>=' and left >= right:
      return True

    return False

  def bool_value(self, v):
    if type(v) == list or type(v) == str or type(v) == unicode:
      return len(v) > 0
    elif type(v) == int or type(v) == float:
      return v != 0
    elif type(v) == bool:
      return v
    
    return False

  def compare_booleans(self, left, right):
    if self.operator == '=' and left == right:
      return True
    elif self.operator == '!=' and left != right:
      return True
  
    return False

  def compare_list_to_list(self, list1, list2):
    if len(list1) > 0 and len(list2) > 0:
      for resource in list1:
        for resource2 in list2:
          if resource.compare(resource2, self.operator):
            return True
    return False




  def compare_list_to_boolean(self, list1, boolean):
    return self.compare_booleans(self.bool_value(list1), boolean)

  def compare_list_to_numeric(self, list1, numeric):
    for resource in list1:
      if resource.is_literal() and isnumeric(str(resource.value)):
        if self.compare_numerics(float(resource.value), numeric):
          return True

    return False

  def compare_list_to_string(self, list1, string):
    if self.operator != '=' and self.operator != '!=':
      return False

    for resource in list1:
      if resource.is_literal():
        if (self.operator == '=' and str(resource.value) == string):
          return True
        elif (self.operator == '!=' and str(resource.value) != string):
          return True

    return False

  def compare_boolean_to_string(boolean, string):
    if self.operator != '=':
      return False

    if len(string) > 0:
      string_bool = True
    else:
      string_bool = False
    if (list_bool == True and boolean == True) or (list_bool == False and boolean == False):
      return True
    else:
      return False

    
class OrExpr:
  def __init__(self, left, right = None):
    self.left = left
    self.right = right

  def __str__(self):
    ret = str(self.left)
    if self.right:
      ret += " or " + str(self.right)
    
    return ret

  def matches(self, candidates, g, context, trace = False):
    if trace:
      print "OrExpr: Selecting resources using left of %s, right of %s" % (self.left, self.right)

    it_matches = False

    if self.left.matches(candidates, g, context, trace):
      it_matches = True
    elif self.right and self.right.matches(candidates, g, context, trace):
      it_matches = True

    if trace:
      if it_matches:
        print "OrExpr: MATCHED using %s" % self
      else:
        print "OrExpr: NO MATCH using %s" % self
    
    return it_matches


class AndExpr:
  def __init__(self, left, right = None):
    self.left = left
    self.right = right

  def __str__(self):
    ret = str(self.left)
    if self.right:
      ret += " and " + str(self.right)
    
    return ret

  def matches(self, candidates, g, context, trace = False):
    if trace:
      print "AndExpr: Selecting resources using left of %s, right of %s" % (self.left, self.right)
    it_matches = False

    if self.left.matches(candidates, g, context, trace):
      if self.right:
        if self.right.matches(candidates, g, context, trace):
          it_matches = True
      else:
        it_matches = True

    if trace:
      if it_matches:
        print "AndExpr: MATCHED using %s" % self
      else:
        print "AndExpr: NO MATCH using %s" % self
    
    return it_matches


class PathFunction:
  def __init__(self, arg):
    self.arg = arg;

  def __str__(self):
    return 'pathfn(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    if trace:
      print "PathFunction: Selecting resources with %s" % self.arg
    
      print type(value)
    # TODO: ensure value is a nodeset
    return self.arg.select(value, g, context, trace)


class CountFunction:
  def __init__(self, arg):
    self.arg = arg;

  def __str__(self):
    return 'count(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    if trace:
      print "CountFunction: Counting number of resources selected by %s" % self.arg
    # TODO: ensure value is a nodeset
    result = self.arg.evaluate(value, g, context, trace)
    
    if isinstance(result, list):
      if trace:
        print "CountFunction: Counted %s resources" % len(result)
      return len(result)

    if trace:
      print "CountFunction: Result was not a list"
    
    return 0
      
    



class LocalNameFunction:
  def __init__(self, arg):
    self.arg = arg;

  def __str__(self):
    return 'local-name(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    selected = self.arg.evaluate(value, g, context, trace);
    
    # TODO: check type of selected
    if len(selected) > 0:
      if selected[0].is_uri():
        if trace:
          print "LocalNameFunction: Determining local name of %s" % selected[0]

        m = re.search('^(.*[\/\#])([a-z0-9\-\_]+)', str(selected[0].value), re.I)
        if m:
          if trace:
            print "LocalNameFunction: Selected local name of %s" % m.group(2)
          return m.group(2)

    return''


class NamespaceUriFunction:
  def __init__(self, arg):
    self.arg = arg;

  def __str__(self):
    return 'namespace-uri(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    selected = self.arg.evaluate(value, g, context, trace);
    # TODO: check type of selected
    if len(selected) > 0:
      if selected[0].is_uri():
        if trace:
          print "NamespaceUriFunction: Determining namespace uri of %s" % selected[0]

        m = re.search('^(.*[\/\#])([a-z0-9\-\_]+)', str(selected[0].value), re.I)
        if m:
          if trace:
            print "NamespaceUriFunction: Selected namespace uri of %s" % m.group(1)
          return [Node(Literal(m.group(1)),g)]

    return []


class UriFunction:
  def __init__(self, arg):
    self.arg = arg;

  def __str__(self):
    return 'uri(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    result = self.arg.evaluate(value, g, context, trace)

    if isinstance(result, list) and len(result) > 0:
      if result[0].is_uri():
        if trace:
          print "UriFunction: Selected URI of %s" % result[0]
        return str(result[0].value)

    return ''

class NotFunction:
  def __init__(self, arg):
    self.arg = BooleanFunction(arg);

  def __str__(self):
    return 'not(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    result = self.arg.evaluate(value, g, context, trace)
    if type(result) == bool:
      if trace:
        print "NotFunction: Inverting boolean %s" % result
      return result == False

    if trace:
      print "NotFunction: Result of evaluating %s was not boolean %s" % value
    return False

class BooleanFunction:
  def __init__(self, arg):
    self.arg = arg;

  def __str__(self):
    return 'boolean(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    v = self.arg.evaluate(value, g, context, trace)
    if type(v) == list or type(v) == str or type(v) == unicode:
      if trace:
        print "BooleanFunction: Checking if list or string has length > 0"
      return len(v) > 0
    elif type(v) == int or type(v) == float:
      if trace:
        print "BooleanFunction: Checking if numeric is != 0"
      return v != 0
    elif type(v) == bool:
      if trace:
        print "BooleanFunction: Checking bool value"
      return v
    
    return False



class ExpFunction:
  def __init__(self, arg):
    self.arg = arg;

  def __str__(self):
    return 'exp(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    result = self.arg.evaluate(value, g, context, trace)

    if isinstance(result, str):
      if trace:
        print "ExpFunction: Attempting to expand %s to URI" % result
      uri = g.qname_to_uri(result)
      if uri is not None:
        if trace:
          print "ExpFunction: Expanded to %s" % uri
        return str(uri)

    if trace:
      print "ExpFunction: Could not expand\n";

    return ''


class LiteralValueFunction:
  def __init__(self, arg):
    self.arg = arg;

  def __str__(self):
    return 'literal-value(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    if trace:
      print "LiteralValueFunction: Using %s to determine literal value" % self.arg
    result = self.arg.evaluate(value, g, context, trace);

    if isinstance(result, list) and len(result) > 0 and result[0].is_arc():
      values = g.get_subject_property_values(result[0].node, result[0].value);
      if len(values) > 0 and isinstance(values[0], Literal):
          if trace:
            print "LiteralValueFunction: Selected value of %s" % values[0]
          return str(values[0])

    return ''

class StringLengthFunction:
  def __init__(self, arg):
    self.arg = arg

  def __str__(self):
    return 'string-length(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    if trace:
      print "LiteralValueFunction: Using %s to determine literal value" % self.arg
    result = self.arg.evaluate(value, g, context, trace);

    if isinstance(result, str) or isinstance(result, unicode):
      return len(result)

    return 0 # TODO: Raise error

class NormalizeSpaceFunction:
  def __init__(self, arg):
    self.arg = arg

  def __str__(self):
    return 'normalize-space(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    result = self.arg.evaluate(value, g, context, trace);

    if isinstance(result, str) or isinstance(result, unicode):
      return re.sub('\s\s+', ' ', result.strip(), re.S)

    return 0 # TODO: Raise error


class StartsWithFunction:
  def __init__(self, arg1, arg2):
    self.arg1 = arg1
    self.arg2 = arg2

  def __str__(self):
    return 'starts-with(%s,%s)' % (self.arg1, self.arg2)

  def evaluate(self, value, g, context, trace = False):
    if trace:
      print "StartsWithFunction: Determine whether %s starts with %s " % (self.arg1, self.arg2)
    result1 = self.arg1.evaluate(value, g, context, trace)
    result2 = self.arg2.evaluate(value, g, context, trace)

    if (isinstance(result1, str) or isinstance(result1, unicode)) and (isinstance(result2, str) or isinstance(result2, unicode)):
      return result1.startswith(result2)

    return 0 # TODO: Raise error

class ContainsFunction:
  def __init__(self, arg1, arg2):
    self.arg1 = arg1
    self.arg2 = arg2

  def __str__(self):
    return 'contains(%s,%s)' % (self.arg1, self.arg2)

  def evaluate(self, value, g, context, trace = False):
    result1 = self.arg1.evaluate(value, g, context, trace)
    result2 = self.arg2.evaluate(value, g, context, trace)

    if (isinstance(result1, str) or isinstance(result1, unicode)) and (isinstance(result2, str) or isinstance(result2, unicode)):
      return result2 in result1

    return 0 # TODO: Raise error

class SubstringBeforeFunction:
  def __init__(self, arg1, arg2):
    self.arg1 = arg1
    self.arg2 = arg2

  def __str__(self):
    return 'substring-before(%s,%s)' % (self.arg1, self.arg2)

  def evaluate(self, value, g, context, trace = False):
    result1 = self.arg1.evaluate(value, g, context, trace)
    result2 = self.arg2.evaluate(value, g, context, trace)

    if (isinstance(result1, str) or isinstance(result1, unicode)) and (isinstance(result2, str) or isinstance(result2, unicode)):
      if result2 in result1:
        return result1.partition(result2)[0]
      else:
        return ''

    return '' # TODO: Raise error


class SubstringAfterFunction:
  def __init__(self, arg1, arg2):
    self.arg1 = arg1
    self.arg2 = arg2

  def __str__(self):
    return 'substring-after(%s,%s)' % (self.arg1, self.arg2)

  def evaluate(self, value, g, context, trace = False):
    result1 = self.arg1.evaluate(value, g, context, trace)
    result2 = self.arg2.evaluate(value, g, context, trace)

    if (isinstance(result1, str) or isinstance(result1, unicode)) and (isinstance(result2, str) or isinstance(result2, unicode)):
      if result2 in result1:
        return result1.partition(result2)[2]
      else:
        return ''

    return '' # TODO: Raise error

class ConcatFunction:
  def __init__(self, args):
    self.args = args

  def __str__(self):
    return 'concat(%s)' % (",".join([str(a) for a in self.args]))

  def evaluate(self, value, g, context, trace = False):
    res = ""
    for arg in self.args:
      result = arg.evaluate(value, g, context, trace)
      if not(isinstance(result, str) or isinstance(result, unicode)):
        return '' # TODO: raise error

      res += result

    return res

class NumberFunction:
  def __init__(self, arg):
    self.arg = arg

  def __str__(self):
    return 'number(%s)' % self.arg

  def evaluate(self, value, g, context, trace = False):
    result = self.arg.evaluate(value, g, context, trace)
    
    if type(result) == list and len(result) > 0 and isnumeric(result[0]):
      return float(result[0])
    elif (type(result) == str or type(result) == unicode) and isnumeric(result):
      return float(result)
    elif type(result) == int or type(result) == float:
      return float(result)

    return None



#~ class NumberFunction:
  #~ def __init__(self, arg):
    #~ self.arg = arg;
#~ 
  #~ def __str__(self):
    #~ return 'number(%s)' % self.arg
#~ 
  #~ def evaluate(self, value, g, context, trace = False):
    #~ if trace:
      #~ print "LiteralValueFunction: Using %s to determine literal value" % self.arg
    #~ result = self.arg.evaluate(value, g, context, trace);
#~ 
    #~ if isinstance(result, list) and len(result) > 0 and result[0].is_arc():
      #~ values = g.get_subject_property_values(result[0].node, result[0].value);
      #~ if len(values) > 0 and isinstance(values[0], Literal):
          #~ if trace:
            #~ print "LiteralValueFunction: Selected value of %s" % values[0]
          #~ return str(values[0])
#~ 
    #~ return ''
#~ 

#~ class LiteralDtFunction:
  #~ def __init__(self, arg):
    #~ self.arg = arg;
#~ 
  #~ def __str__(self):
    #~ return 'literal-dt(%s)' % self.arg
#~ 
#~ 
  #~ def evaluate(self, value, g, context, trace = False):
    #~ if trace:
      #~ print "LiteralDtFunction: Using %s to determine literal datatype" % self.arg
    #~ selected = self.arg.select(candidates, g, context, trace);
    #~ if (count(selected) > 0 && isset(selected[0]['node'])) {
      #~ values = g.get_subject_property_values(selected[0]['node'], selected[0]['value']);
      #~ if (count(values) > 0) {
        #~ if ( values[0]['type'] == 'literal' && isset(values[0]['datatype'])) {
          #~ if trace:
            #~ print "LiteralDtFunction: Selected datatype of " % values[0]['datatype'] . "\n";
          #~ return values[0]['datatype'];
        #~ }
      #~ }
    #~ }
    #~ return '';
  #~ }
#~ 
#~ 
#~ class StringLengthFunction:
  #~ def __init__(self, arg):
    #~ self.arg = arg;
#~ 
  #~ def __str__(self):
    #~ return 'string-length(%s)' % self.arg
#~ 
#~ 
  #~ def evaluate(self, value, g, context, trace = False):
    #~ if trace:
      #~ print "StringLengthFunction: Finding string length of " % self.arg.to_string() . "\n";
    #~ selected = self.arg.select(candidates, g, context, trace);
    #~ if (is_string(selected)) {
      #~ if trace:
        #~ print "StringLengthFunction: String length of "  selected . " is " .  strlen(selected) . "\n";
      #~ return strlen(selected);
    #~ }
    #~ else {
      #~ raise EvaluationError("%s expected a string as an argument but did not receive one" % self);
    #~ }
    #~ return array();
#~ 
#~ class NormalizeSpaceFunction:
  #~ def __init__(self, arg):
    #~ self.arg = arg;
#~ 
  #~ def __str__(self):
    #~ return 'normalize-space(%s)' % self.arg
#~ 
  #~ def evaluate(self, value, g, context, trace = False):
    #~ selected = self.arg.select(candidates, g, context, trace);
    #~ if (is_string(selected)) {
      #~ val = preg_replace("~\s+~m", ' ', selected);
      #~ return trim(val);
    #~ }
    #~ else {
      #~ raise EvaluationError("%s expected a string as an argument but did not receive one" % self);
    #~ }
    #~ return array();
  #~ }
#~ 
#~ 
#~ class BooleanFunction:
  #~ def __init__(self, arg):
    #~ self.arg = arg;
#~ 
  #~ def __str__(self):
    #~ return 'boolean(%s)' % self.arg
#~ 
  #~ def evaluate(self, value, g, context, trace = False):
    #~ selected = self.arg.select(candidates, g, context, trace);
    #~ return Converter::to_boolean(selected);
