import os
import json
import re
import logging

# Define base paths for various files
base_path = r"D:\development\Deepak Support New"
config_folder_path = os.path.join(base_path, "configs")
feed_folder_path = os.path.join(base_path, "feeds")
layout_folder_path = os.path.join(base_path, "layouts")
log_folder_path = os.path.join(base_path, "logs")
output_folder_path = os.path.join(base_path, "outputs")



# Clear the log file before starting the script
with open(os.path.join(log_folder_path, "logs.txt"), 'w'):
    pass  # This will truncate the file


# Set up logging configuration to write logs to a file
logging.basicConfig(filename=os.path.join(log_folder_path, "logs.txt"), level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

config_path = os.path.join(config_folder_path, "basic.json")  # Path to the configuration file

# Helper function to convert COBOL-style names to camelCase
def to_camel_case(cobol_name):
    return cobol_name

def find_field_in_structure(field_name, structure):
    for field in structure:
        if field['name'] == field_name:
            return field
        if field.get('subfields'):
            subfield = find_field_in_structure(field_name, field['subfields'])
            if subfield:
                return subfield
    return None

def parse_copybook(copybook_path):
    # Define regex patterns for parsing the copybook
    level_field_pattern = re.compile(r'^\s*(\d+)\s+([\w-]+)', re.IGNORECASE)  # Matches level and field name
    pic_pattern = re.compile(r'PIC\s*([+-S])?([X9S]+)(?:\((\d+)\))?(?:([V.])(9+)?(?:\((\d+)\))?)?', re.IGNORECASE)  # Matches PIC clauses
    occurs_pattern = re.compile(r'OCCURS\s+(\d+)\s+TIMES', re.IGNORECASE)  # Matches OCCURS clauses
    redefines_pattern = re.compile(r'(\d{2})\s+([A-Z0-9-]+)\s+REDEFINES', re.IGNORECASE)  # Matches REDEFINES clauses
    redefines_pattern_with_definition = re.compile(r'(\d{2})\s+([A-Z0-9-]+)\s+REDEFINES\s+(\d{2})\s+([A-Z0-9-]+)', re.IGNORECASE)  # Matches REDEFINES clauses with definition
    # Read the copybook file
    with open(copybook_path, 'r') as file:
        lines = file.readlines()  # Read all lines into a list

    hierarchy = {}  # Dictionary to hold the hierarchy of fields
    field_info_list = []  # List to hold information about fields
    level_stack = []  # Stack to manage field levels
    top_level_name = None  # Variable to store the top-level field name
    pending_field = None  # Variable to hold a field being processed
    last_field_info = None  # Variable to hold the last processed field info

    # Iterate through each line in the copybook
    for line_idx, line in enumerate(lines):
        line = line.strip()  # Remove leading and trailing whitespace        

        # Match the line against the level field pattern
        level_match = level_field_pattern.search(line)
        if not level_match:
            # If no level match is found, check for pending fields and OCCURS
            if pending_field and occurs_pattern.search(line):
                occurs_match = occurs_pattern.search(line)  # Match OCCURS clause
                pending_field['occurs'] = int(occurs_match.group(1))  # Set the number of occurrences
                pending_field['is_group'] = False  # Mark as not a group field
                field_info_list.append(pending_field)  # Add the pending field to the list
                process_field(pending_field, hierarchy, level_stack, top_level_name, copybook_path, line_idx)  # Process the field
                pending_field = None  # Reset pending field
            # Check if the last field was a REDEFINES
            elif last_field_info and last_field_info['is_redefines']:
                # if line is not empty, add the current line's field name to the last field's definition fields
                if line:
                    last_field_info['definition_field'] = line.split('.')[0]
                continue  # Skip parsing this line
            continue  # Skip to the next line

        # Extract level and field name from the match
        level, field_name = level_match.groups()
        level = int(level)  # Convert level to integer

        # Handle FILLER fields by renaming them
        if field_name.startswith("FILLER"):
            field_name = f"FILLER_{len(field_info_list) + 1}"

        # Match the line against various patterns to extract field information
        pic_match = pic_pattern.search(line)
        occurs_match = occurs_pattern.search(line)
        redefines_match = redefines_pattern.match(line)


        # If there is a pending field, add it to the list and process it
        if pending_field:
            field_info_list.append(pending_field)
            if top_level_name or pending_field['level'] == 1:
                process_field(pending_field, hierarchy, level_stack, top_level_name, copybook_path, line_idx - 1)
            pending_field = None  # Reset pending field

        # Create a dictionary to hold field information
        field_info = {
            'name': field_name,
            'level': level,
            'pic_clause': pic_match.group(0) if pic_match else None,  # Get PIC clause if available
            'occurs': int(occurs_match.group(1)) if occurs_match else None,  # Get number of occurrences if available
            'is_group': pic_match is None and (occurs_match is not None or redefines_match is not None),  # Determine if it's a group field
            'is_redefines': redefines_match is not None,  # Check if it's a REDEFINES field
            'definition_field': None  # Initialize definition fields list
        }
        
        if redefines_match:
            logger.debug(f"\n")
            logger.debug(f"\n")
            logger.debug(f"\n")
            logger.debug(f"redefines field: {field_name}")
            logger.debug(f"line: {line}")
            logger.debug(f"redefines_match: {redefines_match}")
            redefines_match_with_definition = redefines_pattern_with_definition.search(line)
            if redefines_match_with_definition:
                field_info['definition_field'] = redefines_match_with_definition.group(3)
                logger.debug(f"definition_field: {field_info['definition_field']}")

        # Handle top-level fields
        if level == 1:
            top_level_name = field_name  # Set the top-level name
            hierarchy[to_camel_case(field_name)] = {}  # Initialize hierarchy for the top-level field
            level_stack = [{'level': level, 'node': hierarchy[to_camel_case(field_name)], 'occurs': False}]  # Update level stack
            field_info_list.append(field_info)  # Add field info to the list
        elif pic_match and not occurs_match:
            pending_field = field_info  # Set the current field as pending
        else:
            field_info_list.append(field_info)  # Add field info to the list
            if top_level_name:
                process_field(field_info, hierarchy, level_stack, top_level_name, copybook_path, line_idx)  # Process the field

        last_field_info = field_info  # Update last field info to the current field

    # Process any remaining pending fields
    if pending_field:
        field_info_list.append(pending_field)
        if top_level_name:
            process_field(pending_field, hierarchy, level_stack, top_level_name, copybook_path, len(lines) - 1)

    # Raise an error if no top-level field is found
    if top_level_name is None:
        raise ValueError(f"No 01 level found in copybook {copybook_path}")


    structure = []  # List to hold the final structure of fields
    position = 1  # Variable to track the current position in the structure
    skip_subfields = set()  # Set to track fields that should be skipped

    # Iterate through the field information list to build the structure
    for field_info in field_info_list:
        field_name = field_info['name']
        level = field_info['level']
        pic_clause = field_info['pic_clause']
        occurs_times = field_info['occurs']
        is_group = field_info['is_group']
        is_redefines = field_info['is_redefines']
        definition_field = field_info['definition_field']
        
        if level == 1:
            continue  # Skip top-level fields

        field_length = 0  # Initialize field length
        field_type = 'string'  # Default field type
        decimal_places = 0  # Initialize decimal places

        # Process the PIC clause to determine field characteristics
        if pic_clause:
            pic_match = pic_pattern.search(pic_clause)  # Match the PIC clause
            sign, format_part, pic_length, decimal_marker, decimal_part, decimal_count = pic_match.groups() + (None,) * (6 - len(pic_match.groups()))
            has_explicit_sign = sign in ['+', '-']  # Check for explicit sign
            sign_length = 1 if has_explicit_sign else 0  # Determine sign length
            has_explicit_decimal = decimal_marker in ['V', '.']  # Check for explicit decimal
            decimal_length = 1 if has_explicit_decimal else 0  # Determine decimal length

            # Determine decimal places based on the PIC clause
            if decimal_count:
                decimal_places = int(decimal_count)
            elif decimal_part and has_explicit_decimal:
                decimal_places = len(decimal_part)
            else:
                decimal_places = 0

            # Determine field length and type based on the format part
            if 'X' in format_part:
                field_length = int(pic_length) if pic_length else len(format_part)  # Set length for X-type fields
                field_type = 'string'  # Set type to string
            elif '9' in format_part:
                if pic_length:
                    field_length = int(pic_length) + sign_length  # Set length for 9-type fields
                    if has_explicit_decimal and decimal_places > 0:
                        field_length += decimal_length + decimal_places  # Adjust for decimal places
                else:
                    pic_content = pic_clause.split('PIC ')[1].strip()  # Extract content from PIC clause
                    if has_explicit_sign:
                        pic_content = pic_content[1:]  # Remove sign if present
                    field_length = pic_content.count('9') + sign_length  # Count 9s for length
                field_type = 'number'  # Set type to number
            else:
                field_length = len(format_part)  # Set length for other types
                field_type = 'string'  # Default to string type

        # Handle fields that occur multiple times
        if occurs_times:
            if is_group:
                group_info = {
                    'name': field_name,
                    'type': 'group',
                    'length': 0,
                    'start': position,
                    'end': position - 1,
                    'decimal_places': 0,
                    'occurs': occurs_times,
                    'subfields': [],
                    'is_group': True,
                    'level': level
                }
                subfield_position = 0  # Initialize position for subfields
                current_idx = field_info_list.index(field_info)  # Get the index of the current field
                for sub_field in field_info_list[current_idx + 1:]:
                    if sub_field['level'] <= level:
                        break  # Stop if we reach a field of the same or higher level
                    sub_length = 0  # Initialize subfield length
                    sub_type = 'string'  # Default subfield type
                    sub_decimal_places = 0  # Initialize subfield decimal places
                    if sub_field['pic_clause']:
                        sub_pic_match = pic_pattern.search(sub_field['pic_clause'])  # Match subfield PIC clause
                        sub_sign, sub_format, sub_length_str, sub_dec_marker, sub_dec_part, sub_dec_count = sub_pic_match.groups() + (None,) * (6 - len(sub_pic_match.groups()))
                        has_sub_sign = sub_sign in ['+', '-']  # Check for explicit sign
                        sub_sign_length = 1 if has_sub_sign else 0  # Determine subfield sign length
                        has_sub_decimal = sub_dec_marker in ['V', '.']  # Check for explicit decimal
                        sub_decimal_length = 1 if has_sub_decimal else 0  # Determine subfield decimal length

                        # Determine subfield decimal places
                        if sub_dec_count:
                            sub_decimal_places = int(sub_dec_count)
                        elif sub_dec_part and has_sub_decimal:
                            sub_decimal_places = len(sub_dec_part)
                        else:
                            sub_decimal_places = 0

                        # Determine subfield length and type based on the format part
                        if 'X' in sub_format:
                            sub_length = int(sub_length_str) if sub_length_str else len(sub_format)  # Set length for X-type subfields
                            sub_type = 'string'  # Set type to string
                        elif '9' in sub_format:
                            if sub_length_str:
                                sub_length = int(sub_length_str) + sub_sign_length  # Set length for 9-type subfields
                                if has_sub_decimal and sub_decimal_places > 0:
                                    sub_length += sub_decimal_length + sub_decimal_places  # Adjust for decimal places
                            else:
                                sub_pic_content = sub_field['pic_clause'].split('PIC ')[1].strip()  # Extract content from PIC clause
                                if has_sub_sign:
                                    sub_pic_content = sub_pic_content[1:]  # Remove sign if present
                                sub_length = sub_pic_content.count('9') + sub_sign_length  # Count 9s for length
                            sub_type = 'number'  # Set type to number
                        else:
                            sub_length = int(sub_length_str) if sub_length_str else len(sub_format)  # Set length for other types

                    # Create a dictionary for the subfield
                    subfield_info = {
                        'name': sub_field['name'],
                        'type': sub_type,
                        'length': sub_length,
                        'decimal_places': sub_decimal_places,
                        'relative_start': subfield_position,
                        'relative_end': subfield_position + sub_length - 1,
                        'level': sub_field['level']
                    }
                    group_info['subfields'].append(subfield_info)  # Add subfield info to group
                    skip_subfields.add(sub_field['name'])  # Mark subfield to be skipped
                    subfield_position += sub_length  # Update subfield position

                total_length = subfield_position * occurs_times  # Calculate total length for the group
                group_info['length'] = total_length  # Set group length
                group_info['end'] = position + total_length - 1  # Set end position for the group
                structure.append(group_info)  # Add group info to the structure
                position += total_length  # Update current position
            else:
                total_length = field_length * occurs_times  # Calculate total length for non-group fields
                structure.append({
                    'name': field_name,
                    'type': field_type,
                    'length': field_length,
                    'start': position,
                    'end': position + total_length - 1,
                    'decimal_places': decimal_places,
                    'occurs': occurs_times,
                    'is_group': False,
                    'level': level
                })
                position += total_length  # Update current position
        
        elif is_redefines:
            logger.debug(f"redefines field part 2: {field_name}")
            logger.debug(f"definition_field: {definition_field}")
            logger.debug(f"structure: {structure}")
            # find the definition field in the structure
            # find the field in the structure with the same name as the definition field
            # structure might have nested fields, so we need to find the definition field in the nested fields
            definition_field_info = find_field_in_structure(definition_field, structure)
            logger.debug(f"definition_field_info: {definition_field_info}")
            
            # get the start and end of the definition field if it exists else relative start and relative end
            if definition_field_info.get('start',False):
                definition_field_start = definition_field_info['start']
            else:
                definition_field_start = definition_field_info['relative_start']

            if definition_field_info.get('end',False):
                definition_field_end = definition_field_info['end']
            else:
                definition_field_end = definition_field_info['relative_end']
                
            group_info = {
                'name': field_name,
                'type': 'group',
                'length': definition_field_end - definition_field_start + 1,
                'start': definition_field_start,
                'end': definition_field_end,
                'decimal_places': 0,
                'occurs': 1,
                'level': level,
                'is_group': True,
                'is_redefines': True,
                'subfields': []
            }
            
            # add subfields to the group
            subfield_position = group_info['start']  # Initialize position for subfields
            current_idx = field_info_list.index(field_info)  # Get the index of the current field
            for sub_field in field_info_list[current_idx + 1:]:
                if sub_field['level'] <= level:
                    break  # Stop if we reach a field of the same or higher level
                sub_length = 0  # Initialize subfield length
                sub_type = 'string'  # Default subfield type
                sub_decimal_places = 0  # Initialize subfield decimal places
                if sub_field['pic_clause']:
                    sub_pic_match = pic_pattern.search(sub_field['pic_clause'])  # Match subfield PIC clause
                    sub_sign, sub_format, sub_length_str, sub_dec_marker, sub_dec_part, sub_dec_count = sub_pic_match.groups() + (None,) * (6 - len(sub_pic_match.groups()))
                    has_sub_sign = sub_sign in ['+', '-']  # Check for explicit sign
                    sub_sign_length = 1 if has_sub_sign else 0  # Determine subfield sign length
                    has_sub_decimal = sub_dec_marker in ['V', '.']  # Check for explicit decimal
                    sub_decimal_length = 1 if has_sub_decimal else 0  # Determine subfield decimal length

                    # Determine subfield decimal places
                    if sub_dec_count:
                        sub_decimal_places = int(sub_dec_count)
                    elif sub_dec_part and has_sub_decimal:
                        sub_decimal_places = len(sub_dec_part)
                    else:
                        sub_decimal_places = 0

                    # Determine subfield length and type based on the format part
                    if 'X' in sub_format:
                        sub_length = int(sub_length_str) if sub_length_str else len(sub_format)  # Set length for X-type subfields
                        sub_type = 'string'  # Set type to string
                    elif '9' in sub_format:
                        if sub_length_str:
                            sub_length = int(sub_length_str) + sub_sign_length  # Set length for 9-type subfields
                            if has_sub_decimal and sub_decimal_places > 0:
                                sub_length += sub_decimal_length + sub_decimal_places  # Adjust for decimal places
                        else:
                            sub_pic_content = sub_field['pic_clause'].split('PIC ')[1].strip()  # Extract content from PIC clause
                            if has_sub_sign:
                                sub_pic_content = sub_pic_content[1:]  # Remove sign if present
                            sub_length = sub_pic_content.count('9') + sub_sign_length  # Count 9s for length
                        sub_type = 'number'  # Set type to number
                    else:
                        sub_length = int(sub_length_str) if sub_length_str else len(sub_format)  # Set length for other types

                # Create a dictionary for the subfield
                subfield_info = {
                    'name': sub_field['name'],
                    'type': sub_type,
                    'length': sub_length,
                    'decimal_places': sub_decimal_places,
                    'relative_start': subfield_position,
                    'relative_end': subfield_position + sub_length - 1,
                    'level': sub_field['level']
                }
                group_info['subfields'].append(subfield_info)  # Add subfield info to group
                skip_subfields.add(sub_field['name'])  # Mark subfield to be skipped
                subfield_position += sub_length  # Update subfield position

            # add the group to the structure
            structure.append(group_info)
            # logger.debug(f"Group: {group_info}")
            
        # add the field to the structure
        elif field_name not in skip_subfields:
            total_length = field_length  # Set total length for single occurrence fields
            structure.append({
                'name': field_name,
                'type': field_type,
                'length': field_length,
                'start': position,
                'end': position + total_length - 1,
                'decimal_places': decimal_places,
                'occurs': None,
                'is_group': False,
                'level': level
            })
            position += total_length if field_length > 0 else 0  # Update position if length is greater than 0

    # log the structure
    # logger.debug(f"Structure: {structure}")
    return structure, hierarchy  # Return the final structure and hierarchy

def process_field(field_info, hierarchy, level_stack, top_level_name, copybook_path, line_idx):
    level = field_info['level']  # Get the level of the field
    field_name = to_camel_case(field_info['name'])  # Convert field name to camelCase
    occurs_match = field_info['occurs'] is not None  # Check if the field has occurrences

    if level == 1:
        top_level_name = field_info['name']  # Set the top-level name
        hierarchy[field_name] = {}  # Initialize hierarchy for the field
        level_stack = [{'level': level, 'node': hierarchy[field_name], 'occurs': False}]  # Update level stack
        return  # Exit the function for top-level fields

    # Manage the level stack for nested fields
    while level_stack and level_stack[-1]['level'] >= level:
        level_stack.pop()  # Pop from stack until we find the correct parent level
    current_parent = level_stack[-1]['node'] if level_stack else hierarchy[to_camel_case(top_level_name)]  # Get the current parent node
    is_parent_OCCURS = level_stack[-1]['occurs'] if level_stack else False  # Check if the parent is an OCCURS field

    # Handle occurrences for the current field
    if occurs_match:
        if field_info['is_group']:
            current_parent[field_name] = [{}]  # Initialize a new group in the parent
            level_stack.append({'level': level, 'node': current_parent[field_name][0], 'occurs': True})  # Update level stack for the group
        else:
            current_parent[field_name] = []  # Initialize a list for occurrences
    elif field_info['pic_clause']:
        if is_parent_OCCURS:
            current_parent[field_name] = None  # Set to None if the parent is an OCCURS field
        else:
            current_parent[field_name] = None  # Set to None for non-occurring fields
    else:
        current_parent[field_name] = {}  # Initialize a new dictionary for the field
        level_stack.append({'level': level, 'node': current_parent[field_name], 'occurs': False})  # Update level stack

def parse_feed_line(line, layout_structure, line_idx, hierarchy):
    record = {}  # Initialize a dictionary to hold the parsed record
    
    # Iterate through the layout structure to parse the line
    for field in layout_structure:
        if field.get('is_group', False) and not field.get('is_redefines', False):
            # logger.debug(f"field: {field}")
            occurs_count = field['occurs']  # Get the number of occurrences for group fields
            subfields = field['subfields']  # Get the subfields for the group
            group_start = field['start'] - 1  # Calculate the start position for the group
            occurs_values = []  # List to hold values for occurrences
            occurrence_length = sum(subfield['length'] for subfield in subfields)  # Calculate total length for occurrences
            
            # Iterate through each occurrence of the group
            for occurrence in range(occurs_count):
                occurrence_data = {}  # Initialize a dictionary for the occurrence
                occurrence_start = group_start + (occurrence * occurrence_length)  # Calculate start position for the occurrence
                occurrence_end = occurrence_start + occurrence_length  # Calculate end position for the occurrence
                for subfield in subfields:
                    subfield_name = subfield['name']  # Get the name of the subfield
                    subfield_length = subfield['length']  # Get the length of the subfield
                    subfield_start = occurrence_start + subfield['relative_start']  # Calculate start position for the subfield
                    subfield_end = subfield_start + subfield_length  # Calculate end position for the subfield
                    subfield_type = subfield['type']  # Get the type of the subfield

                    # logger.debug(f"subfield_start: {subfield_start}, subfield_end: {subfield_end}, subfield_type: {subfield_type}")
                    # logger.debug(f"subfield_start >= len(line): {subfield_start >= len(line)}")
                    # Handle cases where the subfield exceeds the line length
                    if subfield_start >= len(line):
                        value = ""  # Set value to empty if start exceeds line length
                    elif subfield_end > len(line):
                        value = line[subfield_start:].strip() or ""  # Truncate value if end exceeds line length
                    else:
                        value = line[subfield_start:subfield_end].rstrip()  # Get the value from the line

                    # Handle field type conversion
                    if subfield_type == 'number' and value.strip() and value.strip()[0].isdigit():
                        try:
                            occurrence_data[to_camel_case(subfield_name)] = int(value.strip())  # Convert to integer if valid
                        except ValueError:
                            occurrence_data[to_camel_case(subfield_name)] = value  # Fallback to string if conversion fails
                    else:
                        occurrence_data[to_camel_case(subfield_name)] = value  # Store the value as is
                occurs_values.append(occurrence_data)  # Add occurrence data to the list
            record[to_camel_case(field["name"])] = occurs_values  # Store occurrences in the record
            # logger.debug(f"occurs_values: {occurs_values}")
        elif field.get('is_group', False) and field.get('is_redefines', False):
            # logger.debug(f"redefines field: {field}")
            field_name = field['name']
            group_values = []
            subfields = field['subfields']  # Get the subfields for the group
            for subfield in subfields:
                subfield_name = subfield['name']  # Get the name of the subfield
                subfield_length = subfield['length']  # Get the length of the subfield
                subfield_start = subfield['relative_start'] - 1  # Calculate start position for the subfield
                subfield_end = subfield_start + subfield_length  # Calculate end position for the subfield
                subfield_type = subfield['type']  # Get the type of the subfield

                if subfield_start >= len(line):
                    value = ""  # Set value to empty if start exceeds line length
                elif subfield_end > len(line):
                    value = line[subfield_start:].strip() or ""  # Truncate value if end exceeds line length
                else:
                    value = line[subfield_start:subfield_end].rstrip()  # Get the value from the line

                # logger.debug(f"value: {value}")
                # Handle field type conversion
                if subfield_type == 'number' and value.strip() and value.strip()[0].isdigit():
                    try:
                        group_values.append({to_camel_case(subfield_name): int(value.strip())})  # Convert to integer if valid
                        record[to_camel_case(subfield_name)] = int(value.strip())
                    except ValueError:
                        group_values.append({to_camel_case(subfield_name): value})  # Fallback to string if conversion fails
                        record[to_camel_case(subfield_name)] = value
                else:
                    group_values.append({to_camel_case(subfield_name): value})  # Store the value as is
                    record[to_camel_case(subfield_name)] = value
            record[to_camel_case(field_name)] = group_values  # Store occurrences in the record
            # logger.debug(f"record: {record}")
        elif field.get('occurs'):
            occurs_count = field['occurs']  # Get the number of occurrences
            field_length = field['length']  # Get the length of the field
            start = field['start'] - 1  # Calculate start position
            values = []  # List to hold values for occurrences
            field_type = field['type']  # Get the type of the field

            # Iterate through each occurrence of the field
            for i in range(occurs_count):
                field_start = start + (i * field_length)  # Calculate start position for the occurrence
                field_end = field_start + field_length  # Calculate end position for the occurrence
                if field_start >= len(line):
                    value = ""  # Set value to empty if start exceeds line length
                elif field_end > len(line):
                    value = line[field_start:].strip() or ""  # Truncate value if end exceeds line length
                else:
                    value = line[field_start:field_end].rstrip()  # Get the value from the line
                
                # Handle field type conversion
                if field_type == 'number' and value.strip() and value.strip()[0].isdigit():
                    try:
                        values.append(int(value.strip()))  # Convert to integer if valid
                    except ValueError:
                        values.append(value)  # Fallback to string if conversion fails
                else:
                    values.append(value)  # Store the value as is
            record[to_camel_case(field["name"])] = values  # Store occurrences in the record
        else:
            start = field["start"] - 1  # Calculate start position
            length = field["length"]  # Get the length of the field
            end = start + length  # Calculate end position
            field_type = field['type']  # Get the type of the field

            # Handle cases where the field exceeds the line length
            if start >= len(line):
                value = ""  # Set value to empty if start exceeds line length
            elif end > len(line):
                value = line[start:].strip() or ""  # Truncate value if end exceeds line length
            else:
                value = line[start:end].rstrip()  # Get the value from the line
            
            # Handle field type conversion
            if field_type == 'number' and value.strip() and value.strip()[0].isdigit():
                try:
                    record[to_camel_case(field["name"])] = int(value.strip())  # Convert to integer if valid
                except ValueError:
                    record[to_camel_case(field["name"])] = value  # Fallback to string if conversion fails
            else:
                record[to_camel_case(field["name"])] = value  # Store the value as is

    # Function to build a nested structure from flat data
    def build_nested_structure(hierarchy, flat_data):
        nested = {}  # Initialize a nested dictionary
        for key, value in hierarchy.items():
            if isinstance(value, dict):
                nested[key] = build_nested_structure(value, flat_data)  # Recursively build nested structure for dictionaries
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                occurs_data = flat_data.get(key, [{} for _ in range(len(value))])  # Get data for occurrences
                nested[key] = [dict(build_nested_structure(value[0], item)) for item in occurs_data]  # Build nested structure for lists
            elif isinstance(value, list):
                nested[key] = flat_data.get(key, [])  # Get flat data for lists
            else:
                nested[key] = flat_data.get(key, "")  # Get flat data for other types
        return nested  # Return the nested structure

    nested_record = build_nested_structure(hierarchy, record)  # Build the nested record structure
    return nested_record  # Return the nested record

def parse_feed_file(feed_file_path, layouts, record_layout_mapping):
    records = []  # List to hold all parsed records
    current_policy = None  # Variable to hold the current policy number
    current_records = []  # List to hold records for the current policy
    possible_record_types = list(record_layout_mapping.keys())  # List of possible record types based on layout mapping
    
    # Read the feed file line by line
    with open(feed_file_path, 'r') as file:
        lines = file.readlines()  # Read all lines into a list

    # Iterate through each line in the feed file
    for line_idx, line in enumerate(lines):
        line = line.rstrip()  # Remove trailing whitespace
        record_type = None  # Initialize record type as None
        for possible_type in possible_record_types:
            if possible_type in line:
                record_type = possible_type  # Set record type if found in the line
                break  # Exit the loop once a match is found
        
        # Check for new policy lines
        if line.startswith("NCO"):
            if current_policy:
                records.append({"policy_number": current_policy, "records": current_records})  # Append current records to the list
            current_policy = line.strip()  # Set the current policy number
            current_records = []  # Reset current records for the new policy
        
        # If a record type is found, parse the line
        if record_type:
            layout_file = record_layout_mapping[record_type] + ".TXT"  # Get the layout file for the record type
            layout_path = os.path.join(layout_folder_path, layout_file)  # Construct the full path to the layout file
            if not os.path.exists(layout_path):
                continue  # Skip if the layout file does not exist
            layout_structure, hierarchy = layouts.get(layout_file, ([], {}))  # Get the layout structure and hierarchy
            if not layout_structure:
                continue  # Skip if no layout structure is found
            record = parse_feed_line(line, layout_structure, line_idx, hierarchy)  # Parse the line into a record
            current_records.append(record)  # Add the parsed record to the current records

    # Append any remaining records for the last policy
    if current_policy and current_records:
        records.append({"policy_number": current_policy, "records": current_records})

    return records  # Return the list of all parsed records

def parse_single_layout_feed_file(feed_file_path, layout_structure, hierarchy):
    records = []  # List to hold all parsed records
    
    # Read the feed file line by line
    with open(feed_file_path, 'r') as file:
        lines = file.readlines()  # Read all lines into a list
    
    for line_idx, line in enumerate(lines):
        line = line.rstrip()
        record = parse_feed_line(line, layout_structure, line_idx, hierarchy)
        records.append({"record": record})

    return records


if __name__ == "__main__":

    # Check if the configuration file exists; raise an error if not
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Load the configuration from the JSON file
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    # Retrieve the record layout mapping from the configuration
    layouts = {}

    for feed_config in config.get("feed_configs", []):
        feed_file = feed_config.get("feed_file")
        output_file = feed_config.get("output_file")
        camelCase = feed_config.get("camelCase").lower() == "true"
        layout_config = feed_config.get("layout_config")

        is_single_layout = "layout_file" in layout_config

        if is_single_layout:
            layout_structure, hierarchy = [], {}
            single_layout_file = layout_config["layout_file"] + ".TXT"
            layout_path = os.path.join(layout_folder_path, single_layout_file)
            if os.path.exists(layout_path):
                layout_structure, hierarchy = parse_copybook(layout_path)
            else:
                logger.warning(f"Layout file missing: {layout_path}")
                record_layout_mapping = None

            parsed_records = parse_single_layout_feed_file(os.path.join(feed_folder_path, feed_file), layout_structure, hierarchy)

            try:
                with open(os.path.join(output_folder_path, output_file), "w", encoding="utf-8") as json_file:
                    json.dump(parsed_records, json_file, indent=4)
            except Exception as e:
                logger.error(f"Error writing to output file: {e}")
                continue
        else:
            record_layout_mapping = layout_config.get("record_layout_mapping", {})
            if not record_layout_mapping:
                logger.error(f"No record_layout_mapping in layout_config for {feed_file}")
                continue
            for record_type, layout_file in record_layout_mapping.items():
                layout_filename = layout_file + ".TXT"
                layout_path = os.path.join(layout_folder_path, layout_filename)
                if os.path.exists(layout_path):
                    layouts[layout_filename] = parse_copybook(layout_path)
                else:
                    logger.warning(f"Layout file missing: {layout_path}")

            parsed_records = parse_feed_file(os.path.join(feed_folder_path, feed_file), layouts, record_layout_mapping)

            try:
                with open(os.path.join(output_folder_path, output_file), "w", encoding="utf-8") as json_file:
                    json.dump(parsed_records, json_file, indent=4)
            except Exception as e:
                logger.error(f"Error writing to output file: {e}")
                continue

        logger.info(f"JSON output saved to {output_file}")




# if __name__ == "__main__":
#     with open(os.path.join(layout_folder_path, "ACLMAN00.txt"), "r") as f:
#         copybook_text = f.read()

#     hierarchy, flat_fields = convert_copybook_to_hierarchy(copybook_text)
#     logger.debug(json.dumps(hierarchy, indent=2))

#     # Example feed data (first line)
#     feed_path = os.path.join(feeds_folder_path, "MAN00FIL.txt")
#     if os.path.exists(feed_path):
#         with open(feed_path, "r") as feed_file:
#             feed_line = feed_file.readline()
#             parsed_feed = parse_feed_with_layout(feed_line, hierarchy)
#             logger.debug(json.dumps(parsed_feed, indent=2))
