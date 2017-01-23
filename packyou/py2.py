# -*- coding: utf-8 -*-
import imp
import logging
import ipdb

import sys
from sys import modules, meta_path
from os import mkdir
from os.path import (
    isdir,
    abspath,
    dirname,
    exists,
    join,
)

import encodings.idna
import requests

from git import Repo
from packyou import find_module_in_cloned_repos, find_module_path_in_cloned_repos
from packyou.utils import walklevel

MODULES_PATH = dirname(abspath(__file__))
LOGGER = logging.getLogger(__name__)


class GithubLoader(object):
    """
        Import hook that will allow to import from a  github repo.
    """
    def __init__(self, repo_url=None, path=None, username=None, repository_name=None):
        self.path = path
        self.repo_url = repo_url
        self.username = username
        self.repository_name = repository_name

    def check_root(self, fullname):
        """
            #Sometimes the code is a python package or similar and there is a directory
            #which contains all the code.
            This method is used to search first on the root of the cloned repository for the
            imported module.
        """
        parent, _, module_name = fullname.rpartition('.')
        if self.username and self.repository_name:
            # REVISAR QUE PASE TODOS LOS PATHS
            cloned_root = join(self.path[0], 'github', self.username, self.repository_name)
            candidate_path = join(cloned_root, module_name)
            if exists(candidate_path):
                return candidate_path

            for root, dirs, files in walklevel(cloned_root, level=1):
                pass

    def get_source(self, fullname):
        filename = self.get_filename(fullname)
        with open(filename, 'r') as source_file:
            return source_file.read()

    def get_code(self, fullname):
        source = self.get_source(fullname)
        return compile(source, self.get_filename(fullname), 'exec', dont_inherit=True)

    def get_filename(self, fullname):
        fullname_parts = fullname.split('.')[1:]
        filename = join(MODULES_PATH, '/'.join(fullname_parts))
        if isdir(filename):
            filename = join(filename, '__init__.py')
        else:
            if not filename.endswith('py'):
                module_filename = '{0}.py'.format(filename)
                if exists(module_filename):
                    filename = module_filename
                else:
                    # it could be that it was an import of a class
                    module_filename = '{0}.py'.format(fullname.rpartition('.')[0].rpartition('.')[2])
                    if exists(module_filename):
                        filename = module_filename
        LOGGER.debug('get_filename({0}) is {1}'.format(fullname, filename))
        return filename

    def is_package(self, fullname):
        filename = self.get_filename(fullname)
        return not exists(filename) or isdir(filename)

    def get_or_create_module(self, fullname):
        """
            Given a name and a path it will return a module instance
            if found.
            When the module could not be found it will raise ImportError
        """
        LOGGER.info('Loading module {0}'.format(fullname))
        parent, _, module_name = fullname.rpartition('.')
        if fullname in modules:
            LOGGER.info('Found cache entry for {0}'.format(fullname))
            return modules[fullname]

        if module_name in modules:
            return modules[module_name]

        module = modules.setdefault(fullname, imp.new_module(fullname))
        if len(fullname.strip('.')) > 3:
            absolute_from_root = fullname.split('.', 3)[-1]
            modules.setdefault(absolute_from_root, module)
        if len(fullname.split('.')) == 4:
            # add the root of the project
            modules[fullname.split('.')[-1]] = module
        # required by PEP 302
        module.__file__ = self.get_filename(fullname)
        LOGGER.info('Created module {0} with fullname {1}'.format(self.get_filename(fullname), fullname))
        module.__name__ = fullname
        module.__loader__ = self
        module.__path__ = self.path
        if self.is_package(fullname):
            module.__path__ = self.path
            module.__package__ = fullname
        else:
            module.__package__ = fullname.rpartition('.')[0]

        LOGGER.debug('loading file {0}'.format(self.get_filename(fullname)))
        source = self.get_source(fullname)
        try:
            exec(source, module.__dict__)
        except Exception as ex:
            ipdb.set_trace()
        return module

    def clone_github_repo(self):
        """
            Clones a github repo with a username and repository_name
        """
        if not (self.username and self.repository_name):
            return
        repository_local_destination = join(MODULES_PATH, 'github', self.username, self.repository_name)
        if not exists(repository_local_destination):
            Repo.clone_from(self.repo_url, repository_local_destination, branch='master')
            init_filename = join(repository_local_destination, '__init__.py')
            open(init_filename, 'a').close()

    @property
    def project_fullname(self):
        return 'packyou.github.{0}.{1}'.format(self.username, self.repository_name)

    def absolute_import(self, fullname):
        _, _, module_name = fullname.rpartition('.')
        if not(self.username and self.repository_name):
            return
        if fullname == self.project_fullname:
            return
        for path in self.path:
            absolute_path = join(path, module_name)
            if exists(absolute_path) or exists(join(absolute_path, '__init__.py')):
                fullname = '{0}.{1}'.format(self.project_fullname, module_name)
                LOGGER.info('Finder found absolute import {0}'.format(fullname))
                return self.get_or_create_module(fullname)

            absolute_path = path
            if exists(absolute_path) or exists(join(absolute_path, '__init__.py')):
                fullname = '{0}'.format(self.project_fullname)
                LOGGER.info('Finder found absolute import {0}'.format(fullname))
                return self.get_or_create_module(fullname)

    def load_module(self, fullname):
        """
            Given a name it will load the module from github.
            When the project is not locally stored it will clone the
            repo from github.
        """
        module = None
        splitted_names = fullname.split('.')
        module_name = splitted_names[-1]
