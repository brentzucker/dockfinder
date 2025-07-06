from scrape import *

def test_get_maxpageid():
    with open('test_data/test_pageid.html', 'r', encoding='utf-8') as f:
        html = f.read()
    assert get_maxpageid(html) == 125  # Replace 5 with the expected value 