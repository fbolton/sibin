'''
Created on July 3, 2014

@author: fbolton
'''

from lxml import etree
import sibin.core
import sibin.xml
import sibin.git
import os
import sys
import argparse
import shutil
import subprocess
import hashlib

class BasicTasks:
  def __init__(self,context):
    if not isinstance(context,sibin.core.SibinContext):
      raise Exception('BasicTasks must be initialized with a SibinContext argument')
    self.context = context
  
  def doc_to_xml_string(self,element,entityfile):
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
    return content
  
  def save_doc_to_xml_file(self,element,xmlfile,entityfile):
    f = open(xmlfile, 'w')
    f.write(self.doc_to_xml_string(element, entityfile))
    f.close()
    
  def restore_file_read(self):
    bookSet = set()
    filename = 'sibin.restore'
    if os.path.exists(filename):
      with open(filename, 'r') as f:
        for line in f:
          bookSet.add(line.strip() )
    return bookSet
  
  def restore_file_append(self, line):
    filename = 'sibin.restore'
    with open(filename, 'a') as f:
      f.write(line + '\n')
  
  def restore_file_delete(self):
    if os.path.exists('sibin.restore'):
      os.unlink('sibin.restore')
    
  def check_kerberos_ticket(self):
    kresponse = subprocess.call(['klist'])
    if kresponse != 0:
      # Non-zero exit code
      print 'WARNING: No Kerberos ticket detected. Please run kinit'
      sys.exit()
      
  def set_current_profile(self, new_profile=''):
    if new_profile:
      if new_profile in self.context.profiles:
        self.context.currentProfile = new_profile
      else:
        print 'Error: No such profile as ' + new_profile
        sys.exit()
    elif 'default' in self.context.profiles:
      self.context.currentProfile = 'default'
    else:
      self.context.currentProfile = self.context.profiles[0]
    print 'Current profile set to: ' + self.context.currentProfile
      
  def get_checksum(self,filename):
    parserForEntities = etree.XMLParser(resolve_entities=False)
    doc = etree.parse(filename,parserForEntities)
    doc.xinclude()
    stringifiedbook = etree.tostring(doc.getroot())
    sha = hashlib.sha1()
    sha.update(stringifiedbook)
    checksum = sha.hexdigest()
    del stringifiedbook
    del doc
    return checksum
  
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
  
  def modify_book_info_file(self,xmlfile,bookparser,bookfileroot):
    doc = etree.parse(xmlfile)
    root = doc.getroot()
    ns = { 'db' : 'http://docbook.org/ns/docbook'}
    for title in root.xpath('/db:info/db:title', namespaces = ns):
      title.text = bookparser.book.title
    for subtitle in root.xpath('/db:info/db:subtitle', namespaces = ns):
      subtitle.text = bookparser.book.subtitle
    for productname in root.xpath('/db:info/db:productname', namespaces = ns):
      productname.text = self.context.productname
    for productnumber in root.xpath('/db:info/db:productnumber', namespaces = ns):
      productnumber.text = self.context.productversion
    for abstract in root.xpath('/db:info/db:abstract/db:para', namespaces = ns):
      abstract.text = bookparser.book.abstract
    self.save_doc_to_xml_file(root, xmlfile, bookfileroot + '.ent')
    
  def modify_revhistory_file(self,xmlfile,bookparser,bookfileroot):
    doc = etree.parse(xmlfile)
    root = doc.getroot()
    root.set('{http://www.w3.org/XML/1998/namespace}id', bookfileroot + '-RevHistory')
    ns = { 'db' : 'http://docbook.org/ns/docbook'}
    for revision in root.xpath('/db:appendix/db:para/db:revhistory/db:revision', namespaces = ns):
      revnumber = revision.find('{http://docbook.org/ns/docbook}revnumber')
      revnumber.text = self.context.productversion + '-' + self.context.buildversion
      # Modify just the first revision element
      break
    self.save_doc_to_xml_file(root, xmlfile, bookfileroot + '.ent')

  def gen_dirs(self,bookFile):
    # Use the current profile name as the base directory name
    genbasedir = self.context.currentProfile
    # Make the directories for this publican book
    (bookRoot, ext) = os.path.splitext(os.path.basename(bookFile))
    genbookdir = os.path.join(genbasedir, bookRoot)
    genlangdir = os.path.join(genbookdir, 'en-US')
    if not os.path.exists(genlangdir):
      os.makedirs(genlangdir)
    return (genbookdir, genlangdir)

  def gen_l10n_dirs(self,bookFile):
    # Make the localization directories for this publican book
    bookDir = os.path.dirname(bookFile)
    genbookdir = os.path.join(bookDir, 'publican')
    genlangdir = os.path.join(genbookdir, 'en-US')
    if not os.path.exists(genlangdir):
      os.makedirs(genlangdir)
    return (genbookdir, genlangdir)

  def generate_publican(self,args):
    self.set_current_profile(args.profile)
    if args.modtime:
      self._generate_publican(int(args.modtime))
    elif (args.sincelastcommit):
      self._generate_publican(self.context.git.last_commit_time())
    else:
      # By default, consider all modifications since the Unix epoch
      self._generate_publican(0)
      
  def localize(self,args):
    self.set_current_profile(args.profile)
    self._generate_publican(0,localize=True)
    
  def _generate_publican(self,specifiedmodtime,localize=False):
    # Populate topic link data
    for bookFile in self.context.bookFiles:
      bookParser = sibin.core.BookParser(sibin.core.Book(bookFile))
      bookParser.parse()
      bookParser.appendLinkData(self.context.linkData)
      del bookParser
    booksGenerated = set()
    # Get the list of books we want to generate
    if (localize):
      booksToGenerate = self.context.localizedbooks
    else:
      booksToGenerate = self.context.bookFiles
    # Start generating publican output
    for bookFile in booksToGenerate:
      bookParser = sibin.core.BookParser(sibin.core.Book(bookFile))
      bookParser.parse()
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
      # Decide whether or not to publish this book,
      # depending on whether or not it was modified recently
      # (i.e. if date of last book modification > specifiedmodtime)
      # 
      generateThisBook = False
      for contentfile in (xincludeFileSet | imageFileSet):
        filemodtime = self.context.git.mod_time(contentfile)
        if filemodtime >= specifiedmodtime:
          generateThisBook = True
          booksGenerated.add(bookFile)
          break
      if generateThisBook:
        print 'Generating: ' + bookFile
        # Get the directories for this publican book
        if (localize):
          (genbookdir, genlangdir) = self.gen_l10n_dirs(bookFile)
        else:
          (genbookdir, genlangdir) = self.gen_dirs(bookFile)
        # Create an image file map, used to locate image files
        imageFileMap = {}
        for imageFile in imageFileSet:
          imageFileMap[os.path.basename(imageFile)] = imageFile
        self.context.imageFileMap = imageFileMap
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
        # Copy boilerplate images from the 'template/images' directory
        templatedir = self.context.gettemplate()
        templateimagesdir = os.path.join(templatedir,'images')
        for imageFile in os.listdir(templateimagesdir):
          shutil.copy(os.path.join(templateimagesdir,imageFile),genimagesdir)
        # Transform the main publican book file
        parserForEntities = etree.XMLParser(resolve_entities=False)
        doc = etree.parse(bookFile,parserForEntities)
        doc.xinclude()
        root = doc.getroot()
        if (localize):
          # Reparse document in order to resolve entities
          # Note: need to do it this way in order to resolve entities correctly
          root = etree.fromstring(self.doc_to_xml_string(doc.getroot(),'Library.ent'))
        transformedBook = self.context.transformer.dcbk2publican(root, bookFile, bookParser.book.id)
        publicanBookRoot = bookParser.book.title.replace(' ','_')
        # Write the main publican book file
        genbookfile = os.path.join(genlangdir, publicanBookRoot + '.xml')
        self.save_doc_to_xml_file(transformedBook, genbookfile, publicanBookRoot + '.ent')
        # Copy the entities file
        genentitiesfile = os.path.join(genlangdir, publicanBookRoot + '.ent')
        shutil.copyfile(self.context.bookEntitiesFile, genentitiesfile)
        # Copy the publican.cfg file and append additional settings
        genpublicancfg = os.path.join(genbookdir, 'publican.cfg')
        shutil.copyfile(os.path.join(templatedir,'publican.cfg'), genpublicancfg)
        with open(genpublicancfg, 'a') as filehandle:
          conditions = self.context.getconditions()
          if conditions:
            filehandle.write('condition: ' + conditions + '\n')
          if bookFile in self.context.sortorder:
            filehandle.write('sort_order: ' + self.context.sortorder[bookFile] + '\n')
          if bookFile in self.context.book2publicanprops:
            publicanprops = self.context.book2publicanprops[bookFile]
            for name in publicanprops:
              filehandle.write(name + ': ' + publicanprops[name] + '\n')
        # Copy the template files
        shutil.copyfile(os.path.join(templatedir,'Author_Group.xml'), os.path.join(genlangdir, 'Author_Group.xml'))
        shutil.copyfile(os.path.join(templatedir,'Preface.xml'), os.path.join(genlangdir, 'Preface.xml'))
        # Copy revision history file
        genrevhistory = os.path.join(genlangdir, 'Revision_History.xml')
        shutil.copyfile(os.path.join(templatedir,'Revision_History.xml'), genrevhistory)
        self.modify_revhistory_file(genrevhistory, bookParser, publicanBookRoot)
        # Copy book info file
        genbookinfo = os.path.join(genlangdir, 'Book_Info.xml')
        shutil.copyfile(os.path.join(templatedir,'Book_Info.xml'), genbookinfo)
        self.modify_book_info_file(genbookinfo, bookParser, publicanBookRoot)
        # Copy files from files/ subdirectory
        filesdir = os.path.normpath(os.path.join(os.path.dirname(bookFile),'files'))
        genfilesdir = os.path.join(genlangdir, 'files')
        if os.path.exists(filesdir):
          if not os.path.exists(genfilesdir):
            os.makedirs(genfilesdir)
          for filesFile in os.listdir(filesdir):
            shutil.copy(os.path.join(filesdir,filesFile),genfilesdir)
    return booksGenerated
      
  def build_publican(self,args):
    self.set_current_profile(args.profile)
    # First phase, generate the publican books
    if not args.nogen:
      if args.modtime:
        booksToBuild = self._generate_publican(int(args.modtime))
      elif (args.sincelastcommit):
        booksToBuild = self._generate_publican(self.context.git.last_commit_time())
      else:
        # By default, consider all modifications since the Unix epoch
        booksToBuild = self._generate_publican(0)
    else:
      # If 'nogen', assume that all of the books have already been generated
      booksToBuild = set(self.context.bookFiles)
    # Parse --format command-line argument
    formats = ['html', 'html-single']
    if args.formats:
      formatsMinusSpaces = args.formats.replace(' ','')
      if ',' in formatsMinusSpaces:
        formats = formatsMinusSpaces.split(',')
      else:
        formats = [ formatsMinusSpaces ]
    print 'Building the following formats: ' + str(formats)
    # Second phase, build the books
    self._build_publican(booksToBuild,formats)

  def _build_publican(self,booksToBuild,formats):
    # Check whether the previous build was aborted
    previouslyBuiltBooks = self.restore_file_read()
    if previouslyBuiltBooks:
      print 'WARNING: Restoring after aborted build. Will only build the books not built last time around.'
    # Start building publican books
    genbasedir = 'publican'
    langs = 'en-US'
    isBuildSuccess = True
    booksToBuild = booksToBuild - previouslyBuiltBooks
    for bookFile in booksToBuild:
      # Get the directory name for this publican book
      (bookRoot, ext) = os.path.splitext(os.path.basename(bookFile))
      genbookdir = os.path.join(genbasedir, bookRoot)
      if not os.path.exists(genbookdir):
        print 'WARNING: Generated book directory does not exist: ' + genbookdir
        isBuildSuccess = False
        continue
      # Invoke 'publican' to build the book
      cwd = os.getcwd()
      os.chdir(genbookdir)
      subprocess.check_call(['publican','build','--langs',langs,'--formats',','.join(formats)])
      os.chdir(cwd)
      self.restore_file_append(bookFile)
    # Clean up restore file
    if isBuildSuccess:
      self.restore_file_delete()

  def publish(self,args):
    self.check_kerberos_ticket()
    self.set_current_profile(args.profile)
    if not args.nogen:
      # First phase, generate publican books
      if args.modtime:
        booksToPublish = self._generate_publican(int(args.modtime))
      else:
        # By default, consider all modifications since the Unix epoch
        booksToPublish = self._generate_publican(0)
    # Second phase, publish books
    if args.all and not args.changed and not args.book and not args.modtime:
      for bookFile in self.context.bookFiles:
        self._publish_book(bookFile)
    elif args.changed and not args.book and not args.all and not args.modtime:
      isGitIndexChanged = False
      for bookFile in self.context.bookFiles:
        checksum = self.get_checksum(bookFile)
        checksumFile = bookFile + '.sha'
        # Try to retrieve a saved checksum value
        savedChecksum = ''
        if os.path.exists(checksumFile):
          with open(checksumFile, 'r') as f:
            savedChecksum = f.readline().strip()
        if savedChecksum != checksum:
          self._publish_book(bookFile,checksum)
          isGitIndexChanged = True
      # Commit the new checksums
      if isGitIndexChanged:
        self.context.git.commit()
    elif args.book and not args.all and not args.changed and not args.modtime:
      if os.path.exists(args.book):
        bookFile = args.book
        checksum = self.get_checksum(bookFile)
        checksumFile = bookFile + '.sha'
        # Try to retrieve a saved checksum value
        savedChecksum = ''
        if os.path.exists(checksumFile):
          with open(checksumFile, 'r') as f:
            savedChecksum = f.readline().strip()
        if savedChecksum:
          self._publish_book(bookFile,checksum)
          # Commit the new checksum
          if savedChecksum != checksum:
            self.context.git.commit()
        else:
          self._publish_book(bookFile)          
      else:
        print 'Error: no such book - ' + args.book
    elif args.modtime and not args.all and not args.changed and not args.book:
      for bookFile in booksToPublish:
        self._publish_book(bookFile)
    else:
      print 'Error: must specify exactly ONE of the options --all, --changed, or --book'
      

  def _publish_book(self,bookFile,newChecksum=''):
    print 'Publishing book: ' + bookFile
    bookParser = sibin.core.BookParser(sibin.core.Book(bookFile))
    bookParser.parse()
    # Get the directories for this publican book
    (genbookdir, genlangdir) = self.gen_dirs(bookFile)
    # rhpkg publican-build --lang en-US --message "commit message"
    cwd = os.getcwd()
    os.chdir(genbookdir)
    response = subprocess.call(['rhpkg', 'publican-build', '--nowait', '--lang', 'en-US', '--message','Build ' + self.context.buildversion])
    os.chdir(cwd)
    if response != 0:
      print 'Error: failed to build book: ' + bookFile
      # Don't be too fussy about returning early -- network problems sometimes cause benign errors
      # return
    # Append 'brew tag-pkg' command for this book
    buildID = self.context.productname.replace(' ','_') + '-' + bookParser.book.title.replace(' ','_') + '-' + self.context.productversion + '-web-en-US-' + self.context.productversion + '-' + self.context.buildversion + '.el6eng'
    line = 'brew tag-pkg docs-rhel-6 ' + buildID
    filename = 'brew-tag' + '.' + self.context.buildversion
    with open(filename, 'a') as f:
      f.write(line + '\n')
    # Append build ID to email content for this book
    line = buildID
    filename = 'email' + '.' + self.context.buildversion
    with open(filename, 'a') as f:
      f.write(line + '\n')
    # If upload is successful, save the new checksum and add to git
    if newChecksum:
      checksumFile = bookFile + '.sha'
      with open(checksumFile, 'w') as f:
        f.write(newChecksum)
      self.context.git.add(checksumFile)
      self.context.git.append_message('sibin: build ' + self.context.buildversion + ': saved checksum for ' + bookFile)
    
  def checksum(self,args):
    if args.save:
      self._checksum_save()
    elif args.listchanged:
      self._checksum_listchanged()
    else:
      self._checksum()
  
  def _checksum_save(self):
    isGitIndexChanged = False
    for bookFile in self.context.bookFiles:
      checksum = self.get_checksum(bookFile)
      print bookFile + '\t' + checksum
      checksumFile = bookFile + '.sha'
      with open(checksumFile, 'w') as f:
        f.write(checksum)
      self.context.git.add(checksumFile)
      isGitIndexChanged = True
    if isGitIndexChanged:
      self.context.git.commit('sibin: saved XML document checksums')

  def _checksum_listchanged(self):
    for bookFile in self.context.bookFiles:
      checksum = self.get_checksum(bookFile)
      checksumFile = bookFile + '.sha'
      # Try to retrieve a saved checksum value
      savedChecksum = ''
      if os.path.exists(checksumFile):
        with open(checksumFile, 'r') as f:
          savedChecksum = f.readline().strip()
      if savedChecksum != checksum:
        print bookFile + '\t' + checksum
      
  def _checksum(self):
    for bookFile in self.context.bookFiles:
      checksum = self.get_checksum(bookFile)
      print bookFile + '\t' + checksum
  
  def zip(self,args):
    self.set_current_profile(args.profile)
    print 'Creating a zip file:'
    zipbasedir = 'zip'
    shutil.rmtree(zipbasedir)
    # Iterate over all of the books
    for bookFile in self.context.bookFiles:
      bookParser = sibin.core.BookParser(sibin.core.Book(bookFile))
      bookParser.parse()
      # Get the directories for this publican book
      (genbookdir, genlangdir) = self.gen_dirs(bookFile)
      # Define the directories to copy from
      fromhtmldir = os.path.join(genbookdir,'tmp','en-US','html')
      fromhtmlsingledir = os.path.join(genbookdir,'tmp','en-US','html-single')
      # Define the directories to copy to
      tobookdir = os.path.join(zipbasedir, self.context.productname.replace(' ','_'), self.context.productversion, bookParser.book.title.replace(' ','_'))
      tohtmldir       = os.path.join(tobookdir,'html')
      tohtmlsingledir = os.path.join(tobookdir,'html-single')
      # Copy book formats, if the 'from' dir exists
      if os.path.exists(fromhtmldir):
        shutil.copytree(fromhtmldir, tohtmldir)
      if os.path.exists(fromhtmlsingledir):
        shutil.copytree(fromhtmlsingledir, tohtmlsingledir)
  
  def clean(self,args):
    print 'Cleaning sibin files'
    for genbasedir in self.context.profiles:
      if os.path.exists(genbasedir):
        shutil.rmtree(genbasedir)
      self.restore_file_delete()



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
context.git = sibin.git.GitUtility('.')
tasks = BasicTasks(context)

