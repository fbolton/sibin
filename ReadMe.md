# Installing and Running Sibin

## Prerequisites

You need the following prerequisites to run Sibin:

* Python 2.7.  **NB:** Do not attempt to use Python 3, which has a different syntax.

* [Python library for parsing XML (lxml)](http://lxml.de/). Install it by entering:

        sudo yum install python-lxml

    **Note:** `lxml` depends on the C libraries, `libxml2` and `libxslt` (usually installed on most UNIX/LINUX systems).
    
* Publican. Install it by entering:

        sudo yum install publican
        
* _(Optionally)_ Publican brand. For example, to install the JBoss brand:

        sudo yum install publican-jboss
        

## Installation

Perform the following steps:

1. Unzip the distribution (or just copy the files to a convenient location, if you got the distribution by doing a `git clone`).

1. Add the `bin/sibin` script to your path. For example, from the project directory, you could enter:

        export PATH=`pwd`/bin:$PATH

That's all! You should now be able to invoke the script by entering the command, `sibin`.

## Setting Up a Project

Let's say you have a collection of DocBook books under a directory, `<librarydir>`. You can set up Sibin to start building the books in this library, as follows:

1. Create a new template directory, `<librarydir>/template` and then copy the template resources from `<sibininstall>/resources/template` to `<librarydir>/template`.

1. Edit the template files to customize them as required. In particular, you will almost certainly want to edit the `publican.cfg`. For example, you can edit the `brand:` property to select the relevant Publican brand.

1. Create a new `sibin.cfg` file under `<librarydir>` in the following format:

        <?xml version='1.0' encoding='UTF-8'?>
        <!DOCTYPE context [
        <!ENTITY % BOOK_ENTITIES SYSTEM "Library.ent">
        %BOOK_ENTITIES;
        ]>
        <context>
            <product name="&prodname;" version="&version;" build="&buildversion;"/>
            <books>
                <book file="camel/camel.xml" />
                <book file="lynx/lynx.xml" />
                <book file="lion/lion.xml" />
            </books>
            <entities file="Library.ent"/>
            <profiles>
                <profile name="default">
                    <host name="http://example.com/root/of/published/docs"/>
                    <template dir="template"/>
                    <conditions>
                      <condition match="betadocs"/>
                    </conditions>
                </profile>
            </profiles>
        </context>

Note the following points about this configuration file:

* If you include a `DOCTYPE` declaration as shown here, you can use XML entities in this file. In this case, you must remember to customize the location of the entities file, `Library.ent`.

* The `product` element is used to specify basic metadata for the product. Publican uses this metadata to construct package names for the books and sibin also uses it for resolving olinks. Note that the product name specified by the `name` attribute is allowed to contain spaces (these will be replaced by underscores in the package names).

* The `book` elements are used to specify the locations of all the DocBooks books in your library.

* The file specified by the `entities` element gets copied into all of the generated Publican books.

* Under the `profile` element, the `host` element is needed in order to resolve olinks (by default, these are mapped to the absolute URLs of the books on the specified Web site).

* Use the `template` element to specify the location of the Sibin `template` directory.


## Sibin Commands

Currently, there are two main sub-commands in Sibin. To generate Publican doc source for all of the books in the current library, `cd` into the top-level directory (the same directory as the `sibin.cfg` file) and enter the following command:

    sibin gen
    
The result will be a tree of new book directories in Publican format under the `publican` directory.

The second main command is for building books. You can generate and build the full set of Publican books by entering the following command:

    sibin build

By default, this command combines the generating and building steps. But if you have already generated the books, you can save time by limiting the command to just build the books, as follows:

    sibin build --nogen

Note that if the build process gets interrupted by an error, the next time you run `sibin build --nogen` it will try to pick up from where it left off (by reading the temporary `sibin.restore` file). This can save a lot of time when debugging large builds.

For more information, you can access the built-in command help by entering:

    sibin --help

Or for help on a specific sub-command, enter:

    sibin <sub-command> --help

