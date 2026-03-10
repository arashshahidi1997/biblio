The script extract_doi.py is a command-line tool that attempts to automatically find DOIs for article titles in a CSV file using the CrossRef API. Below is a description of the available options and an example command for how to run the script.

🔧 Command-line Options

Option	Description
title_file	The path to the CSV file containing article titles (required).
-m, --match_threshold	Minimum Levenshtein similarity score to auto-accept a DOI match (default: 0.9).
-a, --ask_threshold	Minimum similarity to prompt user for confirmation (default: 0.8).
-c, --colors	Enable or disable ANSI color highlighting in the terminal (True/False, default: True).
--start	Start processing from a specific line number (default: 0).
--end	Stop processing at a specific line number (default: no limit).
The script expects a column in the CSV file named "Title" or "Article Title" (case-insensitive) to extract article titles for querying.

💡 Example Usage
To run the script on a file named titles.csv, allowing auto-matches above 90% similarity and prompting for matches between 80–90%:

bash
Copy
Edit
python extract_doi.py titles.csv -m 0.9 -a 0.8 -c True --start 1 --end 100
This command:

Starts from line 1 and ends at line 100,

Uses color output,

Accepts matches with ≥0.9 similarity automatically,

Prompts the user for manual confirmation if similarity is between 0.8 and 0.9.
