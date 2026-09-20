# Python standard libraries
import sys
import re
import unicodedata

# Third-party libraries
import icu

# Internal imports
from . import data, numbers, patterns

# Caching dicts
natural_sort_collators = {}
book_name_cache = {}
detection_pattern_cache = {}
ordinal_pattern_cache = {}
numbered_book_pattern_cache = {}

# Punctuation to remove from either end of a reference, gathered from the separators used across all languages
punctuation_to_strip = ''.join(data.scriptures['summary']['punctuation']['referenceSeparator'] + data.scriptures['summary']['punctuation']['verseGroupSeparator'] + data.scriptures['summary']['punctuation']['verseRangeSeparator']) + '(;,.'

# Books with only one chapter, where a bare number is the verse rather than the chapter – "Jude 3" is Jude 1:3, and there is no Jude 3. Citing the whole book is just the name, with no number at all.
single_chapter_book_slugs = {
  slug
  for publication in data.scriptures['structure'].values()
  for slug, book in publication['books'].items()
  if book['churchChapters'] == [1]
}


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

    names_pattern = patterns.build_trie_pattern(scripture_book_names_without_commas)
    # A chapter number has to follow, since this marks where one reference starts after another, and a reference always has one. Without that, a short abbreviation that's also an ordinary word splits text that was never a reference – "De" is French for Deuteronomy, and would break "Article de foi 1:3" into "Article" and "de foi 1:3".
    book_name_cache[lang] = {
      'names_with_commas': scripture_book_names_with_commas,
      'separate_references_pattern': re.compile(rf'(?:^|[^\-])\b({names_pattern}){patterns.not_followed_by_letter_pattern}(?=\s*\d)', flags=re.IGNORECASE),
    }
  return book_name_cache[lang]


# Study helps aren't scripture references, and their abbreviations ("TG", "BD", "IT", "GS") are too short to tell apart from ordinary text
slugs_to_skip_when_detecting = ('topical-guide', 'bible-dictionary', 'index-to-the-triple-combination', 'guide-to-the-scriptures', 'joseph-smith-translation',)


# Build a map of character to character class, so a name with a diacritic also matches text that leaves the
# diacritic out. Example: "é" –> "[eé]", which lets "2 Nephi" match the French name "2 Néphi".
#
# Only the accented character is widened – a plain letter in a name still has to be spelled plainly. Going
# the other way too, so that "e" in a name would also match "é" in the text, is the rarer mistake by far, and
# it costs much more: a class on every "e" in every name roughly triples the time it takes to compile the
# detection pattern, since a plain letter is a great deal more common than an accented one.
#
# The classes are derived from the names themselves, so no per-language table is needed. Each class stands
# in for exactly one character, so the trie invariant described in build_book_names_pattern still holds.
def build_diacritic_character_patterns(names):
  character_patterns = {}
  for name in names:
    for character in name:
      decomposed = unicodedata.normalize('NFKD', character)
      if len(decomposed) > 1 and unicodedata.category(decomposed[0])[0] == 'L' and all(unicodedata.category(c) == 'Mn' for c in decomposed[1:]):
        # Lowercase throughout: build_trie_pattern looks these up by its own lowercased node keys, and the pattern is compiled with re.IGNORECASE, so listing the uppercase forms would only make it bigger
        accented_character = character.lower()
        character_patterns[accented_character] = '[' + ''.join(sorted({accented_character, decomposed[0].lower()})) + ']'
  return character_patterns


# Get the spellings of each name with a plural "s" dropped from one word, since citing the singular is a
# common slip and languages don't pluralize the same word. Examples: "Articles de foi" –> "Article de foi";
# "Artículos de Fe" –> "Artículo de Fe"; "Doctrine et Alliances" –> "Doctrine et Alliance". Only one word is
# changed at a time, since that's the slip being allowed for. Names of a single word are left alone, so an
# ordinary French "acte 2" isn't read as the book "Actes".
def get_singular_name_variants(names):
  variants = set()
  for name in names:
    if ' ' not in name:
      continue
    words = name.split(' ')
    for index, word in enumerate(words):
      if word.endswith('s') and len(word) > 3:
        variants.add(' '.join(words[:index] + [word[:-1]] + words[index + 1:]))
  return variants


