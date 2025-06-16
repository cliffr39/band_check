import re

def parse_phone_bands(text):
    """
    Parses the input text to extract 4G/LTE and 5G band numbers.
    This version is more robust in handling various formats of band listings
    by using section-aware parsing and stricter regex for LTE bands.
    """
    lte_bands = set()
    nr_bands = set() # 5G New Radio bands

    lines = text.split('\n')
    current_section = None # Can be '5G', '4G', or None

    for line in lines:
        line_stripped_lower = line.strip().lower()

        # Check for section headers to determine context
        if '5g' in line_stripped_lower and '4g' not in line_stripped_lower:
            current_section = '5G'
            continue # Move to next line after identifying section
        elif '4g' in line_stripped_lower and '5g' not in line_stripped_lower:
            current_section = '4G'
            continue # Move to next line after identifying section

        # Process bands based on the current section
        if current_section == '5G':
            # Extract numbers prefixed with 'n' for 5G bands.
            # This regex is applied to the full text, as n-bands are uniquely 5G.
            nr_matches = re.findall(r'n(\d+)', line, re.IGNORECASE)
            for band_str in nr_matches:
                try:
                    nr_bands.add(int(band_str))
                except ValueError:
                    pass
        elif current_section == '4G':
            # Extract LTE bands, strictly requiring a 'B' prefix.
            # This prevents general numbers (like "6 of 14") from being misidentified as bands.
            # It also handles bands followed by frequency info in parentheses, e.g., "B2 (1900)".
            lte_matches = re.findall(r'[Bb](\d+)(?:\s*\([^)]*\))?', line, re.IGNORECASE)
            for band_str_tuple in lte_matches:
                # The regex returns a tuple if there are capturing groups,
                # but with [Bb](\d+), it's just the digit group.
                # So we take the first element (the number).
                try:
                    lte_bands.add(int(band_str_tuple))
                except ValueError:
                    pass
    
    return sorted(list(lte_bands)), sorted(list(nr_bands))


def compare_phone_to_carrier(phone_lte_bands, phone_nr_bands, carrier_data):
    """
    Compares the phone's bands against a specific carrier's bands.
    """
    results = {}

    for carrier_name, bands_info in carrier_data.items():
        carrier_lte = set(bands_info['4G/LTE'])
        carrier_nr = set(bands_info['5G'])
        carrier_core_lte = set(bands_info['Core LTE'])

        # Supported bands
        supported_lte = phone_lte_bands.intersection(carrier_lte)
        supported_nr = phone_nr_bands.intersection(carrier_nr)

        # Missing bands
        missing_lte = carrier_lte - phone_lte_bands
        missing_nr = carrier_nr - phone_nr_bands

        # Missing core bands
        missing_core_lte = carrier_core_lte.intersection(missing_lte)

        results[carrier_name] = {
            'supported_lte': sorted(list(supported_lte)),
            'supported_nr': sorted(list(supported_nr)),
            'missing_lte': sorted(list(missing_lte)),
            'missing_nr': sorted(list(missing_nr)),
            'missing_core_lte': sorted(list(missing_core_lte))
        }
    return results

def main():
    """
    Main function to run the band compatibility check.
    """
    # ANSI escape codes for colors and formatting
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BOLD = '\033[1m'
    RESET = '\033[0m' # Reset to default color and style

    print("Welcome to the Cell Phone Band Compatibility Checker!")
    print("Paste the text containing the cell phone's band information below.")
    print("Press Enter twice to finish input.")

    input_lines = []
    while True:
        try:
            line = input()
            if not line: # Empty line signals end of input
                break
            input_lines.append(line)
        except EOFError: # Handles potential EOF if input is piped
            break
    
    phone_info_text = "\n".join(input_lines)

    # Pre-set US carrier band data
    us_carriers = {
        'Verizon': {
            '4G/LTE': {2, 4, 5, 13, 41, 46, 48, 66, 71},
            'Core LTE': {2, 4, 13, 66},
            '5G': {2, 5, 66, 77, 260, 261}
        },
        'AT&T': {
            '4G/LTE': {2, 4, 5, 12, 14, 17, 29, 30, 66, 71},
            'Core LTE': {2, 4, 12, 17, 29},
            '5G': {2, 5, 66, 77, 260}
        },
        'T-Mobile': {
            '4G/LTE': {2, 4, 5, 12, 25, 41, 66, 71},
            'Core LTE': {2, 4, 12, 71},
            '5G': {2, 25, 38, 41, 71, 258, 260, 261}
        }
    }

    # Parse phone bands from the input text
    print("\n--- Parsing Phone Bands ---")
    phone_lte_bands_list, phone_nr_bands_list = parse_phone_bands(phone_info_text)
    phone_lte_bands = set(phone_lte_bands_list)
    phone_nr_bands = set(phone_nr_bands_list)

    print(f"Detected Phone LTE Bands: {phone_lte_bands_list if phone_lte_bands_list else 'None'}")
    print(f"Detected Phone 5G Bands: {phone_nr_bands_list if phone_nr_bands_list else 'None'}")

    if not phone_lte_bands and not phone_nr_bands:
        print("\nNo LTE or 5G bands could be extracted from the provided text.")
        print("Please ensure the text contains band numbers in formats like 'B1', 'Band 2', 'LTE 66', or 'n41'.")
        return

    # Compare phone bands with carrier bands
    print("\n--- Carrier Compatibility Report ---")
    comparison_results = compare_phone_to_carrier(phone_lte_bands, phone_nr_bands, us_carriers)

    for carrier, data in comparison_results.items():
        print(f"\n----- {carrier} -----")
        print(f"  Supported LTE Bands: {GREEN}{data['supported_lte'] if data['supported_lte'] else 'None'}{RESET}")
        
        # Color code missing LTE bands
        if data['missing_lte']:
            print(f"  Missing LTE Bands:   {YELLOW}{data['missing_lte']}{RESET}")
        else:
            print(f"  Missing LTE Bands:   None (All supported!)")

        # Color code critical missing core LTE bands
        if data['missing_core_lte']:
            print(f"  !!! {BOLD}{RED}CRITICAL: Missing Core LTE Bands: {data['missing_core_lte']}{RESET} !!!")
        else:
            print(f"  All Core LTE Bands are Supported.")

        print(f"  Supported 5G Bands:  {GREEN}{data['supported_nr'] if data['supported_nr'] else 'None'}{RESET}")
        
        # Color code missing 5G bands
        if data['missing_nr']:
            print(f"  Missing 5G Bands:    {YELLOW}{data['missing_nr']}{RESET}")
        else:
            print(f"  Missing 5G Bands:    None (All supported!)")
        
        print("-" * (len(carrier) + 12)) # Separator

    print("\nAnalysis complete. Thank you for using the tool!")

if __name__ == "__main__":
    main()
