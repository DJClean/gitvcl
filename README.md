# GitVCL

This is a python based to used together with the Varnish Enterprise Controller to backup all deployed VCL files. These files are saved in a GIT repository to build up a history in case an older file needs to be retrieved or a mistake needs to be corrected.

## Features

- Backup Varnish configuration files

## Installation

To install the necessary dependencies, run:
```sh
pip install -r requirements.txt
```

## Requirements

- Python 3.10

## How to Run

To run the script manually, use:
```sh
python main.py --config settings.yaml
```

To set up a cron job that runs the script every 30 minutes, add the following line to your crontab:
```sh
*/30 * * * * /usr/bin/python3 /path/to/your/project/main.py --config /path/to/your/project/settings.yaml
```