# Get the character-to-pattern map for matching the given names, covering every name set that will share one
# regex. It has to be built from the precomposed spellings, before build_name_matching_pattern adds the
# decomposed ones – a decomposed name has no accented character for a class to be derived from.
def build_character_patterns(*name_sets):
  character_patterns = {' ': r'\s'}
  for names in name_sets:
    character_patterns.update(build_diacritic_character_patterns({patterns.whitespace.sub(' ', name) for name in names}))
  return character_patterns


# Build a regex alternation matching any of the given names, allowing for the ways they get written.
# Every name set in the detection patterns comes through here, so the steps stay in one order.
def build_name_matching_pattern(names, character_patterns):
  # Whitespace inside a name is matched loosely, so a non-breaking space in the data still matches a
  # regular space in the text. That mapping is one character for one character, so the trie is safe.
  names = {patterns.whitespace.sub(' ', name) for name in names}

  # A no-op for a list of number words, none of which are plural
  names |= get_singular_name_variants(names)

  # Text can spell an accented character either precomposed ("é") or decomposed ("e" followed by a combining
  # acute accent). The decomposed spelling is added as its own name, rather than being folded into the
  # character classes, so that every path through the trie still consumes a fixed number of characters – and
  # so that detection never has to rewrite the input, which would shift the offsets it reports.
  names |= {unicodedata.normalize('NFD', name) for name in names}

  return patterns.build_trie_pattern(sorted(names), character_patterns = character_patterns)


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

  # A comma in a name is optional, so both spellings are listed. They have to be separate entries
  # rather than an optional character, so that every path through the trie consumes the same
  # characters – otherwise "TJS Génesis" and "TJS, Génesis 1–8" end up on branches that can both
  # match the same text, and the shorter one wins.
  for name in list(names):
    name_without_comma = patterns.verse_group_separators.sub('', name)
    if name_without_comma != name:
      names.add(name_without_comma)

  return build_name_matching_pattern(names, build_character_patterns(names))


# Get the patterns for a numbered book cited with its number written out or abbreviated – "First Nephi",
# "1st Nephi", "I Nephi" for "1 Nephi". Matching a prefix followed by the rest of the name ("Nephi") keeps
# this small: there are only about 18 of those stems, where spelling out every combination as its own name
# would grow the book names pattern by half.
#
# Each number is paired with the stems that actually exist for it, so "4th John" doesn't match – there is no
# 4 John, and pooling the stems would invent one. Requiring a stem is also what keeps an ordinary "I saw
# Alma 32:21" from matching.
def get_numbered_book_patterns(lang):
  if lang not in numbered_book_pattern_cache:
    number_by_form = data.get_book_number_forms(lang)
    forms_by_number = {}
    for form, number in number_by_form.items():
      forms_by_number.setdefault(number, set()).add(form)

    stems_by_number = {}
    for translated_name in data.scriptures['languages'][lang]['translatedNames'].values():
      for key in ('name', 'abbrev',):
        name = patterns.whitespace.sub(' ', translated_name.get(key) or '')
        number_match = patterns.leading_book_number.match(name)
        if number_match:
          stems_by_number.setdefault(int(number_match.group(1)), set()).add(number_match.group(2))

    # One pair of tries per number, so a prefix only matches the stems that go with it
    character_patterns = build_character_patterns(*stems_by_number.values(), *forms_by_number.values())
    branches = [
      (build_name_matching_pattern(forms_by_number[number], character_patterns), build_name_matching_pattern(stems, character_patterns),)
      for number, stems in sorted(stems_by_number.items())
      if forms_by_number.get(number)
    ]

    if not branches:
      numbered_book_pattern_cache[lang] = None
    else:
      # For parsing: one capture around the whole alternation, so the matched prefix comes back whichever
      # branch it took and can be looked up in number_by_form. The stem is only looked ahead at, so it stays
      # where it is.
      rewrite_alternation = r'|'.join(rf'(?:{form_pattern})(?=\s+(?:{stem_pattern}){patterns.not_followed_by_letter_pattern})' for form_pattern, stem_pattern in branches)
      numbered_book_pattern_cache[lang] = {
        'fragment': r'|'.join(rf'(?:{form_pattern})\s+(?:{stem_pattern})' for form_pattern, stem_pattern in branches),
        'rewrite': re.compile(rf'{patterns.reference_start_boundary_pattern}({rewrite_alternation})\s+', flags=re.IGNORECASE),
        # Keyed for comparison, since the patterns above match spellings the plain forms don't cover
        'number_by_form': data.get_normalized_book_number_forms(lang),
      }
  return numbered_book_pattern_cache[lang]


