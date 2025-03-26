import os
import json
import re
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

base_path = r"D:\development\Deepak Support New"
config_path = os.path.join(base_path, 'configs', "config.json")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

try:
    with open(config_path, "r") as config_file:
        config = json.load(config_file)
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse config.json: {e}")
    raise

feed_configs = config.get("feed_configs", [])
if not feed_configs:
    logger.error("No 'feed_configs' found in config.json")
    raise ValueError("Config must contain 'feed_configs'")

def to_camel_case(cobol_name):
    parts = cobol_name.lower().split('-')
    return parts[0] + ''.join(part.capitalize() for part in parts[1:])

def parse_copybook(copybook_path, use_camel_case=True):
    level_field_pattern = re.compile(r'^\s*(\d+)\s+([\w-]+)', re.IGNORECASE)
    pic_pattern = re.compile(r'PIC\s*([+-S])?([X9S]+)(?:\((\d+)\))?(?:([V.])(9+)?(?:\((\d+)\))?)?', re.IGNORECASE)
    occurs_pattern = re.compile(r'OCCURS\s+(\d+)\s+TIMES', re.IGNORECASE)
    redefines_pattern = re.compile(r'(\d{2})\s+([A-Z0-9-]+)\s+REDEFINES', re.IGNORECASE)

    if not os.path.exists(copybook_path):
        logger.warning(f"Copybook file not found: {copybook_path}")
        return [], {}

    with open(copybook_path, 'r') as file:
        lines = file.readlines()

    hierarchy = {}
    field_info_list = []
    level_stack = []
    top_level_name = None
    pending_field = None
    last_field_info = None

    for line_idx, line in enumerate(lines):
        line = line.strip()
        logger.debug(f"Processing line {line_idx + 1}: '{line}'")
        
        level_match = level_field_pattern.search(line)
        if not level_match:
            if pending_field and occurs_pattern.search(line):
                occurs_match = occurs_pattern.search(line)
                pending_field['occurs'] = int(occurs_match.group(1))
                pending_field['is_group'] = False
                field_info_list.append(pending_field)
                process_field(pending_field, hierarchy, level_stack, top_level_name, copybook_path, line_idx, use_camel_case)
                pending_field = None
            elif last_field_info and last_field_info['is_redefines']:
                if line:
                    last_field_info['definition_field'] = line.split('.')[0]
                continue
            continue

        level, field_name = level_match.groups()
        level = int(level)
        logger.debug(f"Found level={level}, field_name={field_name}")

        if field_name.startswith("FILLER"):
            field_name = f"FILLER_{len(field_info_list) + 1}"

        pic_match = pic_pattern.search(line)
        occurs_match = occurs_pattern.search(line)
        redefines_match = redefines_pattern.match(line)

        field_info = {
            'name': field_name,
            'level': level,
            'pic_clause': pic_match.group(0) if pic_match else None,
            'occurs': int(occurs_match.group(1)) if occurs_match else None,
            'is_group': pic_match is None and (occurs_match is not None or redefines_match is not None),
            'redefines': redefines_match.group(2) if redefines_match else None,
            'is_redefines': redefines_match is not None,
            'definition_field': None
        }

        if pending_field:
            field_info_list.append(pending_field)
            if top_level_name or pending_field['level'] == 1:
                process_field(pending_field, hierarchy, level_stack, top_level_name, copybook_path, line_idx - 1, use_camel_case)
            pending_field = None

        if level == 1:
            top_level_name = field_name
            hierarchy[to_camel_case(field_name) if use_camel_case else field_name] = {}
            level_stack = [{'level': level, 'node': hierarchy[to_camel_case(field_name) if use_camel_case else field_name], 'occurs': False}]
            field_info_list.append(field_info)
            logger.debug(f"Set top-level name to {top_level_name}")
        elif pic_match and not occurs_match:
            pending_field = field_info
        else:
            field_info_list.append(field_info)
            if top_level_name:
                process_field(field_info, hierarchy, level_stack, top_level_name, copybook_path, line_idx, use_camel_case)

        last_field_info = field_info

    if pending_field:
        field_info_list.append(pending_field)
        if top_level_name:
            process_field(pending_field, hierarchy, level_stack, top_level_name, copybook_path, len(lines) - 1, use_camel_case)

    if top_level_name is None:
        logger.warning(f"No 01 level found in copybook {copybook_path}")
        return [], {}

    structure = []
    position = 1
    skip_subfields = set()

    for field_info in field_info_list:
        field_name = field_info['name']
        level = field_info['level']
        pic_clause = field_info['pic_clause']
        occurs_times = field_info['occurs']
        is_group = field_info['is_group']
        redefines = field_info['redefines']
        is_redefines = field_info['is_redefines']
        definition_field = field_info['definition_field']

        if level == 1:
            continue

        field_length = 0
        field_type = 'string'
        decimal_places = 0

        if pic_clause:
            pic_match = pic_pattern.search(pic_clause)
            sign, format_part, pic_length, decimal_marker, decimal_part, decimal_count = pic_match.groups() + (None,) * (6 - len(pic_match.groups()))
            has_explicit_sign = sign in ['+', '-']
            sign_length = 1 if has_explicit_sign else 0
            has_explicit_decimal = decimal_marker in ['V', '.']
            decimal_length = 1 if has_explicit_decimal else 0

            if decimal_count:
                decimal_places = int(decimal_count)
            elif decimal_part and has_explicit_decimal:
                decimal_places = len(decimal_part)
            else:
                decimal_places = 0

            if 'X' in format_part:
                field_length = int(pic_length) if pic_length else len(format_part)
                field_type = 'string'
            elif '9' in format_part:
                if pic_length:
                    field_length = int(pic_length) + sign_length
                    if has_explicit_decimal and decimal_places > 0:
                        field_length += decimal_length + decimal_places
                else:
                    pic_content = pic_clause.split('PIC ')[1].strip()
                    if has_explicit_sign:
                        pic_content = pic_content[1:]
                    field_length = pic_content.count('9') + sign_length
                field_type = 'number'
            else:
                field_length = len(format_part)
                field_type = 'string'

        start = position

        if is_redefines:
            redefined_field = None
            for prev_field in structure:
                if prev_field['name'] == redefines:
                    redefined_field = prev_field
                    break
            if redefined_field:
                start = redefined_field['start']
                group_info = {
                    'name': field_name,
                    'type': 'group',
                    'length': redefined_field['length'],
                    'start': start,
                    'end': start + redefined_field['length'] - 1,
                    'decimal_places': 0,
                    'occurs': occurs_times or 1,
                    'subfields': [],
                    'is_group': True,
                    'level': level,
                    'redefines': redefines
                }
                subfield_position = 0
                current_idx = field_info_list.index(field_info)
                for sub_field in field_info_list[current_idx + 1:]:
                    if sub_field['level'] <= level:
                        break
                    sub_length = 0
                    sub_type = 'string'
                    sub_decimal_places = 0
                    if sub_field['pic_clause']:
                        sub_pic_match = pic_pattern.search(sub_field['pic_clause'])
                        sub_sign, sub_format, sub_length_str, sub_dec_marker, sub_dec_part, sub_dec_count = sub_pic_match.groups() + (None,) * (6 - len(sub_pic_match.groups()))
                        has_sub_sign = sub_sign in ['+', '-']
                        sub_sign_length = 1 if has_sub_sign else 0
                        has_sub_decimal = sub_dec_marker in ['V', '.']
                        sub_decimal_length = 1 if has_sub_decimal else 0

                        if sub_dec_count:
                            sub_decimal_places = int(sub_dec_count)
                        elif sub_dec_part and has_sub_decimal:
                            sub_decimal_places = len(sub_dec_part)
                        else:
                            sub_decimal_places = 0

                        if 'X' in sub_format:
                            sub_length = int(sub_length_str) if sub_length_str else len(sub_format)
                            sub_type = 'string'
                        elif '9' in sub_format:
                            if sub_length_str:
                                sub_length = int(sub_length_str) + sub_sign_length
                                if has_sub_decimal and sub_decimal_places > 0:
                                    sub_length += sub_decimal_length + sub_decimal_places
                            else:
                                sub_pic_content = sub_field['pic_clause'].split('PIC ')[1].strip()
                                if has_sub_sign:
                                    sub_pic_content = sub_pic_content[1:]
                                sub_length = sub_pic_content.count('9') + sub_sign_length
                            sub_type = 'number'
                        else:
                            sub_length = int(sub_length_str) if sub_length_str else len(sub_format)

                    subfield_info = {
                        'name': sub_field['name'],
                        'type': sub_type,
                        'length': sub_length,
                        'decimal_places': sub_decimal_places,
                        'relative_start': subfield_position,
                        'relative_end': subfield_position + sub_length - 1,
                        'level': sub_field['level'],
                        'occurs': sub_field['occurs'],
                        'subfields': []  # Add subfields for nested groups
                    }
                    if sub_field['is_group'] and sub_field['occurs']:
                        sub_subfield_position = 0
                        sub_current_idx = field_info_list.index(sub_field)
                        for sub_sub_field in field_info_list[sub_current_idx + 1:]:
                            if sub_sub_field['level'] <= sub_field['level']:
                                break
                            sub_sub_length = 0
                            sub_sub_type = 'string'
                            sub_sub_decimal_places = 0
                            if sub_sub_field['pic_clause']:
                                sub_sub_pic_match = pic_pattern.search(sub_sub_field['pic_clause'])
                                sub_sub_sign, sub_sub_format, sub_sub_length_str, sub_sub_dec_marker, sub_sub_dec_part, sub_sub_dec_count = sub_sub_pic_match.groups() + (None,) * (6 - len(sub_sub_pic_match.groups()))
                                has_sub_sub_sign = sub_sub_sign in ['+', '-']
                                sub_sub_sign_length = 1 if has_sub_sub_sign else 0
                                has_sub_sub_decimal = sub_sub_dec_marker in ['V', '.']
                                sub_sub_decimal_length = 1 if has_sub_sub_decimal else 0

                                if sub_sub_dec_count:
                                    sub_sub_decimal_places = int(sub_sub_dec_count)
                                elif sub_sub_dec_part and has_sub_sub_decimal:
                                    sub_sub_decimal_places = len(sub_sub_dec_part)
                                else:
                                    sub_sub_decimal_places = 0

                                if 'X' in sub_sub_format:
                                    sub_sub_length = int(sub_sub_length_str) if sub_sub_length_str else len(sub_sub_format)
                                    sub_sub_type = 'string'
                                elif '9' in sub_sub_format:
                                    if sub_sub_length_str:
                                        sub_sub_length = int(sub_sub_length_str) + sub_sub_sign_length
                                        if has_sub_sub_decimal and sub_sub_decimal_places > 0:
                                            sub_sub_length += sub_sub_decimal_length + sub_sub_decimal_places
                                    else:
                                        sub_sub_pic_content = sub_sub_field['pic_clause'].split('PIC ')[1].strip()
                                        if has_sub_sub_sign:
                                            sub_sub_pic_content = sub_sub_pic_content[1:]
                                        sub_sub_length = sub_sub_pic_content.count('9') + sub_sub_sign_length
                                    sub_sub_type = 'number'
                                else:
                                    sub_sub_length = int(sub_sub_length_str) if sub_sub_length_str else len(sub_sub_format)

                            sub_subfield_info = {
                                'name': sub_sub_field['name'],
                                'type': sub_sub_type,
                                'length': sub_sub_length,
                                'decimal_places': sub_sub_decimal_places,
                                'relative_start': sub_subfield_position,
                                'relative_end': sub_subfield_position + sub_sub_length - 1,
                                'level': sub_sub_field['level'],
                                'occurs': sub_sub_field['occurs']
                            }
                            subfield_info['subfields'].append(sub_subfield_info)
                            sub_subfield_position += sub_sub_length

                    group_info['subfields'].append(subfield_info)
                    skip_subfields.add(sub_field['name'])
                    subfield_position += sub_length
                structure.append(group_info)
            else:
                logger.warning(f"REDEFINES target '{redefines}' not found for '{field_name}', using position {position}")
                end = position + field_length - 1
                structure.append({
                    'name': field_name,
                    'type': field_type,
                    'length': field_length,
                    'start': start,
                    'end': end,
                    'decimal_places': decimal_places,
                    'occurs': None,
                    'is_group': False,
                    'level': level,
                    'redefines': redefines
                })
                position = end + 1
        elif occurs_times:
            if is_group:
                group_info = {
                    'name': field_name,
                    'type': 'group',
                    'length': 0,
                    'start': start,
                    'end': start - 1,
                    'decimal_places': 0,
                    'occurs': occurs_times,
                    'subfields': [],
                    'is_group': True,
                    'level': level,
                    'redefines': redefines
                }
                subfield_position = 0
                current_idx = field_info_list.index(field_info)
                for sub_field in field_info_list[current_idx + 1:]:
                    if sub_field['level'] <= level:
                        break
                    sub_length = 0
                    sub_type = 'string'
                    sub_decimal_places = 0
                    if sub_field['pic_clause']:
                        sub_pic_match = pic_pattern.search(sub_field['pic_clause'])
                        sub_sign, sub_format, sub_length_str, sub_dec_marker, sub_dec_part, sub_dec_count = sub_pic_match.groups() + (None,) * (6 - len(sub_pic_match.groups()))
                        has_sub_sign = sub_sign in ['+', '-']
                        sub_sign_length = 1 if has_sub_sign else 0
                        has_sub_decimal = sub_dec_marker in ['V', '.']
                        sub_decimal_length = 1 if has_sub_decimal else 0

                        if sub_dec_count:
                            sub_decimal_places = int(sub_dec_count)
                        elif sub_dec_part and has_sub_decimal:
                            sub_decimal_places = len(sub_dec_part)
                        else:
                            sub_decimal_places = 0

                        if 'X' in sub_format:
                            sub_length = int(sub_length_str) if sub_length_str else len(sub_format)
                            sub_type = 'string'
                        elif '9' in sub_format:
                            if sub_length_str:
                                sub_length = int(sub_length_str) + sub_sign_length
                                if has_sub_decimal and sub_decimal_places > 0:
                                    sub_length += sub_decimal_length + sub_decimal_places
                            else:
                                sub_pic_content = sub_field['pic_clause'].split('PIC ')[1].strip()
                                if has_sub_sign:
                                    sub_pic_content = sub_pic_content[1:]
                                sub_length = sub_pic_content.count('9') + sub_sign_length
                            sub_type = 'number'
                        else:
                            sub_length = int(sub_length_str) if sub_length_str else len(sub_format)

                    subfield_info = {
                        'name': sub_field['name'],
                        'type': sub_type,
                        'length': sub_length,
                        'decimal_places': sub_decimal_places,
                        'relative_start': subfield_position,
                        'relative_end': subfield_position + sub_length - 1,
                        'level': sub_field['level'],
                        'occurs': sub_field['occurs'],
                        'subfields': []  # Add subfields for nested groups
                    }
                    if sub_field['is_group'] and sub_field['occurs']:
                        sub_subfield_position = 0
                        sub_current_idx = field_info_list.index(sub_field)
                        for sub_sub_field in field_info_list[sub_current_idx + 1:]:
                            if sub_sub_field['level'] <= sub_field['level']:
                                break
                            sub_sub_length = 0
                            sub_sub_type = 'string'
                            sub_sub_decimal_places = 0
                            if sub_sub_field['pic_clause']:
                                sub_sub_pic_match = pic_pattern.search(sub_sub_field['pic_clause'])
                                sub_sub_sign, sub_sub_format, sub_sub_length_str, sub_sub_dec_marker, sub_sub_dec_part, sub_sub_dec_count = sub_sub_pic_match.groups() + (None,) * (6 - len(sub_sub_pic_match.groups()))
                                has_sub_sub_sign = sub_sub_sign in ['+', '-']
                                sub_sub_sign_length = 1 if has_sub_sub_sign else 0
                                has_sub_sub_decimal = sub_sub_dec_marker in ['V', '.']
                                sub_sub_decimal_length = 1 if has_sub_sub_decimal else 0

                                if sub_sub_dec_count:
                                    sub_sub_decimal_places = int(sub_sub_dec_count)
                                elif sub_sub_dec_part and has_sub_sub_decimal:
                                    sub_sub_decimal_places = len(sub_sub_dec_part)
                                else:
                                    sub_sub_decimal_places = 0

                                if 'X' in sub_sub_format:
                                    sub_sub_length = int(sub_sub_length_str) if sub_sub_length_str else len(sub_sub_format)
                                    sub_sub_type = 'string'
                                elif '9' in sub_sub_format:
                                    if sub_sub_length_str:
                                        sub_sub_length = int(sub_sub_length_str) + sub_sub_sign_length
                                        if has_sub_sub_decimal and sub_sub_decimal_places > 0:
                                            sub_sub_length += sub_sub_decimal_length + sub_sub_decimal_places
                                    else:
                                        sub_sub_pic_content = sub_sub_field['pic_clause'].split('PIC ')[1].strip()
                                        if has_sub_sub_sign:
                                            sub_sub_pic_content = sub_sub_pic_content[1:]
                                        sub_sub_length = sub_sub_pic_content.count('9') + sub_sub_sign_length
                                    sub_sub_type = 'number'
                                else:
                                    sub_sub_length = int(sub_sub_length_str) if sub_sub_length_str else len(sub_sub_format)

                            sub_subfield_info = {
                                'name': sub_sub_field['name'],
                                'type': sub_sub_type,
                                'length': sub_sub_length,
                                'decimal_places': sub_sub_decimal_places,
                                'relative_start': sub_subfield_position,
                                'relative_end': sub_subfield_position + sub_sub_length - 1,
                                'level': sub_sub_field['level'],
                                'occurs': sub_sub_field['occurs']
                            }
                            subfield_info['subfields'].append(sub_subfield_info)
                            sub_subfield_position += sub_sub_length

                    group_info['subfields'].append(subfield_info)
                    skip_subfields.add(sub_field['name'])
                    subfield_position += sub_length

                total_length = subfield_position * occurs_times
                group_info['length'] = total_length
                group_info['end'] = start + total_length - 1
                structure.append(group_info)
                position += total_length
            else:
                total_length = field_length * occurs_times
                structure.append({
                    'name': field_name,
                    'type': field_type,
                    'length': field_length,
                    'start': start,
                    'end': start + total_length - 1,
                    'decimal_places': decimal_places,
                    'occurs': occurs_times,
                    'is_group': False,
                    'level': level,
                    'redefines': redefines
                })
                position = start + total_length
        elif field_name not in skip_subfields:
            end = start + field_length - 1
            structure.append({
                'name': field_name,
                'type': field_type,
                'length': field_length,
                'start': start,
                'end': end,
                'decimal_places': decimal_places,
                'occurs': None,
                'is_group': False,
                'level': level,
                'redefines': redefines
            })
            if not redefines and field_length > 0:
                position = end + 1

    logger.debug(f"Structure for {copybook_path}: {json.dumps(structure, indent=4)}")
    logger.debug(f"Hierarchy for {copybook_path}: {json.dumps(hierarchy, indent=4)}")
    return structure, hierarchy

