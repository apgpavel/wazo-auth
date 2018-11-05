# Copyright 2018 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0+

import logging
logger = logging.getLogger()


class Purpose:

    def __init__(self, name, metadata_plugins=[]):
        self._name = name
        self._metadata_plugins = set()
        for plugin in metadata_plugins:
            self._metadata_plugins.add(plugin)

    @property
    def name(self):
        return self._name

    @property
    def metadata_plugins(self):
        return self._metadata_plugins

    def add_metadata_plugin(self, metadata_plugin):
        self._metadata_plugins.add(metadata_plugin)

    def __eq__(self, other):
        return self._name == other._name and self._metadata_plugins == other._metadata_plugins

    def __ne__(self, other):
        return not self == other


class Purposes:

    valid_purposes = ['user', 'internal', 'external_api']

    def __init__(self, purposes_config, metadata_plugins):
        self._metadata_plugins = metadata_plugins
        self._purposes = {purpose: Purpose(purpose) for purpose in self.valid_purposes}
        self._set_default_purposes(metadata_plugins)

        for purpose_name, plugin_names in purposes_config.items():
            purpose = self._purposes.get(purpose_name)
            if not purpose:
                logger.warning('Configuration has undefined purpose: %s', purpose_name)
                continue

            for plugin_name in plugin_names:
                plugin = self._get_metadata_plugins(plugin_name)
                if not plugin:
                    continue
                purpose.add_metadata_plugin(plugin.obj)

    def _set_default_purposes(self, metadata_plugins):
        try:
            plugin = metadata_plugins['default_wazo_user']
        except KeyError:
            logger.warning("Purposes must have the following metadata plugins enabled: %s",
                           'default_wazo_user')
            return
        self._purposes['user'].add_metadata_plugin(plugin.obj)

    def _get_metadata_plugins(self, name):
        try:
            return self._metadata_plugins[name]
        except KeyError:
            logger.warning("A purpose has been assigned to an invalid metadata plugin: %s", name)

    def get(self, name):
        return self._purposes.get(name)
