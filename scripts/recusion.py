import re
import os
import logging
import json

base_path = r"D:\development\Deepak Support New"
log_folder_path = os.path.join(base_path, "logs")
layout_folder_path = os.path.join(base_path, "layouts")


os.makedirs(log_folder_path, exist_ok=True)

with open(os.path.join(log_folder_path, "logs.txt"), 'w'): pass
logging.basicConfig(filename=os.path.join(log_folder_path, "logs.txt"), level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger(__name__)


line_pattern = re.compile(
    r'(?P<level>\d{2})\s+'
    r'(?P<name>[A-Z0-9-]+)'
    r'(?:\s+REDEFINES\s+(?P<redefines>[A-Z0-9-]+))?'
    r'(?:\s+PIC\s+(?P<pic>[^\s.]+(?:\([^)]+\))?(?:\.[^\s.]+(?:\([^)]+\))?)?))?'
    r'(?:\s+OCCURS\s+(?P<occurs>\d+)\s+TIMES)?'
    r'\.?',
    re.IGNORECASE
)

pic_pattern = re.compile(
    r'PIC\s*([+-S])?([X9A]+)(?:\((\d+)\))?'
    r'(?:([V.])([9A]+)?(?:\((\d+)\))?)?',
    re.IGNORECASE
)

def parse_pic(pic_clause):
    if not pic_clause:
        return None

    match = pic_pattern.search("PIC " + pic_clause)
    if not match:
        return None

    sign, format_part, pic_length, decimal_marker, decimal_part, decimal_count = match.groups() + (None,) * (6 - len(match.groups()))

    has_explicit_sign = sign in ['+', '-', 'S']
    has_explicit_decimal = decimal_marker in ['V', '.']

    if decimal_count:
        decimal_places = int(decimal_count)
    elif decimal_part and has_explicit_decimal:
        decimal_places = len(decimal_part)
    else:
        decimal_places = 0

    if pic_length:
        int_length = int(pic_length)
    else:
        int_length = format_part.count('9') + (decimal_part.count('9') if decimal_part else 0)

    field_length = int_length

    if 'X' in format_part:
        field_type = 'string'
    elif '9' in format_part:
        field_type = 'number'
    else:
        field_type = 'string'

    return {
        'sign': sign,
        'has_explicit_sign': has_explicit_sign,
        'has_explicit_decimal': has_explicit_decimal,
        'decimal_places': decimal_places,
        'field_length': field_length,
        'field_type': field_type
    }

def preprocess_lines(lines):
    """Merge continuation lines, skip comments, and merge OCCURS on next line."""
    processed = []
    current_line = ""

    for line in lines:
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith('*') or re.match(r'^\*{3,}$', stripped):
            continue

        if re.match(r"^\d{2}\s", stripped):
            if current_line:
                processed.append(current_line)
            current_line = stripped
        else:
            current_line += " " + stripped

    if current_line:
        processed.append(current_line)

    return processed

def parse_lines(lines):
    parsed = []
    for line in lines:
        match = line_pattern.search(line)
        if match:
            parsed.append({k: v for k, v in match.groupdict().items() if v})
    return parsed

def build_hierarchy(lines, index=0, parent_level=0):
    hierarchy = []
    while index < len(lines):
        item = lines[index]
        level = int(item['level'])

        if level <= parent_level:
            break

        children, next_index = build_hierarchy(lines, index + 1, level)

        node = {
            'name': item['name'],
            'level': level,
            'is_group': 'pic' not in item
        }

        if 'pic' in item:
            node['pic'] = item['pic']
            parsed_pic = parse_pic(item['pic'])
            if parsed_pic:
                node['pic_details'] = parsed_pic

        if 'redefines' in item:
            node['redefines'] = item['redefines']
        if 'occurs' in item:
            node['occurs'] = int(item['occurs'])
        if children:
            node['children'] = children

        hierarchy.append(node)
        index = next_index

    return hierarchy, index

def convert_copybook_to_hierarchy(copybook_text):
    lines = copybook_text.strip().splitlines()
    merged_lines = preprocess_lines(lines)
    parsed_lines = parse_lines(merged_lines)
    hierarchy, _ = build_hierarchy(parsed_lines)
    return hierarchy

# Example usage:
if __name__ == "__main__":
    with open(os.path.join(layout_folder_path, "VJLMAN00.TXT"), "r") as f:
        copybook_text = f.read()

    hierarchy = convert_copybook_to_hierarchy(copybook_text)
    logger.debug(json.dumps(hierarchy, indent=2))