# Get the patterns for an article of faith cited by position, as in "First Article of Faith" or "Premier
# article de foi". The Articles of Faith is a single chapter, so the ordinal is the verse.
#
# Only the full name is matched, never the abbreviation: "Premier AF" isn't a real citation style, and a
# two-letter abbreviation would be useless as the prefilter below ("af" sits inside "after" and "draft").
def get_ordinal_patterns(lang):
  if lang not in ordinal_pattern_cache:
    number_by_form = data.get_ordinal_forms(lang)
    translated_name = data.scriptures['languages'][lang]['translatedNames'].get('articles-of-faith') or {}
    book_names = set()
    name = translated_name.get('name') or ''
    if name:
      book_names.add(name)
      book_names.update(data.get_conjunction_aliases(name))
    book_names |= get_singular_name_variants(book_names)

    if not number_by_form or not book_names:
      ordinal_pattern_cache[lang] = None
    else:
      character_patterns = build_character_patterns(book_names, number_by_form)
      ordinals = build_name_matching_pattern(number_by_form, character_patterns)
      books = build_name_matching_pattern(book_names, character_patterns)

      # Ordinals can be listed or given as a range, as in "First and Third Articles of Faith"
      words = data.get_reference_words(lang)
      joiners = [rf'\s*(?:{patterns.verse_group_separators_pattern})\s*']
      for key in ('list_conjunctions', 'range_conjunctions',):
        if words[key]:
          joiners.append(rf'\s+(?:{words[key]})\s+')
      joiner_alternation = r'|'.join(joiners)
      ordinal_run = rf'(?:{ordinals})(?:(?:{joiner_alternation})(?:{ordinals}))*'

      ordinal_pattern_cache[lang] = {
        # Keyed for comparison, since the patterns above match spellings the plain forms don't cover
        'number_by_form': data.get_normalized_ordinal_forms(lang),
        # Spliced into the detection pattern as an anchor that needs no number after it – the ordinal is the number
        'fragment': rf'(?:{ordinal_run})\s+(?:{books})',
        'rewrite': re.compile(rf'{patterns.reference_start_boundary_pattern}({ordinal_run})\s+({books}){patterns.not_followed_by_letter_pattern}', flags=re.IGNORECASE),
        'single_ordinal': re.compile(rf'{patterns.reference_start_boundary_pattern}(?:{ordinals}){patterns.not_followed_by_letter_pattern}', flags=re.IGNORECASE),
        'range_conjunction': re.compile(rf'\s+(?:{words["range_conjunctions"]})\s+', flags=re.IGNORECASE) if words['range_conjunctions'] else None,
        # Plain lowercased strings, for the cheap test that decides whether the ordinal pattern is worth
        # using at all. Taken from the precomposed spellings only – a decomposed duplicate would be one more
        # substring to scan on every call and could never match text the precomposed one doesn't.
        'prefilter_names': sorted({patterns.whitespace.sub(' ', book_name).lower() for book_name in book_names}),
      }
  return ordinal_pattern_cache[lang]


# Rewrite an article of faith cited by position into the book name followed by plain numbers, which the rest
# of parsing already understands. The single-chapter rule then turns those numbers into verses.
# Example: "First and Third Articles of Faith" –> "Articles of Faith 1,3" –> Articles of Faith 1:1 and 1:3
def replace_ordinal_references(input_string, lang):
  ordinal_patterns = get_ordinal_patterns(lang)
  if not ordinal_patterns:
    return input_string

  def replace(match):
    ordinal_run, book_name = match.group(1), match.group(2)
    ordinal_numbers = [ordinal_patterns['number_by_form'][data.normalize_for_compare(ordinal.group(0))] for ordinal in ordinal_patterns['single_ordinal'].finditer(ordinal_run)]
    is_range = len(ordinal_numbers) > 1 and ordinal_patterns['range_conjunction'] and ordinal_patterns['range_conjunction'].search(ordinal_run)
    numbers_string = f'{ordinal_numbers[0]}-{ordinal_numbers[-1]}' if is_range else ','.join(str(number) for number in ordinal_numbers)
    return f'{book_name} {numbers_string}'
  return ordinal_patterns['rewrite'].sub(replace, input_string)