def process_field(field_info, hierarchy, level_stack, top_level_name, copybook_path, line_idx, use_camel_case=True):
    level = field_info['level']
    field_name = to_camel_case(field_info['name']) if use_camel_case else field_info['name']
    occurs_match = field_info['occurs'] is not None
    redefines = field_info['redefines']

    if level == 1:
        top_level_name = field_info['name']
        hierarchy[field_name] = {}
        level_stack = [{'level': level, 'node': hierarchy[field_name], 'occurs': False}]
        logger.debug(f"Set top-level name to {top_level_name}")
        return

    while level_stack and level_stack[-1]['level'] >= level:
        level_stack.pop()
    current_parent = level_stack[-1]['node'] if level_stack else hierarchy[to_camel_case(top_level_name) if use_camel_case else top_level_name]

    if redefines:
        logger.debug(f"Field '{field_name}' redefines '{redefines}' at level {level}")

    if occurs_match:
        if field_info['is_group']:
            current_parent[field_name] = [{}]
            level_stack.append({'level': level, 'node': current_parent[field_name][0], 'occurs': True})
        else:
            current_parent[field_name] = []
    elif field_info['pic_clause']:
        current_parent[field_name] = None
    else:
        current_parent[field_name] = {}
        level_stack.append({'level': level, 'node': current_parent[field_name], 'occurs': False})

