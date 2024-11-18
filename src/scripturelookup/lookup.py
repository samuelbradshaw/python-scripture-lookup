# Python standard libraries
import sys
import re
import unicodedata

# Third-party libraries
import icu

# Internal imports
from . import data, numbers


natural_sort_collators = {}

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
    
    if not self.book_slug:
      skip_book_name = True
    
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
      def format_chapter_range(chapter_string):
        groups = re.split(data.verse_group_separators_pattern, chapter_string)
        new_groups = []
        for group in groups:
          range_parts = re.split(data.verse_range_separators_pattern, group)
          new_range_parts = []
          for range_part in range_parts:
            chapter_verse_parts = re.split(data.chapter_verse_separators_pattern, range_part)
            new_chapter_verse_parts = []
            for num in chapter_verse_parts:
              new_chapter_verse_parts.append(numbers.get_formatted_number(num, target_lang = self.lang, target_custom_numerals = numerals))
            new_range_parts.append(punctuation['chapterVerseSeparator'].join(new_chapter_verse_parts))
          new_groups.append(punctuation['verseRangeSeparator'].join(new_range_parts))
        return punctuation['verseGroupSeparator'].join(new_groups)
      chapter_name = (
        translated_names.get(self.chapter, {}).get('name') or
        english_translated_names.get(self.chapter, {}).get('name') or
        numbers.get_formatted_number(self.chapter, target_lang = self.lang, target_custom_numerals = numerals) or
        format_chapter_range(self.chapter or '') or
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
      if re.match(rf'\d+{data.verse_range_separators_pattern}\d+', chapter):
        # Chapter range – only use the first chapter
        chapter = re.split(data.verse_range_separators_pattern, chapter)[0]
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
  def church_url(self, skip_lang = False, skip_fragment = False):
    url = 'https://www.churchofjesuschrist.org/study'
    url += self.church_uri(use_query_parameters = True)
    if not skip_lang:
      if not self.publication_slug or self.lang not in data.scriptures['summary']['churchAvailability'][self.publication_slug]:
        return ''
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
  
  # Get chapter or verse content
  def content(self, source):
    return data.request_content(self.publication_slug, self.book_slug, self.chapter, self.verse_groups, self.church_url(), lang = self.lang, source = source)
  
  # Get chapter or verse content
  def attributes(self):
    return self.__dict__
  
  def __str__(self):
    return self.label()
  
  def __lt__(self, other):
    # TODO: Provide better algorithm for sorting
    return 0 < 1


# Normalize text by removing anything that's not a letter or number, and converting to lowercase. This allows for a fuzzy comparison between input text and a known list of values.
def normalizeForCompare(text):
  decomposed_text = unicodedata.normalize('NFKD', text)
  normalized_text = ''.join([c for c in decomposed_text if unicodedata.category(c)[0] in ['L', 'N']]).lower()
  return normalized_text


# Parse verses into verse groups
# Example: '1-2,5-7,9' –> [[1, 2], [5, 6, 7], [9]]
def parse_verses_string(verses_string, lang = 'en'):
  verses_string = (verses_string or '').replace('p', '').strip()
  if not verses_string:
    return None
  
  unique_verses = set()
  all_verses_are_integers = True
  for verse_group_string in re.split(rf'(?:{data.verse_group_separators_pattern})+', verses_string):
    verse_strings = re.split(data.verse_range_separators_pattern, verse_group_string)
    lower_int = numbers.convert_number_to_int(verse_strings[0])
    upper_int = numbers.convert_number_to_int(verse_strings[-1])
    
    if isinstance(lower_int, int) and isinstance(upper_int, int):
      if lower_int > upper_int:
        # Handle abbreviated verse ranges, as in D&C 124:123–45
        reversed_lower_str = str(lower_int)[::-1] # 321
        reversed_upper_str = str(upper_int)[::-1] # 54
        digits_to_add = len(reversed_lower_str) - len(reversed_upper_str)
        if digits_to_add > 0:
          new_reversed_upper_str = reversed_upper_str + reversed_lower_str[-digits_to_add:]
          upper_int = int(new_reversed_upper_str[::-1])
      unique_verses.update(range(lower_int, upper_int + 1))
    else:
      all_verses_are_integers = False
      unique_verses.update([lower_int, upper_int])
  
  if all_verses_are_integers:
    verses = sorted(unique_verses)
  else:
    if lang not in natural_sort_collators:
      natural_sort_collators[lang] = icu.Collator.createInstance(icu.Locale(lang))
      natural_sort_collators[lang].setAttribute(icu.UCollAttribute.NUMERIC_COLLATION, icu.UCollAttributeValue.ON)
    verses = sorted([str(v) for v in unique_verses], key=natural_sort_collators[lang].getSortKey)
    verses = [numbers.convert_number_to_int(v) for v in verses]
  
  verse_groups = []
  previous_verse = -1
  for verse in verses:
    if isinstance(verse, int):
      if verse == previous_verse + 1:
        verse_groups[-1].append(verse)
      else:
        verse_groups.append([verse])
      previous_verse = verse
    else:
      verse_groups.append([verse])
      previous_verse = -1
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
def parse_references_string(input_string, lang = 'en', sort_by = None):
  lang = data.get_bcp47(lang)
  
  # Remove leading or trailing whitespace and punctuation
  punctuation_to_strip = ''.join(data.scriptures['summary']['punctuation']['referenceSeparator'] + data.scriptures['summary']['punctuation']['verseGroupSeparator'] + data.scriptures['summary']['punctuation']['verseRangeSeparator']) + '(;,.'
  input_string = input_string.strip().strip(punctuation_to_strip).rstrip(':').strip()
  
  # If language is English, replace roman numerals with numbers. Example: 'II Corinthians" –> "2 Corinthians"
  if lang == 'en':
    input_string = re.sub(r'\bi\s', '1', input_string, flags=re.IGNORECASE)
    input_string = re.sub(r'\bii\s', '2', input_string, flags=re.IGNORECASE)
    input_string = re.sub(r'\biii\s', '3', input_string, flags=re.IGNORECASE)
    input_string = re.sub(r'\biv\s', '4', input_string, flags=re.IGNORECASE)
  
  # Remove commas from book names so further normalization doesn't try to split it into two references. Example: "JST, Genesis 1" –> "JST Genesis 1"
  input_string = input_string.replace('\xa0', ' ')
  scripture_book_names = set()
  scripture_book_names_without_commas = []
  for volume_data in data.scriptures['structure'].values():
    for book_slug in volume_data['books'].keys():
      book_info = data.scriptures['languages'][lang]['translatedNames'].get(book_slug)
      if book_info:
        book_name = (book_info.get('name') or '').replace('\xa0', ' ')
        if book_name:
          scripture_book_names.add(book_name)
        book_abbrev = (book_info.get('abbrev') or '').replace('\xa0', ' ')
        if book_abbrev:
          scripture_book_names.add(book_abbrev)
  scripture_book_names = sorted(scripture_book_names, key=lambda x: (-len(x), x))
  for scripture_book_name in scripture_book_names:
    scripture_book_name_without_comma = re.sub(data.verse_group_separators_pattern, '', scripture_book_name)
    scripture_book_names_without_commas.append(scripture_book_name_without_comma)
    if scripture_book_name in input_string and re.search(data.verse_group_separators_pattern, scripture_book_name):
      input_string = input_string.replace(scripture_book_name, scripture_book_name_without_comma)
  
  # Normalize whitespace-separated references. Example: "Genesis 1:2 1 Nephi 3:7" –> "; Genesis 1:2 ; 1 Nephi 3:7"
  scripture_book_names_pattern = '|'.join([re.escape(sbn) for sbn in scripture_book_names_without_commas])
  input_string = re.sub(rf'(?:^|[^\-])\b({scripture_book_names_pattern})', r'; \1', input_string, flags=re.IGNORECASE)
  
  # Normalize lists and ranges. Example: "Genesis 12:1, 2, and 3; verses 1 and 4; John 2 through 7" –> "Genesis 12:1, 2,,3; verses 1,4; John 2–7"
  input_string = re.sub(r'\s+(?:and|y|e|et|&)\s+(\d+)', r',\1', input_string)
  input_string = re.sub(r'\s+(?:through|thru|to|al|a|à)\s+(\d+)', r'–\1', input_string)
  
  # Normalize verse sets. Example: "chapter 3 verse 7; vv. 3, 6" –> "chapter 3:7; :3, 6"
  input_string = re.sub(r'(?:^|\s)(?:verses|verse|vv\.|v\.|versículos|versículo|versets|verset)\s(\d+)', r':\1', input_string).replace('::', ':')
  
  # Normalize chapter sets. Example: "Genesis 1, 2, 4–5, Exodus 10; Alma 32" –> "Genesis 1; 2; 4–5; Exodus 10; Alma 32"
  if re.search(data.verse_group_separators_pattern, input_string) and not re.search(data.chapter_verse_separators_pattern, input_string):
    input_string = re.sub(rf'(?:{data.verse_group_separators_pattern})+', ';', input_string)
  
  # Normalize chapter:verse sets. Example: "Genesis 6:7a, 6:13a, 15; 1 Nephi 3:7 (twice), 8:21" –> "Genesis 6:7a; 6:13a, 15; 1 Nephi 3:7 (twice); 8:21"
  if re.search(data.chapter_verse_separators_pattern, input_string):
    references_list = re.split(data.reference_separators_pattern, input_string)
    new_references_list = []
    for reference in references_list:
      reference_parts = re.split(data.verse_group_separators_pattern, reference)
      reference_input_string = ''
      for part in reference_parts:
        if reference_input_string == '':
          reference_input_string += part
        elif re.search(data.chapter_verse_separators_pattern, part):
          reference_input_string += ';' + part
        else:
          reference_input_string += ',' + part
      new_references_list.append(reference_input_string)
    input_string = ';'.join(new_references_list)
  
  input_list = re.split(data.reference_separators_pattern, input_string)
  
  references = []
  previous_book_slug = None
  previous_chapter = None
  for input_string in input_list:
    # Remove leading or trailing whitespace and punctuation on the individual reference
    input_string = input_string.strip().strip(punctuation_to_strip).rstrip(':').strip()
    if not input_string:
      continue
    
    # Remove trailing text. Example: "1 John 3:2 2" –> "1 John 3:2"
    trailing_text_match = re.match(rf'^.*?\d((?:\:|{data.closing_parenthesis_pattern})?\s+[^{data.opening_parenthesis_pattern}|\s]+)$', input_string)
    if trailing_text_match:
      trailing_text_string = trailing_text_match.group(1)
      input_string = input_string.removesuffix(trailing_text_string)
    
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
      parts = re.split(data.chapter_verse_separators_pattern, input_string)
      if len(parts) == 2:
        # Regular chapter and verse found
        unparsed, verses_string = parts
      else:
        # Chapter only, or special case like 'Genesis 7:17–8:9' or 'Genesis 1–5'
        unparsed = input_string
        verses_string = ''
      verses_string, context_verses_string = (re.split(data.opening_parenthesis_pattern, re.sub(data.closing_parenthesis_pattern, '', verses_string)) + [''])[:2]
      
      # Get chapter string and book string
      book_string = unparsed
      chapter_match = re.match(rf'^.*?(\d(?:\d|\s|{data.chapter_verse_separators_pattern}|{data.verse_range_separators_pattern}|{data.verse_group_separators_pattern})*)$', book_string)
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
      # Special handling for Abraham facsimiles
      if book_slug == 'facsimiles' or (not book_slug and 'fac' in book_string.lower()):
        if previous_book_slug == 'abraham' and not previous_chapter:
          del references[-1]
        book_slug = 'abraham'
        if chapter:
          chapter = f'fac-{chapter}'
        elif verse_groups:
          chapter = f'fac-{verse_groups[0][0]}'
          verse_groups = None
      # Special handling for Psalms and similar cases
      elif book_slug == 'psalm':
        book_slug = 'psalms'
      elif book_slug == 'section':
        book_slug = 'sections'
      elif book_slug == 'jst-psalms':
        book_slug = 'jst-psalm'
      elif book_slug == 'official-declaration':
        book_slug = 'official-declarations'
    else:
      book_slug = previous_book_slug
    
    if book_slug == previous_book_slug:
      skip_book_name = True
      if previous_chapter and not chapter:
        chapter = previous_chapter
    
    publication_slug = None
    if book_slug in data.scriptures['structure'].keys():
      publication_slug = book_slug
      book_slug = None
    else:
      for pub_slug, pub_data in data.scriptures['structure'].items():
        if book_slug in pub_data['books'].keys():
          publication_slug = pub_slug
    
    reference = Reference(lang = lang, publication_slug = publication_slug, book_slug = book_slug, chapter = chapter, verse_groups = verse_groups, context_verse_groups = context_verse_groups)
    references.append(reference)
    
    previous_chapter = chapter
    previous_book_slug = book_slug
    
  return sort_references(references, lang = lang, sort_by = sort_by)


# Functions that can be called via Python or from the command line (see README.md for more information)

def get_content(input_string, lang = 'en', separator = '\n', source = 'python-scripture-scraper', **kwargs):
  references = parse_references_string(input_string, lang = lang)
  return separator.join([ref.content(source = source) for ref in references])

def get_label(input_string, lang = 'en', separator = '\n', sort_by = None, skip_book_name = False, abbreviated = False, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by)
  return separator.join([ref.label(skip_book_name = skip_book_name, abbreviated = abbreviated) for ref in references])

def get_church_uri(input_string, separator = '\n', sort_by = None, use_query_parameters = False, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by)
  return separator.join([ref.church_uri(use_query_parameters = use_query_parameters) for ref in references])

def get_church_url(input_string, lang = 'en', separator = '\n', sort_by = None, skip_lang = False, skip_fragment = False, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by)
  return separator.join([ref.church_url(skip_lang = skip_lang, skip_fragment = skip_fragment) for ref in references])

def get_church_link(input_string, lang = 'en', separator = '\n', sort_by = None, link_class = None, link_target = None, skip_book_name = False, abbreviated = False, skip_lang = False, skip_fragment = False, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by)
  return separator.join([ref.church_link(link_class = link_class, link_target = link_target, skip_book_name = skip_book_name, abbreviated = abbreviated, skip_lang = skip_lang, skip_fragment = skip_fragment) for ref in references])
  
def get_reference_objects(input_string, lang = 'en', sort_by = None, **kwargs):
  return parse_references_string(input_string, lang = lang, sort_by = sort_by)

def get_reference_attributes(input_string, lang = 'en', sort_by = None, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by)
  return [ref.attributes() for ref in references]

def get_langs(**kwargs):
  return data.scriptures['languages'].keys()

def get_punctuation(lang = 'en', **kwargs):
  return data.scriptures['languages'][lang]['punctuation']

def get_numerals(lang = 'en', **kwargs):
  return data.scriptures['languages'][lang]['numerals']

def sort_references(references, lang = 'en', sort_by = None):
  # Sort by book order or alphabetically by label
  if sort_by == 'traditional' or sort_by == 'label':
    reference_tuples = []
    book_slugs_by_book = []
    book_slugs_by_label = []
    chapters_by_book = {}
    for publication_slug, publication_info in data.scriptures['structure'].items():
      for book_slug, book_info in publication_info['books'].items():
        chapters_by_book[book_slug] = book_info['churchChapters']
        book_slugs_by_book.append(book_slug)
    
    if sort_by == 'label':
      bcp47 = lang
      if lang.endswith('Hant'):
        bcp47 = 'zh-Hant'
      elif lang.endswith('Hans'):
        bcp47 = 'zh-Hans'
      collation_index = icu.AlphabeticIndex(icu.Locale(bcp47 + '-u-ka-shifted')).addLabels(icu.Locale('en' + '-u-ka-shifted'))
      for book_slug in book_slugs_by_book:
        book_name = data.scriptures['languages'][lang]['translatedNames'].get(book_slug, {}).get('name') or book_slug
        collation_index.addRecord(book_name or '', book_slug)
      for (bucket_label, label_type) in collation_index:
        while collation_index.nextRecord():
          book_slugs_by_label.append(collation_index.recordData)
    
    for reference in references:
      book_position = 0
      chapter_position = 0
      verse_position = 0
      number_of_verses = 0
      if reference.book_slug and reference.book_slug in book_slugs_by_book:
        if sort_by == 'traditional':
          book_position = book_slugs_by_book.index(reference.book_slug) + 1
        elif sort_by == 'label':
          book_position = book_slugs_by_label.index(reference.book_slug) + 1
        
        if reference.chapter and reference.chapter in chapters_by_book[reference.book_slug]:
          chapter_position = (chapters_by_book[reference.book_slug].index(reference.chapter) + 1) if isinstance(reference.chapter, int) else 1000
          if reference.verse_groups:
            verse_position = reference.verse_groups[0][0] if isinstance(reference.verse_groups[0][0], int) else 1000
            number_of_verses = sum([len(vg) for vg in reference.verse_groups])
      
      reference_tuple = (book_position, chapter_position, verse_position, number_of_verses, reference)
      reference_tuples.append(reference_tuple)
    sorted_reference_tuples = sorted(reference_tuples)
    return [reference_tuple[4] for reference_tuple in sorted_reference_tuples]
  
  # Return original sort order
  else:
    return references