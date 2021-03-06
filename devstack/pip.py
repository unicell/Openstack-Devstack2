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


from devstack import exceptions as excp
from devstack import log as logging
from devstack import shell as sh

LOG = logging.getLogger("devstack.pip")
PIP_UNINSTALL_CMD_OPTS = ['-y', '-q']
PIP_INSTALL_CMD_OPTS = ['-q']


def _make_pip_name(name, version):
    if version is None:
        return str(name)
    return "%s==%s" % (name, version)


def install(pip, distro):
    name = pip['name']
    root_cmd = distro.get_command('pip')
    LOG.audit("Installing python package (%s) using pip command (%s)" % (name, root_cmd))
    name_full = _make_pip_name(name, pip.get('version'))
    real_cmd = [root_cmd, 'install'] + PIP_INSTALL_CMD_OPTS
    options = pip.get('options')
    if options:
        LOG.debug("Using pip options: %s" % (options))
        real_cmd += [str(options)]
    real_cmd += [name_full]
    sh.execute(*real_cmd, run_as_root=True)


def uninstall(pip, distro, skip_errors=True):
    root_cmd = distro.get_command('pip')
    try:
        # Versions don't seem to matter here...
        name = _make_pip_name(pip['name'], None)
        LOG.audit("Uninstalling python package (%s) using pip command (%s)" % (name, root_cmd))
        cmd = [root_cmd, 'uninstall'] + PIP_UNINSTALL_CMD_OPTS + [name]
        sh.execute(*cmd, run_as_root=True)
    except excp.ProcessExecutionError:
        if skip_errors:
            LOG.debug(("Ignoring execution error that occured when uninstalling pip %s!"
                " (this may be ok if it was uninstalled by a previous component)") % (name))
        else:
            raise
