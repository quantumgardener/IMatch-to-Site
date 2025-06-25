import logging
import multiprocessing
import os
import re
import pprint
from collections import defaultdict

def scan_file(file_path, pattern):
    regex = re.compile(pattern)
    match_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                match = regex.search(line)
                if match:
                    matched_text = match.group()
                    if matched_text not in match_dict:
                        match_dict[matched_text[:6]] = []
                    match_dict[matched_text[:6]].append((file_path, line_num))
                    logging.debug(f"Matched '{matched_text}' in {file_path} on line {line_num}")
    except Exception as e:
        logging.error(f"Error reading {file_path}: {e}")
    return match_dict


def scan_folder_with_subfolders(folder_path, pattern, folders_to_ignore):
    file_paths = []
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d.lower() not in folders_to_ignore]
        for file_name in files:
            file_paths.append(os.path.join(root, file_name))

    # Use multiprocessing
    with multiprocessing.Pool() as pool:
        results = pool.starmap(scan_file, [(file_path, pattern) for file_path in file_paths])

    # Merge the dictionaries
    combined_matches = defaultdict(list)
    for result in results:
        for match_text, occurrences in result.items():
            combined_matches[match_text].extend(occurrences)

    return combined_matches

