# Scripture Lookup

Scripture Lookup is a Python library and command-line tool for looking up scripture verses or chapters. It can also convert scripture references between formats and languages. The tool is built around data from [Python Scripture Scraper](https://github.com/samuelbradshaw/python-scripture-scraper).


## Installation

1. Install [Python 3](https://gist.github.com/samuelbradshaw/932d48ef1eff07e288e25e4355dbce5d) and the [Homebrew](https://brew.sh) package manager (if you don’t already have them installed).
2. Install icu4c via Homebrew:
```
brew install icu4c
```
3. Install Scripture Lookup:
```
pip install scripturelookup
```


## Command-line usage

Pattern:
```
scripturelookup [command] [input] [options]
```

Examples:
```
% scripturelookup get_content "john 3:16" --lang "en"
16 ¶ For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.

% scripturelookup get_label "니파이전서 3:7" --lang "fr" --abbreviated
1 Né 3:7

% scripturelookup get_church_url "helaman 5:12"
https://www.churchofjesuschrist.org/study/scriptures/bofm/hel/5?id=p12&lang=eng#p12

% scripturelookup get_label "/scriptures/nt/1-jn/3.2-3" --lang "cmn-Hant"
約翰一書3：2-3

% scripturelookup get_church_url "/scriptures/ot" --lang "es"
https://www.churchofjesuschrist.org/study/scriptures/ot?lang=spa
```


## Python usage

Examples:
```
from scripturelookup import lookup

lookup.get_content('john 3:16', lang = 'en')
# 16 ¶ For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.

lookup.get_label('니파이전서 3:7', lang = 'fr', abbreviated = True)
# 1 Né 3:7

lookup.get_church_url('helaman 5:12')
# https://www.churchofjesuschrist.org/study/scriptures/bofm/hel/5?id=p12&lang=eng#p12

lookup.get_label('/scriptures/nt/1-jn/3.2-3', lang = 'cmn-Hant')
# 約翰一書3：2-3

lookup.get_church_url('/scriptures/ot', lang = 'es')
# https://www.churchofjesuschrist.org/study/scriptures/ot?lang=spa
```


## Commands, inputs, and options

### Commands

- **get_content** – Get chapter or verse content.
- **get_label** – Get a scripture reference label (i.e. "John 3:16").
- **get_church_uri** – Get a Gospel Library URI (i.e. "/scriptures/bofm/hel/5.12").
- **get_church_url** – Get a Gospel Library URL.
- **get_church_link** – Get an HTML link to Gospel Library.
- **get_reference_objects** – Get a list of references as objects.
- **get_reference_attributes** – Get a list of references as dictionaries.
- **sort_references** – Sort a list of references by label or in traditional book order.

### Inputs

Any of the following input types are supported. You can also provide several inputs at once as a list (separated by semicolons or line-breaks).

- Chapter or verse references, in any supported language. Examples:
  - John 3:16
  - Enos 1:13, 15–18
  - Psalm 23
  - Gen. 1:3 (3–4)
  - D&C 20:23; 76:41
- Scripture publication or book names. Examples:
  - Old Testament
  - Book of Mormon
  - 1 Corinthians
  - Psalms
- Gospel Library URIs (starting with `/scriptures`). Examples:
  - /scriptures/ot/gen
  - /scriptures/nt/matt/1
  - /scriptures/nt/john/3.16
  - /scriptures/bofm/enos/1.13,15-18
  - /scriptures/pgp
- Gospel Library URLs (old or new). Examples:
  - https://www.churchofjesuschrist.org/study/scriptures/bofm/hel/5?id=p12&lang=eng#p12
  - https://www.churchofjesuschrist.org/study/scriptures/ot?lang=eng
  - http://lds.org/scriptures/bofm/1-ne/3.7?lang=eng
  - [gospellibrary://content/scriptures/nt/john/3.16?lang=eng#16](https://www.churchofjesuschrist.org/study/scriptures/nt/john/3?id=p16&lang=eng#p16)

### Options

Several options are available. Some are only applicable to certain commands.

- **lang** (optional) – Output language. BCP 47 language codes and Gospel Library language codes are supported. Default: 'en'.
- **separator** (optional) – String separator between outputs when a list of references is requested. Default: '\n'.
- **sort_by** (optional) – Method for sorting references. Default: 'none'. Supported values: 'none', 'traditional', or 'label'.
- **source** (optional) – Content source. Default: 'python-scripture-scraper'. Supported values: 'python-scripture-scraper' or 'ChurchofJesusChrist.org'.
- **link_class** (optional) – String for the “class” attribute on links. Default: None.
- **link_target** (optional) – String for the “target” attribute on links. Default: None.
- **use_query_parameters** (optional) – Whether query parameters should be used on URIs. Default: False.
- **skip_lang** (optional) – Whether “lang” query parameters should be skipped on URLs. Default: False.
- **skip_fragment** (optional) – Whether fragments should be skipped on URLs. Default: False.
- **skip_book_name** (optional) – Whether book names should be skipped on labels. Default: False.
- **abbreviated** (optional) – Whether book abbrevions should be used on labels. Default: False.


## Acknowledgements
[Python Scripture Scraper](https://github.com/samuelbradshaw/python-scripture-scraper) – tool for scraping scripture content and metadata from ChurchofJesusChrist.org.
[geezify-python](https://github.com/logicalperson0/geezify-python) – tool for converting numbers to and from Geez numerals.
