'''
Created on Nov 21, 2013

@author: fbolton
'''
from lxml import etree
import htmlentitydefs
import re
import os.path
import sys

# Re-encode special character codes to their names (e.g. &#160; to &nbsp;)
def reencode(string):
  #for code,name in htmlentitydefs.codepoint2name.items():
    #string = re.sub('&#'+str(code)+';', '&'+name+';', string)
  string.replace('&#160;', '&nbsp;')
  return string

# Parent function to convert and sanitize and xml etree object into a string
def xmltostring(xml):
  etree.strip_tags(xml, '*', etree.Comment)
  if not xml.text:
    return ''
  string = " ".join(xml.text.split())
  string = reencode(string)
  return string

def extract_title(el):
  if el.tag.endswith('info'):
    # *info topics are a special case - define a placeholder title
    return 'Info'
  # Find first 'title' child element
  titleList = el.xpath(".//*[local-name()='title']")
  if (titleList is not None) and (len(titleList) > 0):
    return xmltostring(titleList[0])
  else:
    return ''
  

class SibinContext:
  def __init__(self):
    # list of all DB book files,
    # where dirs are specified relative to top level dir
    self.bookFiles = []
    # Publican sort_order of book - low numbers listed before high
    self.sortorder = {}
    # A dictionary of publican properties (additional settings in publican.cfg)
    self.book2publicanprops = {}
    # XML elements that divide up the book
    self.divElements = ['part', 'chapter', 'appendix', 'section']
    # Verbatim elements - whitespace is significant for these elements
    self.verbatimElements = ['date', 'screen', 'programlisting', 'literallayout', 'synopsis', 'address', 'computeroutput']
    # List of profiles
    self.profiles = []
    # Profiles can specify the conditions to build with
    self.conditions = {}
    # Profiles can specify the portal hostname
    self.hostnames = {}
    # Profiles can specify the template directory
    self.templates = {}
    # Product name
    self.productname = ''
    # Product version
    self.productversion = ''
    # Build version
    self.buildversion = ''
    # Selects the current effective profile
    self.currentProfile = 'default'
    # XML transformer instance
    self.transformer = None
    # Optional commit comment
    self.comment = ''
    # Contains the data for cross-referencing images and topics across the whole library
    self.linkData = LinkData(self)
    # The relative path name of the book entities file
    self.bookEntitiesFile = 'Library.ent'
    # File extensions used to identify image files
    self.imageFileExtList = ['.gif', '.jpg', '.svg', '.png']
    return
  
  def initializeFromFile(self,filename):
    doc = etree.parse(filename)
    root = doc.getroot()
    product = root.find('product')
    if product is not None:
      self.productname    = product.get('name')
      self.productversion = product.get('version')
      self.buildversion   = product.get('build')
    for book in root.xpath('/context/books/book'):
      self.bookFiles.append(book.get('file'))
      if book.get('sortorder'):
        self.sortorder[book.get('file')] = book.get('sortorder')
      publicanprops = {}
      for publicanprop in book.iter('publicanprop'):
        propname  = publicanprop.get('name')
        propvalue = publicanprop.get('value')
        if propname and propvalue:
          publicanprops[propname] = propvalue
      if publicanprops:
        self.book2publicanprops[book.get('file')] = publicanprops
    for entities in root.xpath('/context/entities'):
      self.bookEntitiesFile = entities.get('file')
    for profile in root.xpath('/context/profiles/profile'):
      profilename = profile.get('name')
      self.profiles.append(profilename)
      conditionlist = []
      for conditions in profile.iter('conditions'):
        for condition in conditions.iter('condition'):
          conditionlist.append(condition.get('match'))
      self.conditions[profilename] = ';'.join(conditionlist)
      host = profile.find('host')
      if host is not None:
        self.hostnames[profilename] = host.get('name')
      template = profile.find('template')
      if template is not None:
        self.templates[profilename] = template.get('dir')
    del doc
    if 'default' in self.profiles:
      self.currentProfile = 'default'
    else:
      self.currentProfile = self.profiles[0]
    # TODO Should change this into a log statement
    print 'Current profile set to: ' + self.currentProfile
  
  def gethostname(self):
    return self.hostnames[self.currentProfile]

  def gettemplate(self):
    return self.templates[self.currentProfile]

  def getconditions(self):
    return self.conditions[self.currentProfile]


