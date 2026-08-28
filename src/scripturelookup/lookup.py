# Python standard libraries
import sys
import re

# Third-party libraries
import icu

# Internal imports
from . import data, numbers, patterns

# Caching dicts
natural_sort_collators = {}
book_name_cache = {}
detection_pattern_cache = {}


# Get scripture book names and abbreviations for a language, sorted longest first so that (for example) "1 John" is recognized before "John"
def get_book_names(lang):
  if lang not in book_name_cache:
    scripture_book_names = set()
    for volume_data in data.scriptures['structure'].values():
      for book_slug in volume_data['books'].keys():
        book_info = data.scriptures['languages'][lang]['translatedNames'].get(book_slug)
        if book_info:
          book_name = patterns.whitespace.sub(' ', book_info.get('name') or '')
          if book_name:
            scripture_book_names.add(book_name)
          book_abbrev = patterns.whitespace.sub(' ', book_info.get('abbrev') or '')
          if book_abbrev:
            scripture_book_names.add(book_abbrev)
    scripture_book_names = sorted(scripture_book_names, key=lambda x: (-len(x), x))

    # Book names with commas removed, so further normalization doesn't try to split one book name into two references. Example: "JST, Genesis 1" –> "JST Genesis 1"
    scripture_book_names_without_commas = []
    scripture_book_names_with_commas = []
    for scripture_book_name in scripture_book_names:
      scripture_book_name_without_comma = patterns.verse_group_separators.sub('', scripture_book_name)
      scripture_book_names_without_commas.append(scripture_book_name_without_comma)
      if patterns.verse_group_separators.search(scripture_book_name):
        scripture_book_names_with_commas.append((scripture_book_name, scripture_book_name_without_comma,))

    names_pattern = r'|'.join([re.escape(sbn) for sbn in scripture_book_names_without_commas])
    book_name_cache[lang] = {
      'names_with_commas': scripture_book_names_with_commas,
      'separate_references_pattern': re.compile(rf'(?:^|[^\-])\b({names_pattern})', flags=re.IGNORECASE),
    }
  return book_name_cache[lang]


# Study helps aren't scripture references, and their abbreviations ("TG", "BD", "IT", "GS") are too short to tell apart from ordinary text
slugs_to_skip_when_detecting = ('topical-guide', 'bible-dictionary', 'index-to-the-triple-combination', 'guide-to-the-scriptures', 'joseph-smith-translation',)

# Build a regex alternation that matches anything that can start a scripture reference, allowing flexible whitespace and optional commas. Example: "JST, Genesis" –> "JST(?:,?)\sGenesis"
def build_book_names_pattern(lang):
  # Every translated name is included, not just the books in "structure". That picks up publication names ("Doctrine and Covenants"), alternate forms ("Psalm" alongside "Psalms"), and things like "Official Declaration" and "Facsimile", which can all start a reference.
  names = set()
  for slug, translated_name in data.scriptures['languages'][lang]['translatedNames'].items():
    if slug in slugs_to_skip_when_detecting:
      continue
    for key in ('name', 'abbrev',):
      # Whitespace inside the name doesn't need to be normalized here – it's all converted to "\s" below
      name = translated_name.get(key) or ''
      if name:
        names.add(name)
        names.update(data.get_conjunction_aliases(name))

  names = sorted(names, key=lambda x: (-len(x), x))
  alternatives = []
  for scripture_book_name in names:
    alternative = re.escape(scripture_book_name)
    alternative = re.sub(r'\\?\s', r'\\s', alternative)
    alternative = patterns.verse_group_separators.sub(r'(?:,?)', alternative)
    alternatives.append(alternative)
  return r'|'.join(alternatives)


