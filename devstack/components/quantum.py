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

import io

from devstack import cfg
from devstack import component as comp
from devstack import log as logging
from devstack import shell as sh
from devstack import utils

from devstack.components import db

LOG = logging.getLogger("devstack.components.quantum")

# Openvswitch special settings
VSWITCH_PLUGIN = 'openvswitch'
V_PROVIDER = "quantum.plugins.openvswitch.ovs_quantum_plugin.OVSQuantumPlugin"

# Config files (some only modified if running as openvswitch)
PLUGIN_CONF = "plugins.ini"
QUANTUM_CONF = 'quantum.conf'
PLUGIN_LOC = ['etc']
AGENT_CONF = 'ovs_quantum_plugin.ini'
AGENT_LOC = ["etc", "quantum", "plugins", "openvswitch"]
AGENT_BIN_LOC = ["quantum", "plugins", "openvswitch", 'agent']
CONFIG_FILES = [PLUGIN_CONF, AGENT_CONF]

# This db will be dropped and created
DB_NAME = 'ovs_quantum'

# Opensvswitch bridge setup/teardown/name commands
OVS_BRIDGE_DEL = ['ovs-vsctl', '--no-wait', '--', '--if-exists', 'del-br', '%OVS_BRIDGE%']
OVS_BRIDGE_ADD = ['ovs-vsctl', '--no-wait', 'add-br', '%OVS_BRIDGE%']
OVS_BRIDGE_EXTERN_ID = ['ovs-vsctl', '--no-wait', 'br-set-external-id', '%OVS_BRIDGE%', 'bridge-id', '%OVS_EXTERNAL_ID%']
OVS_BRIDGE_CMDS = [OVS_BRIDGE_DEL, OVS_BRIDGE_ADD, OVS_BRIDGE_EXTERN_ID]

# Subdirs of the downloaded
CONFIG_DIR = 'etc'
BIN_DIR = 'bin'

# What to start (only if openvswitch enabled)
APP_Q_SERVER = 'quantum-server'
APP_Q_AGENT = 'ovs_quantum_agent.py'
APP_OPTIONS = {
    APP_Q_SERVER: ["%QUANTUM_CONFIG_FILE%"],
    APP_Q_AGENT: ["%OVS_CONFIG_FILE%", "-v"],
}


class QuantumUninstaller(comp.PkgUninstallComponent):
    def __init__(self, *args, **kargs):
        comp.PkgUninstallComponent.__init__(self, *args, **kargs)


