'''
Created on Dec 20, 2013

@author: fbolton
'''
import sibin.core
import copy
import os.path
from lxml import etree
from lxml import objectify

class XMLTransformer:
  '''
  A class that converts XML to Publican format
  '''

  def __init__(self,context):
    if not isinstance(context,sibin.core.SibinContext):
      raise Exception('XMLTransformer must be initialized with a SibinContext argument')
    self.context = context
    self.SECTION_TAGS = ['section', 'simplesect', 'sect1', 'sect2', 'sect3', 'sect4', 'sect5']

  def dcbk2publican(self,element,xmlfile):
    result = copy.deepcopy(element)
    self._dcbk2publican_element( result, xmlfile, with_tail=False )
    # Cleans away all remaining traces of the DocBook namespace
    objectify.deannotate(result, cleanup_namespaces=True)
    return result
  
  def _dcbk2publican_element(self,el,xmlfile,with_tail=True):
    # Strip DocBook 5 namespace out of tag name (if any)
    i = el.tag.find('}')
    if i >= 0:
      el.tag = el.tag[i+1:]
    # Process attributes
    for attName in el.keys():
      val = el.get(attName)
      if attName == '{http://www.w3.org/XML/1998/namespace}id':
        el.set('id', val)
        del( el.attrib[attName] )
      if attName.endswith('pgwide') or attName.endswith('version'):
        # pgwide and version attributes are only available in DB5, not DB4.5
        del( el.attrib[attName] )        
    # Process text
    el.text = self._dcbk2publican_text(el.text)
    if with_tail:
      el.tail = self._dcbk2publican_text(el.tail)
    # Process specific tags
    if el.tag == 'olink':
      self._dcbk2publican_olink(el)
      return
    elif el.tag == 'xref':
      self._dcbk2publican_xref(el)
      return
    elif el.tag == 'link':
      self._dcbk2publican_link(el)
      return
    elif el.tag == 'imagedata':
      fileref = el.get('fileref')
      if fileref:
        (root, ext) = os.path.splitext(fileref)
        imageFile = os.path.normpath(os.path.join(os.path.dirname(xmlfile),fileref))
        (imageId, localeId) = self.context.linkData.getimageid(imageFile)
        if imageId:
          el.set('fileref', 'images/' + imageId + ext)
    elif el.tag in self.SECTION_TAGS:
      el.tag = 'section'
    elif el.tag.endswith('info'):
      el.tag = 'sectioninfo'
    # Iterate over all child nodes
    for child in el:
      if isinstance(child, etree._Comment):
        self._dcbk2publican_comment(child)
      elif isinstance(child, etree._Entity):
        self._dcbk2publican_entity(child)
      elif isinstance(child, etree._ProcessingInstruction):
        self._dcbk2publican_pi(child)
      elif isinstance(child, etree._Element):
        self._dcbk2publican_element(child,xmlfile)
      else:
        # TODO Log warning - should never get here!
        # print "child type = Unknown(!)"
        pass

  def _dcbk2publican_comment(self,el):
    # No need to process comments. Currently a no-op.
    pass
  
  def _dcbk2publican_entity(self,el):
    # No need to process entities. Currently a no-op.
    pass
  
  def _dcbk2publican_pi(self,el):
    # Remove any ccms Processing Instructions
    if el.target=='ccms':
      parent = el.getparent()
      parent.remove(el)
  
  def _dcbk2publican_text(self,text):
    return text
  
  def _dcbk2publican_olink(self,el):
    parent = el.getparent()
    targetdoc = el.get('targetdoc')
    targetptr = el.get('targetptr')
    if targetdoc and targetptr:
      # Link between books
      # Maps to a 'phrase' element in CCMS
      # Use 'remap' attribute to encode 'olink' data
      # e.g. remap="olink:targetdoc/targetptr"
      phrase = el.makeelement('phrase')
      phrase.set('remap', 'olink:' + targetdoc + '/' + targetptr)
      phrase.text = self.context.linkData.getolinktext(targetdoc,targetptr)
      phrase.tail = el.tail
      parent.replace(el,phrase)
    elif targetptr:
      # Link within a book
      self.transform_intra_link(el, targetptr)
    else:
      # TODO log a warning
      # Should not happen!
      pass
    
  def _dcbk2publican_xref(self,el):
    linkend = el.get('linkend')
    if linkend:
      # Link within a book
      self.transform_intra_link(el, linkend)
    else:
      # TODO log a warning
      # Should not happen!
      pass

  def _dcbk2publican_link(self,el):
    # Map 'link' to 'ulink', which is the required way to define HREFs in DocBook 4
    parent = el.getparent()
    href = el.get('{http://www.w3.org/1999/xlink}href')
    linkend = el.get('linkend')
    text = el.text
    if href:
      # Link to external URL
      ulink = el.makeelement('ulink')
      ulink.set('url', href)
      if text:
        ulink.text = text
      ulink.tail = el.tail
      parent.replace(el,ulink)
    elif linkend:
      # Link within a book
      self.transform_intra_link(el, linkend)
    else:
      # TODO log a warning
      pass
  
  def transform_intra_link(self,el,xmlId):
    # Transform link within a book
    parent = el.getparent()
    # Can we find the referenced element *inside* the current topic element?
    nodeset = el.xpath('id($val)', val=xmlId)
    if len(nodeset) > 0:
      # If already an 'xref' element, do nothing
      if el.tag.endswith('xref'):
        return
      # Else transform link into an 'xref' element
      xref = el.makeelement('xref')
      xref.set('linkend', xmlId)
      xref.tail = el.tail
      parent.replace(el,xref)
    else:
      # Transform link into a Pressgang topic injection
      topicId = self.context.linkData.gettopicid(xmlId)
      if topicId:
        comment = etree.Comment(' Inject: ' + topicId + ' ')
      else:
        # Use 0 as place-holder for the missing topic ID
        comment = etree.Comment(' Inject: 0 ')
      comment.tail = el.tail
      # Replace 'el' by the newly created 'comment'
      parent.replace(el,comment)