# Create the top-level parser
parser = argparse.ArgumentParser(prog='sibin')
subparsers = parser.add_subparsers()

# Create the sub-parser for the 'gen' command
gen_parser = subparsers.add_parser('gen', help='Generate Publican books')
gen_parser.add_argument('-m', '--modtime', help='Generate any books modified after the specified time')
gen_parser.add_argument('-s', '--sincelastcommit', help='Generate any books modified since the last commit', action='store_true')
gen_parser.add_argument('-p', '--profile', help='Specify the build profile')
gen_parser.set_defaults(func=tasks.generate_publican)

# Create the sub-parser for the 'build' command
build_parser = subparsers.add_parser('build', help='Build Publican books')
build_parser.add_argument('--nogen', help='Do not generate books, just build', action='store_true')
build_parser.add_argument('--formats', help='Specify output formats, as a comma-separated list')
build_parser.add_argument('-m', '--modtime', help='Build any books modified after the specified time')
build_parser.add_argument('-s', '--sincelastcommit', help='Build any books modified since the last commit', action='store_true')
build_parser.add_argument('-p', '--profile', help='Specify the build profile')
build_parser.set_defaults(func=tasks.build_publican)

# Create the sub-parser for the 'publish' command
publish_parser = subparsers.add_parser('publish', help='Publish Publican books')
publish_parser.add_argument('--nogen', help='Do not generate books, just publish', action='store_true')
publish_parser.add_argument('-a', '--all', help='Publish all books', action='store_true')
publish_parser.add_argument('-c', '--changed', help='Publish only changed books, as determined by comparing with stored checksums', action='store_true')
publish_parser.add_argument('-b', '--book', help='Specify a book to publish, as a pathname relative to the top directory of this project')
publish_parser.add_argument('-m', '--modtime', help='Publish any books modified after the specified time')
publish_parser.add_argument('-p', '--profile', help='Specify the build profile')
publish_parser.set_defaults(func=tasks.publish)

# Create the sub-parser for the 'localize' command
localize_parser = subparsers.add_parser('localize', help='Localize Publican books')
localize_parser.add_argument('-p', '--profile', help='Specify the build profile')
localize_parser.set_defaults(func=tasks.localize)

# Create the sub-parser for the 'checksum' command
checksum_parser = subparsers.add_parser('checksum', help='Calculate the current checksum for every book in the library')
checksum_parser.add_argument('-s', '--save', help='Save and commit the current checksum to <Book>.xml.sha for each book', action='store_true')
checksum_parser.add_argument('-l', '--listchanged', help='List the books that have changed since the last time the checksum was saved', action='store_true')
checksum_parser.set_defaults(func=tasks.checksum)

# Create the sub-parser for the 'clean' command
clean_parser = subparsers.add_parser('clean', help='Delete files generated by sibin')
clean_parser.set_defaults(func=tasks.clean)

# Create the sub-parser for the 'zip' command
zip_parser = subparsers.add_parser('zip', help='Create a Zip file of all the books that have just been built locally')
zip_parser.add_argument('-p', '--profile', help='Specify the build profile')
zip_parser.set_defaults(func=tasks.zip)

# Now, parse the args and call the relevant sub-command
args = parser.parse_args()
args.func(args)