class QuantumInstaller(comp.PkgInstallComponent):
    def __init__(self, *args, **kargs):
        comp.PkgInstallComponent.__init__(self, *args, **kargs)
        self.q_vswitch_agent = False
        self.q_vswitch_service = False
        plugin = self.cfg.getdefaulted("quantum", "q_plugin", VSWITCH_PLUGIN)
        if plugin == VSWITCH_PLUGIN:
            self.q_vswitch_agent = True
            self.q_vswitch_service = True

    def _get_download_locations(self):
        places = list()
        places.append({
            'uri': ("git", "quantum_repo"),
            'branch': ("git", "quantum_branch"),
        })
        return places

    def known_options(self):
        return set(['no-ovs-db-init', 'no-ovs-bridge-init'])

    def _get_config_files(self):
        return list(CONFIG_FILES)

    def _get_target_config_name(self, config_fn):
        if config_fn == PLUGIN_CONF:
            tgt_loc = [self.app_dir] + PLUGIN_LOC + [config_fn]
            return sh.joinpths(*tgt_loc)
        elif config_fn == AGENT_CONF:
            tgt_loc = [self.app_dir] + AGENT_LOC + [config_fn]
            return sh.joinpths(*tgt_loc)
        else:
            return comp.PkgInstallComponent._get_target_config_name(self, config_fn)

    def _config_adjust(self, contents, config_fn):
        if config_fn == PLUGIN_CONF and self.q_vswitch_service:
            # Need to fix the "Quantum plugin provider module"
            newcontents = contents
            with io.BytesIO(contents) as stream:
                config = cfg.IgnoreMissingConfigParser()
                config.readfp(stream)
                provider = config.get("PLUGIN", "provider")
                if provider != V_PROVIDER:
                    config.set("PLUGIN", "provider", V_PROVIDER)
                    with io.BytesIO() as outputstream:
                        config.write(outputstream)
                        outputstream.flush()
                        newcontents = cfg.add_header(config_fn, outputstream.getvalue())
            return newcontents
        elif config_fn == AGENT_CONF and self.q_vswitch_agent:
            # Need to adjust the sql connection
            newcontents = contents
            with io.BytesIO(contents) as stream:
                config = cfg.IgnoreMissingConfigParser()
                config.readfp(stream)
                db_dsn = config.get("DATABASE", "sql_connection")
                if db_dsn:
                    generated_dsn = db.fetch_dbdsn(self.cfg, self.pw_gen, DB_NAME)
                    if generated_dsn != db_dsn:
                        config.set("DATABASE", "sql_connection", generated_dsn)
                        with io.BytesIO() as outputstream:
                            config.write(outputstream)
                            outputstream.flush()
                            newcontents = cfg.add_header(config_fn, outputstream.getvalue())
            return newcontents
        else:
            return comp.PkgInstallComponent._config_adjust(self, contents, config_fn)

    def _setup_bridge(self):
        if not self.q_vswitch_agent or \
                'no-ovs-bridge-init' in self.options:
            return
        bridge = self.cfg.getdefaulted("quantum", "ovs_bridge", 'br-int')
        LOG.info("Fixing up ovs bridge named %s.", bridge)
        external_id = self.cfg.getdefaulted("quantum", 'ovs_bridge_external_name', bridge)
        params = dict()
        params['OVS_BRIDGE'] = bridge
        params['OVS_EXTERNAL_ID'] = external_id
        cmds = list()
        for cmd_templ in OVS_BRIDGE_CMDS:
            cmds.append({
                'cmd': cmd_templ,
                'run_as_root': True,
            })
        utils.execute_template(*cmds, params=params)

    def post_install(self):
        comp.PkgInstallComponent.post_install(self)
        self._setup_db()
        self._setup_bridge()

    def _setup_db(self):
        if not self.q_vswitch_service or \
                'no-ovs-db-init' in self.options:
            return
        LOG.info("Fixing up database named %s.", DB_NAME)
        db.drop_db(self.cfg, self.pw_gen, self.distro, DB_NAME)
        db.create_db(self.cfg, self.pw_gen, self.distro, DB_NAME)

    def _get_source_config(self, config_fn):
        if config_fn == PLUGIN_CONF:
            srcloc = [self.app_dir] + PLUGIN_LOC + [config_fn]
            srcfn = sh.joinpths(*srcloc)
            contents = sh.load_file(srcfn)
            return (srcfn, contents)
        elif config_fn == AGENT_CONF:
            srcloc = [self.app_dir] + AGENT_LOC + [config_fn]
            srcfn = sh.joinpths(*srcloc)
            contents = sh.load_file(srcfn)
            return (srcfn, contents)
        else:
            return comp.PkgInstallComponent._get_source_config(self, config_fn)


class QuantumRuntime(comp.ProgramRuntime):
    def __init__(self, *args, **kargs):
        comp.ProgramRuntime.__init__(self, *args, **kargs)
        self.q_vswitch_agent = False
        self.q_vswitch_service = False
        plugin = self.cfg.getdefaulted("quantum", "q_plugin", VSWITCH_PLUGIN)
        if plugin == VSWITCH_PLUGIN:
            # Default to on if not specified
            self.q_vswitch_agent = True
            self.q_vswitch_service = True

    def _get_apps_to_start(self):
        app_list = comp.ProgramRuntime._get_apps_to_start(self)
        if self.q_vswitch_service:
            app_list.append({
                    'name': APP_Q_SERVER,
                    'path': sh.joinpths(self.app_dir, BIN_DIR, APP_Q_SERVER),
            })
        if self.q_vswitch_agent:
            full_pth = [self.app_dir] + AGENT_BIN_LOC + [APP_Q_AGENT]
            app_list.append({
                    'name': APP_Q_AGENT,
                    'path': sh.joinpths(*full_pth)
            })
        return app_list

    def _get_app_options(self, app_name):
        return APP_OPTIONS.get(app_name)

    def _get_param_map(self, app_name):
        param_dict = comp.ProgramRuntime._get_param_map(self, app_name)
        if app_name == APP_Q_AGENT:
            tgt_loc = [self.app_dir] + AGENT_LOC + [AGENT_CONF]
            param_dict['OVS_CONFIG_FILE'] = sh.joinpths(*tgt_loc)
        elif app_name == APP_Q_SERVER:
            param_dict['QUANTUM_CONFIG_FILE'] = sh.joinpths(self.app_dir, CONFIG_DIR, QUANTUM_CONF)
        return param_dict
