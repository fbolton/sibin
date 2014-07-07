'''
Created on July 3, 2014

@author: fbolton
'''

from lxml import etree
import sibin.core
import sibin.xml
import os
import sys
import argparse
import shutil

class BasicTasks:
  def __init__(self,context):
    if not isinstance(context,sibin.core.SibinContext):
      raise Exception('BasicTasks must be initialized with a SibinContext argument')
    self.context = context
    
  def save_doc_to_xml_file(self,element,xmlfile,entityfile):
    tagname = element.tag
    # If necessary, strip off the preceding namespace (DocBook 5)
    if tagname.startswith('{'):
      tagname = tagname[tagname.find('}')+1:]
    content = "<?xml version='1.0' encoding='UTF-8'?>\n"
    content += '<!DOCTYPE ' + tagname + ' [\n'
    content += '<!ENTITY % BOOK_ENTITIES SYSTEM "' + entityfile + '">\n'
    content += '%BOOK_ENTITIES;\n'
    content += ']>\n'
    content += etree.tostring(element)
    content += '\n'
    f = open(xmlfile, 'w')
    f.write(content)
    f.close()
    del content

  def parse_xincludes(self, xmlfile, ignoreDirs=[]):
    '''
    Return the set of all files recursively xincluded by xmlfile,
    optionally excluding the contents of any directories specified by ignoreDirs
    '''
    xincludeSet = set()
    doc = etree.parse(xmlfile)
    root = doc.getroot()
    for xinclude in root.findall('.//{http://www.w3.org/2001/XInclude}include'):
      # Ignore fallback includes (implies that main include must be provided)
      if xinclude.getparent().tag == '{http://www.w3.org/2001/XInclude}fallback':
        break
      href = xinclude.get('href') or xinclude.get('{http://www.w3.org/2001/XInclude}href')
      xincludeFile = os.path.normpath(os.path.join(os.path.dirname(xmlfile),href))
      if not os.path.exists(xincludeFile):
        raise Exception('File referenced in xi:include does not exist:  ' + xincludeFile)
      ignore = False
      for ignoredir in ignoreDirs:
        if xincludeFile.startswith(ignoredir):
          ignore = True
          break
      if not ignore:
        xincludeSet.add(xincludeFile)
        xincludeSet |= self.parse_xincludes(xincludeFile, ignoreDirs)
    # Garbage collect parsed file, to avoid memory leaks!
    del doc
    return xincludeSet

  def getImageFileSet(self,element,xmlfile):
    imageFileSet = set()
    for imagedata in element.xpath(".//*[local-name()='imagedata']"):
      fileref = imagedata.get('fileref') or imagedata.get('{http://docbook.org/ns/docbook}fileref')
      if fileref.startswith('http:'):
        # No need to process the image, if it's just a URL reference
        continue
      if not fileref:
        raise Exception('appendImageLinkData() - non-existent imagedata/@fileref attribute in file:' + xmlfile)
      imageFile = os.path.normpath(os.path.join(os.path.dirname(xmlfile),fileref))
      imageFileSet.add(imageFile)
    return imageFileSet
  
  def generate_publican(self,args):
    # Populate topic link data
    for bookFile in self.context.bookFiles:
      bookParser = sibin.core.BookParser(sibin.core.Book(bookFile))
      bookParser.parse()
      bookParser.appendLinkData(self.context.linkData)
      del bookParser
    # Start generating publican output
    genbasedir = 'publican'
    for bookFile in self.context.bookFiles:
      bookParser = sibin.core.BookParser(sibin.core.Book(bookFile))
      bookParser.parse()
      # cspec = self.initialize_cspec(bookParser.book)
      # Make the directories for this publican book
      (bookRoot, ext) = os.path.splitext(os.path.basename(bookFile))
      genbookdir = os.path.join(genbasedir, bookRoot)
      genlangdir = os.path.join(genbookdir, 'en-US')
      if not os.path.exists(genlangdir):
        os.makedirs(genlangdir)
      # Need to compile a list of all the image files referenced by
      # each book and copy all of those images files into the en-US/images sub-directory.
      # Also need to check each fileref attribute, to make sure it has the form
      # fileref="images/<imagefile>.<ext>" , modifying it if necessary.
      # 
      # Generate the set of recursively xincluded files, including the book file
      xincludeFileSet = set()
      xincludeFileSet.add(bookFile)
      xincludeFileSet |= self.parse_xincludes(bookFile)
      # print 'xincludeFileSet = ' + str(xincludeFileSet)
      # Get the set of image files for this book
      imageFileSet = set()
      for xmlfile in xincludeFileSet:
        parserForEntities = etree.XMLParser(resolve_entities=False)
        doc = etree.parse(xmlfile,parserForEntities)
        root = doc.getroot()
        imageFileSet |= self.getImageFileSet(root,xmlfile)
      # print 'imageFileSet for book [' + bookFile + '] is: ' + str(imageFileSet)
      # Copy image files to en-US/images sub-directory
      genimagesdir = os.path.join(genlangdir, 'images')
      if not os.path.exists(genimagesdir):
        os.makedirs(genimagesdir)
      for imageFile in imageFileSet:
        genimagefile = os.path.join(genimagesdir, os.path.basename(imageFile) )
        shutil.copyfile(imageFile, genimagefile)
        # ToDo: Really ought to disambiguate file names in case
        # where two base file names are identical
      transformedBook = self.context.transformer.dcbk2publican(bookParser.root, bookFile)
      # Generate the main publican book file
      genbookfile = os.path.join(genlangdir, bookRoot + '.xml')
      self.save_doc_to_xml_file(transformedBook, genbookfile, bookRoot + '.ent')
      # Copy the entities file
      genentitiesfile = os.path.join(genlangdir, bookRoot + '.ent')
      shutil.copyfile(self.context.bookEntitiesFile, genentitiesfile)
        
      



# MAIN CODE - PROGRAM STARTS HERE!
# --------------------------------
#
# Basic initialization
if not os.path.exists('sibin.cfg'):
  print 'WARN: No sibin.cfg file found in this directory.'
  sys.exit()
context = sibin.core.SibinContext()
context.initializeFromFile('sibin.cfg')
context.transformer = sibin.xml.XMLTransformer(context)
tasks = BasicTasks(context)

# Create the top-level parser
parser = argparse.ArgumentParser(prog='sibin')
subparsers = parser.add_subparsers()

# Create the sub-parser for the 'gen' command
gen_parser = subparsers.add_parser('gen', help='Generate Publican books')
gen_parser.set_defaults(func=tasks.generate_publican)

# Now, parse the args and call the relevant sub-command
args = parser.parse_args()
args.func(args)
