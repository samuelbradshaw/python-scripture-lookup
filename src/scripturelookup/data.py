# Python standard libraries
import os
import sys
import json

# Third-party libraries
import requests


data_directory = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
os.makedirs(data_directory, exist_ok = True)

# Download JSON data
def download_data(filename, filepath):
  request_url = f'https://raw.githubusercontent.com/samuelbradshaw/python-scripture-scraper/refs/heads/main/sample/{filename}'
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
    load_data(filename)

# Update JSON data
def update_data():
  for filename in ('metadata-languages.min.json', 'metadata-scriptures.min.json',):
    download_data(filename, os.path.join(data_directory, filename))

languages = load_data('metadata-languages.min.json')
scriptures = load_data('metadata-scriptures.min.json')



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