#        if not(self.username and self.repository_name):
#            sys.path.append('/home/leonardo/visible/packyou/packyou/github/sqlmapproject/sqlmap')
        if 'github' in splitted_names:
            #module = self.absolute_import(fullname)
            #if module:
            #    modules[fullname] = module
            #    return module
            self.clone_github_repo()
            if len(splitted_names) == 2:
                module = self.get_or_create_module(fullname)
            if len(splitted_names) == 3:
                username_directory = join(MODULES_PATH, 'github', self.username)
                if not exists(username_directory):
                    mkdir(username_directory)
                username_init_filename = join(MODULES_PATH, 'github', self.username, '__init__.py')
                open(username_init_filename, 'a').close()
                module = self.get_or_create_module(fullname)
            if len(splitted_names) >= 4:
                module = self.get_or_create_module(fullname)
        modules[fullname] = module
        return module


class GithubFinder(object):

    def check_repository_available(self, username, repository_name):
        """
            Sometimes github has a - in the username or repository name.
            The - can't be used in the import statement.
        """
        repo_url = 'https://github.com/{0}/{1}.git'.format(username, repository_name)
        response = requests.get(repo_url)
        if response.status_code == 404:
            if '_' in username:
                repo_url = 'https://github.com/{0}/{1}.git'.format(username.replace('_', '-'), repository_name)
                response = requests.get(repo_url)
                if response.status_code == 200:
                    return repo_url
            if '_' in repository_name:
                repo_url = 'https://github.com/{0}/{1}.git'.format(username, repository_name.replace('_', '-'))
                response = requests.get(repo_url)
                if response.status_code == 200:
                    return repo_url

            repo_url = 'https://github.com/{0}/{1}.git'.format(username.replace('_', '-'), repository_name.replace('_', '-'))
            response = requests.get(repo_url)
            if response.status_code == 200:
                return repo_url
            raise ImportError('Github repository not found.')

        return repo_url

    def find_module_in_cloned_repos(self, fullname):
        return find_module_in_cloned_repos(fullname, GithubLoader)

    def find_module(self, fullname, path=None):
        """
            Finds a module and returns a module loader when
            the import uses packyou
        """
        current_path = dirname(abspath(__file__))
        path = [current_path]
        LOGGER.info('Finding {0}'.format(fullname))
        partent, _, module_name = fullname.rpartition('.')
        try:
            # sometimes the project imported from github does an
            # "import x" (absolute import), this translates to import github...x
            # we try first to do an import x and cache the module in the sys.path.
            # and return None if the imp.find_module was successful.
            # This will allow python finders in the meta_path to do the import, and not packyou
            # loaders.
            imp.find_module(module_name)
            LOGGER.debug('Absolute import: {0}. Original fullname {1}'.format(module_name, fullname))
            return None
        except ImportError as ex:
            LOGGER.debug('imp.find_module could not find {0}. this is ussually fine.'.format(module_name))

        if 'packyou.github' in fullname:
            fullname_parts = fullname.split('.')
            repo_url = None
            username = None
            repository_name = None
            if len(fullname_parts) >= 3:
                username = fullname.split('.')[2]
            if len(fullname_parts) >= 4:
                repository_name = fullname.split('.')[3]
                repo_url = self.check_repository_available(username, repository_name)
                current_path = dirname(abspath(__file__))

                repo_path = join(current_path, 'github', username, repository_name)
                if repo_path not in path:
                    path.insert(0, repo_path)
            path = find_module_path_in_cloned_repos(fullname)
            LOGGER.debug('Found {0} with path {1}'.format(fullname, path))
            return GithubLoader(repo_url, path, username, repository_name)
        else:
            loader = self.find_module_in_cloned_repos(fullname)
            LOGGER.debug('Fullname {0} does not start with packyou, searching in cloned repos. Result was {1}'.format(fullname, loader))
            return loader


meta_path.append(GithubFinder())