def parse_feed_line(line, layout_structure, line_idx, hierarchy, use_camel_case=True):
    record = {}
    processed_positions = {}
    
    logger.debug(f"Parsing line {line_idx}: '{line}' (length: {len(line)})")
    
    def parse_subfields(subfields, base_start, occurs_count=1, parent_length=None):
        result = []
        if parent_length and subfields:
            if any(sf.get('occurs') and sf.get('subfields') for sf in subfields):
                occurrence_length = parent_length // occurs_count
            else:
                occurrence_length = sum(sf['length'] for sf in subfields if not sf.get('occurs') or not sf['subfields'])
        else:
            occurrence_length = sum(sf['length'] for sf in subfields if not sf.get('occurs') or not sf['subfields'])
            for sf in subfields:
                if sf.get('occurs') and sf['subfields']:
                    occurrence_length += sum(sub_sf['length'] for sub_sf in sf['subfields']) * sf['occurs']
        
        for outer_idx in range(occurs_count):
            occurrence_data = {}
            occurrence_start = base_start + (outer_idx * occurrence_length)
            subfield_position = 0
            for subfield in subfields:
                subfield_name = to_camel_case(subfield['name']) if use_camel_case else subfield['name']
                subfield_length = subfield['length']
                subfield_type = subfield['type']
                subfield_occurs = subfield.get('occurs')
                subfield_subfields = subfield.get('subfields', [])

                if subfield_occurs and subfield_subfields:
                    sub_occurrence_length = sum(sf['length'] for sf in subfield_subfields)
                    subfield_result = []
                    subfield_start = occurrence_start + subfield_position
                    for sub_idx in range(subfield_occurs):
                        sub_occurrence_start = subfield_start + (sub_idx * sub_occurrence_length)
                        sub_occurrence_data = {}
                        sub_subfield_position = 0
                        for sub_subfield in subfield_subfields:
                            sub_subfield_name = to_camel_case(sub_subfield['name']) if use_camel_case else sub_subfield['name']
                            sub_subfield_length = sub_subfield['length']
                            sub_subfield_type = sub_subfield['type']
                            sub_subfield_start = sub_occurrence_start + sub_subfield_position
                            sub_subfield_end = sub_subfield_start + sub_subfield_length
                            if sub_subfield_start >= len(line):
                                value = ""
                            elif sub_subfield_end > len(line):
                                value = line[sub_subfield_start:].strip() or ""
                            else:
                                value = line[sub_subfield_start:sub_subfield_end].rstrip()
                            
                            logger.debug(f"Line {line_idx}: Subfield '{sub_subfield_name}' - Start: {sub_subfield_start + 1}, End: {sub_subfield_end}, Length: {sub_subfield_length}, Value: '{value}'")
                            
                            if sub_subfield_type == 'number' and value.strip():
                                try:
                                    sub_occurrence_data[sub_subfield_name] = float(value.strip()) if '.' in value else int(value.strip())
                                except ValueError:
                                    sub_occurrence_data[sub_subfield_name] = value
                            else:
                                sub_occurrence_data[sub_subfield_name] = value
                            sub_subfield_position += sub_subfield_length
                        subfield_result.append(sub_occurrence_data)
                    occurrence_data[subfield_name] = subfield_result
                    subfield_position += sub_occurrence_length * subfield_occurs
                else:
                    subfield_start = occurrence_start + subfield_position
                    subfield_end = subfield_start + subfield_length
                    if subfield_start >= len(line):
                        value = ""
                    elif subfield_end > len(line):
                        value = line[subfield_start:].strip() or ""
                    else:
                        value = line[subfield_start:subfield_end].rstrip()
                    
                    logger.debug(f"Line {line_idx}: Subfield '{subfield_name}' - Start: {subfield_start + 1}, End: {subfield_end}, Length: {subfield_length}, Value: '{value}'")
                    
                    if subfield_type == 'number' and value.strip():
                        try:
                            occurrence_data[subfield_name] = float(value.strip()) if '.' in value else int(value.strip())
                        except ValueError:
                            occurrence_data[subfield_name] = value
                    else:
                        occurrence_data[subfield_name] = value
                    subfield_position += subfield_length
            result.append(occurrence_data)
        return result

    for field in layout_structure:
        field_name = field['name']
        start = field['start'] - 1
        length = field['length']
        end = start + length
        field_type = field['type']
        redefines = field.get('redefines')
        occurs_count = field.get('occurs')
        is_group = field.get('is_group', False)
        subfields = field.get('subfields', [])

        if is_group and subfields:
            if redefines:
                # For REDEFINES groups, parse subfields from the redefined position
                occurs_values = parse_subfields(subfields, start, occurs_count or 1, length)
                record[to_camel_case(field_name) if use_camel_case else field_name] = occurs_values[0] if occurs_count == 1 else occurs_values
            else:
                occurs_values = parse_subfields(subfields, start, occurs_count or 1)
                record[to_camel_case(field_name) if use_camel_case else field_name] = occurs_values[0] if occurs_count == 1 else occurs_values
        elif occurs_count:
            values = []
            for i in range(occurs_count):
                field_start = start + (i * length)
                field_end = field_start + length
                if field_start >= len(line):
                    value = ""
                elif field_end > len(line):
                    value = line[field_start:].strip() or ""
                else:
                    value = line[field_start:field_end].rstrip()
                
                logger.debug(f"Line {line_idx}: Field '{field_name}' (Occurrence {i + 1}) - Start: {field_start + 1}, End: {field_end}, Length: {length}, Value: '{value}'")
                
                if field_type == 'number' and value.strip():
                    try:
                        values.append(float(value.strip()) if '.' in value else int(value.strip()))
                    except ValueError:
                        values.append(value)
                else:
                    values.append(value)
            record[to_camel_case(field_name) if use_camel_case else field_name] = values
        else:
            if start >= len(line):
                value = ""
            elif end > len(line):
                value = line[start:].strip() or ""
            else:
                value = line[start:end].rstrip()

            position_key = f"{start}-{end}"
            if redefines and position_key in processed_positions:
                logger.debug(f"Field '{field_name}' redefines '{redefines}' at positions {start + 1}-{end} (overlaps with '{processed_positions[position_key]}')")

            logger.debug(f"Line {line_idx}: Field '{field_name}' - Start: {start + 1}, End: {end}, Length: {length}, Value: '{value}', Redefines: {redefines}")

            if field_type == 'number' and value.strip():
                try:
                    record[to_camel_case(field_name) if use_camel_case else field_name] = float(value.strip()) if '.' in value else int(value.strip())
                except ValueError:
                    record[to_camel_case(field_name) if use_camel_case else field_name] = value
            else:
                record[to_camel_case(field_name) if use_camel_case else field_name] = value
            
            processed_positions[position_key] = field_name

    def build_nested_structure(hierarchy, flat_data):
        nested = {}
        for key, value in hierarchy.items():
            if isinstance(value, dict):
                nested[key] = build_nested_structure(value, flat_data)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                occurs_data = flat_data.get(key, [{} for _ in range(len(value))])
                nested[key] = [dict(build_nested_structure(value[0], item)) for item in occurs_data]
            elif isinstance(value, list):
                nested[key] = flat_data.get(key, [])
            else:
                nested[key] = flat_data.get(key, "")
        return nested

    nested_record = build_nested_structure(hierarchy, record)
    logger.debug(f"Nested record: {json.dumps(nested_record, indent=4)}")
    return nested_record

