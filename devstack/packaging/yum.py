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

from devstack import log as logging
from devstack import packager as pack
from devstack import shell as sh

LOG = logging.getLogger("devstack.packaging.yum")

# Root yum command
YUM_CMD = ['yum']

# Tolerant is enabled since we might already have it installed/erased
YUM_INSTALL = ["install", "-y", "-t"]
YUM_REMOVE = ['erase', '-y', "-t"]

# Yum separates its pkg names and versions with a dash
VERSION_TEMPL = "%s-%s"


class YumPackager(pack.Packager):
    def __init__(self, distro, keep_packages):
        pack.Packager.__init__(self, distro, keep_packages)

    def _format_pkg_name(self, name, version):
        if version:
            return VERSION_TEMPL % (name, version)
        else:
            return name

    def _execute_yum(self, cmd, **kargs):
        full_cmd = YUM_CMD + cmd
        return sh.execute(*full_cmd, run_as_root=True,
            check_exit_code=True,
            **kargs)

    def _remove_special(self, name, info):
        return False

    def _install_special(self, name, info):
        return False

    def install(self, pkg):
        name = pkg['name']
        if self._install_special(name, pkg):
            return
        else:
            pkg_full = self._format_pkg_name(name, pkg.get("version"))
            cmd = YUM_INSTALL + [pkg_full]
            self._execute_yum(cmd)

    def _remove(self, pkg):
        removable = pkg.get('removable', True)
        if not removable:
            return False
        name = pkg['name']
        if self._remove_special(name, pkg):
            return True
        else:
            pkg_full = self._format_pkg_name(name, pkg.get("version"))
            cmd = YUM_REMOVE + [pkg_full]
            self._execute_yum(cmd)
            return True
