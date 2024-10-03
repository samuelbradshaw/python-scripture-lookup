# Python standard libraries
import sys
import re
import unicodedata

# Internal imports
from . import data, numbers


class Reference:
  def __init__(self, lang = 'en', publication_slug = None, book_slug = None, chapter = None, verse_groups = [], context_verse_groups = []):
    self.lang = lang
    self.publication_slug = publication_slug
    self.book_slug = book_slug
    self.chapter = chapter
    self.verse_groups = verse_groups
    self.context_verse_groups = context_verse_groups
  
  # Get a localized label (e.g. Old Testament, Genesis 1, Helaman 5:12, etc.)
  def label(self, skip_book_name = False, abbreviated = False):
    translated_names = data.scriptures['languages'][self.lang]['translatedNames']
    english_translated_names = data.scriptures['languages']['en']['translatedNames']
    
    if self.publication_slug and not self.book_slug:
      publication_name = translated_names.get(self.publication_slug, {}).get('name') or english_translated_names.get(self.publication_slug, {}).get('name')
      if abbreviated:
        publication_name = translated_names.get(self.publication_slug, {}).get('abbrev') or publication_name
      return publication_name
    
    label = ''
    book_slug = self.book_slug
    if not skip_book_name:
      if book_slug == 'psalms':
        book_slug = 'psalm'
      elif book_slug == 'sections':
        book_slug = 'doctrine-and-covenants'
      elif book_slug == 'official-declarations':
        book_slug = 'official-declaration'
      elif book_slug == 'facsimiles':
        book_slug = 'facsimile'
      elif book_slug == 'jst-psalms':
        book_slug = 'jst-psalm'
      
      book_name = translated_names.get(book_slug, {}).get('name') or english_translated_names.get(book_slug, {}).get('name') or ''
      if abbreviated:
        book_name = translated_names.get(book_slug, {}).get('abbrev') or book_name
      label += book_name
    
    if self.chapter:
      punctuation = data.scriptures['languages'][self.lang]['punctuation']
      numerals = data.scriptures['languages'][self.lang]['numerals']
      if not skip_book_name:
        label += punctuation['bookChapterSeparator']
      
      # Get localized chapter name
      chapter_name = (
        translated_names.get(self.chapter, {}).get('name') or
        english_translated_names.get(self.chapter, {}).get('name') or
        numbers.get_formatted_number(self.chapter, target_lang = self.lang, target_custom_numerals = numerals) or
        punctuation['verseRangeSeparator'].join([numbers.get_formatted_number(ch, target_lang = self.lang, target_custom_numerals = numerals) for ch in re.split(verse_range_separators_pattern, self.chapter)]) or
        self.chapter
      )
      if abbreviated:
        chapter_name = translated_names.get(self.chapter, {}).get('abbrev') or chapter_name
      label += chapter_name
      
      # Get localized verses
      if self.verse_groups:
        label += punctuation['chapterVerseSeparator']
        label += convert_verse_groups_to_string(self.verse_groups, punctuation['verseRangeSeparator'], punctuation['verseGroupSeparator'], numerals, lang = self.lang)
        if self.context_verse_groups:
          label += punctuation['openingParenthesis'] + convert_verse_groups_to_string(self.context_verse_groups, punctuation['verseRangeSeparator'], punctuation['verseGroupSeparator'], numerals, lang = self.lang) + punctuation['closingParenthesis']
    
    return label
  
  # Get the Church URI (e.g. /scriptures/ot, /scriptures/bofm/1-ne/3.7)
  def church_uri(self, use_query_parameters = False):
    if self.publication_slug and not self.book_slug:
      uri = data.scriptures['structure'].get(self.publication_slug, {}).get('churchUri')
      return uri
    
    uri = ''
    for publication_data in data.scriptures['structure'].values():
      for slug, book_data in publication_data['books'].items():
        if slug == self.book_slug:
          uri += book_data['churchUri']
          break
    
    if uri and self.chapter:
      chapter = str(self.chapter)
      if re.match(rf'\d+{verse_range_separators_pattern}\d+', chapter):
        # Chapter range – only use the first chapter
        chapter = re.split(verse_range_separators_pattern, chapter)[0]
      uri += '/' + str(chapter)
      if self.verse_groups:
        if use_query_parameters:
          uri += '?id=' + convert_verse_groups_to_string(self.verse_groups, '-', ',', verse_number_prefix = 'p')
          if self.context_verse_groups:
            uri += '&context=' + convert_verse_groups_to_string(self.context_verse_groups, '-', ',', verse_number_prefix = 'p')
        else:
          uri += '.' + convert_verse_groups_to_string(self.verse_groups, '-', ',')
          if self.context_verse_groups:
            uri += '(' + convert_verse_groups_to_string(self.context_verse_groups, '-', ',') + ')'
    
    return uri
  
  # Get the Church website URL (e.g. https://www.churchofjesuschrist.org/study/scriptures/bofm/1-ne/3?id=p7&lang=eng#p7)
  # TODO: Add validation based on online availability in the given language
  def church_url(self, skip_lang = False, skip_fragment = False):
    url = 'https://www.churchofjesuschrist.org/study'
    url += self.church_uri(use_query_parameters = True)
    if not skip_lang:
      church_lang = data.languages['languages'][self.lang]['churchLang']
      url += f'&lang={church_lang}' if '?' in url else f'?lang={church_lang}'
    if self.verse_groups and not skip_fragment:
      url += '#p' + str(self.verse_groups[0][0])
    return url
  
  # Get an HTML link to the Church website
  def church_link(self, link_class = None, link_target = None, skip_book_name = False, abbreviated = False, skip_lang = False, skip_fragment = False):
    additional_attributes = ''
    if link_class:
      additional_attributes += f' class="{link_class}"'
    if link_target:
      additional_attributes += f' target="{link_target}"'
    label = self.label(skip_book_name = skip_book_name, abbreviated = abbreviated)
    url = self.church_url(skip_lang = skip_lang, skip_fragment = skip_fragment)
    return f'<a href="{url}"{additional_attributes}>{label}</a>'
  
  def __str__(self):
    return label(self)