def parse_feed_file(feed_file_path, layouts, is_single_layout, record_layout_mapping=None, use_camel_case=True):
    records = []
    current_policy = None
    current_records = []
    
    if not os.path.exists(feed_file_path):
        logger.error(f"Feed file not found: {feed_file_path}")
        return records

    with open(feed_file_path, 'r') as file:
        lines = file.readlines()

    if is_single_layout:
        if not layouts:
            logger.error(f"No layouts provided for single layout parsing of {feed_file_path}")
            return records
        layout_key = list(layouts.keys())[0]
        layout_structure, hierarchy = layouts.get(layout_key, ([], {}))
        if not layout_structure:
            logger.warning(f"No layout structure for {layout_key}")
            return records

        for line_idx, line in enumerate(lines):
            line = line.rstrip()
            record = parse_feed_line(line, layout_structure, line_idx, hierarchy, use_camel_case)
            records.append({"record": record})
            logger.debug(f"Line {line_idx}: Processed with single layout {layout_key}")
    else:
        if not record_layout_mapping:
            logger.error(f"No record_layout_mapping provided for multi-layout parsing of {feed_file_path}")
            return records
        possible_record_types = list(record_layout_mapping.keys())
        
        for line_idx, line in enumerate(lines):
            line = line.rstrip()
            record_type = None
            for possible_type in possible_record_types:
                if possible_type in line:
                    record_type = possible_type
                    break
            
            if line.startswith("NCO"):
                if current_policy:
                    records.append({"policy_number": current_policy, "records": current_records})
                current_policy = line.strip()
                current_records = []
                logger.debug(f"Line {line_idx}: New policy: {current_policy}")
            
            if record_type:
                layout_file = record_layout_mapping[record_type] + ".TXT"
                layout_path = os.path.join(base_path, 'layouts', layout_file)
                if not os.path.exists(layout_path):
                    logger.warning(f"Line {line_idx}: Layout file not found: {layout_path}")
                    continue
                layout_structure, hierarchy = layouts.get(layout_file, ([], {}))
                if not layout_structure:
                    logger.warning(f"Line {line_idx}: No layout structure for {layout_file}")
                    continue
                record = parse_feed_line(line, layout_structure, line_idx, hierarchy, use_camel_case)
                current_records.append(record)
        
        if current_policy and current_records:
            records.append({"policy_number": current_policy, "records": current_records})

    return records