class Book:
  def __init__(self,filename=''):
    if filename:
      self.filename = filename
    return

class BookParser:
  def __init__(self,book=Book()):
    self.book = book
    self.divElements = ['part', 'chapter', 'appendix', 'section']
    return
  
  def parse(self,bookFile=''):
    if bookFile:
      self.bookFile = bookFile
      self.book.filename = bookFile
    else:
      self.bookFile = self.book.filename
    print 'Parsing book: ' + self.bookFile
    self.doc = etree.parse(self.bookFile)
    self.doc.xinclude()
    self.root = self.doc.getroot()
    if not self.root.tag.endswith('book'):
      print 'ERROR: Not a book file: ' + self.bookFile
      print '       Check the settings in .git-ccms'
      sys.exit()
    self.book.id = self.root.get('id') or self.root.get('{http://www.w3.org/XML/1998/namespace}id')
    titleList = self.root.xpath("./*[local-name()='title']")
    if len(titleList)==0:
      titleList = self.root.xpath("./*[local-name()='info']/*[local-name()='title']")
    subtitleList = self.root.xpath("./*[local-name()='subtitle']")
    if len(subtitleList)==0:
      subtitleList = self.root.xpath("./*[local-name()='info']/*[local-name()='subtitle']")
    self.book.title         = xmltostring(titleList[0])
    self.book.subtitle      = xmltostring(subtitleList[0])
    self.book.abstract      = xmltostring(self.root.xpath("./*[local-name()='info']/*[local-name()='abstract']")[0])
    self.book.productname   = xmltostring(self.root.xpath("./*[local-name()='info']/*[local-name()='productname']")[0])
    productnumberList = self.root.xpath("./*[local-name()='info']/*[local-name()='productnumber']")
    if len(productnumberList) > 0:
      self.book.productnumber = xmltostring(productnumberList[0])
    else:
      self.book.productnumber = ''
    editionList = self.root.xpath("./*[local-name()='info']/*[local-name()='edition']")
    if len(editionList) > 0:
      self.book.edition = xmltostring(editionList[0])
    else:
      self.book.edition = ''
  
  def appendLinkData(self,ld):
    root = self.doc.getroot()
    self._parse_for_linkdata(ld, root)
  
  def _parse_for_linkdata(self,ld,el,pageId=''):
    # A consequence of this is that each xmlId can map to multiple topicIds.
    # In the topicId-to-xmlId map, however, only the topic element is recorded,
    # so that the topicId maps to a unique xmlId.
    xmlId = el.get('id') or el.get('{http://www.w3.org/XML/1998/namespace}id')
    # If necessary, strip off the preceding namespace (DocBook 5)
    tagname = el.tag.lower()
    if tagname.startswith('{'):
      tagname = tagname[tagname.find('}')+1:]
    # print el.tag + '/@id = ' + xmlId
    title = extract_title(el)
    if xmlId:
      if tagname=='chapter' or tagname=='appendix' or tagname=='part':
        # Start a new page
        pageId = xmlId
      if tagname=='section' and (el.getprevious() is not None) and isinstance(el.getprevious().tag, type('')):
        parentTag = el.getparent().tag.lower()
        if parentTag.startswith('{'):
          parentTag = parentTag[parentTag.find('}')+1:]
        previousTag = el.getprevious().tag.lower()
        if previousTag.startswith('{'):
          previousTag = previousTag[previousTag.find('}')+1:]
        if (parentTag=='chapter' or parentTag=='appendix') and previousTag=='section':
          # Start a new page
          pageId = xmlId
      ld.addLinkData(self.book,tagname,xmlId,title,pageId)
    for child in el.iterchildren(tag=etree.Element):
      self._parse_for_linkdata(ld, child, pageId)