reference_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['referenceSeparator']] + [re.escape(';'), re.escape('\n')])
chapter_verse_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['chapterVerseSeparator']] + [re.escape(':')])
verse_group_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['verseGroupSeparator']] + [re.escape(',')])
verse_range_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['verseRangeSeparator']] + [re.escape('-'), re.escape('–'), re.escape('〜')])
opening_parenthesis_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['openingParenthesis']] + [re.escape('(')])
closing_parenthesis_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['closingParenthesis']] + [re.escape(')')])


# Normalize text by removing anything that's not a letter or number, and converting to lowercase. This allows for a fuzzy comparison between input text and a known list of values.
def normalizeForCompare(text):
  decomposed_text = unicodedata.normalize('NFKD', text)
  normalized_text = ''.join([c for c in decomposed_text if unicodedata.category(c)[0] in ['L', 'N']]).lower()
  return normalized_text


# Parse verses into verse groups
# Example: '1-2,5-7' –> [[1, 2], [5, 6, 7]]
def parse_verses_string(verses_string):
  verses_string = (verses_string or '').replace('p', '').strip()
  if not verses_string:
    return None
  
  unique_verses = set()
  for verse_group_string in re.split(verse_group_separators_pattern, verses_string):
    verse_strings = re.split(verse_range_separators_pattern, verse_group_string)
    lower_int = numbers.convert_number_to_int(verse_strings[0])
    upper_int = numbers.convert_number_to_int(verse_strings[-1])
    unique_verses.update(range(lower_int, upper_int + 1))
  
  verse_groups = []
  verses = sorted(unique_verses)
  previous_verse = -1
  for verse in verses:
    if verse == previous_verse + 1:
      verse_groups[-1].append(verse)
    else:
      verse_groups.append([verse])
    previous_verse = verse
  
  return verse_groups


# Format verse groups to a localized string
# Example: [[1, 2], [5, 6, 7]] –> '1-2,5-7'
def convert_verse_groups_to_string(verse_groups, verse_range_separator, verse_group_separator, numerals = [], lang = 'en', verse_number_prefix = ''):
  verse_ranges = []
  for verse_group in verse_groups:
    if verse_group[0] == verse_group[-1]:
      verse_range = verse_number_prefix + numbers.get_formatted_number(verse_group[0], target_lang = lang, target_custom_numerals = numerals)
    else:
      verse_range = verse_number_prefix + numbers.get_formatted_number(verse_group[0], target_lang = lang, target_custom_numerals = numerals) + verse_range_separator + verse_number_prefix + numbers.get_formatted_number(verse_group[-1], target_lang = lang, target_custom_numerals = numerals)
    verse_ranges.append(verse_range)
  return verse_group_separator.join(verse_ranges)