# Replace a book number written out or abbreviated with its digit, so the name matches the data.
# Examples: "II Corinthians" –> "2 Corinthians"; "1st John" –> "1 John"; "Premier Néphi" –> "1 Néphi"
def replace_book_number_prefixes(input_string, lang):
  numbered_book_patterns = get_numbered_book_patterns(lang)
  if not numbered_book_patterns:
    return input_string

  def replace(match):
    return str(numbered_book_patterns['number_by_form'][data.normalize_for_compare(match.group(1))]) + ' '
  return numbered_book_patterns['rewrite'].sub(replace, input_string)


# Get the compiled regexes for detecting scripture references embedded in text
def get_detection_patterns(lang):
  if lang not in detection_pattern_cache:
    words = data.get_reference_words(lang)

    # Words that can be spelled out between two numbers, or between a book name and a number. Examples: "1, 2, and 3"; "Alma chapter 32 verse 21"
    inline_words = r'|'.join([w for w in (words['list_conjunctions'], words['range_conjunctions'], words['verse_words'], words['chapter_words'],) if w])
    leading_words = r'|'.join([w for w in (words['verse_words'], words['chapter_words'],) if w])

    books = build_book_names_pattern(lang)
    # A numbered book can be cited with its number written out, as in "First Nephi" or "I Nephi". That spelling has to be part of the anchor, since it's what starts the reference.
    numbered_book_patterns = get_numbered_book_patterns(lang)
    numbered_books = numbered_book_patterns['fragment'] if numbered_book_patterns else None
    anchor = rf'(?P<book>{books})'
    if numbered_books:
      anchor += rf'|(?P<numbered_book>{numbered_books})'
    if words['chapter_words']:
      anchor += rf'|(?P<chapter_word>{words["chapter_words"]})'
    anchor_continued = r'|'.join([p for p in (books, numbered_books, words['chapter_words'] or None,) if p])

    # Separator between two numbers in a reference – a chapter/verse separator, or a verse group or range separator
    number_separator = rf'{patterns.chapter_verse_separator_pattern}|\s*(?:{patterns.verse_group_separators_pattern}|{patterns.verse_range_separators_pattern})\s*'
    if inline_words:
      number_separator = rf'(?:{number_separator})(?:(?:{inline_words})\s+)?|\s+(?:{inline_words})\s+'

    # Chapter and verses, ending on a digit or a closing parenthesis so that trailing whitespace and punctuation are never included in the match
    leading_word = rf'(?:(?:{leading_words})\s+)?' if leading_words else ''
    # A number that starts a book name belongs to the next reference, not to this one's verse list. Without this, "Alma 5 and 2 Ne. 2:25" would run together as "Alma 5 and 2".
    not_the_next_book = rf'(?!(?:{anchor_continued})\s*\d)'

    # A chapter or verse is never more than three digits, so a longer run of digits – a year, a page number – isn't part of a reference. The lookahead rejects the whole number, rather than matching just its first three digits.
    number = r'\d{1,3}(?!\d)'

    context = rf'(?:\s*(?:{patterns.opening_parenthesis_pattern})\s*{number}(?:(?:{number_separator}){number})*\s*(?:{patterns.closing_parenthesis_pattern}))?'
    tail = rf'{leading_word}{number}(?:(?:{number_separator}){not_the_next_book}{number})*{context}'

    # Additional references that continue the same run. A conjunction can follow the separator, as in "Genesis 11:29; 22:23; and 24:15".
    conjunction_after_separator = rf'(?:(?:{inline_words})\s+)?' if inline_words else ''
    continued = rf'(?:\s*(?:{patterns.reference_separators_pattern})\s*{conjunction_after_separator}(?:(?:{anchor_continued})\s*)?{tail})*'

    ordinal_patterns = get_ordinal_patterns(lang)
    detection_pattern_cache[lang] = {
      'detection': re.compile(rf'{patterns.reference_start_boundary_pattern}(?:{anchor})\s*{tail}{continued}', flags=re.IGNORECASE),
      # The two below are kept as strings and compiled only when they're needed – see get_lazy_pattern.
      # Everything that can follow a book name, without the anchor in front.
      'reference_tail': rf'\s*{tail}{continued}',
      # The detection pattern with an article of faith cited by position allowed as an anchor of its own,
      # needing no number after it.
      'detection_with_ordinals': rf'{patterns.reference_start_boundary_pattern}(?:(?:{anchor})\s*{tail}|{ordinal_patterns["fragment"]}){continued}' if ordinal_patterns else None,
    }
  return detection_pattern_cache[lang]


