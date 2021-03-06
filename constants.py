# coding: utf-8
#
# Copyright 2017 The Oppia Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Loads constants for backend use."""

from __future__ import absolute_import  # pylint: disable=import-only-modules
from __future__ import unicode_literals  # pylint: disable=import-only-modules

import json
import os
import re

import python_utils


def parse_json_from_js(js_file):
    """Extracts JSON object from JS file."""
    text = js_file.read()
    text_without_comments = remove_comments(text)
    first_bracket_index = text_without_comments.find('= {')
    last_bracket_index = text_without_comments.rfind('}')
    json_text = (
        text_without_comments[first_bracket_index + 2:last_bracket_index + 1]
    )
    return json.loads(json_text)


def remove_comments(text):
    """Removes comments from given text."""
    return re.sub(r'  //.*\n', r'', text)


class Constants(dict):
    """Transforms dict to object, attributes can be accessed by dot notation."""

    __getattr__ = dict.__getitem__


with python_utils.open_file(os.path.join('assets', 'constants.ts'), 'r') as f:
    constants = Constants(parse_json_from_js(f))  # pylint:disable=invalid-name

with python_utils.open_file('release_constants.json', 'r') as f:
    release_constants = Constants(json.loads(f.read()))  # pylint:disable=invalid-name
