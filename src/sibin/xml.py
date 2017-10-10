'''
Created on Dec 20, 2013

@author: fbolton
'''
import sibin.core
import copy
import os.path
import subprocess
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

  def getImageWidth(self,imagefile):
    # Call the ImageMagick 'identify' utility to get the image metadata
    metadata = subprocess.check_output(['identify', imagefile]).split()
    (imagewidth, imagedepth) = metadata[2].split('x')
    return imagewidth

  def dcbk2publican(self,element,xmlfile,bookid):
    self.bookid = bookid
    result = copy.deepcopy(element)
    self._dcbk2publican_element( result, xmlfile, with_tail=False )
    return result

  def _dcbk2publican_element(self,el,xmlfile,with_tail=True):
    # Remove namespace from tag
    i = el.tag.find('}')
    if i >= 0:
      tagname = el.tag[i+1:]
    else:
      tagname = el.tag
    # Process attributes
    xmlBaseName = '{http://www.w3.org/XML/1998/namespace}base'
    if xmlBaseName in el.attrib:
      del( el.attrib[xmlBaseName] )
    # Process text
    el.text = self._dcbk2publican_text(el.text)
    if with_tail:
      el.tail = self._dcbk2publican_text(el.tail)
    # Process specific tags
    if tagname == 'olink':
      self._dcbk2publican_olink(el)
      return
    elif tagname == 'xref':
      self._dcbk2publican_xref(el)
      return
    elif tagname == 'link':
      self._dcbk2publican_link(el)
      return
    elif tagname == 'imagedata':
      fileref = el.get('fileref') or el.get('{http://docbook.org/ns/docbook}fileref')
      if fileref and (not fileref.startswith('http:')):
        el.set('fileref', 'images/' + os.path.basename(fileref))
        # Fix image scaling
        contentwidth = el.get('contentwidth') or el.get('{http://docbook.org/ns/docbook}contentwidth')
        (imageroot, imageformat) = os.path.splitext(fileref)
        imageformat = imageformat.lower()
        if not contentwidth and imageformat != 'svg':
          imagefile = self.context.imageFileMap[os.path.basename(fileref)]
          imagewidth = self.getImageWidth(imagefile)
          scale = el.get('scale') or el.get('{http://docbook.org/ns/docbook}scale')
          if scale:
            el.set('contentwidth', str( int(imagewidth)*int(scale) // 100 ) + 'px')
            del el.attrib['scale']
          else:
            el.set('contentwidth', imagewidth + 'px')
    elif tagname == 'programlisting':
      self._dcbk2publican_verbatim(el)
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
    if targetdoc and targetptr and (targetdoc != self.bookid):
      # Link between books
      # Maps to a 'link' element
      link = el.makeelement('link')
      link.set('{http://www.w3.org/1999/xlink}href', self.context.linkData.olink2url(targetdoc,targetptr))
      if el.text:
        link.text = el.text
      else:
        link.text = self.context.linkData.getolinktext(targetdoc,targetptr)
      link.tail = el.tail
      parent.replace(el,link)
    elif targetptr and el.text:
      # If link text => map to a 'link' element
      link = el.makeelement('link')
      link.set('linkend', targetptr)
      link.text = el.text
      link.tail = el.tail
      parent.replace(el,link)
    elif targetptr:
      # Link within a book
      # Maps to an 'xref' element
      xref = el.makeelement('xref')
      xref.set('linkend', targetptr)
      xref.tail = el.tail
      parent.replace(el,xref)
    else:
      # Badly defined 'olink' element
      # Map to a 'phrase' element
      phrase = el.makeelement('phrase')
      phrase.text = el.text
      phrase.tail = el.tail
      parent.replace(el,phrase)
    
  def _dcbk2publican_xref(self,el):
    # No-op!
    return
    linkend = el.get('linkend')
    if linkend:
      # Link within a book
      self.transform_intra_link(el, linkend)
    else:
      # TODO log a warning
      # Should not happen!
      pass

  def _dcbk2publican_link(self,el):
    # No-op!
    return
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

  def _dcbk2publican_verbatim(self,el):
    for child in el.xpath("./*[local-name()='emphasis']"):
      if (child.text is not None) and ('\n' in child.text):
        lines = child.text.splitlines()
        lastline = lines.pop()
        for line in lines:
          # Publican requires leading whitespace to lie *outside* the inline element
          (leadspaces, restofline) = self.splitleadingspaces(line)
          if child.getprevious() is not None:
            if child.getprevious().tail is not None:
              child.getprevious().tail += leadspaces
            else:
              child.getprevious().tail = leadspaces
          else:
            if el.text is not None:
              el.text += leadspaces
            else:
              el.text = leadspaces
          # Make a new child element
          newchild = el.makeelement('{http://docbook.org/ns/docbook}emphasis', child.attrib)
          newchild.text = restofline
          newchild.tail = '\n'
          # Insert newchild immediately before child
          childindex = el.index(child)
          el.insert(childindex, newchild)
        # Publican requires leading whitespace to lie *outside* the inline element
        (leadspaces, restofline) = self.splitleadingspaces(lastline)
        if child.getprevious() is not None:
          if child.getprevious().tail is not None:
            child.getprevious().tail += leadspaces
          else:
            child.getprevious().tail = leadspaces
        else:
          if el.text is not None:
            el.text += leadspaces
          else:
            el.text = leadspaces
        child.text = restofline

  def splitleadingspaces(self,text):
    strippedstr = text.lstrip()
    difflen = len(text) - len(strippedstr)
    leadspaces = '' + ' ' * difflen
    return (leadspaces, strippedstr)