# Compile one of the detection patterns that get_detection_patterns left as a string, and remember it. Both
# of them spell the book names out several times over, so compiling either costs about as much as preparing
# the whole language – and most callers need neither. "reference_tail" is only reached when a match ends on a
# bare number that turns out to start an unrecognized book name; "detection_with_ordinals" only when the text
# names the Articles of Faith.
compiled_lazy_pattern_cache = {}
def get_lazy_pattern(lang, key):
  if (lang, key,) not in compiled_lazy_pattern_cache:
    compiled_lazy_pattern_cache[(lang, key,)] = re.compile(get_detection_patterns(lang)[key], flags=re.IGNORECASE)
  return compiled_lazy_pattern_cache[(lang, key,)]


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
  # A footnote letter marks a study note, not part of the verse, so it's dropped. Example: "7a" –> "7"
  verses_string = patterns.verse_footnote_letter.sub('', verses_string)
  
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

  if not skip_cleanup:
    input_string = input_string.strip().strip(punctuation_to_strip).rstrip(':').strip()

    # Compose accented characters, so text that spells "é" as "e" plus a combining acute accent still matches
    # a book name. Parsing returns Reference objects rather than offsets into the input, so shortening the
    # string here is harmless – detection handles the same case without rewriting anything (see
    # build_book_names_pattern).
    if not unicodedata.is_normalized('NFC', input_string):
      input_string = unicodedata.normalize('NFC', input_string)

    # Replace a written-out book number with its digit. Examples: "II Corinthians" –> "2 Corinthians";
    # "1st John" –> "1 John"; "Premier Néphi" –> "1 Néphi". A book name has to follow, so an ordinary
    # "I saw Alma 32:21" is left alone.
    input_string = replace_book_number_prefixes(input_string, lang)

    # Normalize whitespace so it matches the spaces in book names, but keep line breaks, since they separate one reference from the next
    input_string = patterns.whitespace_except_line_breaks.sub(' ', input_string)

    # Close up whitespace around a separator that sits between two numbers, so spacing conventions like the French "D&A 110 :11-16" are read the same as "D&A 110:11-16". Doing this before anything else keeps the rest of the cleanup from mistaking the spaced-out part for trailing text.
    input_string = patterns.separator_whitespace_between_digits.sub(r'\1', input_string)

    # Turn an article of faith cited by position into the book name followed by numbers. Example: "First and Third Articles of Faith" –> "Articles of Faith 1,3"
    input_string = replace_ordinal_references(input_string, lang)

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
      # Only numbers count as context verses, so stray words after an unclosed parenthesis are dropped. Example: "Matthew 7:1–2 (see" –> "Matthew 7:1–2"
      remaining_context_verses_string = remaining_context_verses_string.strip()
      if context_verses_string is None and patterns.numbers_and_separators.match(remaining_context_verses_string):
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
      # A name off by one character, as in "Doctrine et Alliance" or "Helamen", only resolves when cleanup is
      # wanted – skip_cleanup promises well-formed input, and the loose comparison is the expensive stage
      book_slug = data.get_book_slug(book_string, allow_loose_match = not skip_cleanup)
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

    # A book with only one chapter takes a bare number as its verse. "Jude 3" is Jude 1:3 – there is no Jude 3.
    # This happens before previous_chapter is set below, so a continuation like "Jude 3; 5" inherits chapter 1.
    if book_slug in single_chapter_book_slugs and chapter is not None and not verse_groups:
      verse_groups = parse_verses_string(str(chapter), range_split_limit = range_split_limit)
      chapter = 1

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
  
# Look for a book name that the detection pattern didn't recognize, sitting just past the end of a match that
# ended on a bare number. The number belongs to that name rather than to the reference before it, as in
# "Luc 2:10-11 | 2 Nefi 3", where "| 2" starts "2 Nefi" instead of continuing Luke. Returns the position the
# name ends at, or None.
#
# The lookup is what tells this case apart from a genuine continuation – in "See Alma 5; 7 for more context",
# the 7 really is Alma chapter 7, and the words after it are ordinary text. A name that the detection pattern
# already knows never gets here, since the pattern would have carried it into the same match.
def find_unrecognized_book_name(working_string, number, position):
  words = []
  for word_match in patterns.following_word.finditer(working_string, position):
    if word_match.start() > (words[-1][1] if words else position) + 1:
      # A gap wider than a single space means the words aren't part of one name
      break
    words.append((word_match.group(0), word_match.end(),))
    if len(words) == 3:
      break

  # Longest first, so "2 Doctrine and Covenants" is preferred over "2 Doctrine"
  for count in range(len(words), 0, -1):
    book_string = (number + ' ' + ' '.join(word for word, word_end in words[:count])).strip(punctuation_to_strip)
    if data.get_book_slug(book_string):
      return words[count - 1][1]
  return None


