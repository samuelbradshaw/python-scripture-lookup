# Python standard libraries
import os
import sys
import json
import time
import re
import unicodedata

# Third-party libraries are imported where they're used, rather than here, so that commands that
# never reach the network don't pay for loading them. Together they add about 0.12 seconds to startup.


data_directory = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
os.makedirs(data_directory, exist_ok = True)

# Download JSON data
def download_data(filename, filepath):
  import requests

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

# Update JSON data. Returns the names of the files that were downloaded.
def update_data():
  filenames = ('metadata-languages.min.json', 'metadata-scriptures.min.json',)
  for filename in filenames:
    download_data(filename, os.path.join(data_directory, filename))
  return filenames

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

# Ordinal forms 1–13, for citing an article of faith by position ("First Article of Faith"), and – in the
# first four entries – for a numbered book cited as "First Nephi" or "1st Nephi". A form's position in the
# list is the number it stands for, so there are no numbers written out separately to keep in sync.
# Gendered forms appear where the noun takes them: Portuguese cites "Regras de Fé", so an article there is
# "Primeira regra de fé", while Spanish cites "Artículos de Fe" and so takes "Primer artículo de fe".
ordinal_words = {
  'en': [
    ('first', '1st',), ('second', '2nd',), ('third', '3rd',), ('fourth', '4th',),
    ('fifth', '5th',), ('sixth', '6th',), ('seventh', '7th',), ('eighth', '8th',),
    ('ninth', '9th',), ('tenth', '10th',), ('eleventh', '11th',), ('twelfth', '12th',),
    ('thirteenth', '13th',),
  ],
  'fr': [
    ('premier', 'première', '1er', '1re', '1ère',),
    ('deuxième', 'second', 'seconde', '2e', '2ème', '2d', '2de',),
    ('troisième', '3e', '3ème',), ('quatrième', '4e', '4ème',), ('cinquième', '5e', '5ème',),
    ('sixième', '6e', '6ème',), ('septième', '7e', '7ème',), ('huitième', '8e', '8ème',),
    ('neuvième', '9e', '9ème',), ('dixième', '10e', '10ème',), ('onzième', '11e', '11ème',),
    ('douzième', '12e', '12ème',), ('treizième', '13e', '13ème',),
  ],
  # Spanish has two accepted systems for 11 and 12 – the classical "undécimo" and the modern
  # "decimoprimero" – and each ordinal has a masculine, a feminine, and (for 1, 3 and their compounds) an
  # apocopated form used before a masculine noun. Every spelling is listed, so a reference resolves whichever
  # the writer reached for, and whether or not the gender agrees with the name being cited.
  'es': [
    ('primero', 'primer', 'primera', '1º', '1er', '1ª',),
    ('segundo', 'segunda', '2º', '2ª',),
    ('tercero', 'tercer', 'tercera', '3º', '3er', '3ª',),
    ('cuarto', 'cuarta', '4º', '4ª',),
    ('quinto', 'quinta', '5º', '5ª',),
    ('sexto', 'sexta', '6º', '6ª',),
    ('séptimo', 'séptima', '7º', '7ª',),
    ('octavo', 'octava', '8º', '8ª',),
    ('noveno', 'novena', '9º', '9ª',),
    ('décimo', 'décima', '10º', '10ª',),
    ('undécimo', 'undécima', 'decimoprimero', 'decimoprimera', 'decimoprimer', 'décimo primero', 'décima primera', 'décimo primer', '11º', '11ª',),
    ('duodécimo', 'duodécima', 'decimosegundo', 'decimosegunda', 'décimo segundo', 'décima segunda', '12º', '12ª',),
    ('decimotercero', 'decimotercera', 'decimotercer', 'décimo tercero', 'décima tercera', 'décimo tercer', '13º', '13ª',),
  ],
  # Portuguese cites "Regras de Fé", which is feminine, so the feminine forms are the ones that occur – but
  # the masculine are listed too, along with the classical "undécimo" and "duodécimo" alongside the ordinary
  # two-word spellings.
  'pt': [
    ('primeiro', 'primeira', '1º', '1ª',), ('segundo', 'segunda', '2º', '2ª',),
    ('terceiro', 'terceira', '3º', '3ª',), ('quarto', 'quarta', '4º', '4ª',),
    ('quinto', 'quinta', '5º', '5ª',), ('sexto', 'sexta', '6º', '6ª',),
    ('sétimo', 'sétima', '7º', '7ª',), ('oitavo', 'oitava', '8º', '8ª',),
    ('nono', 'nona', '9º', '9ª',), ('décimo', 'décima', '10º', '10ª',),
    ('décimo primeiro', 'décima primeira', 'undécimo', 'undécima', '11º', '11ª',),
    ('décimo segundo', 'décima segunda', 'duodécimo', 'duodécima', '12º', '12ª',),
    ('décimo terceiro', 'décima terceira', '13º', '13ª',),
  ],
}

# Roman numerals are typography rather than language, so they stand in for a book number in any language.
# Only 1–4 are needed, since no book is numbered higher.
roman_numeral_words = ['i', 'ii', 'iii', 'iv']

# The highest number any book name starts with ("4 Nephi"). patterns.leading_book_number is built from this.
highest_book_number = len(roman_numeral_words)