# Get a compiled regex for detecting scripture references embedded in text
def get_detection_pattern(lang):
  if lang not in detection_pattern_cache:
    words = data.get_reference_words(lang)

    # Words that can be spelled out between two numbers, or between a book name and a number. Examples: "1, 2, and 3"; "Alma chapter 32 verse 21"
    inline_words = r'|'.join([w for w in (words['list_conjunctions'], words['range_conjunctions'], words['verse_words'], words['chapter_words'],) if w])
    leading_words = r'|'.join([w for w in (words['verse_words'], words['chapter_words'],) if w])

    books = build_book_names_pattern(lang)
    anchor = rf'(?P<book>{books})'
    if words['chapter_words']:
      anchor += rf'|(?P<chapter_word>{words["chapter_words"]})'
    anchor_continued = rf'{books}|{words["chapter_words"]}' if words['chapter_words'] else books

    # Separator between two numbers in a reference. A period is one of the possible chapter/verse separators, and it can't be followed by whitespace – without that restriction, "Alma 32. 5 people" would be read as "Alma 32:5". The other chapter/verse separators are unambiguous, so "Mosiah 28: 13" is fine.
    chapter_verse_separators_allowing_space = r'|'.join([s for s in patterns.chapter_verse_separators_pattern.split(r'|') if s != re.escape('.')])
    number_separator = rf'(?:{chapter_verse_separators_allowing_space})\s*|(?:{patterns.chapter_verse_separators_pattern})|\s*(?:{patterns.verse_group_separators_pattern}|{patterns.verse_range_separators_pattern})\s*'
    if inline_words:
      number_separator = rf'(?:{number_separator})(?:(?:{inline_words})\s+)?|\s+(?:{inline_words})\s+'

    # Chapter and verses, ending on a digit or a closing parenthesis so that trailing whitespace and punctuation are never included in the match
    leading_word = rf'(?:(?:{leading_words})\s+)?' if leading_words else ''
    # A number that starts a book name belongs to the next reference, not to this one's verse list. Without this, "Alma 5 and 2 Ne. 2:25" would run together as "Alma 5 and 2".
    not_the_next_book = rf'(?!(?:{books})\s*\d)'

    context = rf'(?:\s*(?:{patterns.opening_parenthesis_pattern})\s*\d+(?:(?:{number_separator})\d+)*\s*(?:{patterns.closing_parenthesis_pattern}))?'
    tail = rf'{leading_word}\d+(?:(?:{number_separator}){not_the_next_book}\d+)*{context}'

    # Additional references that continue the same run. A conjunction can follow the separator, as in "Genesis 11:29; 22:23; and 24:15".
    conjunction_after_separator = rf'(?:(?:{inline_words})\s+)?' if inline_words else ''
    continued = rf'(?:\s*(?:{patterns.reference_separators_pattern})\s*{conjunction_after_separator}(?:(?:{anchor_continued})\s*)?{tail})*'

    detection_pattern_cache[lang] = re.compile(rf'(?<![-\w])(?:{anchor})\s*{tail}{continued}', flags=re.IGNORECASE)
  return detection_pattern_cache[lang]


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
        groups = patterns.verse_group_separators.split(chapter_string)
        new_groups = []
        for group in groups:
          range_parts = patterns.verse_range_separators.split(group)
          new_range_parts = []
          for range_part in range_parts:
            chapter_verse_parts = patterns.chapter_verse_separators.split(range_part)
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
      if patterns.chapter_range.match(chapter):
        # Chapter range – only use the first chapter
        chapter = patterns.verse_range_separators.split(chapter)[0]
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


