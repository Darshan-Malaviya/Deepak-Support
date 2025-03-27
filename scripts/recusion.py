import re
import os
import logging
import json

base_path = r"D:\development\Deepak Support New"
log_folder_path = os.path.join(base_path, "logs")
layout_folder_path = os.path.join(base_path, "layouts")

os.makedirs(log_folder_path, exist_ok=True)

with open(os.path.join(log_folder_path, "logs.json"), 'w'): pass
logging.basicConfig(filename=os.path.join(log_folder_path, "logs.json"), level=logging.DEBUG, format='%(message)s')
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

pic_pattern = re.compile(r'PIC\s*([+-S])?([X9S]+)(?:\((\d+)\))?(?:([V.])(9+)?(?:\((\d+)\))?)?', re.IGNORECASE)

def parse_pic(pic_clause):
    if not pic_clause:
        return None

    match = pic_pattern.search("PIC " + pic_clause)
    if not match:
        return None

    sign, format_part, int_count, decimal_marker, decimal_part, decimal_count = match.groups() + (None,) * (6 - len(match.groups()))

    has_explicit_sign = sign in ['+', '-']
    has_explicit_decimal = decimal_marker in ['V', '.']

    if int_count:
        int_len = int(int_count)
    else:
        if all(c == '9' for c in pic_clause):
            sign = None
            int_len = len(pic_clause)
        else:
            int_len = len(format_part)

    if decimal_count:
        dec_len = int(decimal_count)
    elif decimal_part:
        dec_len = len(decimal_part)
    else:
        dec_len = 0

    field_length = int_len + dec_len
    if has_explicit_sign:
        field_length += 1
    if has_explicit_decimal:
        field_length += 1

    if 'X' in format_part:
        field_type = 'string'
    else:
        field_type = 'number'

    return {
        'sign': sign,
        'has_explicit_sign': has_explicit_sign,
        'has_explicit_decimal': has_explicit_decimal,
        'decimal_places': dec_len,
        'field_length': field_length,
        'field_type': field_type
    }

def preprocess_lines(lines):
    processed = []
    current_line = ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
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

def build_hierarchy(lines, index=0, parent_level=0, start_offset=1, flat_fields=None, ref_map=None):
    if flat_fields is None:
        flat_fields = []
    if ref_map is None:
        ref_map = {}

    hierarchy = []
    position = start_offset

    while index < len(lines):
        item = lines[index]
        level = int(item['level'])
        if level <= parent_level:
            break

        node = {
            'name': item['name'],
            'level': level,
            'is_group': 'pic' not in item,
        }

        occurs_count = int(item['occurs']) if 'occurs' in item else 1
        if 'occurs' in item:
            node['occurs'] = occurs_count

        if 'pic' in item:
            node['pic'] = item['pic']
            parsed_pic = parse_pic(item['pic'])
            if parsed_pic:
                node['pic_details'] = parsed_pic
                size = parsed_pic['field_length']
                total_size = size * occurs_count
                if 'redefines' in item and item['redefines'] in ref_map:
                    ref_node = ref_map[item['redefines']]
                    node['start_position'] = ref_node['start_position']
                    node['end_position'] = ref_node['end_position']
                    node['length'] = ref_node['length']
                else:
                    node['start_position'] = position
                    node['length'] = total_size
                    node['end_position'] = position + total_size - 1
                    position += total_size
                flat_fields.append(node.copy())
        else:
            if 'redefines' in item and item['redefines'] in ref_map:
                ref_node = ref_map[item['redefines']]
                node['start_position'] = ref_node['start_position']
            else:
                node['start_position'] = position
            children, next_index = build_hierarchy(lines, index + 1, level, node['start_position'], flat_fields, ref_map)
            node['children'] = children
            child_starts = [c['start_position'] for c in children if 'start_position' in c]
            child_ends = [c['end_position'] for c in children if 'end_position' in c]
            if child_starts and child_ends:
                if 'redefines' in item and item['redefines'] in ref_map:
                    ref_node = ref_map[item['redefines']]
                    node['start_position'] = ref_node['start_position']
                    node['end_position'] = ref_node['end_position']
                    node['length'] = ref_node['length']
                else:
                    node['start_position'] = min(child_starts)
                    node['length'] = (max(child_ends) - min(child_starts) + 1) * occurs_count
                    node['end_position'] = node['start_position'] + node['length'] - 1
                    position = node['end_position'] + 1
            index = next_index

        if 'redefines' in item:
            node['redefines'] = item['redefines']

        ref_map[node['name']] = node
        hierarchy.append(node)
        if 'children' not in node:
            index += 1

    return hierarchy, index

def convert_copybook_to_hierarchy(copybook_text):
    lines = copybook_text.strip().splitlines()
    merged_lines = preprocess_lines(lines)
    parsed_lines = parse_lines(merged_lines)
    flat_fields = []
    ref_map = {}
    hierarchy, _ = build_hierarchy(parsed_lines, flat_fields=flat_fields, ref_map=ref_map)
    return hierarchy, flat_fields

if __name__ == "__main__":
    with open(os.path.join(layout_folder_path, "VCLMXCSV.txt"), "r") as f:
        copybook_text = f.read()

    hierarchy, flat_fields = convert_copybook_to_hierarchy(copybook_text)
    logger.debug(json.dumps(hierarchy, indent=2))
    # logger.debug(json.dumps(flat_fields, indent=2))