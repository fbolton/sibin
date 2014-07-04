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
  for code,name in htmlentitydefs.codepoint2name.items():
    string = re.sub('&#'+str(code)+';', '&'+name+';', string)
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
    # XML elements that divide up the book
    self.divElements = ['part', 'chapter', 'appendix', 'section']
    # Verbatim elements - whitespace is significant for these elements
    self.verbatimElements = ['date', 'screen', 'programlisting', 'literallayout', 'synopsis', 'address', 'computeroutput']
    # List of profiles
    self.profiles = []
    # Profiles can specify the conditions to build with
    self.conditions = {}
    # Selects the current effective profile
    self.currentProfile = 'default'
    # XML transformer instance
    self.transformer = None
    # Optional commit comment
    self.comment = ''
    # Contains the data for cross-referencing images and topics across the whole library
    self.linkData = LinkData()
    # The relative path name of the book entities file
    self.bookEntitiesFile = 'Library.ent'
    # File extensions used to identify image files
    self.imageFileExtList = ['.gif', '.jpg', '.svg', '.png']
    return
  
  def initializeFromFile(self,filename):
    doc = etree.parse(filename)
    root = doc.getroot()
    for book in root.xpath('/context/books/book'):
      self.bookFiles.append(book.get('file'))
    for entities in root.xpath('/context/entities'):
      self.bookEntitiesFile = entities.get('file')
    for profile in root.xpath('/context/profiles/profile'):
      profilename = profile.get('name')
      self.profiles.append(profilename)
      conditionlist = []
      for conditions in profile.iter('conditions'):
        for condition in conditions.iter('condition'):
          conditionlist.append(condition.get('match'))
      self.conditions[profilename] = '|'.join(conditionlist)
      host = profile.find('host')
      if host is not None:
        self.hostnames[profilename] = host.get('name')
    del doc
    if 'default' in self.profiles:
      self.currentProfile = 'default'
    else:
      self.currentProfile = self.profiles[0]
    # TODO Should change this into a log statement
    print 'Current profile set to: ' + self.currentProfile
  
  def getproject(self):
    # TODO Provide proper implementation
    return self.currentProfile
  

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
  
  def appendTopicLinkData(self,ld):
    root = self.doc.getroot()
    self._parse_for_linkdata(ld, root, ancestorTopicId='')
  
  def _parse_for_linkdata(self,ld,el,ancestorTopicId):
    # In Pressgang, we can only cross-reference topics. So, if we have a link to
    # an element that is not a topic, we must try to identify the 'nearest' topic
    # and use that topic ID instead.
    # 
    # A consequence of this is that each xmlId can map to multiple topicIds.
    # In the topicId-to-xmlId map, however, only the topic element is recorded,
    # so that the topicId maps to a unique xmlId.
    (topicId, syncVersion, frozen) = ('', '', False)
    xmlId = el.get('id') or el.get('{http://www.w3.org/XML/1998/namespace}id')
    # If necessary, strip off the preceding namespace (DocBook 5)
    tagname = el.tag.lower()
    if tagname.startswith('{'):
      tagname = tagname[tagname.find('}')+1:]
    firstchild = el[0] if len(el) else None
    if (firstchild is not None) and isinstance(firstchild, etree._ProcessingInstruction) and firstchild.target=='ccms':
      topicId = firstchild.get('topic')
      syncVersion = firstchild.get('syncVersion')
      frozen = firstchild.get('frozen')
      for child in el.iterchildren(tag=etree.Element):
        self._parse_for_linkdata(ld, child, topicId)
    elif xmlId and (tagname in self.divElements):
      topicId = 'T-' + xmlId
      for child in el.iterchildren(tag=etree.Element):
        self._parse_for_linkdata(ld, child, topicId)
    elif ancestorTopicId:
      topicId = ancestorTopicId
      for child in el.iterchildren(tag=etree.Element):
        self._parse_for_linkdata(ld, child, topicId)
    else:
      for child in el.iterchildren(tag=etree.Element):
        childTopicId = self._parse_for_linkdata(ld, child, '')
        if childTopicId and (not topicId):
          # Use the first child topic ID that is found
          topicId = childTopicId
    # TODO Log statement
    # print el.tag + '/@id = ' + xmlId
    title = extract_title(el)
    if xmlId:
      ld.addTopicData(self.book,el.tag,xmlId,title,topicId,syncVersion,frozen)
    return topicId