# Parse verses into verse groups
# Example: '1-2,5-7,9' –> [[1, 2], [5, 6, 7], [9]]
def parse_verses_string(verses_string, lang = 'en', range_split_limit = 1):
  verses_string = (verses_string or '').replace('p', '').strip()
  if not verses_string:
    return None
  
  unique_verses = set()
  all_verses_are_integers = True
  for verse_group_string in patterns.verse_group_separators_repeated.split(verses_string):
    verse_strings = patterns.verse_range_separators.split(verse_group_string)
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
  elif hasattr(icu, 'Collator'):
    # TODO: On Windows, getting the collator fails with "AttributeError: module 'icu' has no attribute 'Collator'"
    if lang not in natural_sort_collators:
      natural_sort_collators[lang] = icu.Collator.createInstance(icu.Locale(lang))
      natural_sort_collators[lang].setAttribute(icu.UCollAttribute.NUMERIC_COLLATION, icu.UCollAttributeValue.ON)
    verses = sorted([str(v) for v in unique_verses], key=natural_sort_collators[lang].getSortKey)
    verses = [numbers.convert_number_to_int(v) for v in verses]
  else:
    verses = sorted([str(v) for v in unique_verses])
  
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
  
  # Split ranges at range split limit. Examples:
  # [[2], [2, 3, 4], [2, 3]], limit 1 –> [[2], [2, 3, 4], [2, 3]]
  # [[2], [2, 3, 4], [2, 3]], limit 2 –> [[2], [2, 3, 4], [2], [3]]
  # [[2], [2, 3, 4], [2, 3]], limit 3 –> [[2], [2], [3], [4], [2], [3]]
  refined_verse_groups = []
  for group in verse_groups:
    if len(group) <= range_split_limit:
      refined_verse_groups.extend([v] for v in group)
    else:
      refined_verse_groups.append(group)
  
  return refined_verse_groups


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
# The script will run faster if skip_cleanup is True, but all scripture references or URIs will be expected to have consistent formatting
def parse_references_string(input_string, lang = 'en', sort_by = None, skip_cleanup = False, range_split_limit = 1):
  lang = data.get_bcp47(lang)
  
  # Remove leading or trailing whitespace and punctuation
  punctuation_to_strip = ''.join(data.scriptures['summary']['punctuation']['referenceSeparator'] + data.scriptures['summary']['punctuation']['verseGroupSeparator'] + data.scriptures['summary']['punctuation']['verseRangeSeparator']) + '(;,.'
  
  if not skip_cleanup:
    input_string = input_string.strip().strip(punctuation_to_strip).rstrip(':').strip()
    
    # If language is English, replace roman numerals with numbers. Example: 'II Corinthians" –> "2 Corinthians"
    if lang == 'en':
      for roman_numeral_pattern, arabic_numeral in patterns.roman_numerals:
        input_string = roman_numeral_pattern.sub(arabic_numeral, input_string)
    
    # Normalize whitespace so it matches the spaces in book names, but keep line breaks, since they separate one reference from the next
    input_string = patterns.whitespace_except_line_breaks.sub(' ', input_string)

    # Remove commas from book names so further normalization doesn't try to split it into two references. Example: "JST, Genesis 1" –> "JST Genesis 1"
    book_names = get_book_names(lang)
    for scripture_book_name, scripture_book_name_without_comma in book_names['names_with_commas']:
      if scripture_book_name in input_string:
        input_string = input_string.replace(scripture_book_name, scripture_book_name_without_comma)

    # Normalize whitespace-separated references. Example: "Genesis 1:2 1 Nephi 3:7" –> "; Genesis 1:2 ; 1 Nephi 3:7"
    input_string = book_names['separate_references_pattern'].sub(r'; \1', input_string)

    normalization_patterns = patterns.get_normalization_patterns(lang)

    # Normalize lists and ranges. Example: "Genesis 12:1, 2, and 3; verses 1 and 4; John 2 through 7" –> "Genesis 12:1, 2,,3; verses 1,4; John 2–7"
    if normalization_patterns['list_conjunctions']:
      input_string = normalization_patterns['list_conjunctions'].sub(r',\1', input_string)
    if normalization_patterns['range_conjunctions']:
      input_string = normalization_patterns['range_conjunctions'].sub(r'–\1', input_string)

    # Normalize verse sets. Example: "chapter 3 verse 7; vv. 3, 6" –> "chapter 3:7; :3, 6"
    if normalization_patterns['verse_words']:
      input_string = normalization_patterns['verse_words'].sub(r':\1', input_string).replace('::', ':')

    # Normalize chapter words. Example: "Alma chapter 32 verse 21" –> "Alma 32:21"
    if normalization_patterns['chapter_words']:
      input_string = normalization_patterns['chapter_words'].sub(r' \1', input_string)

    # Normalize chapter sets. Example: "Genesis 1, 2, 4–5, Exodus 10; Alma 32" –> "Genesis 1; 2; 4–5; Exodus 10; Alma 32"
    if patterns.verse_group_separators.search(input_string) and not patterns.chapter_verse_separators.search(input_string):
      input_string = patterns.verse_group_separators_repeated.sub(';', input_string)
    
    # Normalize chapter:verse sets. Example: "Genesis 6:7a, 6:13a, 15; 1 Nephi 3:7 (twice), 8:21" –> "Genesis 6:7a; 6:13a, 15; 1 Nephi 3:7 (twice); 8:21"
    if patterns.chapter_verse_separators.search(input_string):
      references_list = patterns.reference_separators.split(input_string)
      new_references_list = []
      for reference in references_list:
        reference_parts = patterns.verse_group_separators.split(reference)
        reference_input_string = ''
        for part in reference_parts:
          if reference_input_string == '':
            reference_input_string += part
          elif patterns.chapter_verse_separators.search(part):
            reference_input_string += ';' + part
          else:
            reference_input_string += ',' + part
        new_references_list.append(reference_input_string)
      input_string = ';'.join(new_references_list)
  
  input_list = patterns.reference_separators.split(input_string)
  
  references = []
  previous_book_slug = None
  previous_chapter = None
  for input_string in input_list:
    # Remove leading or trailing whitespace and punctuation on the individual reference
    input_string = input_string.strip().strip(punctuation_to_strip).rstrip(':').strip()
    if not input_string:
      continue
    
    if not skip_cleanup:
      # Remove trailing text. Example: "1 John 3:2 2" –> "1 John 3:2"
      trailing_text_match = patterns.trailing_text.match(input_string)
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
      
      # Get context verses from a trailing parenthetical, so it doesn't interfere with parsing the rest of the reference. Example: "Gen. 1:3 (3–4)"
      context_match = patterns.trailing_parenthetical.match(input_string)
      if context_match and patterns.numbers_and_separators.match(context_match.group(2)):
        input_string = context_match.group(1)
        context_verses_string = context_match.group(2)

      # Get verses string. The separator has to sit between two digits, so that the period in an abbreviation like "Gen." isn't mistaken for a chapter/verse separator.
      parts = patterns.chapter_verse_separator_between_digits.split(input_string)
      if len(parts) == 2:
        # Regular chapter and verse found
        unparsed, verses_string = parts
      else:
        # Chapter only, or special case like 'Genesis 7:17–8:9' or 'Genesis 1–5'
        unparsed = input_string
        verses_string = ''
      verses_string, remaining_context_verses_string = (patterns.opening_parenthesis.split(patterns.closing_parenthesis.sub('', verses_string)) + [''])[:2]
      if context_verses_string is None:
        context_verses_string = remaining_context_verses_string

      # Get chapter string and book string
      book_string = unparsed
      chapter_match = patterns.trailing_chapter.match(book_string)
      if chapter_match:
        chapter_string = chapter_match.group(1)
        book_string = book_string.removesuffix(chapter_string).strip()
    
    verse_groups = parse_verses_string(verses_string, range_split_limit = range_split_limit)
    context_verse_groups = parse_verses_string(context_verses_string, range_split_limit = range_split_limit)
    chapter = numbers.convert_number_to_int(chapter_string)
    book_slug = None
    skip_book_name = False
    if book_string:
      book_slug = data.scriptures['mapToSlug'].get(book_string, None) or data.scriptures['mapToSlugNormalized'].get(data.normalize_for_compare(book_string), None)
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

