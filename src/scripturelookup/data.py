# Python standard libraries
import os
import sys
import json
import time
import re
import unicodedata

# Third-party libraries
import requests
from bs4 import BeautifulSoup


data_directory = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
os.makedirs(data_directory, exist_ok = True)

# Download JSON data
def download_data(filename, filepath):
  request_url = f'https://cdn.jsdelivr.net/gh/samuelbradshaw/python-scripture-scraper@main/sample/{filename}'
  r = requests.get(request_url)
  r.encoding = 'utf-8'
  if r and r.status_code == 200:
    data = r.content
    with open(filepath, 'wb') as f:
      f.write(data)
  else:
    sys.exit('\nError: Couldn’t download JSON data:\n{request_url}\n')

# Load JSON data
def load_data(filename):
  filepath = os.path.join(data_directory, filename)
  if os.path.isfile(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
      return json.load(f)
  else:
    download_data(filename, filepath)
    return load_data(filename)

# Update JSON data
def update_data():
  for filename in ('metadata-languages.min.json', 'metadata-scriptures.min.json',):
    download_data(filename, os.path.join(data_directory, filename))

# Normalize text by removing anything that's not a letter or number, and converting to lowercase. This allows for a fuzzy comparison between input text and a known list of values.
def normalize_for_compare(text):
  decomposed_text = unicodedata.normalize('NFKD', text)
  normalized_text = ''.join([c for c in decomposed_text if unicodedata.category(c)[0] in ['L', 'N']]).lower()
  return normalized_text

# Words that can appear in a scripture reference, by language. Longer words should come before shorter words that they start with, so that (for example) "chapters" is matched before "chapter".
reference_words = {
  'en': {
    'list_conjunctions': ['and', '&'],
    'range_conjunctions': ['through', 'thru', 'to'],
    'verse_words': ['verses', 'verse', 'vv.', 'v.'],
    'chapter_words': ['chapters', 'chapter', 'chs.', 'ch.'],
  },
  'es': {
    'list_conjunctions': ['y', 'e'],
    'range_conjunctions': ['a', 'al'],
    'verse_words': ['versículos', 'versículo'],
    'chapter_words': ['capítulos', 'capítulo'],
  },
  'fr': {
    'list_conjunctions': ['et'],
    'range_conjunctions': ['à'],
    'verse_words': ['versets', 'verset'],
    'chapter_words': ['chapitres', 'chapitre'],
  },
  'pt': {
    'list_conjunctions': ['e'],
    'range_conjunctions': ['a'],
    'verse_words': ['versículos', 'versículo'],
    'chapter_words': ['capítulos', 'capítulo'],
  },
}
reference_word_keys = ('list_conjunctions', 'range_conjunctions', 'verse_words', 'chapter_words',)

# List conjunctions from every language, split into the ones written as a word ("and", "y", "et") and the ones written as a symbol ("&")
all_list_conjunctions = sorted({c for words in reference_words.values() for c in words['list_conjunctions']})
list_conjunction_words = [c for c in all_list_conjunctions if any(char.isalpha() for char in c)]
list_conjunction_symbols = [c for c in all_list_conjunctions if not any(char.isalpha() for char in c)]

# Get alternate spellings of a name where a spelled-out list conjunction is swapped for a symbol, or the other way around. Example: "Doctrine and Covenants" –> "Doctrine & Covenants"
def get_conjunction_aliases(name):
  aliases = set()
  for word in list_conjunction_words:
    for symbol in list_conjunction_symbols:
      if f' {word} ' in name:
        aliases.add(name.replace(f' {word} ', f' {symbol} '))
      if f' {symbol} ' in name:
        aliases.add(name.replace(f' {symbol} ', f' {word} '))
  return aliases


languages = load_data('metadata-languages.min.json')
scriptures = load_data('metadata-scriptures.min.json')

# Accept a symbol conjunction ("&") wherever a name spells the conjunction out, and vice versa. The words come from the language data below rather than being hard-coded, so this covers "Doctrine & Covenants" for "Doctrine and Covenants" and "Doctrina & Convenios" for "Doctrina y Convenios".
for key, value in list(scriptures['mapToSlug'].items()):
  for alias in get_conjunction_aliases(key):
    scriptures['mapToSlug'].setdefault(alias, value)

scriptures['mapToSlugNormalized'] = {}
for key, value in scriptures['mapToSlug'].items():
  normalized_key = normalize_for_compare(key)
  scriptures['mapToSlugNormalized'][normalized_key] = value


# Get regex patterns for the words that can appear in a scripture reference in a given language. Languages that aren't listed above return empty patterns.
reference_words_cache = {}
def get_reference_words(lang):
  if lang not in reference_words_cache:
    words_for_lang = reference_words.get(lang, {})
    reference_words_cache[lang] = {
      key: r'|'.join([re.escape(w) for w in words_for_lang.get(key, [])])
      for key in reference_word_keys
    }
  return reference_words_cache[lang]


# Get the BCP 47 language tag for a given language code
def get_bcp47(lang):
  if lang and 'Hant' in lang:
    lang = 'cmn-Hant'
  elif lang and 'Hans' in lang:
    lang = 'cmn-Hans'
  
  bcp47 = languages.get('mapToBcp47', {}).get(lang)
  if not bcp47:
    bcp47 = 'en'
    if lang:
      sys.stdout.write(f'Warning: Couldn’t find BCP 47 language tag for “{lang}” – falling back to “en” (English).\n')
  
  return bcp47


# Get the content for a given chapter verse from python-scripture-scraper or ChurchofJesusChrist.org
def request_content(publication_slug, book_slug, chapter, verse_groups, church_url, lang = 'en', source = 'python-scripture-scraper'):
  text_content = ''
  
  if not publication_slug and book_slug and chapter:
    return text_content
  
  verse_numbers = []
  if verse_groups:
    for verse_group in verse_groups:
      for verse_number in verse_group:
        verse_numbers.append(str(verse_number))
  
  if source == 'python-scripture-scraper':
    request_url = f'https://cdn.jsdelivr.net/gh/samuelbradshaw/python-scripture-scraper@main/sample/en-json/{publication_slug}/{book_slug}/{book_slug}-{chapter}.json'
    r = requests.get(request_url)
    r.encoding = 'utf-8'
    if r and r.status_code == 200:
      chapter_data = r.json()
      
      if verse_numbers:
        for paragraph in chapter_data['paragraphs']:
          if paragraph['type'] == 'verse' and paragraph['number'] in verse_numbers:
            text_content += paragraph['number'] + ' ' + paragraph['content'] + '\n\n'
      else:
        for paragraph in chapter_data['paragraphs']:
          text_content += (paragraph['number'] + ' ' if paragraph['number'] else '') + paragraph['content'] + '\n\n'
      
      text_content += '---------------------\n'
      text_content += 'Source: https://github.com/samuelbradshaw/python-scripture-scraper/tree/main/sample\n'
      text_content += 'Public domain.\n'
  
  elif source == 'ChurchofJesusChrist.org' and church_url:
    r = requests.get(church_url)
    r.encoding = 'utf-8'
    if r and r.status_code == 200:
      soup = BeautifulSoup(r.text, 'html.parser')
      paragraphs = soup.select('header [data-aid], .body-block [data-aid]')
      if verse_numbers:
        for paragraph in paragraphs:
          verse_number_span = paragraph.select_one('.verse-number')
          if verse_number_span and verse_number_span.text.strip() in verse_numbers:
            text_content += paragraph.text.strip() + '\n\n'
      else:
        for paragraph in paragraphs:
          text_content += paragraph.text.strip() + '\n\n'
        
      text_content += '---------------------\n'
      text_content += f'Source: {church_url}\n'
      text_content += 'Some content from this source may be subject to copyright.\n'
      
      # Pause for 1 second between requests to avoid overloading server
      time.sleep(1)
    
  return text_content

