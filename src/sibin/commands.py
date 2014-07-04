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

  def generate_publican(self,args):
    genbasedir = 'publican'
    for bookFile in self.context.bookFiles:
      bookParser = sibin.core.BookParser(sibin.core.Book(bookFile))
      bookParser.parse()
      # cspec = self.initialize_cspec(bookParser.book)
      # Determine name of generated book file
      (bookRoot, ext) = os.path.splitext(os.path.basename(bookFile))
      genbookdir = os.path.join(genbasedir, bookRoot)
      genlangdir = os.path.join(genbookdir, 'en-US')
      if not os.path.exists(genlangdir):
        os.makedirs(genlangdir)
      genbookfile = os.path.join(genlangdir, bookRoot + '.xml')
      # Generate the main publican book file
      self.save_doc_to_xml_file(bookParser.root, genbookfile, bookRoot + '.ent')


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