def get_content(input_string, lang = 'en', separator = '\n', source = 'python-scripture-scraper', skip_cleanup = False, range_split_limit = 1, **kwargs):
  references = parse_references_string(input_string, lang = lang, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)
  return separator.join([ref.content(source = source) for ref in references])

def get_label(input_string, lang = 'en', separator = '\n', sort_by = None, skip_book_name = False, abbreviated = False, skip_cleanup = False, range_split_limit = 1, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)
  return separator.join([ref.label(skip_book_name = skip_book_name, abbreviated = abbreviated) for ref in references])

def get_church_uri(input_string, lang = 'en', separator = '\n', sort_by = None, use_query_parameters = False, skip_cleanup = False, range_split_limit = 1, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)
  return separator.join([ref.church_uri(use_query_parameters = use_query_parameters) for ref in references])

def get_church_url(input_string, lang = 'en', separator = '\n', sort_by = None, skip_lang = False, skip_fragment = False, skip_cleanup = False, range_split_limit = 1, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)
  return separator.join([ref.church_url(skip_lang = skip_lang, skip_fragment = skip_fragment) for ref in references])

def get_church_link(input_string, lang = 'en', separator = '\n', sort_by = None, link_class = None, link_target = None, skip_book_name = False, abbreviated = False, skip_lang = False, skip_fragment = False, skip_cleanup = False, range_split_limit = 1, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)
  return separator.join([ref.church_link(link_class = link_class, link_target = link_target, skip_book_name = skip_book_name, abbreviated = abbreviated, skip_lang = skip_lang, skip_fragment = skip_fragment) for ref in references])
  
def detect_references(input_string, lang = 'en', range_split_limit = 1, **kwargs):
  lang = data.get_bcp47(lang)

  # Replace newlines and other whitespace with regular spaces, one character for one character, so offsets stay valid in the original string
  working_string = patterns.whitespace.sub(' ', input_string)

  detections = []
  for match in get_detection_pattern(lang).finditer(working_string):
    references = parse_references_string(match.group(0), lang = lang, range_split_limit = range_split_limit)
    if match.group('book') and not any(ref.book_slug or ref.publication_slug for ref in references):
      # Looked like a book name, but it didn't resolve to a known book
      continue
    if not any(ref.chapter for ref in references):
      continue
    detections.append([input_string[match.start():match.end()], match.start(), match.end()])
  return detections

def get_reference_objects(input_string, lang = 'en', sort_by = None, skip_cleanup = False, range_split_limit = 1, **kwargs):
  return parse_references_string(input_string, lang = lang, sort_by = sort_by, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)

def get_reference_attributes(input_string, lang = 'en', sort_by = None, skip_cleanup = False, range_split_limit = 1, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)
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