# Parse one or more scripture references, URIs, URLs, or slugs
def parse_references_string(input_string, lang = 'en'):
  lang = data.get_bcp47(lang)
  
  input_list = re.split(reference_separators_pattern, input_string)
  references = []
  
  previous_book_slug = None
  for input_string in input_list:
    input_string = input_string.strip()
    
    verses_string = None
    context_verses_string = None
    chapter_string = None
    book_string = None
    
    if '/scriptures/' in input_string:
      # Church URI or URL
      # Example: /scriptures/ot
      # Example: /scriptures/ot/gen
      # Example: /scriptures/ot/gen/1
      # Example: /scriptures/ot/gen/1.1-3
      # Example: gospellibrary://content/scriptures/ot/gen/3.1-3
      # Example: http://lds.org/scriptures/ot/gen/3.1-3?lang=eng
      # Example: https://www.churchofjesuschrist.org/study/scriptures/ot/gen/3?id=p1-p3&lang=eng#p1
      
      unparsed = '/scriptures/' + input_string.split('/scriptures/')[1]
      query_string = None
      if '?' in unparsed:
        unparsed, query_string = unparsed.split('?')
      
      # Get verses string
      if '.' in unparsed:
        unparsed, verses_string = unparsed.split('.')
        if '(' in verses_string:
          verses_string, context_verses_string = verses_string.replace(')', '').split('(')
      elif query_string:
        if 'id=' in query_string:
          verses_string = query_string.split('id=')[1].split('&')[0]
          if 'context=' in query_string:
            context_verses_string = query_string.split('context=')[1].split('&')[0]
        elif '#' in query_string:
          verses_string = query_string.split('#')[1]
      
      # Get chapter string and book string
      book_string = unparsed
      if book_string.count('/') > 3:
        book_string, chapter_string = book_string.rsplit('/', 1)
      
    else:
      # Scripture reference or slug
      # Examples: Old Testament; 1 Nephi; Matthew 1; Helaman 5:12; words-of-mormon
      
      # Get verses string
      unparsed, verses_string = (re.split(chapter_verse_separators_pattern, input_string) + [''])[:2]
      verses_string, context_verses_string = (re.split(opening_parenthesis_pattern, re.sub(closing_parenthesis_pattern, '', verses_string)) + [''])[:2]
      
      # Get chapter string and book string
      book_string = unparsed
      chapter_match = re.match(rf'^(?:.*[^\d{verse_range_separators_pattern}])?([\d{verse_range_separators_pattern}]*)$', book_string)
      if chapter_match:
        chapter_string = chapter_match.group(1)
        book_string = book_string.removesuffix(chapter_string).strip()
    
    verse_groups = parse_verses_string(verses_string)
    context_verse_groups = parse_verses_string(context_verses_string)
    chapter = numbers.convert_number_to_int(chapter_string)
    book_slug = None
    skip_book_name = False
    if book_string:
      book_slug = data.scriptures['mapToSlug'].get(book_string, None)
      if not book_slug:
        for key, value in data.scriptures['mapToSlug'].items():
          if normalizeForCompare(book_string) == normalizeForCompare(key):
            book_slug = value
            break
      if book_slug == previous_book_slug:
        skip_book_name = True
      previous_book_slug = book_slug
    else:
      book_slug = previous_book_slug
      skip_book_name = True
    
    publication_slug = None
    if book_slug in data.scriptures['structure'].keys():
      publication_slug = book_slug
      book_slug = None
    
    reference = Reference(lang = lang, publication_slug = publication_slug, book_slug = book_slug, chapter = chapter, verse_groups = verse_groups, context_verse_groups = context_verse_groups)
    references.append(reference)
    
  return references



def get_label(input_string, lang = 'en', separator = '\n', skip_book_name = False, abbreviated = False, **kwargs):
  references = parse_references_string(input_string, lang = lang)
  return separator.join([ref.label(skip_book_name = skip_book_name, abbreviated = abbreviated) for ref in references])

def get_church_uri(input_string, separator = '\n', use_query_parameters = False, **kwargs):
  references = parse_references_string(input_string)
  return separator.join([ref.church_uri(use_query_parameters = use_query_parameters) for ref in references])

def get_church_url(input_string, lang = 'en', separator = '\n', skip_lang = False, skip_fragment = False, **kwargs):
  references = parse_references_string(input_string, lang = lang)
  return separator.join([ref.church_url(skip_lang = skip_lang, skip_fragment = skip_fragment) for ref in references])

def get_church_link(input_string, lang = 'en', separator = '\n', link_class = None, link_target = None, skip_book_name = False, abbreviated = False, skip_lang = False, skip_fragment = False, **kwargs):
  references = parse_references_string(input_string, lang = lang)
  return separator.join([ref.church_link(link_class = link_class, link_target = link_target, skip_book_name = skip_book_name, abbreviated = abbreviated, skip_lang = skip_lang, skip_fragment = skip_fragment) for ref in references])
  
def get_langs(**kwargs):
  return data.scriptures['languages'].keys()

def get_punctuation(lang = 'en', **kwargs):
  return data.scriptures['languages'][lang]['punctuation']

def get_numerals(lang = 'en', **kwargs):
  return data.scriptures['languages'][lang]['numerals']