class LinkData:
  def __init__(self):
    self.XmlId2TopicId = {}
    self.TopicId2XmlId = {}
    self.ImageFile2ImageId = {}
    self.ImageId2ImageFile = {}
    return
  
  def addTopicData(self, book, elementTag, xmlId='', title='', topicId='', syncVersion='', frozen=False):
    topicTuple = (book,elementTag,xmlId,title,topicId,syncVersion,frozen)
    if xmlId:
      if xmlId not in self.XmlId2TopicId:
        self.XmlId2TopicId[xmlId] = { book.id:topicTuple }
      else:
        self.XmlId2TopicId[xmlId][book.id] = topicTuple
    if topicId:
      if topicId not in self.TopicId2XmlId:
        self.TopicId2XmlId[topicId] = { book.id:topicTuple }
      elif not book.id in self.TopicId2XmlId[topicId]:
        # Note that the preceding 'if' statement stops the topic
        # entry from being clobbered, in case there are multiple
        # topicId --> xmlId mappings in a given book.
        # In practice, this means that the topicId --> xmlId mapping for the 
        # topic element itself is the only one that gets recorded (see _parse_for_linkdata func)
        self.TopicId2XmlId[topicId][book.id] = topicTuple
    return
  
  def addImageData(self,imageFile,imageId='',syncVersion='',frozen=False,localeSpecificID='',localeSpecificRev=''):
    imageTuple = (imageFile,imageId,syncVersion,frozen,localeSpecificID,localeSpecificRev)
    self.ImageFile2ImageId[imageFile] = imageTuple
    if imageId:
      self.ImageId2ImageFile[imageId] = imageTuple
    return
  
  def getimageid(self,imageFile):
    if not self.ImageFile2ImageId.has_key(imageFile):
      return ('','')
    imageTuple = self.ImageFile2ImageId[imageFile]
    if imageTuple:
      return (imageTuple[1], imageTuple[4])
    else:
      return ('','')
    
  def check_targetlink_consistency(self):
    '''
    In cases where an xml:id appears in more than one book, check that they all refer to the same
    topic ID. Pressgang has no way of resolving ambiguous xml:id values. Return False, if any
    inconsistencies are found.
    '''
    isconsistent = True
    for xmlId in self.XmlId2TopicId.keys():
      # This routine is deliberately written such that it keeps going after finding the
      # first inconsistency, so that warnings for all inconsistencies can be logged in one go
      isconsistent = isconsistent and self.check_single_targetlink(xmlId)
    return isconsistent
  
  def gettopicid(self,xmlId):
    '''
    Returns the topic ID corresponding to the xml:id, or a blank string.
    If the xml:id appears in more than one book, checks that the topic IDs are all the same.
    If the xml:id maps to multiple, unequal topic IDs, returns a blank string.
    '''
    if not self.XmlId2TopicId.has_key(xmlId):
      return ''
    bookId2Tuple = self.XmlId2TopicId[xmlId]
    firstTopicId = ''
    for bookId in bookId2Tuple.keys():
      currentTopicId = bookId2Tuple[bookId][4]
      if not currentTopicId:
        # Skip blank topic IDs
        continue
      if not firstTopicId:
        firstTopicId = currentTopicId
        continue
      elif currentTopicId != firstTopicId:
        # TODO Should be changed to a log statement
        print "WARNING: inconsistent topic IDs corresponding to xml:id = " + xmlId
        print "currentTopicId = " + currentTopicId + ", firstTopicId = " + firstTopicId
        print "    " + str(bookId2Tuple)
        raise Warning("Inconsistent topic IDs")
    return firstTopicId

  def getbookfilesfortopic(self,topicId):
    filenames = []
    if not self.TopicId2XmlId.has_key(topicId):
      return []
    bookDict = self.TopicId2XmlId[topicId]
    for topicTuple in bookDict.values():
      filenames.append(topicTuple[0].filename)
    return filenames
  
  def check_single_targetlink(self,xmlId):
    '''
    Returns True, if the specified xmlId maps consistently to a unique topic ID, otherwise False.
    If the xml:id appears in more than one book, checks that the topic IDs are all the same.
    '''
    try:
      topicId = self.gettopicid(xmlId)
    except Warning as warnmsg:
      return False
    return True
  
  def getolinktext(self,targetdoc,targetptr):
    if not self.XmlId2TopicId.has_key(targetptr):
      return ''
    bookId2Tuple = self.XmlId2TopicId[targetptr]
    if bookId2Tuple:
      if targetdoc not in bookId2Tuple:
        print 'WARNING: <olink targetdoc="' + targetdoc + '" targetptr="' + targetptr + '/>',
        print 'references a non-existent book ID: ' + targetdoc
        print '    The book ID might be obsolete or you might have forgotten to add all of the',
        print 'relevant books to your .git-cms file.'
      topicTuple = bookId2Tuple[targetdoc]
      if topicTuple:
        bookTitle = topicTuple[0].title
        sectionTitle = topicTuple[3]
        if targetdoc==targetptr:
          return '"' + bookTitle + '"'
        else:
          return 'section "' + sectionTitle + '" in "' + bookTitle + '"'
    return ''
    
  
  def __str__(self):
    print 'XmlId2TopicId = {'
    for xmlId in self.XmlId2TopicId.keys():
      print '  xmlId = ' + xmlId + ' {'
      entries = self.XmlId2TopicId[xmlId]
      for bookId in entries.keys():
        print '    ' , entries[bookId]
      print '  }'
    print '}'
    
    print 'TopicId2XmlId = {'
    for topicId in self.TopicId2XmlId.keys():
      print '  topicId = ' + topicId + ' {'
      entries = self.TopicId2XmlId[topicId]
      for bookId in entries.keys():
        print '    ' , entries[bookId]
      print '  }'
    print '}'
    
    print 'ImageFile2ImageId = {'
    for fileref in self.ImageFile2ImageId.keys():
      print '  fileref = ' + fileref + ' {'
      entry = self.ImageFile2ImageId[fileref]
      print '    ' , entry
    print '}'
    
    print 'ImageId2ImageFile = {'
    for imageId in self.ImageId2ImageFile.keys():
      print '  imageId = ' + imageId + ' {'
      entry = self.ImageId2ImageFile[imageId]
      print '    ' , entry
    print '}'