# Process each feed configuration
for feed_config in feed_configs:
    feed_file_path = os.path.join(base_path, 'feeds', feed_config["feed_file"])
    output_json_path = os.path.join(base_path, 'outputs', feed_config["output_file"])
    layout_config = feed_config["layout_config"]
    use_camel_case = feed_config.get("camelCase", "True").lower() == "true"
    
    is_single_layout = "layout_file" in layout_config
    layouts = {}
    
    if is_single_layout:
        single_layout_file = layout_config["layout_file"] + ".TXT"
        layout_path = os.path.join(base_path, 'layouts', single_layout_file)
        if os.path.exists(layout_path):
            layouts[single_layout_file] = parse_copybook(layout_path, use_camel_case)
        else:
            logger.warning(f"Layout file missing: {layout_path}")
        record_layout_mapping = None
    else:
        record_layout_mapping = layout_config.get("record_layout_mapping", {})
        if not record_layout_mapping:
            logger.error(f"No record_layout_mapping in layout_config for {feed_file_path}")
            continue
        for record_type, layout_file in record_layout_mapping.items():
            layout_filename = layout_file + ".TXT"
            layout_path = os.path.join(base_path, 'layouts', layout_filename)
            if os.path.exists(layout_path):
                layouts[layout_filename] = parse_copybook(layout_path, use_camel_case)
            else:
                logger.warning(f"Layout file missing: {layout_path}")

    parsed_records = parse_feed_file(feed_file_path, layouts, is_single_layout, record_layout_mapping, use_camel_case)

    try:
        with open(output_json_path, "w", encoding="utf-8") as json_file:
            json.dump(parsed_records, json_file, indent=4)
        print(f"JSON output saved to {output_json_path}")
    except Exception as e:
        logger.error(f"Failed to write to {output_json_path}: {e}")