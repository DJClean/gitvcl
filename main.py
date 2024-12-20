#!/usr/bin/env python3.10
import requests
import os
import sys
from requests.auth import HTTPBasicAuth
from base64 import b64decode
import hashlib
import git
import datetime
import yaml
import logging
import argparse

def load_settings(config_path):
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

def initialize_git_repo(save_folder, remote_repo_url=None, push_to_repo=False, ssh_push_key=None):
    if not os.path.isdir(os.path.join(save_folder, '.git')):
        repo = git.Repo.init(save_folder)
        repo.git.checkout('-b', 'main') 

        initial_file = os.path.join(save_folder, '.gitkeep')
        with open(initial_file, 'w') as f:
            f.write('')

        repo.index.add([initial_file])
        repo.index.commit('Initial commit')

        if push_to_repo and remote_repo_url:
            origin = repo.create_remote('origin', remote_repo_url)
            with repo.git.custom_environment(GIT_SSH_COMMAND=f'ssh -i {ssh_push_key}'):
                repo.git.fetch('origin')
            repo.create_head('main').set_tracking_branch(origin.refs.main)
    else:
        repo = git.Repo(save_folder)
        if push_to_repo:
            origin = repo.remotes.origin if 'origin' in repo.remotes else repo.create_remote('origin', remote_repo_url)
            if origin.url != remote_repo_url:
                origin.set_url(remote_repo_url)
            with repo.git.custom_environment(GIT_SSH_COMMAND=f'ssh -i {ssh_push_key}'):
                repo.git.fetch('origin')
            repo.heads.main.set_tracking_branch(origin.refs.main)
    return repo

def process_file(file, save_folder):
    logger.debug('Processing file ID: %s, File Name: %s, File SHA: %s', file['id'], file['name'], file['sha'])
    file_source = file['draft'] if file['source'] == "" else file['source']
    file_path = os.path.join(save_folder, file['name'])
    
    if os.path.isfile(file_path):
        original_hash = hashlib.sha256()
        original_hash.update(open(file_path, "rb").read())
        if original_hash.hexdigest() != file['sha']:
            write_file(file['name'], b64decode(file_source).decode('utf-8'), save_folder)
            return True
    else:
        write_file(file['name'], b64decode(file_source).decode('utf-8'), save_folder)
        return True
    return False

def write_file(filename, source, save_folder):
    logger.info('Writing file: %s', filename)
    with open(os.path.join(save_folder, filename), "w") as vcl_file:
        vcl_file.write(source)

def main():
    parser = argparse.ArgumentParser(description='GitVCL - Varnish Controller VCL Backup Tool')
    parser.add_argument('--config', type=str, default='settings.yaml', help='Path to the configuration file')
    args = parser.parse_args()
    
    settings = load_settings(args.config)
    global logger
    logging.basicConfig(level=getattr(logging, settings['logging']['level'].upper()), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename=settings['logging']['file'])
    logger = logging.getLogger(__name__)

    # Vars
    api_url = settings['api_url']
    controller_username = settings['controller']['username']
    controller_password = settings['controller']['password']
    controller_org = settings['controller']['organization']
    save_folder = settings['git']['repo_folder']
    push_to_repo = settings['git']['push_to_repo']
    ssh_push_key = settings['git']['ssh_key']
    remote_repo_url = settings['git']['repository']
    git_author_name = settings['git']['author']
    git_author_email = settings['git']['email']

    base_url = api_url + '/api/v1'
    org_data = '{\"Org\": \"' + controller_org + '\"}'
    basic_auth = HTTPBasicAuth(controller_username, controller_password)

    repo = initialize_git_repo(save_folder, remote_repo_url, push_to_repo, ssh_push_key)
    
    with repo.config_writer() as git_config:
        git_config.set_value('user', 'name', git_author_name)
        git_config.set_value('user', 'email', git_author_email)

    if not os.path.isdir(save_folder):
        logger.info('Folder (%s) does not exist, creating', save_folder)
        try:
            os.makedirs(save_folder)
            git.Repo.init(save_folder)
        except FileExistsError as err:
            logger.error('File already exists: %s', err)

    try:
        login = requests.post(base_url + "/auth/login", data=org_data, auth=basic_auth)
        login.raise_for_status()
        
        commit_required = False
        api_token = login.json()['accessToken']
        files_header = { "Authorization": "Bearer " + api_token} 
        
        files = requests.get(base_url + '/files', headers=files_header)
        files.raise_for_status()
        
        file_ids = []
        files_to_backup = []
        files_on_disk = next(os.walk(save_folder), (None, None, []))[2]
        
        for file in files.json():
            if file['deployed']:
                file_ids.append(file['id'])
                files_to_backup.append(file['name'])
                
        for vclfile_id in file_ids:
            vclfile_request = requests.get(base_url + '/files/' + str(vclfile_id), headers=files_header)
            vclfile_request.raise_for_status()
            if process_file(vclfile_request.json(), save_folder):
                commit_required = True
        
        # Cleanup here
        for file in files_on_disk:
            if file not in files_to_backup:
                os.remove(os.path.join(save_folder, file))
                repo.index.remove([file])
                commit_required = True
        
        if commit_required or repo.is_dirty(untracked_files=True):
            logger.info("Changes detected ready to commit.")
            repo.git.add(A=True)
            commit_message = datetime.datetime.now().strftime('Updated configs at %Y-%m-%d %H:%M')
            repo.index.commit(commit_message)
            logger.info("Changes committed to repository.")
            if push_to_repo:
                logger.info("Pushing changes to remote repository.")
                ssh_cmd = f'ssh -i {ssh_push_key}'
                with repo.git.custom_environment(GIT_SSH_COMMAND=ssh_cmd):
                    repo.remotes.origin.push()
                logger.info("Changes pushed to remote repository.")
        else:
            logger.info("No changes detected.")
            
    except requests.exceptions.HTTPError as errh:
        logger.error("HTTP error: %s", errh)
    except requests.exceptions.ConnectionError as errc:
        logger.error("Connection error: %s", errc)
    except requests.exceptions.Timeout as errt:
        logger.error("Timeout error: %s", errt)
    except requests.exceptions.RequestException as err:
        logger.error("General error: %s", err)

if __name__ == "__main__":
    main()
