# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright (C) 2012 Yahoo! Inc. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import os.path

from devstack import component as comp
from devstack import log as logging
from devstack import settings
from devstack import shell as sh
from devstack import utils

LOG = logging.getLogger("devstack.components.swift_keystone")

# id
TYPE = settings.SWIFT_KEYSTONE

# subdirs of the git checkout
BIN_DIR = 'bin'
CONFIG_DIR = 'etc'

CONFIGS = []

# what to start
APP_OPTIONS = {
}

#the pkg json files swift_keystone requires for installation
REQ_PKGS = ['general.json', 'swift.json']


class SwiftKeystoneUninstaller(comp.PythonUninstallComponent):
    def __init__(self, *args, **kargs):
        comp.PythonUninstallComponent.__init__(self, TYPE, *args, **kargs)


class SwiftKeystoneInstaller(comp.PythonInstallComponent):
    def __init__(self, *args, **kargs):
        comp.PythonInstallComponent.__init__(self, TYPE, *args, **kargs)
        self.cfgdir = sh.joinpths(self.appdir, CONFIG_DIR)
        self.bindir = sh.joinpths(self.appdir, BIN_DIR)

    def _get_download_locations(self):
        return comp.PythonInstallComponent._get_download_locations(self) + [
            {
                'uri': ('git', 'swift_keystone_repo'),
                'branch': ('git', 'swift_keystone_branch')
            }]

    def _get_config_files(self):
        return CONFIGS

    def _get_pkgs(self):
        return REQ_PKGS

    def _post_install(self):
        pass


class SwiftKeystoneRuntime(comp.PythonRuntime):
    def __init__(self, *args, **kargs):
        comp.PythonRuntime.__init__(self, TYPE, *args, **kargs)


def describe(opts=None):
    description = """
 Module: {module_name}
  Description:
   {description}
  Component options:
   {component_opts}
"""
    params = dict()
    params['component_opts'] = "TBD"
    params['module_name'] = __name__
    params['description'] = __doc__ or "Handles actions for the swift keystone component."
    out = description.format(**params)
    return out.strip("\n")