def detect_references(input_string, lang = 'en', range_split_limit = 1, **kwargs):
  if not input_string:
    return []

  lang = data.get_bcp47(lang)

  # An article of faith can be cited by position, with no digit anywhere ("First Article of Faith"), so the
  # book name is looked for as well. It's a plain substring test on text lowercased once, which is cheaper
  # than the digit scan, and it only runs for the few languages that have ordinals seeded.
  ordinal_patterns = get_ordinal_patterns(lang)
  ordinal_book_named = False
  if ordinal_patterns:
    lowercased_string = input_string.lower()
    ordinal_book_named = any(book_name in lowercased_string for book_name in ordinal_patterns['prefilter_names'])

  # Every other reference includes a chapter number, so text with no digits in it can be skipped without
  # building the language's detection pattern or scanning for book names.
  if not ordinal_book_named and not patterns.any_digit.search(input_string):
    return []

  # The pattern that also allows an ordinal anchor costs more to scan, so it's only used when the text
  # actually names the Articles of Faith
  detection_pattern = get_lazy_pattern(lang, 'detection_with_ordinals') if ordinal_book_named else get_detection_patterns(lang)['detection']
  # Only some languages have a numbered-book branch, so the group may not be in the pattern at all
  has_numbered_book_group = 'numbered_book' in detection_pattern.groupindex

  # Replace newlines and other whitespace with regular spaces, one character for one character, so offsets stay valid in the original string
  working_string = patterns.whitespace.sub(' ', input_string)

  detections = []
  previous_end = 0
  for match in detection_pattern.finditer(working_string):
    # A trailing reference picked up below can reach past the end of its match, so anything already covered is skipped
    if match.start() < previous_end:
      continue
    start, end = match.start(), match.end()

    # A match that ends on a bare number may have claimed the start of a book name it didn't recognize
    trailing_reference = None
    bare_number_match = patterns.trailing_bare_number.search(working_string, start, end)
    if bare_number_match:
      book_name_end = find_unrecognized_book_name(working_string, bare_number_match.group(1), end)
      if book_name_end:
        # Give the number back, stopping before the separator so the match never ends on whitespace
        end = start + len(working_string[start:bare_number_match.start()].rstrip())
        tail_match = get_lazy_pattern(lang, 'reference_tail').match(working_string, book_name_end)
        if tail_match:
          trailing_reference = (bare_number_match.start(1), tail_match.end(),)

    references = parse_references_string(working_string[start:end], lang = lang, range_split_limit = range_split_limit)
    matched_a_book_name = match.group('book') or (has_numbered_book_group and match.group('numbered_book'))
    if matched_a_book_name and not any(ref.book_slug or ref.publication_slug for ref in references):
      # Looked like a book name, but it didn't resolve to a known book
      continue
    if not any(ref.chapter for ref in references):
      continue
    detections.append([input_string[start:end], start, end])
    previous_end = end

    if trailing_reference:
      trailing_start, trailing_end = trailing_reference
      references = parse_references_string(working_string[trailing_start:trailing_end], lang = lang, range_split_limit = range_split_limit)
      if any(ref.chapter for ref in references):
        detections.append([input_string[trailing_start:trailing_end], trailing_start, trailing_end])
        previous_end = trailing_end
  return detections

def get_reference_objects(input_string, lang = 'en', sort_by = None, skip_cleanup = False, range_split_limit = 1, **kwargs):
  return parse_references_string(input_string, lang = lang, sort_by = sort_by, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)

def get_reference_attributes(input_string, lang = 'en', sort_by = None, skip_cleanup = False, range_split_limit = 1, **kwargs):
  references = parse_references_string(input_string, lang = lang, sort_by = sort_by, skip_cleanup = skip_cleanup, range_split_limit = range_split_limit)
  return [ref.attributes() for ref in references]

# Download the latest scripture and language metadata. Metadata that's already been loaded stays in memory, so the new data is used from the next run onward.
def refresh_metadata(**kwargs):
  filenames = data.update_data()
  return 'Updated metadata: ' + ', '.join(filenames)

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