class LinkData:
  def __init__(self,context):
    if not isinstance(context,SibinContext):
      raise Exception('LinkData must be initialized with a SibinContext argument')
    self.context = context
    self.XmlId2Target = {}
    return
  
  def addLinkData(self, book, elementTag, xmlId='', title='', pageId=''):
    # pageId is the xml:id of the ancestor element that ultimately gets rendered as a HTML page
    topicTuple = (book,elementTag,xmlId,title,pageId)
    if xmlId:
      if xmlId not in self.XmlId2Target:
        self.XmlId2Target[xmlId] = { book.id:topicTuple }
      else:
        self.XmlId2Target[xmlId][book.id] = topicTuple
    return
  
  def getolinktext(self,targetdoc,targetptr):
    if not self.XmlId2Target.has_key(targetptr):
      return ''
    bookId2Tuple = self.XmlId2Target[targetptr]
    if bookId2Tuple:
      if targetdoc not in bookId2Tuple:
        print 'WARNING: <olink targetdoc="' + targetdoc + '" targetptr="' + targetptr + '/>',
        print 'references a non-existent book ID: ' + targetdoc
        print '    The book ID might be obsolete or you might have forgotten to add all of the',
        print 'relevant books to your sibin.cfg file.'
        # TODO Might be better to add an option that specifies whether or
        # not to ignore this warning (current default is to ignore).
        # A legitimate reason for ignoring is when the broken link is
        # inside a condition that will NOT be included in the book.
        return ''
      topicTuple = bookId2Tuple[targetdoc]
      if topicTuple:
        bookTitle = topicTuple[0].title
        sectionTitle = topicTuple[3]
        if targetdoc==targetptr:
          return '"' + bookTitle + '"'
        else:
          thingName = 'section'
          tagname = topicTuple[1]
          if tagname in ['part', 'chapter', 'appendix', 'example', 'figure']:
            thingName = tagname
          return thingName + ' "' + sectionTitle + '" in "' + bookTitle + '"'
    return ''

  def olink2url(self,targetdoc,targetptr):
    if not self.XmlId2Target.has_key(targetptr):
      return ''
    bookId2Tuple = self.XmlId2Target[targetptr]
    if bookId2Tuple:
      if targetdoc not in bookId2Tuple:
        print 'WARNING: <olink targetdoc="' + targetdoc + '" targetptr="' + targetptr + '/>',
        print 'references a non-existent book ID: ' + targetdoc
        print '    The book ID might be obsolete or you might have forgotten to add all of the',
        print 'relevant books to your sibin.cfg file.'
        # TODO Might be better to add an option that specifies whether or
        # not to ignore this warning (current default is to ignore).
        # A legitimate reason for ignoring is when the broken link is
        # inside a condition that will NOT be included in the book.
        return ''
      topicTuple = bookId2Tuple[targetdoc]
      if topicTuple:
        baseUrl = self.context.gethostname()
        bookTitle = topicTuple[0].title.replace(' ','_')
        prodName  = self.context.productname.replace(' ','_')
        version   = self.context.productversion
        pageId    = topicTuple[4]
        if pageId:
          if pageId==targetptr:
            pageRef = pageId + '.html'
          else:
            pageRef = pageId + '.html#' + targetptr
        else:
          # Default to start of book
          pageRef = 'index.html'
        return baseUrl + '/en-US/' + prodName + '/' + version + '/html/' + bookTitle + '/' + pageRef
    return ''
  
  def __str__(self):
    print 'XmlId2Target = {'
    for xmlId in self.XmlId2Target.keys():
      print '  xmlId = ' + xmlId + ' {'
      entries = self.XmlId2Target[xmlId]
      for bookId in entries.keys():
        print '    ' , entries[bookId]
      print '  }'
    print '}'