# Get a map of ordinal form to the number it stands for, for an article of faith cited by position
ordinal_forms_cache = {}
def get_ordinal_forms(lang):
  if lang not in ordinal_forms_cache:
    forms = {}
    for index, group in enumerate(ordinal_words.get(lang, [])):
      for form in group:
        forms[form.lower()] = index + 1
        # The ordinal indicators are hard to type on many keyboards, so "1º" is also accepted as "1o" and
        # "1ª" as "1a". They're derived rather than listed, so a language only spells out what's linguistic.
        plain_form = form.lower().replace('º', 'o').replace('ª', 'a')
        forms.setdefault(plain_form, index + 1)
    ordinal_forms_cache[lang] = forms
  return ordinal_forms_cache[lang]

# Get a map of number form to the number it stands for, for the prefix on a numbered book name. It's the
# ordinals above, stopping at the highest number any book carries, plus the roman numerals that work in
# every language.
book_number_forms_cache = {}
def get_book_number_forms(lang):
  if lang not in book_number_forms_cache:
    forms = {form: number for form, number in get_ordinal_forms(lang).items() if number <= highest_book_number}
    for index, form in enumerate(roman_numeral_words):
      forms.setdefault(form, index + 1)
    book_number_forms_cache[lang] = forms
  return book_number_forms_cache[lang]

# Get the maps above keyed for comparison, so the number a matched form stands for can be looked up however
# the form was spelled. The pattern built from these forms matches text the map has no key for: a character
# class matches "Decimo" where the map holds "décimo", and whitespace is matched loosely, so "décimo
# primero" can arrive with a non-breaking space between the words.
normalized_ordinal_forms_cache = {}
def get_normalized_ordinal_forms(lang):
  if lang not in normalized_ordinal_forms_cache:
    normalized_ordinal_forms_cache[lang] = {normalize_for_compare(form): number for form, number in get_ordinal_forms(lang).items()}
  return normalized_ordinal_forms_cache[lang]

normalized_book_number_forms_cache = {}
def get_normalized_book_number_forms(lang):
  if lang not in normalized_book_number_forms_cache:
    normalized_book_number_forms_cache[lang] = {normalize_for_compare(form): number for form, number in get_book_number_forms(lang).items()}
  return normalized_book_number_forms_cache[lang]

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

# Get a map of normalized names to book slugs, for comparing input that doesn't match a known name exactly. It's built the first time it's needed, rather than at import, since normalizing all ~10,000 names takes a moment and input that's already well-formed never needs it.
map_to_slug_normalized = None
def get_map_to_slug_normalized():
  global map_to_slug_normalized
  if map_to_slug_normalized is None:
    map_to_slug_normalized = {normalize_for_compare(key): value for key, value in scriptures['mapToSlug'].items()}
  return map_to_slug_normalized


# The shortest normalized name that's worth matching loosely. Below this, a single typo is most of the word – "Alma" is one edit away from far too much ordinary text.
minimum_fuzzy_name_length = 5

# Every spelling of a name with one letter taken out. Example: "alma" –> ["lma", "ama", "ala", "alm"]
# Digits are never dropped, so a number always has to match exactly – it's part of which book is meant, not
# something that can be mistyped into another book. Without that, "5th Nephi" would resolve to "4th Nephi",
# which is a real name one substitution away.
def get_single_character_deletions(key):
  return [key[:i] + key[i + 1:] for i in range(len(key)) if not key[i].isdigit()]

# Get a map of every single-character deletion of every known name to its book slug. Comparing deletions on
# both sides is what makes a one-character difference cheap to find: a missing letter, an extra letter, or a
# wrong letter all line up on some shared deletion, so a lookup costs one dict get per character instead of
# a comparison against all ~10,000 names. Names that two different slugs both claim are dropped, since an
# ambiguous match is worse than none. Built the first time a name fails to match exactly, since input that's
# spelled correctly never needs it.
map_to_slug_deletions = None
def get_map_to_slug_deletions():
  global map_to_slug_deletions
  if map_to_slug_deletions is None:
    map_to_slug_deletions = {}
    for key, value in scriptures['mapToSlug'].items():
      normalized_key = normalize_for_compare(key)
      if len(normalized_key) < minimum_fuzzy_name_length:
        continue
      for deletion in get_single_character_deletions(normalized_key):
        map_to_slug_deletions[deletion] = value if map_to_slug_deletions.get(deletion, value) == value else None
  return map_to_slug_deletions

# Look up a book slug for a normalized name that's off by one character. Diacritics are already handled by
# normalize_for_compare, so only letter-level slips reach this point. Like mapToSlug itself, the index covers
# every language's names, so a typo resolves no matter which language was asked for.
def fuzzy_map_to_slug(normalized_name):
  if len(normalized_name) < minimum_fuzzy_name_length:
    return None
  deletions = get_map_to_slug_deletions()

  # The known name has one character that the input is missing
  slug = deletions.get(normalized_name)
  if slug:
    return slug

  # The input has one character too many, or one character wrong
  for deletion in get_single_character_deletions(normalized_name):
    slug = deletions.get(deletion)
    if slug:
      return slug

  return None


# Look up the book slug for a name as it was written. The name is tried as-is, then normalized (which folds
# case, diacritics and punctuation), and finally – unless allow_loose_match is False – as a name that's off
# by one character. Every caller that resolves a name should come through here, so the three stages stay in
# one order.
def get_book_slug(book_string, allow_loose_match = True):
  slug = scriptures['mapToSlug'].get(book_string)
  if slug:
    return slug
  normalized_name = normalize_for_compare(book_string)
  return get_map_to_slug_normalized().get(normalized_name) or (fuzzy_map_to_slug(normalized_name) if allow_loose_match else None)


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
  import requests
  from bs4 import BeautifulSoup

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

