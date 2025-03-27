import re
from pprint import pprint
import os
import logging
import json

# Log setup
log_folder_path = os.path.join("D:\\development\\Deepak Support New", "logs")
os.makedirs(log_folder_path, exist_ok=True)
with open(os.path.join(log_folder_path, "logs.txt"), 'w'): pass
logging.basicConfig(filename=os.path.join(log_folder_path, "logs.txt"), level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger(__name__)

# Main line parser
line_pattern = re.compile(
    r'(?P<level>\d{2})\s+'
    r'(?P<name>[A-Z0-9-]+)'
    r'(?:\s+REDEFINES\s+(?P<redefines>[A-Z0-9-]+))?'
    r'(?:\s+OCCURS\s+(?P<occurs>\d+)\s+TIMES)?'
    r'(?:\s+PIC\s+(?P<pic>[^\s.]+(?:\([^)]+\))?(?:\.[^\s.]+(?:\([^)]+\))?)?))?'
    r'\.?'
)

# Advanced PIC parser
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

    # Determine decimal places
    if decimal_count:
        decimal_places = int(decimal_count)
    elif decimal_part and has_explicit_decimal:
        decimal_places = len(decimal_part)
    else:
        decimal_places = 0

    # Determine total field length (excluding sign and decimal marker)
    if pic_length:
        int_length = int(pic_length)
    else:
        int_length = format_part.count('9') + (decimal_part.count('9') if decimal_part else 0)

    field_length = int_length  # No sign or marker counted

    # Determine type
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
    """Merge continuation lines, skip comments, and handle OCCURS on next line."""
    processed = []
    current_line = ""

    for line in lines:
        stripped = line.strip()

        # Skip empty or comment lines
        if not stripped or stripped.startswith('*') or re.match(r'^\*{3,}$', stripped):
            continue

        if re.match(r"^\d{2}\s", stripped):  # New COBOL level (e.g. 01, 05, 10)
            if current_line:
                processed.append(current_line)
            current_line = stripped
        else:
            # Continuation or OCCURS line — merge it in
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
            'is_group': 'pic' not in item  # <-- Add is_group flag
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

# Example COBOL Copybook
copybook_text = """
      * ------------------------------------------------------------ *          
      *         <<<<<    AO010  >>>>>>                                          
      * COPYBOOK NAME: AO010CVN                                                 
      * ------------------------------------------------------------ *          
      * THIS AOS COPYBOOK IS OUTPUT SPECIFIC.                                   
      * ------------------------------------------------------------ *          
      *            INITIALS OF   DATE                                           
      * IDENTIFIER PROGRAMMER   CHANGED    DESCRIPTION OF CHANGES               
      * ------------------------------------------------------------ *          
      *            TCS         2025/03/04  INITIAL CREATION                     
      * ------------------------------------------------------------ *          
       01 AO010-OUTPUT-AREA.                                                    
      *****************************************************************         
      * START OF OCWFEED LAYOUT                                       *         
      *****************************************************************         
      *                                                                         
       02  W-CTRL-WORD.                                                         
           05  W-FILLER                                PIC X(04).               
           05  W-CW-EXPANSION-POS                      PIC X(01).               
           05  W-CW-IA.                                                         
               10  W-CW-ADMIN-UNIT-IA                  PIC X(01).               
               10  W-CW-CODE-IA.                                                
                   15  W-CW-TYPE-IA                    PIC X(01).               
                   15  W-CW-KIND-IA.                                            
                       20  W-CW-KIND-IA-1ST-DIGIT      PIC 9(01).               
                       20  W-CW-KIND-IA-2ND-3RD-DIGITS PIC 9(02).               
               10  W-CW-DATA-IA.                                                
                   15  W-CW-ASSEMBLY-AREA-IA           PIC X(02).               
                   15  W-CW-DESTINATION-IA-1-2         PIC X(02).               
                   15  W-CW-DESTINATION-IA-3-4         PIC X(02).               
                   15  W-CW-SEQUENCE-AREA-IA.                                   
                       20  W-CW-1ST-SEQUENCE-IA        PIC X(08).               
                       20  W-CW-2ND-SEQUENCE-IA        PIC X(09).               
                       20  W-POLICY-NUMBER             REDEFINES                
                           W-CW-2ND-SEQUENCE-IA.                                
                           25  W-DO-POL-TYPE           PIC X(01).               
                           25  W-POL-TYPE              PIC X(01).               
                           25  W-POL-FILLER            PIC 9(07).               
           05  W-CW-SEQ-CTRL-IA                        PIC X(01).               
         02  OCW-TRAILER.                                                       
             05  SB-AU-AND-CODE.                                                
                 10  SB-AU                             PIC X(02).               
                 10  SB-CODE                           PIC X(02).               
             05  AA-ACCESS-AREA.                                                
                 10  AA-CENTRALIZED-OFF-FLAG           PIC X(01).               
                 10  AA-OFFICE.                                                 
                     15  INFORCE-OFFICE                PIC X(04).               
                     15  DETACHED-OFFICE               PIC X(01).               
             05  FOT-TRLR.                                                      
                 10  W-FORMAT-ID                       PIC X(01).               
                 10  REQ-RHO                           PIC X(01).               
                 10  F                                 PIC X(01).               
                 10  REQ-OFFICE.                                                
                     15  REQ-OFF                       PIC X(04).               
                     15  F                             PIC X(01).               
                     15  DETACH-OFF                    PIC X(01).               
                 10  RESP-BU-CODE                      PIC X(02).               
                 10  F                                 PIC X(03).               
                 10  PROC-RHO                          PIC X(01).               
             05  AGENTS-NUMBER.                                                 
                 10  AGENT-TYPE                        PIC X(01).               
                 10  AGENTS-NUM                        PIC X(05).               
             05  POL-ID-ITEM-NUM.                                               
                 10  POL-ID-FILLER                     PIC +9(05).              
             05  DEBIT-MAIL-PAY-SIG                    PIC X(01).               
             05  SIGNED-SOURCE-DOC                     PIC X(01).               
             05  INPUT-ID                              PIC 9(07).               
             05  COMPANY-CODE                          PIC X(03).               
             05  LANG-CODE                             PIC X(02).               
             05  NEW-PATH-SWITCH                       PIC X(01).               
             05  TRANS-CODE                            PIC +9(03).              
             05  PRODUCT-CODE                          PIC 9(05).               
             05  PRU-SELECT-SERV-REP-CONTR-NO          PIC X(06).               
             05  W-POLICY-NUMBER.                                               
                 06  W-POLICY-NO-1                     PIC X(01).               
                 06  W-POLICY-NO-2                     PIC X(01).               
                 06  W-POLICY-FILLER                   PIC +9(07).              
             05  OP-1-AND-2-SIGNAL                     PIC X(01).               
             05  MKTG-CHANNEL-POLICY                   PIC +9(01).              
             05  PRUSEL-COPY-SIGNAL                    PIC +9(01).              
             05  AS400-IND                             PIC X(01).               
             05  TRANS-BATCH-TYPE                      PIC X(01).               
             05  BUNDLING-IND                          PIC X(03).               
             05  OFFICE-INFORCE-HOLD-FILLER            PIC X(04).               
             05  F-CO-SETTLEMENT-STATUS                PIC X.                   
             05  F-CO-ADR-CLAIM-DISP                   PIC X                    
                                                       OCCURS 3 TIMES.          
             05  F-CO-SETTLE-OVERFLOW-SIGNAL           PIC X.                   
             05  F-CO-OPL-LOAN-STATUS                  PIC X.                   
             05  F-CO-ADR-STATUS                       PIC X.                   
             05  OCW-NOTICE-HANDLING                   PIC +9(03).              
             05  OCW-FILLER                            PIC X(11).               
      *****************************************************************         
      * END  OF OCWFEED LAYOUT                                        *         
      *****************************************************************         
      *************   START OF AO010-INPUT-BLOCK      *****************         
       02  AO010I-RECORD.                                                       
           03  FILLER.                                                          
               04  W-PPA-DO                        PIC X.                       
               04  W-PPA-RO                        PIC X.                       
               04  W-PPA-POL                       PIC +9(7).                   
           03  FILLER.                                                          
               04  W-T-TRANS-YR                    PIC +9(5).                   
               04  W-T-TRANS-MO                    PIC +999.                    
               04  W-T-TRANS-DAY                   PIC +999.                    
           03  W-OFFICE                            PIC XXXX.                    
           03  W-INFORCE-DEBIT                     PIC +999.                    
           03  W-CODE                              PIC X.                       
           03  W-STAFF                             PIC X.                       
           03  W-AGENTS-INITIALS                   PIC XXX.                     
           03  W-BILLING-TYPE                      PIC +9.                      
           03  W-PROCESSING-RHO-CODE               PIC 9.                       
           03  FILLER-1                            PIC X(7).                    
           03  W-PREM-PAYER                        PIC X(28).                   
           03  W-ARCS-ADDR                         PIC X(23)                    
                                                   OCCURS 4     TIMES.          
           03  W-PPA-CPN-YR                        PIC +9(5).                   
           03  W-PPA-CPN-MO                        PIC +999.                    
           03  W-NUM-CPNS                          PIC +999.                    
           03  W-GROSS-BUCKETS                     PIC +9(5).99                 
                                                   OCCURS 12    TIMES.          
           03  W-NUM-POLS                          PIC +9.                      
           03  W-POLICY-DATA                       OCCURS 8     TIMES.          
               04  FILLER.                                                      
                   05  W-DO-POL                    PIC X.                       
                   05  W-RO-POL                    PIC X.                       
                   05  W-POLICY-NUM                PIC +9(7).                   
               04  W-NAME-OF-INSURED               PIC X(24).                   
               04  W-CAN-ADD-MODAL-AMT             PIC +9(5).99.                
               04  W-CAN-ADD-INDICATOR             PIC +9.                      
               04  W-CAN-ADD-BEN-SECTION-SIGNAL    PIC +9.                      
               04  W-POLICY-DATE.                                               
                   05  W-POLICY-YR                 PIC +9(5).                   
                   05  W-POLICY-MO                 PIC +999.                    
                   05  W-POLICY-DAY                PIC +999.                    
               04  W-D-EFF-M-R-PAID-TO-DATE.                                    
                   05  W-EFF-PTD-YR                PIC +9(5).                   
                   05  W-EFF-PTD-MO                PIC +9(3).                   
               04  FILLER                                                       
                                                   OCCURS  3     TIMES.         
                   05  W-DUR-1-2-3                 PIC +999.                    
                   05  W-PREMS-1-2-3               PIC +999.99.                 
               04  W-DO-PREM                       PIC +999.99                  
                                                   OCCURS  12    TIMES.         
               04  W-KIND                          PIC +9.                      
               04  W-M-BILLED-TO-DATE.                                          
                   05  W-M-BILLED-TO-YR            PIC +9(5).                   
                   05  W-M-BILLED-TO-MO            PIC +999.                    
               04  FILLER-2                        PIC X(14).                   
      *****************************************************************         
      * END  OF COPY BOOK AO010I                                                
      *****************************************************************         
      *****************************************************************         
      * END  OF COPY BOOK AO010CVN                                    *         
      *****************************************************************         
"""

# Convert and Log Output
hierarchy = convert_copybook_to_hierarchy(copybook_text)
logger.debug(json.dumps(hierarchy, indent=2))
