'''
Created on Dec 17, 2013

@author: fbolton
'''

import glob
import subprocess
import os.path
import os

class GitUtility:
  '''
  A utility class for accessing git source control
  '''

  def __init__(self,root):
    # Cumulative commit message
    self.commitMessage = ''
    # Make sure that the 'root' dir  is specified as an absolute path name
    if os.path.isabs(root):
      self.root = root
    else:
      self.root = os.path.normpath(os.path.join(os.getcwd(),root))

  def init(self):
    '''
    Creates a new (empty) git repository
    '''
    subprocess.check_call(['git', 'init'])
    
  def append_message(self,message):
    if self.commitMessage:
      self.commitMessage += '\n'
    self.commitMessage += message
  
  def add(self,filesOrDirs=[]):
    '''
    Add a list of files or directories to the git index,
    where the filesOrDirs argument is either a string or a list of strings
    '''
    if isinstance(filesOrDirs, str):
      filesOrDirs = [filesOrDirs]
    subprocess.check_call(['git', 'add'] + filesOrDirs)
  
  def add_globs(self,globList=[]):
    '''
    Add a list of glob patterns to the git index
    '''
    for pattern in globList:
      files = glob.glob(pattern)
      if files:
        self.add(files)
    
  def commit(self,comment=''):
    '''
    Commit all of the files in the git index, with the specified commit comment
    '''
    if not comment:
      comment = self.commitMessage
      self.commitMessage = ''
    subprocess.check_call(['git', 'commit', '-m', comment])
    # Consult the git log to get the SHA of that last commit
    commit = subprocess.check_output(['git', 'log', '-n', '1', '--pretty=format:%H'])
    return commit
  
  def diff_tree(self,commit1,commit2,deletedFileSet,modifiedFileSet,addedFileSet):
    '''
    Perform a diff-tree of commit1 and commit2, populating the following sets:
      deletedFileSet  - set of files deleted since the earlier commit
      modifiedFileSet - set of files modified since the earlier commit
      addedFileSet    - set of files added since the earlier commit
    '''
    diffstring = subprocess.check_output(['git', 'diff-tree', '-r', commit1, commit2])
    if not diffstring:  return
    for diffline in diffstring.split('\n'):
      if not diffline: continue
      (srcMode, dstMode, srcSHA1, dstSHA1, statusAndFile) = diffline.split(' ', 4)
      if statusAndFile[0] in ['D', 'M', 'A']:
        (status, filename) = statusAndFile.split('\t')
        if status == 'D':
          deletedFileSet.add(filename)
        elif status == 'M':
          modifiedFileSet.add(filename)
        elif status == 'A':
          addedFileSet.add(filename)
  
  def show(self,commit,filename):
    '''
    Return the contents of 'filename' as it was in the 'commit' revision.
    Where 'commit' is the SHA hash of the requested revision and
    'filename' is the relative filename of the requested file in the git repo.
    '''
    blobContents = subprocess.check_output(['git', 'show', commit + ':' + filename])
    return blobContents
  
  def mod_time(self,filename):
    '''
    Get the last modification time of 'filename', according to the commit log.
    Time is returned as UNIX time (number of seconds since 1970, I think).
    '''
    unixtime = subprocess.check_output(['git', 'log', '-1', '--format=%ct', filename])
    if not unixtime:
      # If unixtime is empty, it probably means that 'filename' is in a submodule,
      # so we switch to the subdirectory and retry the git log command.
      if filename.find(os.sep) >= 0:
        (subdir, subfilename) = filename.split(os.sep, 1)
        cwd = os.getcwd()
        os.chdir(subdir)
        unixtime = subprocess.check_output(['git', 'log', '-1', '--format=%ct', subfilename])
        os.chdir(cwd)
        # print 'In submodule ' + subdir + ': for filename = ' + subfilename + ', unixtime = ' + unixtime
      if not unixtime:
        # If all else fails, set 'unixtime' to zero
        unixtime = 0
    return int(unixtime)

  def last_commit_time(self):
    '''
    Get the time of the last commit, returned as UNIX time.
    '''
    unixtime = subprocess.check_output(['git', 'log', '-1', '--format=%ct'])
    return int(unixtime)
  