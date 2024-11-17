# Python standard libraries
import os
import sys
import json
import time
import re

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

languages = load_data('metadata-languages.min.json')
scriptures = load_data('metadata-scriptures.min.json')

reference_separators_pattern = r'|'.join([re.escape(s.strip()) for s in scriptures['summary']['punctuation']['referenceSeparator']] + [re.escape(';'), re.escape('\n')])
chapter_verse_separators_pattern = r'|'.join([re.escape(s.strip()) for s in scriptures['summary']['punctuation']['chapterVerseSeparator']] + [re.escape(':')])
verse_group_separators_pattern = r'|'.join([re.escape(s.strip()) for s in scriptures['summary']['punctuation']['verseGroupSeparator']] + [re.escape(',')])
verse_range_separators_pattern = r'|'.join([re.escape(s.strip()) for s in scriptures['summary']['punctuation']['verseRangeSeparator']] + [re.escape('-'), re.escape('–'), re.escape('〜')])
opening_parenthesis_pattern = r'|'.join([re.escape(s.strip()) for s in scriptures['summary']['punctuation']['openingParenthesis']] + [re.escape('(')])
closing_parenthesis_pattern = r'|'.join([re.escape(s.strip()) for s in scriptures['summary']['punctuation']['closingParenthesis']] + [re.escape(')')])


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

