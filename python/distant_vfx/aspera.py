import json
import subprocess
import traceback
from html import unescape
from operator import itemgetter
from bs4 import BeautifulSoup
from .constants import LAST_PROCESSED_PACKAGE_JSON_FILE


class AsperaCLI:

    def __init__(self, user, password, url, url_prefix='aspera/faspex'):
        self.user = user
        self.password = password
        self.url = url
        self.url_prefix = url_prefix

    def download_package_by_name(self, package_name, output_path, content_protect_password=None, inbox_packages=None):
        if not inbox_packages:
            inbox_packages = self._fetch_inbox_packages()
        link = None
        for package in inbox_packages:
            title = package[1]
            if package_name in title:
                link = package[2]
                break
        if link:
            self._download_package(link, output_path, content_protect_password=content_protect_password)
        else:
            raise FileNotFoundError(f'No package found with name {package_name}')

    def download_new_packages(self, output_path, content_protect_password=None):
        last_processed_package_id = self._get_last_processed_package_id_from_file(LAST_PROCESSED_PACKAGE_JSON_FILE)
        inbox_packages = self._fetch_inbox_packages()
        if not inbox_packages:
            return
        if not last_processed_package_id:
            max_package_id = self._get_max_package_id_from_list(inbox_packages)
            self._write_last_processed_package_id_file(max_package_id, LAST_PROCESSED_PACKAGE_JSON_FILE)
            return

        new_packages = self._filter_new_packages(inbox_packages, last_processed_package_id)

        # sort by package id smallest -> greatest
        new_packages.sort(key=itemgetter(0))

        # download packages
        for package in new_packages:
            package_id, title, link = package
            try:
                self._download_package(
                    link=link,
                    output_path=output_path,
                    content_protect_password=content_protect_password
                )
                self._write_last_processed_package_id_file(package_id, LAST_PROCESSED_PACKAGE_JSON_FILE)
            except:
                traceback.print_exc()

    def _download_package(self, link, output_path, content_protect_password=None):
        flags = ['--file', output_path, '--url', link]
        if content_protect_password:
            flags += ['--content-protect-password', content_protect_password]
        cmd = self._construct_cmd(sub_cmd='get', flags=flags)
        return self._call_aspera_cli(cmd)

    @staticmethod
    def _filter_new_packages(inbox_packages, last_processed_package_id):
        new_packages = [package for package in inbox_packages if package[0] > last_processed_package_id]
        return new_packages

    @staticmethod
    def _get_max_package_id_from_list(inbox_packages):
        packages_ids = [package[0] for package in inbox_packages]
        max_package_id = max(packages_ids)
        return max_package_id

    @staticmethod
    def _write_last_processed_package_id_file(last_processed_package_id, json_file):
        json_dict = {
            'id': last_processed_package_id
        }
        if last_processed_package_id is None:
            raise ValueError('Last processed package id cannot be None')
        with open(json_file, 'w') as file:
            json.dump(json_dict, file)

    @staticmethod
    def _get_last_processed_package_id_from_file(json_file):
        last_processed_package_id = None
        try:
            with open(json_file, 'r') as file:
                data = json.load(file)
                last_processed_package_id = data.get('id')
        except FileNotFoundError:
            traceback.print_exc()
        finally:
            return last_processed_package_id

    def _fetch_inbox_packages(self):
        return self._fetch_packages(mailbox='inbox')

    def _fetch_packages(self, mailbox):
        if mailbox not in ['inbox', 'sent', 'archived']:
            raise ValueError('mailbox must be either inbox, sent, or archived')
        mailbox_flag = '--' + mailbox
        flags = ['--xml', mailbox_flag]
        cmd = self._construct_cmd(sub_cmd='list', flags=flags)
        response, errors = self._call_aspera_cli(cmd)
        return self._parse_xml_response(response)

    @staticmethod
    def _parse_xml_response(xml):
        packages = []
        xml = xml[xml.index('<'):]
        soup = BeautifulSoup(xml, 'xml')
        entries = soup.find_all('entry')
        for entry in entries:
            delivery_id = int(entry.findChild('package:delivery_id').get_text())
            title = entry.findChild('title').get_text()
            link = unescape(entry.findChild('link', {'rel': 'package'})['href'])
            package = (delivery_id, title, link)
            packages.append(package)
        return packages

    def _construct_cmd(self, sub_cmd, flags=None):
        cmd = ['aspera', 'faspex', sub_cmd]
        std_flags = ['--host', self.url, '--user', self.user, '--password', self.password, '-U', self.url_prefix]
        cmd += std_flags
        if flags:
            cmd += flags
        cmd = [str(i) for i in cmd]
        return cmd

    @staticmethod
    def _call_aspera_cli(cmd):
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            shell=False
        )
        try:
            stdout, stderr = process.communicate()
            return stdout, stderr
        except:
            traceback.print_exc()
